"""Acceso a datos de inscripciones de asistentes.

Mismo criterio que `organizations/repository.py`: se filtra siempre por
`organization_id` de forma explícita. RLS es la red de seguridad, no el filtro
principal.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.events.models import Event
from app.modules.registrations.models import EventRegistration, EventRegistrationQuestion


async def get_questions(
    session: AsyncSession, organization_id: uuid.UUID, event_id: uuid.UUID
) -> list[EventRegistrationQuestion]:
    filas = await session.scalars(
        select(EventRegistrationQuestion)
        .where(
            EventRegistrationQuestion.organization_id == organization_id,
            EventRegistrationQuestion.event_id == event_id,
        )
        .order_by(EventRegistrationQuestion.sort_order)
    )
    return list(filas)


async def get_registration_by_event_and_email(
    session: AsyncSession, organization_id: uuid.UUID, event_id: uuid.UUID, email: str
) -> EventRegistration | None:
    resultado: EventRegistration | None = await session.scalar(
        select(EventRegistration).where(
            EventRegistration.organization_id == organization_id,
            EventRegistration.event_id == event_id,
            EventRegistration.email == email,
        )
    )
    return resultado


async def lock_event_for_capacity(
    session: AsyncSession, organization_id: uuid.UUID, event_id: uuid.UUID
) -> Event:
    """Bloquea la fila del evento para serializar la evaluación de aforo.

    Sin este `SELECT ... FOR UPDATE`, dos altas o verificaciones simultáneas
    contra el último hueco de aforo podrían confirmar a más personas de las
    que `capacity` permite.
    """
    evento = await session.scalar(
        select(Event)
        .where(Event.organization_id == organization_id, Event.id == event_id)
        .with_for_update()
    )
    if evento is None:
        # No debería ocurrir: la existencia del evento ya se validó antes de
        # llegar aquí. Si pasa, es un error de programación del llamador, no
        # una condición esperable del negocio.
        raise RuntimeError(f"Evento {event_id} no encontrado al bloquear su fila de aforo.")
    return evento


async def count_confirmed_registrations(
    session: AsyncSession, organization_id: uuid.UUID, event_id: uuid.UUID
) -> int:
    total = await session.scalar(
        select(func.count())
        .select_from(EventRegistration)
        .where(
            EventRegistration.organization_id == organization_id,
            EventRegistration.event_id == event_id,
            EventRegistration.status == "confirmed",
        )
    )
    return int(total or 0)


async def find_user_id_by_email(session: AsyncSession, email: str) -> uuid.UUID | None:
    """Resuelve el `user_id` de una cuenta existente por email, si la hay.

    Usa `app_find_user_by_email` (`SECURITY DEFINER`, `0004_correo_y_verificacion`):
    la persona que se inscribe no comparte necesariamente organización con la
    cuenta que pueda existir con ese correo, y `users` está bajo RLS que exige
    justo eso.
    """
    fila = (
        await session.execute(
            text("SELECT id FROM app_find_user_by_email(:email)"), {"email": email}
        )
    ).first()
    return fila[0] if fila is not None else None
