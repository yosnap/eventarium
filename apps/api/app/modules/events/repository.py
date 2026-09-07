"""Acceso a datos de eventos y agenda.

Filtra siempre por `organization_id` de forma explícita, igual que
`organizations/repository.py`: RLS es la red de seguridad, no el filtro
principal.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.events.models import Event, EventMember, EventSession, EventSessionParticipant
from app.modules.organizations.models import OrganizationMember
from app.modules.roles.models import Role
from app.modules.users.models import User


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


def event_members_query(organization_id: uuid.UUID, event_id: uuid.UUID) -> Select[Any]:
    """Roster de un evento, con la persona y el rol de su membresía de origen."""
    return (
        select(EventMember, OrganizationMember, User, Role)
        .join(OrganizationMember, OrganizationMember.id == EventMember.organization_member_id)
        .join(User, User.id == OrganizationMember.user_id)
        .join(Role, Role.id == OrganizationMember.role_id)
        .where(EventMember.organization_id == organization_id, EventMember.event_id == event_id)
        .order_by(User.first_name, User.last_name, User.email)
    )


async def get_event_member(
    session: AsyncSession,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    event_member_id: uuid.UUID,
) -> EventMember | None:
    resultado: EventMember | None = await session.scalar(
        select(EventMember).where(
            EventMember.id == event_member_id,
            EventMember.event_id == event_id,
            EventMember.organization_id == organization_id,
        )
    )
    return resultado


async def get_event_member_by_organization_member(
    session: AsyncSession,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    organization_member_id: uuid.UUID,
) -> EventMember | None:
    resultado: EventMember | None = await session.scalar(
        select(EventMember).where(
            EventMember.event_id == event_id,
            EventMember.organization_id == organization_id,
            EventMember.organization_member_id == organization_member_id,
        )
    )
    return resultado


async def count_active_participations(
    session: AsyncSession, organization_id: uuid.UUID, event_member_id: uuid.UUID
) -> int:
    """Sesiones en las que participa `event_member_id`, para el 409 al quitarlo
    del roster (RESTRICT en base de datos es la red, esto es el mensaje legible)."""
    total = await session.scalar(
        select(func.count())
        .select_from(EventSessionParticipant)
        .where(
            EventSessionParticipant.organization_id == organization_id,
            EventSessionParticipant.event_member_id == event_member_id,
        )
    )
    return int(total or 0)


def session_participants_query(organization_id: uuid.UUID, session_id: uuid.UUID) -> Select[Any]:
    """Participantes de una sesión, con la persona a la que pertenece cada uno."""
    return (
        select(EventSessionParticipant, EventMember, OrganizationMember, User)
        .join(EventMember, EventMember.id == EventSessionParticipant.event_member_id)
        .join(OrganizationMember, OrganizationMember.id == EventMember.organization_member_id)
        .join(User, User.id == OrganizationMember.user_id)
        .where(
            EventSessionParticipant.organization_id == organization_id,
            EventSessionParticipant.session_id == session_id,
        )
        .order_by(EventSessionParticipant.sort_order)
    )


async def event_member_ids(
    session: AsyncSession, organization_id: uuid.UUID, event_id: uuid.UUID
) -> set[uuid.UUID]:
    """IDs del roster de un evento, para validar pertenencia sin cargar filas enteras."""
    filas = await session.scalars(
        select(EventMember.id).where(
            EventMember.organization_id == organization_id, EventMember.event_id == event_id
        )
    )
    return set(filas)
