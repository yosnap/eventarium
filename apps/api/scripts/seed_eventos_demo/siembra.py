"""Alta idempotente de una pieza de un evento de demostración.

Cada función busca por su clave natural (email, slug, nombre, título) antes de
crear, así que el seed se puede ejecutar tantas veces como haga falta sin
duplicar filas — mismo patrón que `app/seed/demo.py` y `seed_manual_qa.py`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import PropertyMock, patch
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import hash_password
from app.core.storage import build_object_key
from app.modules.events import repository as events_repository
from app.modules.events import service as events_service
from app.modules.events.models import (
    Event,
    EventMember,
    EventSession,
    EventSessionParticipant,
    EventVenue,
    SpeakerPublicProfile,
)
from app.modules.organizations.models import OrganizationMember
from app.modules.payments import repository as payments_repository
from app.modules.payments import service as payments_service
from app.modules.payments.models import EventTicketType
from app.modules.registrations.models import EventRegistration
from app.modules.sponsors import service as sponsors_service
from app.modules.sponsors.models import Sponsor, SponsorTier
from app.modules.users.models import User
from scripts.seed_eventos_demo.imagenes import _logo, _portada


async def _get_or_create_persona(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    speaker_role_id: uuid.UUID,
    datos: dict[str, Any],
) -> tuple[OrganizationMember, SpeakerPublicProfile | None]:
    """Usuario + membresía con rol de ponente + (si procede) perfil público."""
    usuario = await session.scalar(select(User).where(User.email == datos["email"]))
    if usuario is None:
        usuario = User(
            email=datos["email"],
            password_hash=hash_password(str(uuid.uuid4())),
            first_name=datos["first_name"],
            last_name=datos["last_name"],
            is_active=True,
            is_superadmin=False,
            email_verified_at=datetime.now(UTC),
        )
        session.add(usuario)
        await session.flush()

    miembro = await session.scalar(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.user_id == usuario.id,
            OrganizationMember.role_id == speaker_role_id,
        )
    )
    if miembro is None:
        miembro = OrganizationMember(
            organization_id=organization_id,
            user_id=usuario.id,
            role_id=speaker_role_id,
            profile_data={
                "bio": datos["bio"],
                "titular": datos["titular"],
                "empresa": datos["empresa"],
                "web": f"https://example.test/{datos['first_name'].lower()}",
                "contacto": datos["email"],
            },
        )
        session.add(miembro)
        await session.flush()

    if datos["slug"] is None:
        return miembro, None

    perfil = await session.scalar(
        select(SpeakerPublicProfile).where(
            SpeakerPublicProfile.organization_id == organization_id,
            SpeakerPublicProfile.user_id == usuario.id,
        )
    )
    if perfil is None:
        perfil = SpeakerPublicProfile(
            organization_id=organization_id,
            user_id=usuario.id,
            public_slug=datos["slug"],
            source_organization_member_id=miembro.id,
        )
        session.add(perfil)
        await session.flush()
    return miembro, perfil


def _local_a_utc(momento: datetime, zona: str) -> datetime:
    """El catálogo declara las fechas en la **hora local del evento** (es como las
    piensa quien organiza: «empieza a las 9:00»), aunque lleven `tzinfo=UTC` solo
    para ser conscientes de zona. Al persistir se reinterpretan en la zona del
    evento y se convierten a UTC, que es como se guardan en base de datos."""
    return momento.replace(tzinfo=ZoneInfo(zona)).astimezone(UTC)


async def _get_or_create_evento(
    session: AsyncSession, *, organization_id: uuid.UUID, spec: dict[str, Any]
) -> Event:
    """Alta idempotente del evento, siempre en borrador.

    Se crea en `draft` aunque el catálogo pida `published`: publicar un evento de
    pago exige cuenta de Stripe conectada, que no existe en este entorno, y además
    la guarda exige que el evento ya tenga un tipo de entrada vigente — cosa
    imposible mientras la fila no exista. Se publica después, en
    `_publicar_eventos_de_pago`.
    """
    evento = await events_repository.get_event_by_slug(session, organization_id, spec["slug"])
    if evento is not None:
        # Fila ya existente: si se quedó sin coordenadas (p. ej. porque se sembró
        # antes de que la tabla local cubriera su ciudad), se completan ahora sin
        # volver a tocar el resto del evento.
        if evento.geocoded_at is None and evento.location_address:
            await events_service._sincronizar_geocodificacion_evento(
                evento,
                location_mode=evento.location_mode,
                address=evento.location_address,
                direccion_anterior=None,
            )
            await session.flush()
        return evento

    zona = spec.get("timezone", "Europe/Madrid")
    return await events_service.create_event(
        session,
        organization_id=organization_id,
        datos={
            "slug": spec["slug"],
            "title": spec["title"],
            "summary": spec.get("summary"),
            "description": spec.get("description"),
            "status": "draft",
            "visibility": spec.get("visibility", "public"),
            "timezone": zona,
            "starts_at": _local_a_utc(spec["starts_at"], zona),
            "ends_at": _local_a_utc(spec["ends_at"], zona),
            "location_mode": spec["location_mode"],
            "location_name": spec.get("location_name"),
            "location_address": spec.get("location_address"),
            "city": spec.get("city"),
            "online_url": spec.get("online_url"),
            "capacity": spec.get("capacity"),
            "registration_mode": spec["registration_mode"],
            "registration_opens_at": (
                _local_a_utc(spec["registration_opens_at"], zona)
                if spec.get("registration_opens_at")
                else None
            ),
            "email_verification_required": False,
        },
    )


async def _get_or_create_sede(
    session: AsyncSession, *, organization_id: uuid.UUID, event_id: uuid.UUID, datos: dict[str, Any]
) -> uuid.UUID:
    """Sede del evento por nombre; devuelve su id."""
    existente = await session.scalar(
        select(EventVenue).where(
            EventVenue.organization_id == organization_id,
            EventVenue.event_id == event_id,
            EventVenue.name == datos["name"],
        )
    )
    if existente is not None:
        if existente.geocoded_at is None and existente.address:
            await events_service._sincronizar_geocodificacion_sede(
                existente, address=existente.address, direccion_anterior=None
            )
            await session.flush()
        return existente.id
    sede = await events_service.create_venue(
        session,
        organization_id=organization_id,
        event_id=event_id,
        datos={
            "name": datos["name"],
            "address": datos.get("address"),
            "capacity": datos.get("capacity"),
        },
    )
    return sede.id


async def _get_or_create_sesion(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    spec: dict[str, Any],
    inicio_evento: datetime,
    zona: str,
    venue_id: uuid.UUID | None,
) -> EventSession:
    existente = await session.scalar(
        select(EventSession).where(
            EventSession.organization_id == organization_id,
            EventSession.event_id == event_id,
            EventSession.title == spec["title"],
        )
    )
    if existente is not None:
        return existente

    dias, hora, minuto, duracion_horas, duracion_minutos = spec["starts_offset"]
    inicio = _inicio_de_sesion(inicio_evento, dias, hora, minuto, zona)
    fin = inicio + timedelta(hours=duracion_horas, minutes=duracion_minutos)
    return await events_service.create_session(
        session,
        organization_id=organization_id,
        event_id=event_id,
        datos={
            "session_type": spec["session_type"],
            "title": spec["title"],
            "description": spec.get("description"),
            "starts_at": inicio,
            "ends_at": fin,
            "room": spec.get("room"),
            "venue_id": str(venue_id) if venue_id is not None else None,
            "video_platform": spec.get("video_platform"),
            "video_url": spec.get("video_url"),
            "materials": spec.get("materials", []),
            "sort_order": datos_orden(spec),
        },
    )


def datos_orden(spec: dict[str, Any]) -> int:
    """`sort_order` derivado de la posición temporal de la sesión, para que la
    agenda quede ordenada sin declarar el campo a mano."""
    dias, hora, minuto, _, _ = spec["starts_offset"]
    return dias * 1440 + hora * 60 + minuto


def _inicio_de_sesion(
    inicio_evento: datetime, dias: int, hora: int, minuto: int, zona: str
) -> datetime:
    """`starts_offset` es (día, hora, minuto) en la **zona del evento**, no un
    desplazamiento desde `inicio_evento`: una sesión del día 2 a las 10:00 es eso,
    las diez de la mañana, no «inicio del evento + 2 días + 10 horas». Se toma el
    día natural del evento en su zona, se fija la hora pedida y se convierte a
    UTC, que es como se guarda (`DateTime(timezone=True)`)."""
    tz = ZoneInfo(zona)
    dia = (inicio_evento.astimezone(tz) + timedelta(days=dias)).date()
    return datetime(dia.year, dia.month, dia.day, hora, minuto, tzinfo=tz).astimezone(UTC)


async def _get_or_create_miembro_evento(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    organization_member_id: uuid.UUID,
) -> EventMember:
    existente = await events_repository.get_event_member_by_organization_member(
        session, organization_id, event_id, organization_member_id
    )
    if existente is not None:
        return existente
    return await events_service.add_event_member(
        session,
        organization_id=organization_id,
        event_id=event_id,
        organization_member_id=organization_member_id,
    )


async def _get_or_create_participante(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    session_id: uuid.UUID,
    event_member_id: uuid.UUID,
    role_key: str,
    sort_order: int,
) -> None:
    existente = await session.scalar(
        select(EventSessionParticipant).where(
            EventSessionParticipant.session_id == session_id,
            EventSessionParticipant.event_member_id == event_member_id,
            EventSessionParticipant.role_key == role_key,
        )
    )
    if existente is not None:
        return
    session.add(
        EventSessionParticipant(
            session_id=session_id,
            event_member_id=event_member_id,
            organization_id=organization_id,
            role_key=role_key,
            sort_order=sort_order,
        )
    )
    await session.flush()


async def _get_or_create_ticket_type(
    session: AsyncSession, *, organization_id: uuid.UUID, event_id: uuid.UUID, datos: dict[str, Any]
) -> None:
    existente = await session.scalar(
        select(EventTicketType).where(
            EventTicketType.organization_id == organization_id,
            EventTicketType.event_id == event_id,
            EventTicketType.name == datos["name"],
        )
    )
    if existente is not None:
        return
    await payments_service.create_ticket_type(
        session,
        organization_id=organization_id,
        event_id=event_id,
        datos={
            "name": datos["name"],
            "description": datos.get("description"),
            "price_cents": datos["price_cents"],
            "currency": "eur",
            "sort_order": datos.get("sort_order", 0),
        },
    )


async def _get_or_create_tier(
    session: AsyncSession, *, organization_id: uuid.UUID, nombre: str, logo_size: str, orden: int
) -> uuid.UUID:
    existente = await session.scalar(
        select(SponsorTier).where(
            SponsorTier.organization_id == organization_id, SponsorTier.name == nombre
        )
    )
    if existente is not None:
        return existente.id
    nivel = await sponsors_service.create_tier(
        session,
        organization_id=organization_id,
        datos={"name": nombre, "logo_size": logo_size, "display_order": orden},
    )
    return nivel.id


async def _sembrar_patrocinadores(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    evento: Event,
    lista: list[dict[str, Any]],
    almacen: Any,
) -> None:
    for entrada in lista:
        nombre_tier, logo_size, orden = entrada["tier"]
        tier_id = await _get_or_create_tier(
            session,
            organization_id=organization_id,
            nombre=nombre_tier,
            logo_size=logo_size,
            orden=orden,
        )

        patrocinador = await session.scalar(
            select(Sponsor).where(
                Sponsor.organization_id == organization_id,
                Sponsor.event_id == evento.id,
                Sponsor.name == entrada["nombre"],
            )
        )
        if patrocinador is None:
            patrocinador = await sponsors_service.create_sponsor(
                session,
                organization_id=organization_id,
                event_id=evento.id,
                datos={
                    "tier_id": tier_id,
                    "name": entrada["nombre"],
                    "website": entrada.get("website"),
                    "contribution_type": "monetaria",
                    "contribution_amount": Decimal("1000.00"),
                },
            )

        if entrada.get("logo") and patrocinador.logo_object_key is None:
            clave = build_object_key(organization_id, f"sponsors/{patrocinador.id}/logo", "png")
            await almacen.put_object(clave, _logo(entrada["nombre"]), "image/png")
            patrocinador.logo_object_key = clave
            await session.flush()


async def _poner_portada(
    session: AsyncSession, *, organization_id: uuid.UUID, evento: Event, almacen: Any
) -> None:
    if evento.cover_object_key is not None:
        return
    clave = build_object_key(organization_id, f"events/{evento.id}/cover", "png")
    await almacen.put_object(clave, _portada(evento.slug), "image/png")
    evento.cover_object_key = clave
    await session.flush()


async def _sembrar_inscripciones(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    evento: Event,
    lista: list[tuple[str, str]],
) -> None:
    """Inscripciones confirmadas para dar `reserved_count` real en el listado."""
    for email, nombre in lista:
        existente = await session.scalar(
            select(EventRegistration).where(
                EventRegistration.event_id == evento.id, EventRegistration.email == email
            )
        )
        if existente is not None:
            continue
        ahora = datetime.now(UTC)
        session.add(
            EventRegistration(
                event_id=evento.id,
                organization_id=organization_id,
                email=email,
                full_name=nombre,
                status="confirmed",
                verified_at=ahora,
                confirmed_at=ahora,
            )
        )
        await session.flush()


async def _publicar_eventos(
    session: AsyncSession, *, organization_id: uuid.UUID, eventos: list[Event]
) -> None:
    """Publica todos los eventos del catálogo, relajando solo la guarda de Stripe.

    Todos nacen en `draft` (ver `_get_or_create_evento`). Publicar un evento `paid`
    exige, con razón, una cuenta de Stripe conectada y verificada, que no existe en
    este entorno; aquí es un seed de demo, así que durante estas llamadas se
    simula **solo** la existencia de la cuenta (`payments_repository.
    get_cuenta_activa`) y la configuración de Stripe (`payments_enabled`). El resto
    de la guarda — que un evento `paid` tenga al menos un tipo de entrada vigente —
    se sigue evaluando y es real: si el catálogo dejara un `paid` sin tipos
    vigentes, esto falla, que es lo correcto.

    `demo-oculto` se publica igual: es `visibility="hidden"`, así que debe existir
    pero no aparecer ni en el listado ni en la ficha.
    """

    class _CuentaSimulada:
        charges_enabled = True

    async def _cuenta_activa(_session: AsyncSession, _organization_id: uuid.UUID) -> Any:
        return _CuentaSimulada()

    settings = get_settings()
    with (
        patch.object(
            type(settings), "payments_enabled", new_callable=PropertyMock, return_value=True
        ),
        patch.object(payments_repository, "get_cuenta_activa", _cuenta_activa),
    ):
        for evento in eventos:
            if evento.status == "published":
                continue
            await events_service.update_event(
                session,
                organization_id=organization_id,
                event_id=evento.id,
                datos={"status": "published"},
            )


async def _sembrar_evento(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    spec: dict[str, Any],
    personas: dict[str, tuple[OrganizationMember, SpeakerPublicProfile | None]],
    almacen: Any,
) -> Event:
    evento = await _get_or_create_evento(session, organization_id=organization_id, spec=spec)

    # Sedes primero: las sesiones pueden referenciarlas por índice.
    ids_sedes = [
        await _get_or_create_sede(
            session, organization_id=organization_id, event_id=evento.id, datos=sede
        )
        for sede in spec.get("sedes", [])
    ]

    for tipo in spec.get("ticket_types", []):
        await _get_or_create_ticket_type(
            session, organization_id=organization_id, event_id=evento.id, datos=tipo
        )

    for spec_sesion in spec.get("sesiones", []):
        venue_index = spec_sesion.get("venue_index")
        venue_id = ids_sedes[venue_index] if venue_index is not None else None
        sesion = await _get_or_create_sesion(
            session,
            organization_id=organization_id,
            event_id=evento.id,
            spec=spec_sesion,
            inicio_evento=_local_a_utc(spec["starts_at"], spec.get("timezone", "Europe/Madrid")),
            zona=spec.get("timezone", "Europe/Madrid"),
            venue_id=venue_id,
        )
        for orden, (email, rol) in enumerate(spec_sesion.get("ponentes", [])):
            miembro_org, _ = personas[email]
            miembro_evento = await _get_or_create_miembro_evento(
                session,
                organization_id=organization_id,
                event_id=evento.id,
                organization_member_id=miembro_org.id,
            )
            await _get_or_create_participante(
                session,
                organization_id=organization_id,
                session_id=sesion.id,
                event_member_id=miembro_evento.id,
                role_key=rol,
                sort_order=orden,
            )

    await _sembrar_patrocinadores(
        session,
        organization_id=organization_id,
        evento=evento,
        lista=spec.get("patrocinadores", []),
        almacen=almacen,
    )

    if spec.get("inscripciones"):
        await _sembrar_inscripciones(
            session, organization_id=organization_id, evento=evento, lista=spec["inscripciones"]
        )

    if spec.get("portada"):
        await _poner_portada(
            session, organization_id=organization_id, evento=evento, almacen=almacen
        )

    return evento
