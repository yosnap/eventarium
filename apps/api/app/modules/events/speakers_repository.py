"""Historial de participación de un ponente entre ediciones.

Se resuelve por `user_id` a través de **todas** las membresías de esa persona en la
organización (no solo la que activó el perfil público): la misma persona puede tener
varias filas en `organization_members` (una por rol) a lo largo del tiempo.

El filtro de visibilidad se recibe como parámetro explícito (`only_published_public`),
nunca como valor por defecto: esta consulta la usan tanto el endpoint de
administración (previsualización, que puede querer ver también lo no publicado) como
el público (fase 4, que **siempre** exige `published` + `public`) — un valor por
defecto sería demasiado fácil de olvidar pasar desde uno de los dos lados.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.events.models import Event, EventMember, EventSession, EventSessionParticipant
from app.modules.organizations.models import OrganizationMember


def speaker_history_query(
    organization_id: uuid.UUID, user_id: uuid.UUID, *, only_published_public: bool
) -> Select[Any]:
    consulta = (
        select(EventSessionParticipant, EventSession, Event)
        .join(EventSession, EventSession.id == EventSessionParticipant.session_id)
        .join(Event, Event.id == EventSession.event_id)
        .join(EventMember, EventMember.id == EventSessionParticipant.event_member_id)
        .join(OrganizationMember, OrganizationMember.id == EventMember.organization_member_id)
        .where(
            EventSessionParticipant.organization_id == organization_id,
            OrganizationMember.user_id == user_id,
        )
        .order_by(EventSession.starts_at.desc())
    )
    if only_published_public:
        # Nunca `hidden`/`private`, aunque el evento ya esté `published`: la
        # regla pública es la conjunción de ambos campos, no solo el estado.
        consulta = consulta.where(Event.status == "published", Event.visibility == "public")
    return consulta


async def get_speaker_history(
    session: AsyncSession,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    only_published_public: bool,
) -> list[tuple[EventSessionParticipant, EventSession, Event]]:
    filas = (
        await session.execute(
            speaker_history_query(
                organization_id, user_id, only_published_public=only_published_public
            )
        )
    ).all()
    return [(participacion, sesion, evento) for participacion, sesion, evento in filas]
