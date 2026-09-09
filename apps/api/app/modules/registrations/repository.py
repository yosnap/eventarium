"""Acceso a datos de inscripciones de asistentes.

Mismo criterio que `organizations/repository.py`: se filtra siempre por
`organization_id` de forma explícita. RLS es la red de seguridad, no el filtro
principal.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Select, and_, case, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.events.models import Event
from app.modules.registrations.models import (
    EventRegistration,
    EventRegistrationAnswer,
    EventRegistrationQuestion,
)


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


async def count_reserved_registrations(
    session: AsyncSession, organization_id: uuid.UUID, event_id: uuid.UUID
) -> int:
    """`confirmed` + promociones de lista de espera todavía dentro de su
    ventana de confirmación + `pending_payment` todavía dentro de su ventana
    de pago (fase 6 del PRD, decisión #5) — las tres ocupan un hueco real de
    aforo, aunque la persona no haya confirmado ni pagado todavía. Sin esto,
    una verificación o aprobación concurrente podría colarse en un hueco ya
    reservado por quien está en mitad de confirmar su promoción, o N compras
    simultáneas podrían cobrarse todas sobre la última plaza (sobreventa de
    aforo)."""
    total = await session.scalar(
        select(func.count())
        .select_from(EventRegistration)
        .where(
            EventRegistration.organization_id == organization_id,
            EventRegistration.event_id == event_id,
            or_(
                EventRegistration.status == "confirmed",
                and_(
                    EventRegistration.status == "waitlisted",
                    EventRegistration.waitlist_promoted_at.is_not(None),
                    EventRegistration.waitlist_promotion_expires_at >= datetime.now(UTC),
                ),
                and_(
                    EventRegistration.status == "pending_payment",
                    EventRegistration.payment_expires_at >= datetime.now(UTC),
                ),
            ),
        )
    )
    return int(total or 0)


async def count_registrations(
    session: AsyncSession, organization_id: uuid.UUID, event_id: uuid.UUID, *, status: str | None
) -> int:
    """Recuento para la paginación del listado, con el mismo filtro que
    `registrations_query` pero sin materializar las filas (ni sus `answers`/
    `consent` eager-loaded) solo para contarlas."""
    consulta = (
        select(func.count())
        .select_from(EventRegistration)
        .where(
            EventRegistration.organization_id == organization_id,
            EventRegistration.event_id == event_id,
        )
    )
    if status is not None:
        consulta = consulta.where(EventRegistration.status == status)
    return int(await session.scalar(consulta) or 0)


def registrations_query(
    organization_id: uuid.UUID, event_id: uuid.UUID, *, status: str | None = None
) -> Select[tuple[EventRegistration]]:
    consulta = (
        select(EventRegistration)
        .where(
            EventRegistration.organization_id == organization_id,
            EventRegistration.event_id == event_id,
        )
        .order_by(EventRegistration.created_at.desc())
    )
    if status is not None:
        consulta = consulta.where(EventRegistration.status == status)
    return consulta


async def get_registration(
    session: AsyncSession,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    registration_id: uuid.UUID,
) -> EventRegistration | None:
    resultado: EventRegistration | None = await session.scalar(
        select(EventRegistration).where(
            EventRegistration.id == registration_id,
            EventRegistration.event_id == event_id,
            EventRegistration.organization_id == organization_id,
        )
    )
    return resultado


async def get_registration_for_update(
    session: AsyncSession,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    registration_id: uuid.UUID,
) -> EventRegistration | None:
    """Como `get_registration`, pero con `SELECT ... FOR UPDATE`.

    Necesario antes de decidir si una cancelación libera una plaza: sin este
    bloqueo, dos cancelaciones concurrentes de la misma inscripción (dos
    tokens vigentes, o el organizador y la persona a la vez) podrían leer
    ambas el estado `confirmed` antes de que ninguna confirme su cambio, y
    las dos acabarían promoviendo a alguien de la lista de espera para un
    único hueco liberado.
    """
    resultado: EventRegistration | None = await session.scalar(
        select(EventRegistration)
        .where(
            EventRegistration.id == registration_id,
            EventRegistration.event_id == event_id,
            EventRegistration.organization_id == organization_id,
        )
        .with_for_update()
    )
    return resultado


async def get_oldest_waitlisted(
    session: AsyncSession, organization_id: uuid.UUID, event_id: uuid.UUID
) -> EventRegistration | None:
    """La siguiente persona a promover: la más antigua en espera que no esté ya
    en mitad de una promoción vigente.

    Orden: primero quien nunca ha sido promovida (`waitlist_position` a `NULL`,
    por orden de alta), después quien volvió al final de la cola tras dejar
    caducar una promoción anterior (`waitlist_position` creciente) — así una
    promoción caducada de verdad manda a esa persona al final, no la deja
    competir por antigüedad con quien nunca tuvo su turno.
    """
    orden_grupo = case((EventRegistration.waitlist_position.is_(None), 0), else_=1)
    resultado: EventRegistration | None = await session.scalar(
        select(EventRegistration)
        .where(
            EventRegistration.organization_id == organization_id,
            EventRegistration.event_id == event_id,
            EventRegistration.status == "waitlisted",
            EventRegistration.waitlist_promoted_at.is_(None),
        )
        .order_by(orden_grupo, EventRegistration.waitlist_position, EventRegistration.created_at)
    )
    return resultado


async def get_expired_waitlist_promotions(
    session: AsyncSession, organization_id: uuid.UUID, event_id: uuid.UUID
) -> list[EventRegistration]:
    """Promociones vencidas sin confirmar, bloqueadas para la tarea cron."""
    filas = await session.scalars(
        select(EventRegistration)
        .where(
            EventRegistration.organization_id == organization_id,
            EventRegistration.event_id == event_id,
            EventRegistration.status == "waitlisted",
            EventRegistration.waitlist_promoted_at.is_not(None),
            EventRegistration.waitlist_promotion_expires_at < datetime.now(UTC),
        )
        .with_for_update()
    )
    return list(filas)


async def events_with_expired_waitlist_promotions(
    session: AsyncSession,
) -> list[tuple[uuid.UUID, uuid.UUID]]:
    """`(organization_id, event_id)` con al menos una promoción vencida, para
    que la tarea cron sepa qué eventos recorrer sin barrer toda la tabla fila a
    fila fuera de una sección crítica."""
    filas = (
        await session.execute(
            select(EventRegistration.organization_id, EventRegistration.event_id)
            .where(
                EventRegistration.status == "waitlisted",
                EventRegistration.waitlist_promoted_at.is_not(None),
                EventRegistration.waitlist_promotion_expires_at < datetime.now(UTC),
            )
            .distinct()
        )
    ).all()
    return [(fila.organization_id, fila.event_id) for fila in filas]


async def requeue_to_back_of_waitlist(
    session: AsyncSession,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    inscripcion: EventRegistration,
) -> None:
    """Manda una promoción caducada al final de la cola de espera del evento."""
    maxima = await session.scalar(
        select(func.max(EventRegistration.waitlist_position)).where(
            EventRegistration.organization_id == organization_id,
            EventRegistration.event_id == event_id,
        )
    )
    inscripcion.waitlist_position = (maxima or 0) + 1
    inscripcion.waitlist_promoted_at = None
    inscripcion.waitlist_promotion_expires_at = None


async def count_registrations_by_status(
    session: AsyncSession, organization_id: uuid.UUID, event_id: uuid.UUID
) -> dict[str, int]:
    filas = (
        await session.execute(
            select(EventRegistration.status, func.count())
            .where(
                EventRegistration.organization_id == organization_id,
                EventRegistration.event_id == event_id,
            )
            .group_by(EventRegistration.status)
        )
    ).all()
    return {estado: int(total) for estado, total in filas}


async def count_verified_registrations(
    session: AsyncSession, organization_id: uuid.UUID, event_id: uuid.UUID
) -> int:
    """Inscripciones que llegaron a verificarse, cualquiera que sea su estado
    posterior — sirve de denominador de la conversión confirmados/verificados."""
    total = await session.scalar(
        select(func.count())
        .select_from(EventRegistration)
        .where(
            EventRegistration.organization_id == organization_id,
            EventRegistration.event_id == event_id,
            EventRegistration.verified_at.is_not(None),
        )
    )
    return int(total or 0)


async def get_question(
    session: AsyncSession, organization_id: uuid.UUID, event_id: uuid.UUID, question_id: uuid.UUID
) -> EventRegistrationQuestion | None:
    resultado: EventRegistrationQuestion | None = await session.scalar(
        select(EventRegistrationQuestion).where(
            EventRegistrationQuestion.id == question_id,
            EventRegistrationQuestion.event_id == event_id,
            EventRegistrationQuestion.organization_id == organization_id,
        )
    )
    return resultado


async def question_has_answers(
    session: AsyncSession, organization_id: uuid.UUID, question_id: uuid.UUID
) -> bool:
    existe = await session.scalar(
        select(EventRegistrationAnswer.id)
        .where(
            EventRegistrationAnswer.organization_id == organization_id,
            EventRegistrationAnswer.question_id == question_id,
        )
        .limit(1)
    )
    return existe is not None


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
