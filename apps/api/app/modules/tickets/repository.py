"""Acceso a datos de entradas QR y sus escaneos.

Mismo criterio que `registrations/repository.py`: se filtra siempre por
`organization_id` de forma explícita. RLS es la red de seguridad, no el
filtro principal.
"""

from __future__ import annotations

import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organizations.models import OrganizationMember
from app.modules.registrations.models import EventRegistration
from app.modules.tickets.models import EventTicket, EventTicketScan

# Tope defensivo de la búsqueda manual: es un respaldo de check-in en la
# puerta, no un listado administrativo — nadie necesita ver más de un puñado
# de coincidencias a la vez.
_LIMITE_BUSQUEDA = 50


async def get_ticket_by_registration(
    session: AsyncSession, organization_id: uuid.UUID, registration_id: uuid.UUID
) -> EventTicket | None:
    resultado: EventTicket | None = await session.scalar(
        select(EventTicket).where(
            EventTicket.organization_id == organization_id,
            EventTicket.registration_id == registration_id,
        )
    )
    return resultado


async def get_ticket(
    session: AsyncSession, organization_id: uuid.UUID, ticket_id: uuid.UUID
) -> EventTicket | None:
    resultado: EventTicket | None = await session.scalar(
        select(EventTicket).where(
            EventTicket.id == ticket_id, EventTicket.organization_id == organization_id
        )
    )
    return resultado


async def get_ticket_for_update(
    session: AsyncSession, organization_id: uuid.UUID, ticket_id: uuid.UUID
) -> EventTicket | None:
    """Como `get_ticket`, pero con `SELECT ... FOR UPDATE`.

    Serializa dos escaneos casi simultáneos del mismo QR en dos dispositivos:
    el segundo espera a que el primero termine de marcar `used_at` antes de
    poder leerlo, y lo ve ya puesto.
    """
    resultado: EventTicket | None = await session.scalar(
        select(EventTicket)
        .where(EventTicket.id == ticket_id, EventTicket.organization_id == organization_id)
        .with_for_update()
    )
    return resultado


async def get_scan_by_client_scan_id(
    session: AsyncSession, organization_id: uuid.UUID, client_scan_id: uuid.UUID
) -> EventTicketScan | None:
    resultado: EventTicketScan | None = await session.scalar(
        select(EventTicketScan).where(
            EventTicketScan.organization_id == organization_id,
            EventTicketScan.client_scan_id == client_scan_id,
        )
    )
    return resultado


async def search_confirmed_tickets(
    session: AsyncSession, organization_id: uuid.UUID, event_id: uuid.UUID, q: str
) -> list[tuple[EventTicket, EventRegistration]]:
    """Entradas vigentes (no revocadas) de inscripciones `confirmed`, por
    nombre o email — el email va completo, sin enmascarar (mismo criterio que
    el resto del panel de organizador con `registrations:read`)."""
    patron = f"%{q}%"
    filas = (
        await session.execute(
            select(EventTicket, EventRegistration)
            .join(EventRegistration, EventRegistration.id == EventTicket.registration_id)
            .where(
                EventTicket.organization_id == organization_id,
                EventTicket.event_id == event_id,
                EventTicket.revoked_at.is_(None),
                EventRegistration.status == "confirmed",
                or_(
                    EventRegistration.full_name.ilike(patron),
                    EventRegistration.email.ilike(patron),
                ),
            )
            .order_by(EventRegistration.full_name)
            .limit(_LIMITE_BUSQUEDA)
        )
    ).all()
    return [(fila[0], fila[1]) for fila in filas]


async def get_ticket_with_registration(
    session: AsyncSession,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    registration_id: uuid.UUID,
) -> tuple[EventTicket, EventRegistration] | None:
    fila = (
        await session.execute(
            select(EventTicket, EventRegistration)
            .join(EventRegistration, EventRegistration.id == EventTicket.registration_id)
            .where(
                EventTicket.organization_id == organization_id,
                EventTicket.event_id == event_id,
                EventTicket.registration_id == registration_id,
            )
        )
    ).first()
    return (fila[0], fila[1]) if fila is not None else None


async def get_any_organization_member_id(
    session: AsyncSession, organization_id: uuid.UUID, user_id: uuid.UUID
) -> uuid.UUID | None:
    """Cualquiera de las membresías de la persona en la organización.

    Una persona puede tener varias filas en `organization_members` (una por
    rol); para el registro de auditoría de quién escaneó basta con
    cualquiera de ellas — no importa cuál en concreto.
    """
    resultado: uuid.UUID | None = await session.scalar(
        select(OrganizationMember.id)
        .where(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.user_id == user_id,
        )
        .limit(1)
    )
    return resultado
