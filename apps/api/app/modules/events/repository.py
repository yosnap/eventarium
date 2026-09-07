"""Acceso a datos de eventos y agenda.

Filtra siempre por `organization_id` de forma explícita, igual que
`organizations/repository.py`: RLS es la red de seguridad, no el filtro
principal.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.events.models import Event, EventSession


def events_query(organization_id: uuid.UUID, *, status: str | None = None) -> Select[tuple[Event]]:
    consulta = (
        select(Event)
        .where(Event.organization_id == organization_id)
        .order_by(Event.starts_at.desc())
    )
    if status is not None:
        consulta = consulta.where(Event.status == status)
    return consulta


async def get_event(
    session: AsyncSession, organization_id: uuid.UUID, event_id: uuid.UUID
) -> Event | None:
    resultado: Event | None = await session.scalar(
        select(Event).where(Event.id == event_id, Event.organization_id == organization_id)
    )
    return resultado


async def get_event_by_slug(
    session: AsyncSession, organization_id: uuid.UUID, slug: str
) -> Event | None:
    resultado: Event | None = await session.scalar(
        select(Event).where(Event.organization_id == organization_id, Event.slug == slug)
    )
    return resultado


def sessions_query(organization_id: uuid.UUID, event_id: uuid.UUID) -> Select[tuple[EventSession]]:
    return (
        select(EventSession)
        .where(
            EventSession.organization_id == organization_id,
            EventSession.event_id == event_id,
        )
        .order_by(EventSession.starts_at, EventSession.sort_order)
    )


async def get_event_session(
    session: AsyncSession, organization_id: uuid.UUID, event_id: uuid.UUID, session_id: uuid.UUID
) -> EventSession | None:
    resultado: EventSession | None = await session.scalar(
        select(EventSession).where(
            EventSession.id == session_id,
            EventSession.event_id == event_id,
            EventSession.organization_id == organization_id,
        )
    )
    return resultado
