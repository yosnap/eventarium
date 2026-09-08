"""Emisión, revocación y firma de entradas QR.

Fase 4 del PRD, fase 1 de trabajo. `emitir_entrada`/`revocar_entrada` se
enganchan en `registrations/service.py` (`_enviar_email_por_estado` y
`_cancelar_inscripcion`), no se exponen todavía por HTTP — eso es la fase 2.
"""

from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from io import BytesIO

import jwt
import segno
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.auth.verification import PROPOSITO_CANCELACION_INSCRIPCION, peek_token
from app.modules.events.models import Event
from app.modules.registrations.models import EventRegistration
from app.modules.tickets import repository
from app.modules.tickets.models import EventTicket
from app.shared.errors import ValidationDomainError


async def emitir_entrada(session: AsyncSession, inscripcion: EventRegistration) -> EventTicket:
    """Emite la entrada de una inscripción `confirmed`, o devuelve la ya emitida.

    Idempotente por el `UNIQUE(registration_id)` de `event_tickets`: el
    reenvío del formulario con un email ya `confirmed` (fase 3) pasa por el
    mismo punto de enganche sin ser una confirmación nueva, y no debe crear
    una segunda entrada.
    """
    existente = await repository.get_ticket_by_registration(
        session, inscripcion.organization_id, inscripcion.id
    )
    if existente is not None:
        return existente

    # `_enviar_email_por_estado` no tiene el `Event` cargado en todos sus
    # llamadores (`confirm_waitlist_promotion` no lo necesita hoy), así que es
    # más simple resolverlo aquí que cambiar la firma de sus cinco llamadores.
    evento = await session.get(Event, inscripcion.event_id)
    if evento is None:  # pragma: no cover - la FK compuesta lo hace imposible
        raise RuntimeError(f"Evento {inscripcion.event_id} no encontrado al emitir una entrada.")

    ticket = EventTicket(
        event_id=inscripcion.event_id,
        organization_id=inscripcion.organization_id,
        registration_id=inscripcion.id,
    )
    # Se asigna en memoria, no por una consulta aparte: `generar_token_qr`
    # necesita `evento.ends_at` más tarde (misma petición o tarea de email de
    # la fase 4 de trabajo) sin que su firma tenga que aceptar un `Event`.
    ticket.event = evento

    try:
        # `begin_nested` (SAVEPOINT): si la inserción choca con el `UNIQUE`,
        # solo se deshace este intento, no la transacción de la petición
        # completa (que ya puede llevar el cambio de `status` a `confirmed`
        # hecho por el llamador) ni el contexto RLS (`SET LOCAL`) que vive en
        # ella.
        async with session.begin_nested():
            session.add(ticket)
            await session.flush()
    except IntegrityError:
        # Condición de carrera: otra transición a `confirmed` de la misma
        # inscripción ganó entre la comprobación de arriba y este `flush`.
        ganadora = await repository.get_ticket_by_registration(
            session, inscripcion.organization_id, inscripcion.id
        )
        if ganadora is None:  # pragma: no cover - el UNIQUE lo hace imposible
            raise
        return ganadora
    return ticket


async def revocar_entrada(
    session: AsyncSession, *, organization_id: uuid.UUID, registration_id: uuid.UUID
) -> None:
    """Revoca la entrada de una inscripción cancelada, si existía.

    No-op si no existe: una inscripción `waitlisted`/`pending_approval`
    cancelada nunca tuvo entrada.
    """
    ticket = await repository.get_ticket_by_registration(session, organization_id, registration_id)
    if ticket is None:
        return
    ticket.revoked_at = datetime.now(UTC)


def generar_token_qr(ticket: EventTicket) -> str:
    """JWT HS256 firmado con `ticket_qr_secret` — propio y distinto del de
    autenticación (decisión #3 del plan de la fase 4): comprometer uno no
    debe permitir forjar el otro.

    El payload nunca lleva nombre, email ni ninguna otra columna de la
    inscripción — solo identificadores opacos (no-funcional del plan): un QR
    interceptado no filtra datos personales por sí solo.
    """
    settings = get_settings()
    margen = timedelta(hours=settings.ticket_qr_expiry_margin_hours)
    expira = ticket.event.ends_at.astimezone(UTC) + margen
    payload = {
        "tid": str(ticket.id),
        "eid": str(ticket.event_id),
        "exp": int(expira.timestamp()),
        # Solo higiene (dos tokens de la misma entrada nunca coinciden como
        # cadena): no es un identificador de negocio, el propio JWT ya varía
        # por `iat`.
        "jti": secrets.token_urlsafe(8),
    }
    return jwt.encode(payload, settings.ticket_qr_secret, algorithm=settings.jwt_algorithm)


def generar_imagen_qr(token: str) -> bytes:
    """PNG del código QR a partir del JWT ya firmado.

    `segno`: puro Python, sin dependencias propias (a diferencia de `qrcode`,
    que necesita Pillow para generar PNG) — la más ligera que cubre "PNG a
    partir de una cadena" (riesgo documentado en el plan de la fase 4).
    """
    buffer = BytesIO()
    segno.make(token, error="m").save(buffer, kind="png", scale=6, border=2)
    return buffer.getvalue()


@dataclass(frozen=True, slots=True)
class MiEntrada:
    """Lo que necesita `/mi-entrada` para decidir qué mostrar."""

    status: str
    full_name: str
    tiene_qr: bool


async def _resolver_mi_entrada(
    session: AsyncSession, token: str
) -> tuple[EventRegistration, EventTicket | None]:
    """Resuelve la inscripción y su entrada (si la hay) a partir del token de
    autocancelación — **sin consumirlo** (`peek_token`, no `consume_token`):
    mirar el QR no debe invalidar el enlace de cancelar del mismo correo.
    """
    bruto = await peek_token(PROPOSITO_CANCELACION_INSCRIPCION, token)
    if bruto is None:
        raise ValidationDomainError("El enlace no es válido o ha caducado.")

    inscripcion = await session.get(EventRegistration, uuid.UUID(bruto))
    if inscripcion is None:
        raise ValidationDomainError("El enlace no es válido o ha caducado.")

    ticket: EventTicket | None = None
    if inscripcion.status == "confirmed":
        candidata = await repository.get_ticket_by_registration(
            session, inscripcion.organization_id, inscripcion.id
        )
        # Una entrada revocada nunca se muestra como válida, aunque el token
        # de cancelación siga sin caducar (decisión del plan de la fase 4).
        if candidata is not None and candidata.revoked_at is None:
            ticket = candidata
    return inscripcion, ticket


async def get_my_ticket_info(session: AsyncSession, *, token: str) -> MiEntrada:
    inscripcion, ticket = await _resolver_mi_entrada(session, token)
    return MiEntrada(
        status=inscripcion.status, full_name=inscripcion.full_name, tiene_qr=ticket is not None
    )


async def get_my_ticket_qr_png(session: AsyncSession, *, token: str) -> bytes:
    _inscripcion, ticket = await _resolver_mi_entrada(session, token)
    if ticket is None:
        raise ValidationDomainError("Esta inscripción no tiene ninguna entrada disponible.")
    return generar_imagen_qr(generar_token_qr(ticket))
