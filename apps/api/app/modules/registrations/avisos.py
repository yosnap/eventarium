"""Correos de una inscripción según su estado y aviso a la organización."""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta
from functools import partial

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.tasks import (
    send_registration_confirmed_email,
    send_registration_pending_approval_email,
    send_registration_received_organizer_email,
    send_registration_waitlisted_email,
)
from app.core.tras_commit import encolar_tras_commit
from app.modules.auth.verification import (
    PROPOSITO_CANCELACION_INSCRIPCION,
    generate_token,
)
from app.modules.events.models import Event
from app.modules.payments import repository as payments_repository
from app.modules.registrations import repository
from app.modules.registrations.models import (
    EventRegistration,
)
from app.modules.tickets.service import emitir_entrada, generar_token_qr
from app.shared.errors import ValidationDomainError

logger = logging.getLogger(__name__)


def _ttl_cancelacion() -> timedelta:
    return timedelta(days=get_settings().registration_cancel_token_ttl_days)


async def _generar_token_cancelacion(registration_id: uuid.UUID) -> str:
    """El token se genera cada vez que se encola un email que lo ofrece, nunca
    una sola vez al confirmar — así una persona `waitlisted` también puede
    cancelar, no solo una `confirmed` (decisión #5 del PRD)."""
    return await generate_token(
        PROPOSITO_CANCELACION_INSCRIPCION, str(registration_id), ttl=_ttl_cancelacion()
    )


async def _enviar_email_por_estado(session: AsyncSession, inscripcion: EventRegistration) -> None:
    """Encola el email de confirmación o de lista de espera según el estado
    ya asignado a `inscripcion` — usado por el alta sin verificación, la
    verificación posterior, la aprobación manual y la promoción de lista de
    espera, para no repetir esta decisión en cada llamador.

    Es también el único punto por el que pasan los cuatro caminos que pueden
    dejar una inscripción en `confirmed` (fase 4 del PRD): emitir la entrada
    aquí, no en cada llamador, cubre los cuatro de una vez. `emitir_entrada` es
    idempotente, así que el reenvío del formulario con un email ya
    `confirmed` (que no es una confirmación nueva) no crea una segunda
    entrada.

    Cinturón de seguridad (capa 2 de la guarda de pago, fase 6 del PRD):
    antes de emitir, si la inscripción está `confirmed` y su
    evento es de pago, exige un `event_payments` en `paid`. La capa 1
    (`_estado_confirmable`) ya impide que los cuatro caminos conocidos
    lleguen aquí en ese estado sin haber pagado; esta capa protege el quinto
    camino que alguien escriba más adelante, en el único sitio por el que
    necesariamente tiene que pasar.
    """
    token_cancelacion = await _generar_token_cancelacion(inscripcion.id)
    organization_id = str(inscripcion.organization_id)
    if inscripcion.status == "confirmed":
        evento = await session.get(Event, inscripcion.event_id)
        if evento is not None and evento.registration_mode == "paid":
            tiene_pago = await payments_repository.tiene_pago_confirmado(
                session, inscripcion.organization_id, inscripcion.id
            )
            if not tiene_pago:
                raise ValidationDomainError(
                    "No se puede confirmar una inscripción de un evento de pago sin un "
                    "pago verificado."
                )
        ticket = await emitir_entrada(session, inscripcion)
        await send_registration_confirmed_email.kiq(
            inscripcion.email,
            organization_id,
            token_cancelacion,
            generar_token_qr(ticket),
            locale=inscripcion.locale,
        )
    elif inscripcion.status == "waitlisted":
        await send_registration_waitlisted_email.kiq(
            inscripcion.email, organization_id, token_cancelacion, locale=inscripcion.locale
        )
    elif inscripcion.status == "pending_approval":
        await send_registration_pending_approval_email.kiq(
            inscripcion.email, organization_id, locale=inscripcion.locale
        )


# Estados con los que una inscripción nueva se avisa al organizador. Los que
# faltan llegan más tarde a uno de estos: `pending_verification` al verificarse
# y `pending_payment` al pagarse (un checkout abandonado no es una inscripción).
_ESTADOS_QUE_AVISAN_AL_ORGANIZADOR = ("confirmed", "waitlisted", "pending_approval")


async def avisar_al_organizador(
    session: AsyncSession, inscripcion: EventRegistration, *, pagada: bool = False
) -> None:
    """Avisa por correo a quien gestiona las inscripciones de la organización.

    Solo desde los puntos donde nace una inscripción (alta, reactivación de una
    compra abandonada, verificación del correo) o se paga: nunca desde
    `_enviar_email_por_estado`, que también recorren aprobaciones, promociones
    y reenvíos, y avisaría dos veces de la misma persona. Se encola tras el
    commit (`core/tras_commit.py`): si la petición acaba revirtiéndose, el
    aviso no sale.
    """
    if inscripcion.status not in _ESTADOS_QUE_AVISAN_AL_ORGANIZADOR:
        return
    evento = await session.get(Event, inscripcion.event_id)
    if evento is None:
        return
    destinatarios = await repository.correos_que_gestionan_inscripciones(
        session, inscripcion.organization_id
    )
    if not destinatarios:
        logger.warning(
            "Inscripción %s sin nadie a quien avisar: ningún miembro gestiona "
            "inscripciones y la organización no tiene correo de contacto.",
            inscripcion.id,
        )
        return
    for correo, idioma in destinatarios:
        encolar_tras_commit(
            session,
            partial(
                send_registration_received_organizer_email.kiq,
                to_email=correo,
                organization_id=str(inscripcion.organization_id),
                event_id=str(evento.id),
                registration_id=str(inscripcion.id),
                event_title=evento.title,
                participant_name=inscripcion.full_name,
                participant_email=inscripcion.email,
                status=inscripcion.status,
                paid=pagada,
                locale=idioma,
            ),
        )
