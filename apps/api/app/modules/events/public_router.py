"""Endpoints públicos de eventos, sesiones y ponentes (fase 4 del PRD).

Prefijo fijado a `/public/...`: no es una decisión abierta de implementación, la
tomó el plan tras el red-team. Sin autenticación (son lecturas): usan
`OrganizationDep` + `DbDep`, que resuelven la organización por host y fijan el
contexto RLS sin pasar por `get_current_user`. El filtro de publicación
(`published` + `public`) se aplica siempre de forma explícita en la propia
consulta — nunca se confía en que RLS ya lo hace, porque RLS aísla por
organización, no por si un evento está publicado: un borrador de la propia
organización seguiría siendo visible bajo su contexto anónimo sin ese filtro.

El 404 es uniforme dentro de cada tipo de recurso, sin distinguir la razón de la
ausencia (borrador, oculto, privado, slug ajeno o inexistente): dar códigos o
mensajes distintos permitiría enumerar qué eventos existen sin verlos, mismo
patrón que ya usa el registro para no filtrar si un correo existe.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.core.deps import DbDep, OrganizationDep
from app.core.ratelimit import PUBLICO_POR_IP, limit_per_ip
from app.core.storage import get_storage
from app.modules.events import repository, speakers_repository
from app.modules.events.models import (
    Event,
    EventMember,
    EventSessionParticipant,
    SpeakerPublicProfile,
)
from app.modules.events.schemas import (
    PublicEventDetail,
    PublicEventSession,
    PublicEventSummary,
    PublicParticipant,
    PublicSessionDetail,
)
from app.modules.organizations.models import OrganizationMember
from app.modules.users.models import User, UserSocialLink
from app.modules.users.schemas import (
    PublicSpeakerHistoryItem,
    PublicSpeakerProfile,
    SocialLinkResponse,
    filter_public_profile_fields,
)
from app.shared.errors import NotFoundError

router = APIRouter(prefix="/public", tags=["público"])


def _display_name(persona: User) -> str:
    nombre = " ".join(parte for parte in (persona.first_name, persona.last_name) if parte)
    return nombre or "Persona"


def _cover_url(evento: Event) -> str | None:
    if not evento.cover_object_key:
        return None
    return get_storage().public_url(evento.cover_object_key)


async def _sesiones_publicas(
    session: DbDep, organization_id: uuid.UUID, event_id: uuid.UUID
) -> list[PublicEventSession]:
    """Agenda completa de un evento, con los participantes de cada sesión.

    Una sola consulta para todos los participantes de todas las sesiones, en vez
    de una por sesión: evita el N+1 en una agenda con muchas charlas.
    """
    sesiones = (
        (await session.execute(repository.sessions_query(organization_id, event_id)))
        .scalars()
        .all()
    )
    if not sesiones:
        return []

    ids_sesion = [sesion.id for sesion in sesiones]
    consulta = (
        select(EventSessionParticipant, EventMember, OrganizationMember, User)
        .join(EventMember, EventMember.id == EventSessionParticipant.event_member_id)
        .join(OrganizationMember, OrganizationMember.id == EventMember.organization_member_id)
        .join(User, User.id == OrganizationMember.user_id)
        .where(
            EventSessionParticipant.organization_id == organization_id,
            EventSessionParticipant.session_id.in_(ids_sesion),
        )
        .order_by(EventSessionParticipant.sort_order)
    )
    filas = (await session.execute(consulta)).all()

    user_ids = {persona.id for _, _, _, persona in filas}
    slugs = await speakers_repository.get_public_slugs_by_user_ids(
        session, organization_id, user_ids
    )

    por_sesion: dict[uuid.UUID, list[PublicParticipant]] = defaultdict(list)
    for participante, _, _, persona in filas:
        por_sesion[participante.session_id].append(
            PublicParticipant(
                display_name=_display_name(persona),
                role_key=participante.role_key,
                public_slug=slugs.get(persona.id),
            )
        )

    return [
        PublicEventSession(
            id=str(sesion.id),
            session_type=sesion.session_type,  # type: ignore[arg-type]
            title=sesion.title,
            description=sesion.description,
            starts_at=sesion.starts_at,
            ends_at=sesion.ends_at,
            room=sesion.room,
            video_platform=sesion.video_platform,  # type: ignore[arg-type]
            video_url=sesion.video_url,
            materials=sesion.materials,
            participants=por_sesion.get(sesion.id, []),
        )
        for sesion in sesiones
    ]


@router.get(
    "/events",
    summary="Listar eventos publicados",
    response_model=list[PublicEventSummary],
    dependencies=[limit_per_ip("public-events", PUBLICO_POR_IP)],
)
async def list_public_events(
    organizacion: OrganizationDep, session: DbDep
) -> list[PublicEventSummary]:
    eventos = (await session.execute(repository.public_events_query(organizacion.id))).scalars()
    return [
        PublicEventSummary(
            slug=evento.slug,
            title=evento.title,
            summary=evento.summary,
            cover_url=_cover_url(evento),
            timezone=evento.timezone,
            starts_at=evento.starts_at,
            ends_at=evento.ends_at,
            location_mode=evento.location_mode,  # type: ignore[arg-type]
            location_name=evento.location_name,
        )
        for evento in eventos
    ]


async def _obtener_evento_publico_o_404(
    organizacion: OrganizationDep, session: DbDep, slug: str
) -> Event:
    evento = await repository.get_public_event_by_slug(session, organizacion.id, slug)
    if evento is None:
        raise NotFoundError("El evento no existe.")
    return evento


@router.get(
    "/events/{slug}",
    summary="Ver el detalle de un evento publicado",
    response_model=PublicEventDetail,
    dependencies=[limit_per_ip("public-event-detail", PUBLICO_POR_IP)],
)
async def get_public_event(
    evento: Annotated[Event, Depends(_obtener_evento_publico_o_404)], session: DbDep
) -> PublicEventDetail:
    sesiones = await _sesiones_publicas(session, evento.organization_id, evento.id)
    return PublicEventDetail(
        slug=evento.slug,
        title=evento.title,
        summary=evento.summary,
        description=evento.description,
        cover_url=_cover_url(evento),
        timezone=evento.timezone,
        starts_at=evento.starts_at,
        ends_at=evento.ends_at,
        location_mode=evento.location_mode,  # type: ignore[arg-type]
        location_name=evento.location_name,
        location_address=evento.location_address,
        online_url=evento.online_url,
        capacity=evento.capacity,
        registration_mode=evento.registration_mode,  # type: ignore[arg-type]
        sessions=sesiones,
    )


@router.get(
    "/events/{slug}/sessions/{session_id}",
    summary="Ver el detalle de una sesión publicada",
    description=(
        "Anidado bajo el evento: exige que el evento sea `published` + `public` "
        "además de que la propia sesión le pertenezca. Sin este anidamiento, un "
        "`id` de sesión (UUIDv7, con entropía reducida frente a un v4 dentro de "
        "una ventana de tiempo conocida) sería enumerable y filtraría agendas de "
        "eventos sin publicar."
    ),
    response_model=PublicSessionDetail,
    dependencies=[limit_per_ip("public-session-detail", PUBLICO_POR_IP)],
)
async def get_public_session(
    evento: Annotated[Event, Depends(_obtener_evento_publico_o_404)],
    session: DbDep,
    session_id: str,
) -> PublicSessionDetail:
    try:
        id_sesion = uuid.UUID(session_id)
    except ValueError as exc:
        raise NotFoundError("La sesión no existe.") from exc

    sesion = await repository.get_event_session(
        session, evento.organization_id, evento.id, id_sesion
    )
    if sesion is None:
        raise NotFoundError("La sesión no existe.")

    consulta = repository.session_participants_query(evento.organization_id, sesion.id)
    filas = (await session.execute(consulta)).all()
    user_ids = {persona.id for _, _, _, persona in filas}
    slugs = await speakers_repository.get_public_slugs_by_user_ids(
        session, evento.organization_id, user_ids
    )
    participantes = [
        PublicParticipant(
            display_name=_display_name(persona),
            role_key=participante.role_key,
            public_slug=slugs.get(persona.id),
        )
        for participante, _, _, persona in filas
    ]

    return PublicSessionDetail(
        id=str(sesion.id),
        session_type=sesion.session_type,  # type: ignore[arg-type]
        title=sesion.title,
        description=sesion.description,
        starts_at=sesion.starts_at,
        ends_at=sesion.ends_at,
        room=sesion.room,
        video_platform=sesion.video_platform,  # type: ignore[arg-type]
        video_url=sesion.video_url,
        materials=sesion.materials,
        participants=participantes,
        event_slug=evento.slug,
        event_title=evento.title,
    )


@router.get(
    "/speakers/{public_slug}",
    summary="Ver el perfil público de un ponente",
    response_model=PublicSpeakerProfile,
    dependencies=[limit_per_ip("public-speaker-detail", PUBLICO_POR_IP)],
)
async def get_public_speaker(
    public_slug: str, organizacion: OrganizationDep, session: DbDep
) -> PublicSpeakerProfile:
    perfil = await session.scalar(
        select(SpeakerPublicProfile).where(
            SpeakerPublicProfile.organization_id == organizacion.id,
            SpeakerPublicProfile.public_slug == public_slug,
        )
    )
    if perfil is None:
        raise NotFoundError("El ponente no existe.")

    miembro = await session.get(OrganizationMember, perfil.source_organization_member_id)
    persona = await session.get(User, perfil.user_id)
    if miembro is None or persona is None:
        raise NotFoundError("El ponente no existe.")

    enlaces = (
        await session.scalars(
            select(UserSocialLink)
            .where(UserSocialLink.user_id == perfil.user_id)
            .order_by(UserSocialLink.kind)
        )
    ).all()

    historial_filas = await speakers_repository.get_speaker_history(
        session, organizacion.id, perfil.user_id, only_published_public=True
    )

    return PublicSpeakerProfile(
        display_name=_display_name(persona),
        public_slug=perfil.public_slug,
        fields=filter_public_profile_fields(miembro.profile_data),
        social_links=[SocialLinkResponse.model_validate(enlace) for enlace in enlaces],
        history=[
            PublicSpeakerHistoryItem(
                event_slug=evento.slug,
                event_title=evento.title,
                session_id=str(sesion.id),
                session_title=sesion.title,
                starts_at=sesion.starts_at,
                role_key=participacion.role_key,
            )
            for participacion, sesion, evento in historial_filas
        ],
    )
