"""Endpoints públicos de eventos, sesiones y ponentes (fase 4 del PRD).

Prefijo fijado a `/public/...`: no es una decisión abierta de implementación, la
tomó el plan tras el red-team. Sin autenticación (son lecturas). Sin dominio
por organización (fase 2 del plan de organización sin dominio), el detalle de
un evento (`GET /events/{slug}` y todo lo que cuelga de él) resuelve su
organización desde el propio evento (`events.service.resolve_public_event_by_slug`,
`SessionDep`, sin ningún contexto RLS previo), igual que ya hace
`checkout_service.iniciar_compra` con `event.organization_id` — no por host.

`list_public_events` (`GET /events`, el listado, no el detalle) lista los
eventos publicados de **toda la instalación** (fase 6 del plan de
organización sin dominio, corrección de comportamiento: seguía resolviendo
por host, lo que en producción sin dominio por organización eran 404 sin
más — ver `list_public_events_across_organizations` en `events/service.py`
para el porqué de la resolución organización a organización).

El filtro de publicación (`published` + `public`) se aplica siempre de forma
explícita en la propia consulta — nunca se confía en que RLS ya lo hace,
porque RLS aísla por organización, no por si un evento está publicado: un
borrador de la propia organización seguiría siendo visible bajo su contexto
anónimo sin ese filtro.

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
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import set_organization_context
from app.core.deps import SessionDep
from app.core.ratelimit import PUBLICO_POR_IP, limit_per_ip
from app.core.storage import get_storage
from app.modules.events import repository, service, speakers_repository
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
    PublicTheme,
    PublicVenue,
)
from app.modules.organizations.models import OrganizationMember
from app.modules.payments import service as payments_service
from app.modules.registrations import repository as registrations_repository
from app.modules.sponsors import repository as sponsors_repository
from app.modules.sponsors.schemas import (
    PublicSponsor,
    PublicSponsorDetail,
    PublicSponsorHistoryItem,
    PublicSponsorTier,
)
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
    session: AsyncSession, organization_id: uuid.UUID, event_id: uuid.UUID
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
            venue_id=str(sesion.venue_id) if sesion.venue_id else None,
            video_platform=sesion.video_platform,  # type: ignore[arg-type]
            video_url=sesion.video_url,
            materials=sesion.materials,
            participants=por_sesion.get(sesion.id, []),
        )
        for sesion in sesiones
    ]


async def _sedes_publicas(
    session: AsyncSession, organization_id: uuid.UUID, event_id: uuid.UUID
) -> list[PublicVenue]:
    filas = (
        (await session.execute(repository.venues_query(organization_id, event_id))).scalars().all()
    )
    return [
        PublicVenue(
            id=str(sede.id),
            name=sede.name,
            address=sede.address,
            capacity=sede.capacity,
            latitude=float(sede.latitude) if sede.latitude is not None else None,
            longitude=float(sede.longitude) if sede.longitude is not None else None,
        )
        for sede in filas
    ]


async def _tema_del_evento(session: AsyncSession, evento: Event) -> PublicTheme | None:
    """La plantilla del evento, con la herencia ya resuelta.

    Tres niveles, y el orden importa: la del evento si la eligió, si no la de su
    organización, y si tampoco la marcada por defecto en el catálogo. Se resuelve
    aquí y no en el cliente porque encadenar tres consultas desde el navegador
    para pintar una página pública sería absurdo, y porque el catálogo es una
    tabla de instalación que el visitante no tiene por qué conocer.
    """
    fila = (
        await session.execute(
            text(
                "SELECT t.id, t.key, t.name, t.tokens "
                "FROM events e "
                "LEFT JOIN organization_branding b ON b.organization_id = e.organization_id "
                "LEFT JOIN theme_templates t ON t.id = COALESCE("
                "    e.theme_template_id, "
                "    b.theme_template_id, "
                "    (SELECT id FROM theme_templates WHERE is_default IS TRUE LIMIT 1)"
                ") "
                "WHERE e.id = :id"
            ),
            {"id": evento.id},
        )
    ).first()

    if fila is None or fila[0] is None:
        return None
    return PublicTheme(id=str(fila[0]), key=fila[1], name=fila[2], tokens=fila[3])


@router.get(
    "/events",
    summary="Listar eventos publicados",
    response_model=list[PublicEventSummary],
    dependencies=[limit_per_ip("public-events", PUBLICO_POR_IP)],
)
async def list_public_events(session: SessionDep) -> list[PublicEventSummary]:
    filas = await service.list_public_events_across_organizations(session)
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
            city=evento.city,
            registration_mode=evento.registration_mode,  # type: ignore[arg-type]
            registration_opens_at=evento.registration_opens_at,
            capacity=evento.capacity,
            reserved_count=reservadas,
            price_from_cents=precio.tipo.price_cents if precio else None,
            price_currency=precio.tipo.currency if precio else None,
            price_multiple=precio.varios_precios if precio else False,
        )
        for evento, reservadas, precio in filas
    ]


async def _obtener_evento_publico_o_404(session: SessionDep, slug: str) -> Event:
    return await service.resolve_public_event_by_slug(session, slug)


async def _sponsor_tiers_publicos(
    session: AsyncSession, organization_id: uuid.UUID, event_id: uuid.UUID
) -> list[PublicSponsorTier]:
    """Patrocinadores del evento agrupados por nivel y ordenados por
    `display_order` (Fase 5 del PRD, fase 2 de trabajo). Sin aportación: el
    PRD no pide hacer pública la valoración económica de nadie."""
    filas = (
        await session.execute(sponsors_repository.public_sponsors_query(organization_id, event_id))
    ).all()
    if not filas:
        return []

    almacen = get_storage()
    grupos: dict[uuid.UUID, PublicSponsorTier] = {}
    orden: list[uuid.UUID] = []
    for patrocinador, nivel in filas:
        if nivel.id not in grupos:
            grupos[nivel.id] = PublicSponsorTier(
                name=nivel.name, logo_size=nivel.logo_size, sponsors=[]
            )
            orden.append(nivel.id)
        grupos[nivel.id].sponsors.append(
            PublicSponsor(
                id=str(patrocinador.id),
                name=patrocinador.name,
                logo_url=almacen.public_url(patrocinador.logo_object_key)
                if patrocinador.logo_object_key
                else None,
                website=patrocinador.website,
                contribution_type=patrocinador.contribution_type,
                contribution_description=patrocinador.contribution_description,
            )
        )
    return [grupos[tier_id] for tier_id in orden]


@router.get(
    "/events/{slug}",
    summary="Ver el detalle de un evento publicado",
    response_model=PublicEventDetail,
    dependencies=[limit_per_ip("public-event-detail", PUBLICO_POR_IP)],
)
async def get_public_event(
    evento: Annotated[Event, Depends(_obtener_evento_publico_o_404)], session: SessionDep
) -> PublicEventDetail:
    sesiones = await _sesiones_publicas(session, evento.organization_id, evento.id)
    sedes = await _sedes_publicas(session, evento.organization_id, evento.id)
    niveles_con_patrocinadores = await _sponsor_tiers_publicos(
        session, evento.organization_id, evento.id
    )
    reservadas = await registrations_repository.count_reserved_registrations(
        session, evento.organization_id, evento.id
    )
    tema = await _tema_del_evento(session, evento)
    precio = None
    if evento.registration_mode == "paid":
        precios = await payments_service.get_min_public_prices(
            session, organization_id=evento.organization_id, event_ids=[evento.id]
        )
        precio = precios.get(evento.id)
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
        registration_opens_at=evento.registration_opens_at,
        reserved_count=reservadas,
        price_from_cents=precio.tipo.price_cents if precio else None,
        price_currency=precio.tipo.currency if precio else None,
        price_multiple=precio.varios_precios if precio else False,
        latitude=float(evento.latitude) if evento.latitude is not None else None,
        longitude=float(evento.longitude) if evento.longitude is not None else None,
        theme=tema,
        sessions=sesiones,
        venues=sedes,
        sponsor_tiers=niveles_con_patrocinadores,
    )


@router.get(
    "/events/{slug}/sponsors/{sponsor_id}",
    summary="Ver la ficha pública de un patrocinador",
    description=(
        "Anidado bajo el evento, mismo criterio que la sesión: exige "
        "`published` + `public` además de que el patrocinador pertenezca a "
        "este evento. Nunca lleva el importe de la aportación (ver "
        "`PublicSponsor`)."
    ),
    response_model=PublicSponsorDetail,
    dependencies=[limit_per_ip("public-sponsor-detail", PUBLICO_POR_IP)],
)
async def get_public_sponsor(
    evento: Annotated[Event, Depends(_obtener_evento_publico_o_404)],
    session: SessionDep,
    sponsor_id: str,
) -> PublicSponsorDetail:
    try:
        id_patrocinador = uuid.UUID(sponsor_id)
    except ValueError as exc:
        raise NotFoundError("El patrocinador no existe.") from exc

    patrocinador = await sponsors_repository.get_sponsor(
        session, evento.organization_id, evento.id, id_patrocinador
    )
    if patrocinador is None:
        raise NotFoundError("El patrocinador no existe.")

    nivel = await sponsors_repository.get_tier(
        session, evento.organization_id, patrocinador.tier_id
    )
    if nivel is None:
        raise NotFoundError("El patrocinador no existe.")

    filas_historial = (
        await session.execute(
            sponsors_repository.public_sponsor_history_query(
                evento.organization_id, patrocinador.name, evento.id
            )
        )
    ).all()

    almacen = get_storage()
    return PublicSponsorDetail(
        id=str(patrocinador.id),
        name=patrocinador.name,
        logo_url=almacen.public_url(patrocinador.logo_object_key)
        if patrocinador.logo_object_key
        else None,
        website=patrocinador.website,
        contribution_type=patrocinador.contribution_type,  # type: ignore[arg-type]
        contribution_description=patrocinador.contribution_description,
        tier_name=nivel.name,
        tier_benefits=nivel.benefits,
        event_slug=evento.slug,
        event_title=evento.title,
        history=[
            PublicSponsorHistoryItem(
                event_slug=otro_evento.slug,
                event_title=otro_evento.title,
                starts_at=otro_evento.starts_at,
                tier_name=otro_nivel.name,
            )
            for otro_evento, otro_nivel in filas_historial
        ],
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
    session: SessionDep,
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
        venue_id=str(sesion.venue_id) if sesion.venue_id else None,
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
    public_slug: str, session: SessionDep
) -> PublicSpeakerProfile:
    # `public_slug` es único en toda la instalación desde la fase 0: la
    # organización se resuelve desde el propio perfil, no por host
    # (`app_resolve_speaker_organization`, SECURITY DEFINER de alcance mínimo).
    organization_id = await session.scalar(
        text("SELECT app_resolve_speaker_organization(:slug)"), {"slug": public_slug}
    )
    if organization_id is None:
        raise NotFoundError("El ponente no existe.")
    await set_organization_context(session, organization_id)

    perfil = await session.scalar(
        select(SpeakerPublicProfile).where(
            SpeakerPublicProfile.organization_id == organization_id,
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
        session, organization_id, perfil.user_id, only_published_public=True
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
