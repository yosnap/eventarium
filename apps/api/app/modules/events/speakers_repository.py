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
from collections.abc import Sequence
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.events.models import (
    Event,
    EventMember,
    EventSession,
    EventSessionParticipant,
    SpeakerPublicProfile,
)
from app.modules.organizations.models import OrganizationMember
from app.modules.roles.models import Role
from app.modules.roles.system_roles import SPEAKER_KEY
from app.modules.users.models import User

# Las claves de la ficha de ponente cuya presencia define la completitud:
# las mismas que define la plantilla del rol `speaker` en `system_roles`.
# Fijadas aquí (y no leídas de la plantilla) para que la fórmula del panel
# sea estable: si la plantilla cambia en el futuro, la vista del organizador
# no cambia de criterio sin decidirlo.
CLAVES_FICHA_PONENTE: tuple[str, ...] = (
    "bio",
    "titular",
    "empresa",
    "curriculum",
    "web",
    "contacto",
)


def _clave_rellena(valor: Any) -> bool:
    """Una clave cuenta como rellenada cuando tiene texto no vacío."""
    return isinstance(valor, str) and bool(valor.strip())


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


async def get_public_slugs_by_user_ids(
    session: AsyncSession, organization_id: uuid.UUID, user_ids: set[uuid.UUID]
) -> dict[uuid.UUID, str]:
    """`user_id → public_slug` para quienes activaron su perfil, sin N+1 al pintar
    una agenda con varios participantes."""
    if not user_ids:
        return {}
    filas = await session.execute(
        select(SpeakerPublicProfile.user_id, SpeakerPublicProfile.public_slug).where(
            SpeakerPublicProfile.organization_id == organization_id,
            SpeakerPublicProfile.user_id.in_(user_ids),
        )
    )
    return {user_id: slug for user_id, slug in filas}

async def listar_ponentes_del_evento(
    session: AsyncSession, organization_id: uuid.UUID, event_id: uuid.UUID
) -> tuple[
    Sequence[Any],
    dict[uuid.UUID, list[tuple[uuid.UUID, str, Any]]],
    dict[uuid.UUID, int],
    dict[uuid.UUID, str],
    int,
]:
    """Vista agregada de ponentes de un evento, una consulta por tabla.

    Devuelve, en orden: las filas de ponente (miembro de evento con rol de
    ponente en la organización, junto a su membresía, persona y rol), las
    sesiones del evento por `event_member_id`, el número de eventos de la
    organización donde cada persona está en el roster (por `user_id`, un
    solo `GROUP BY` — nunca el historial por ponente, que es N+1), el slug
    público por `user_id` y el total de sesiones del evento.
    """
    filas = (
        await session.execute(
            select(EventMember, OrganizationMember, User, Role)
            .join(OrganizationMember, OrganizationMember.id == EventMember.organization_member_id)
            .join(User, User.id == OrganizationMember.user_id)
            .join(Role, Role.id == OrganizationMember.role_id)
            .where(
                EventMember.event_id == event_id,
                EventMember.organization_id == organization_id,
                Role.key == SPEAKER_KEY,
            )
            .order_by(User.first_name.asc().nulls_last(), User.last_name.asc().nulls_last())
        )
    ).all()

    ids_miembro = [miembro.id for miembro, _, _, _ in filas]
    ids_usuario = {miembro_org.user_id for _, miembro_org, _, _ in filas}

    sesiones_por_miembro: dict[uuid.UUID, list[tuple[uuid.UUID, str, Any]]] = {}
    if ids_miembro:
        filas_sesiones = (
            await session.execute(
                select(EventSessionParticipant, EventSession)
                .join(EventSession, EventSession.id == EventSessionParticipant.session_id)
                .where(
                    EventSessionParticipant.event_member_id.in_(ids_miembro),
                    EventSessionParticipant.organization_id == organization_id,
                    EventSession.event_id == event_id,
                )
                .order_by(EventSession.starts_at.asc().nulls_last())
            )
        ).all()
        for participacion, sesion in filas_sesiones:
            sesiones_por_miembro.setdefault(participacion.event_member_id, []).append(
                (sesion.id, sesion.title, sesion.starts_at)
            )

    ediciones_por_usuario: dict[uuid.UUID, int] = {}
    if ids_usuario:
        filas_ediciones = (
            await session.execute(
                select(OrganizationMember.user_id, func.count(func.distinct(EventMember.event_id)))
                .join(EventMember, EventMember.organization_member_id == OrganizationMember.id)
                .where(
                    OrganizationMember.organization_id == organization_id,
                    OrganizationMember.user_id.in_(ids_usuario),
                )
                .group_by(OrganizationMember.user_id)
            )
        ).all()
        ediciones_por_usuario = {user_id: conteo for user_id, conteo in filas_ediciones}

    slugs = await get_public_slugs_by_user_ids(session, organization_id, ids_usuario)

    total_sesiones = (
        await session.execute(
            select(func.count())
            .select_from(EventSession)
            .where(EventSession.event_id == event_id)
        )
    ).scalar_one()

    return filas, sesiones_por_miembro, ediciones_por_usuario, slugs, total_sesiones


async def obtener_email_de_miembro_del_evento(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    organization_member_id: uuid.UUID,
) -> str | None:
    """Correo de un ponente del roster del evento, o `None` si no lo es.

    Exige el rol de ponente en la membresía de la organización, la misma
    condición que filtra la vista: pedir bio a cualquier miembro del roster
    (voluntariado, personal) enviaría un correo que no le corresponde.
    """
    fila = (
        await session.execute(
            select(User.email)
            .join(OrganizationMember, OrganizationMember.user_id == User.id)
            .join(Role, Role.id == OrganizationMember.role_id)
            .join(EventMember, EventMember.organization_member_id == OrganizationMember.id)
            .where(
                EventMember.event_id == event_id,
                EventMember.organization_id == organization_id,
                OrganizationMember.id == organization_member_id,
                OrganizationMember.organization_id == organization_id,
                Role.key == SPEAKER_KEY,
            )
        )
    ).first()
    return fila[0] if fila else None
