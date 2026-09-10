"""Datos de prueba para la verificación manual de la fase 4 (sistema de diseño).

No es una migración ni un cambio de esquema: siembra filas de desarrollo sobre
el evento de pago E2E ya existente (`evento-pago-ec519f22`) y crea un segundo
evento gratuito, para poder recorrer a mano portada → listado → evento →
sesión → ponente → inscripción → (retorno de pago | correo real) → entrada,
en los dos temas y a distintos anchos.

Idempotente por diseño (mismo patrón que `app/seed/demo.py`): cada paso busca
por su clave natural (slug, email, nombre) antes de crear, así que se puede
ejecutar tantas veces como haga falta sin duplicar filas. El único efecto que
varía entre ejecuciones es el token de autocancelación que se imprime al
final (`generate_token` no es determinista, y cada llamada genera un token
nuevo válido — no se guarda ninguna fila nueva por ello).

Uso:
    python -m scripts.seed_manual_qa
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import maintenance_session
from app.core.security import hash_password
from app.modules.auth.verification import PROPOSITO_CANCELACION_INSCRIPCION, generate_token
from app.modules.events import repository as events_repository
from app.modules.events import service as events_service
from app.modules.events.models import (
    Event,
    EventMember,
    EventSession,
    EventSessionParticipant,
    SpeakerPublicProfile,
)
from app.modules.organizations.models import Organization, OrganizationMember
from app.modules.payments import service as payments_service
from app.modules.payments.models import EventPayment, EventTicketType
from app.modules.registrations.models import EventRegistration, EventRegistrationConsent
from app.modules.roles.models import Role
from app.modules.tickets.models import EventTicket
from app.modules.tickets.service import emitir_entrada
from app.modules.users.models import User

ORG_SLUG = "iawic"

EVENT_PAGO_SLUG = "evento-pago-ec519f22"
EVENT_GRATIS_SLUG = "ia-week-meetup-comunidad"

SPEAKER_EMAIL = "elena.ruiz.speaker@example.test"
ASISTENTE_EMAIL = "laura.martinez.qa@example.test"

# TTL largo a propósito: es un token de un solo enlace de QA manual, no el de
# producción (`registration_cancel_token_ttl_days`), y una verificación manual
# puede alargarse varios días.
TTL_TOKEN_QA = timedelta(days=30)


async def _get_or_create_speaker(
    session: AsyncSession, *, organization_id: uuid.UUID, speaker_role_id: uuid.UUID
) -> tuple[User, OrganizationMember, SpeakerPublicProfile]:
    usuario = await session.scalar(select(User).where(User.email == SPEAKER_EMAIL))
    if usuario is None:
        usuario = User(
            email=SPEAKER_EMAIL,
            password_hash=hash_password(str(uuid.uuid4())),
            first_name="Elena",
            last_name="Ruiz",
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
                "bio": (
                    "Investigadora en sistemas de recomendación y aprendizaje "
                    "automático aplicado. Ponente habitual en congresos de IA "
                    "en España, con foco en llevar modelos de investigación a "
                    "producción de forma responsable."
                ),
                "titular": "Directora de Ingeniería de IA",
                "empresa": "Nébula Data Labs",
                "web": "https://elenaruiz.example.test",
                "contacto": "elena.ruiz.speaker@example.test",
            },
        )
        session.add(miembro)
        await session.flush()

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
            public_slug="elena-ruiz",
            source_organization_member_id=miembro.id,
        )
        session.add(perfil)
        await session.flush()

    return usuario, miembro, perfil


async def _get_or_create_event_member(
    session: AsyncSession, *, organization_id: uuid.UUID, event_id: uuid.UUID, member: OrganizationMember
) -> EventMember:
    existente = await events_repository.get_event_member_by_organization_member(
        session, organization_id, event_id, member.id
    )
    if existente is not None:
        return existente
    nuevo = EventMember(
        event_id=event_id, organization_id=organization_id, organization_member_id=member.id
    )
    session.add(nuevo)
    await session.flush()
    return nuevo


async def _get_or_create_session(
    session: AsyncSession, *, organization_id: uuid.UUID, event_id: uuid.UUID, titulo: str, datos: dict
) -> EventSession:
    existente = await session.scalar(
        select(EventSession).where(
            EventSession.organization_id == organization_id,
            EventSession.event_id == event_id,
            EventSession.title == titulo,
        )
    )
    if existente is not None:
        return existente
    return await events_service.create_session(
        session, organization_id=organization_id, event_id=event_id, datos={"title": titulo, **datos}
    )


async def _get_or_create_participant(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    session_id: uuid.UUID,
    event_member_id: uuid.UUID,
    role_key: str,
) -> EventSessionParticipant:
    existente = await session.scalar(
        select(EventSessionParticipant).where(
            EventSessionParticipant.session_id == session_id,
            EventSessionParticipant.event_member_id == event_member_id,
            EventSessionParticipant.role_key == role_key,
        )
    )
    if existente is not None:
        return existente
    nuevo = EventSessionParticipant(
        session_id=session_id,
        event_member_id=event_member_id,
        organization_id=organization_id,
        role_key=role_key,
    )
    session.add(nuevo)
    await session.flush()
    return nuevo


async def _get_or_create_ticket_type(
    session: AsyncSession, *, organization_id: uuid.UUID, event_id: uuid.UUID, nombre: str, datos: dict
) -> EventTicketType:
    existente = await session.scalar(
        select(EventTicketType).where(
            EventTicketType.organization_id == organization_id,
            EventTicketType.event_id == event_id,
            EventTicketType.name == nombre,
        )
    )
    if existente is not None:
        return existente
    return await payments_service.create_ticket_type(
        session, organization_id=organization_id, event_id=event_id, datos={"name": nombre, **datos}
    )


async def _sembrar_evento_de_pago(
    session: AsyncSession, *, organizacion: Organization, speaker_role_id: uuid.UUID
) -> dict:
    evento = await session.scalar(
        select(Event).where(Event.organization_id == organizacion.id, Event.slug == EVENT_PAGO_SLUG)
    )
    if evento is None:
        raise RuntimeError(
            f"No existe el evento «{EVENT_PAGO_SLUG}» en la organización «{ORG_SLUG}»: "
            "este script asume que ya lo creó el trabajo previo de la fase 6 del PRD."
        )

    _usuario, miembro, perfil = await _get_or_create_speaker(
        session, organization_id=organizacion.id, speaker_role_id=speaker_role_id
    )
    miembro_evento = await _get_or_create_event_member(
        session, organization_id=organizacion.id, event_id=evento.id, member=miembro
    )

    sesion_presencial = await _get_or_create_session(
        session,
        organization_id=organizacion.id,
        event_id=evento.id,
        titulo="Del laboratorio a producción: MLOps para equipos pequeños",
        datos={
            "session_type": "talk",
            "description": (
                "Cómo llevar un modelo de un notebook a un sistema en producción "
                "con monitorización, reentrenamiento y control de coste, sin un "
                "equipo de plataforma dedicado. Caso real de IA Week Valencia."
            ),
            "starts_at": datetime(2027, 1, 15, 10, 30, tzinfo=UTC),
            "ends_at": datetime(2027, 1, 15, 11, 30, tzinfo=UTC),
            "room": "Auditorio Principal",
        },
    )
    sesion_online = await _get_or_create_session(
        session,
        organization_id=organizacion.id,
        event_id=evento.id,
        titulo="Mesa redonda online: retos legales de la IA generativa en Europa",
        datos={
            "session_type": "talk",
            "description": (
                "Sesión retransmitida en directo sobre el Reglamento de IA de la "
                "UE, propiedad intelectual y protección de datos aplicados a "
                "productos con modelos generativos."
            ),
            "starts_at": datetime(2027, 1, 15, 12, 0, tzinfo=UTC),
            "ends_at": datetime(2027, 1, 15, 13, 0, tzinfo=UTC),
            "video_platform": "youtube",
            "video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        },
    )

    for sesion in (sesion_presencial, sesion_online):
        await _get_or_create_participant(
            session,
            organization_id=organizacion.id,
            session_id=sesion.id,
            event_member_id=miembro_evento.id,
            role_key="speaker",
        )

    tipo_general = await _get_or_create_ticket_type(
        session,
        organization_id=organizacion.id,
        event_id=evento.id,
        nombre="General",
        datos={
            "description": "Acceso completo a todas las sesiones del evento.",
            "price_cents": 2500,
            "currency": "eur",
            "sort_order": 0,
        },
    )
    await _get_or_create_ticket_type(
        session,
        organization_id=organizacion.id,
        event_id=evento.id,
        nombre="VIP",
        datos={
            "description": "Acceso completo + zona VIP y encuentro con ponentes.",
            "price_cents": 6000,
            "currency": "eur",
            "sort_order": 1,
        },
    )

    inscripcion = await session.scalar(
        select(EventRegistration).where(
            EventRegistration.event_id == evento.id, EventRegistration.email == ASISTENTE_EMAIL
        )
    )
    if inscripcion is None:
        ahora = datetime.now(UTC)
        inscripcion = EventRegistration(
            event_id=evento.id,
            organization_id=organizacion.id,
            email=ASISTENTE_EMAIL,
            full_name="Laura Martínez",
            status="confirmed",
            ticket_type_id=tipo_general.id,
            verified_at=ahora,
            confirmed_at=ahora,
        )
        session.add(inscripcion)
        await session.flush()
        session.add(
            EventRegistrationConsent(
                registration_id=inscripcion.id,
                organization_id=organizacion.id,
                data_processing_accepted_at=ahora,
                marketing_accepted_at=None,
                recording_accepted_at=None,
            )
        )
        await session.flush()

    pago = await session.scalar(
        select(EventPayment).where(EventPayment.registration_id == inscripcion.id)
    )
    if pago is None:
        ahora = datetime.now(UTC)
        pago = EventPayment(
            organization_id=organizacion.id,
            event_id=evento.id,
            registration_id=inscripcion.id,
            # Placeholder de QA manual: no hay cuenta Stripe conectada en este
            # entorno (`organization_stripe_accounts` vacía), y esta columna no
            # lleva FK — solo identifica bajo qué cuenta se cobró un pago real.
            stripe_account_id="acct_seed_manual_qa",
            ticket_type_id=tipo_general.id,
            amount_cents=tipo_general.price_cents,
            discount_cents=0,
            currency=tipo_general.currency,
            status="paid",
            paid_at=ahora,
        )
        session.add(pago)
        await session.flush()

    ticket = await emitir_entrada(session, inscripcion)
    token_mi_entrada = await generate_token(
        PROPOSITO_CANCELACION_INSCRIPCION, str(inscripcion.id), ttl=TTL_TOKEN_QA
    )

    return {
        "evento": evento,
        "sesion_presencial": sesion_presencial,
        "sesion_online": sesion_online,
        "ponente_slug": perfil.public_slug,
        "inscripcion": inscripcion,
        "ticket": ticket,
        "token_mi_entrada": token_mi_entrada,
    }


async def _sembrar_evento_gratuito(
    session: AsyncSession, *, organizacion: Organization, speaker_role_id: uuid.UUID
) -> dict:
    evento = await events_repository.get_event_by_slug(session, organizacion.id, EVENT_GRATIS_SLUG)
    if evento is None:
        evento = await events_service.create_event(
            session,
            organization_id=organizacion.id,
            datos={
                "slug": EVENT_GRATIS_SLUG,
                "title": "IA Week Meetup: comunidad y networking",
                "summary": (
                    "Encuentro gratuito y abierto de la comunidad de IA Week "
                    "Valencia: una charla corta y espacio de networking."
                ),
                "description": (
                    "Meetup mensual gratuito de IA Week Valencia. Sin coste de "
                    "entrada: solo hace falta inscribirse y confirmar el correo "
                    "para reservar plaza. Habrá una charla breve y tiempo para "
                    "conectar con otras personas de la comunidad."
                ),
                "status": "published",
                "visibility": "public",
                "timezone": "Europe/Madrid",
                "starts_at": datetime(2027, 2, 5, 18, 0, tzinfo=UTC),
                "ends_at": datetime(2027, 2, 5, 20, 30, tzinfo=UTC),
                "location_mode": "in_person",
                "location_name": "Espacio Rambleta",
                "location_address": "Carrer de la Ribera, 46003 València",
                "city": "Valencia",
                "capacity": None,
                "registration_mode": "free",
            },
        )

    _usuario, miembro, perfil = await _get_or_create_speaker(
        session, organization_id=organizacion.id, speaker_role_id=speaker_role_id
    )
    miembro_evento = await _get_or_create_event_member(
        session, organization_id=organizacion.id, event_id=evento.id, member=miembro
    )
    sesion = await _get_or_create_session(
        session,
        organization_id=organizacion.id,
        event_id=evento.id,
        titulo="Lightning talk: qué ha cambiado en un año de IA generativa",
        datos={
            "session_type": "talk",
            "description": (
                "Repaso rápido y sin tecnicismos de los cambios más relevantes "
                "del último año en modelos generativos, pensado para abrir la "
                "conversación del meetup."
            ),
            "starts_at": datetime(2027, 2, 5, 18, 15, tzinfo=UTC),
            "ends_at": datetime(2027, 2, 5, 18, 45, tzinfo=UTC),
            "room": "Sala principal",
        },
    )
    await _get_or_create_participant(
        session,
        organization_id=organizacion.id,
        session_id=sesion.id,
        event_member_id=miembro_evento.id,
        role_key="speaker",
    )

    return {"evento": evento, "sesion": sesion, "ponente_slug": perfil.public_slug}


async def main() -> None:
    settings = get_settings()
    async with maintenance_session() as session:
        organizacion = await session.scalar(select(Organization).where(Organization.slug == ORG_SLUG))
        if organizacion is None:
            raise RuntimeError(
                f"No existe la organización «{ORG_SLUG}»: ejecuta primero "
                "`python -m app.cli seed`."
            )

        rol_speaker = await session.scalar(
            select(Role).where(Role.organization_id == organizacion.id, Role.key == "speaker")
        )
        if rol_speaker is None:
            raise RuntimeError(
                f"La organización «{ORG_SLUG}» no tiene el rol de sistema «speaker» "
                "clonado: revisa `clone_system_roles`."
            )

        pago = await _sembrar_evento_de_pago(
            session, organizacion=organizacion, speaker_role_id=rol_speaker.id
        )
        gratis = await _sembrar_evento_gratuito(
            session, organizacion=organizacion, speaker_role_id=rol_speaker.id
        )

    base = "http://localhost:4200"
    evento_pago = pago["evento"]
    evento_gratis = gratis["evento"]

    print("\n=== Datos de prueba para verificación manual (fase 4) ===\n")
    print(f"Base usada para las URLs impresas: {base}")
    print(
        f"Aviso: `web_base_url` de la API (usado por enlaces generados por el backend, "
        f"como el retorno de Stripe o los correos) es «{settings.web_base_url}», no "
        f"«{base}» — son puertos distintos (Caddy en 8080 vs. Angular dev server en "
        "4200) que en este entorno resuelven al mismo host `localhost` y por tanto "
        "funcionan ambos, pero si algo no carga al copiar un enlace de un correo, "
        "prueba a cambiar el puerto por 8080. No he tocado este valor.\n"
    )

    print("--- Navegación general ---")
    print(f"Portada:                 {base}/")
    print(f"Listado de eventos:      {base}/eventos")

    print("\n--- Evento de pago (ya confirmado, sin pasar por Stripe) ---")
    print(f"Ficha del evento:        {base}/eventos/{evento_pago.slug}")
    print(f"Sesión presencial:       {base}/eventos/{evento_pago.slug}/sesiones/{pago['sesion_presencial'].id}")
    print(f"Sesión online:           {base}/eventos/{evento_pago.slug}/sesiones/{pago['sesion_online'].id}")
    print(f"Ponente:                 {base}/ponentes/{pago['ponente_slug']}")
    print(
        "Retorno de pago (debe salir «confirmado»): "
        f"{base}/pago/retorno?registration_id={pago['inscripcion'].id}&slug={evento_pago.slug}"
    )
    print(f"Mi entrada (token real):  {base}/mi-entrada?token={pago['token_mi_entrada']}")
    print(
        "  (el token de «mi entrada» dura 30 días desde esta ejecución; si caduca, "
        "vuelve a ejecutar este script para generar uno nuevo — no duplica ninguna fila)"
    )

    print("\n--- Evento gratuito (inscríbete de verdad en el navegador) ---")
    print(f"Ficha del evento:        {base}/eventos/{evento_gratis.slug}")
    print(f"Sesión:                  {base}/eventos/{evento_gratis.slug}/sesiones/{gratis['sesion'].id}")
    print(f"Ponente:                 {base}/ponentes/{gratis['ponente_slug']}")
    print(f"Formulario de inscripción: {base}/eventos/{evento_gratis.slug}/inscribirse")
    print(
        "  Nota: este es el evento a rellenar de verdad en el navegador (no hay "
        "Stripe involucrado, es gratuito) — usa un correo cualquiera y revisa "
        "Mailpit para ver el correo real de verificación/confirmación: "
        "http://localhost:8025"
    )

    print("\n=== Fin ===\n")


if __name__ == "__main__":
    asyncio.run(main())
