"""Lo que ve la persona antes de confirmar que cancela su inscripción.

La página de cancelar ya no cancela al abrirse: primero enseña qué se va a
cancelar y si se devolvería el pago, y solo el clic de confirmación consume el
token. Esta lectura usa `peek_token`, nunca `consume_token`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import set_organization_context
from app.core.mensajes import marcar
from app.modules.auth.verification import PROPOSITO_CANCELACION_INSCRIPCION, peek_token
from app.modules.events.models import Event
from app.modules.payments import refunds_service
from app.modules.registrations import repository
from app.modules.registrations.models import EventRegistration
from app.modules.registrations.schemas import CancelPreviewResponse
from app.shared.errors import ValidationDomainError

_INVALIDO = marcar("El enlace de cancelación no es válido o ha caducado.")


async def vista_previa_de_cancelacion(
    session: AsyncSession, *, token: str
) -> CancelPreviewResponse:
    bruto = await peek_token(PROPOSITO_CANCELACION_INSCRIPCION, token)
    if bruto is None:
        raise ValidationDomainError(_INVALIDO)  # mensaje marcado
    registration_id = uuid.UUID(bruto)
    organization_id = await repository.resolve_registration_organization(session, registration_id)
    await set_organization_context(session, organization_id)

    inscripcion = await session.get(EventRegistration, registration_id)
    evento = await session.get(Event, inscripcion.event_id) if inscripcion is not None else None
    if inscripcion is None or evento is None:
        raise ValidationDomainError(_INVALIDO)  # mensaje marcado

    cancelable = inscripcion.status not in ("cancelled", "rejected")
    reembolso = (
        await refunds_service.reembolso_si_se_cancela(
            session,
            organization_id=inscripcion.organization_id,
            event_id=evento.id,
            registration_id=inscripcion.id,
        )
        if cancelable
        else None
    )
    return CancelPreviewResponse(
        status=inscripcion.status,
        event_title=evento.title,
        starts_at=evento.starts_at,
        timezone=evento.timezone,
        already_started=datetime.now(UTC) >= evento.starts_at,
        refund=reembolso,
    )
