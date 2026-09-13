"""Invitación de ponente desde el evento — fase 3 del plan de invitaciones.

Comparte todo el mecanismo de la fase 1; lo que añade es el `event_id` y el
alta en el roster (`event_members`), idempotente y en la misma transacción
que la membresía.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.database import SessionMaintenance
from app.core.permissions import Permission
from app.core.security import hash_password
from app.modules.events.models import Event, EventMember
from app.modules.organizations import invitations_service
from app.modules.organizations.models import OrganizationMember
from app.modules.roles.models import Role
from app.modules.roles.system_roles import SPEAKER
from app.modules.users.models import User
from tests.conftest import OrganizacionDePrueba, crear_miembro, iniciar_sesion

EVENTS = "/api/v1/events"
CONTRASENA_ACEPTAR = "Acepta-Esta-Invitacion-1!"

AHORA = datetime.now(UTC).replace(microsecond=0)


def _payload_evento(slug: str = "iawic-2026") -> dict:
    return {
        "slug": slug,
        "title": "IA Week in Cascais 2026",
        "starts_at": AHORA.isoformat(),
        "ends_at": (AHORA + timedelta(days=2)).isoformat(),
        "location_mode": "in_person",
    }


async def _crear_evento(cliente: AsyncClient, cabeceras: dict[str, str], slug: str = "iawic-2026"):
    respuesta = await cliente.post(EVENTS, headers=cabeceras, json=_payload_evento(slug))
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


async def _role_id(organizacion: OrganizacionDePrueba, key: str) -> uuid.UUID:
    async with SessionMaintenance() as session:
        rol = await session.scalar(
            select(Role).where(Role.organization_id == organizacion.id, Role.key == key)
        )
        assert rol is not None, f"no existe el rol {key}"
        return rol.id


async def test_invitar_ponente_desde_evento_crea_invitacion_con_event_id_y_rol_speaker(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_evento(cliente, cabeceras)

    respuesta = await cliente.post(
        f"{EVENTS}/{evento['id']}/invitations",
        headers=cabeceras,
        json={"email": "nuevo-ponente@example.com"},
    )

    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["status"] == "invited"
    assert cuerpo["invitation"]["event_id"] == evento["id"]
    assert cuerpo["invitation"]["role_key"] == "speaker"


async def test_aceptar_invitacion_de_ponente_deja_en_organizacion_y_en_roster(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_evento(cliente, cabeceras)

    async with SessionMaintenance() as session:
        rol_speaker = await _role_id(organizacion, "speaker")
        resultado = await invitations_service.create_invitation(
            session,
            organization_id=organizacion.id,
            actor_id=organizacion.owner_id,
            actor_permissions=set(Permission),
            email="acepta-ponente@example.com",
            role_id=rol_speaker,
            event_id=uuid.UUID(evento["id"]),
        )
        await session.commit()
    assert resultado.token is not None
    token = resultado.token

    respuesta = await cliente.post(
        f"/api/v1/public/invitations/{token}/accept",
        json={"first_name": "Grace", "last_name": "Hopper", "password": CONTRASENA_ACEPTAR},
        headers={"Host": organizacion.host},
    )
    assert respuesta.status_code == 200, respuesta.text

    async with SessionMaintenance() as session:
        usuario = await session.scalar(
            select(User).where(User.email == "acepta-ponente@example.com")
        )
        assert usuario is not None

        miembro = await session.scalar(
            select(OrganizationMember).where(OrganizationMember.user_id == usuario.id)
        )
        assert miembro is not None

        en_roster = await session.scalar(
            select(EventMember).where(
                EventMember.event_id == uuid.UUID(evento["id"]),
                EventMember.organization_member_id == miembro.id,
            )
        )
        assert en_roster is not None


async def test_invitar_a_persona_con_cuenta_la_anade_al_roster_de_inmediato(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_evento(cliente, cabeceras)

    async with SessionMaintenance() as session:
        usuario = User(
            email="ya-tiene-cuenta-ponente@example.com",
            first_name="Ya",
            last_name="Tiene",
            password_hash=hash_password("una-contraseña-cualquiera"),
            is_active=True,
        )
        session.add(usuario)
        await session.commit()

    respuesta = await cliente.post(
        f"{EVENTS}/{evento['id']}/invitations",
        headers=cabeceras,
        json={"email": "ya-tiene-cuenta-ponente@example.com"},
    )
    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json()["status"] == "added"

    async with SessionMaintenance() as session:
        usuario = await session.scalar(
            select(User).where(User.email == "ya-tiene-cuenta-ponente@example.com")
        )
        assert usuario is not None
        miembro = await session.scalar(
            select(OrganizationMember).where(OrganizationMember.user_id == usuario.id)
        )
        assert miembro is not None
        en_roster = await session.scalar(
            select(EventMember).where(
                EventMember.event_id == uuid.UUID(evento["id"]),
                EventMember.organization_member_id == miembro.id,
            )
        )
        assert en_roster is not None  # sin esperar a ningún «aceptar»


async def test_el_alta_en_el_roster_es_idempotente(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_evento(cliente, cabeceras)
    ponente = await crear_miembro(organizacion, "speaker")

    async with SessionMaintenance() as session:
        await invitations_service._add_to_event_roster_if_needed(  # noqa: SLF001
            session,
            organization_id=organizacion.id,
            event_id=uuid.UUID(evento["id"]),
            organization_member_id=ponente.member_id,
        )
        await invitations_service._add_to_event_roster_if_needed(  # noqa: SLF001
            session,
            organization_id=organizacion.id,
            event_id=uuid.UUID(evento["id"]),
            organization_member_id=ponente.member_id,
        )
        await session.commit()

    async with SessionMaintenance() as session:
        filas = (
            await session.scalars(
                select(EventMember).where(
                    EventMember.event_id == uuid.UUID(evento["id"]),
                    EventMember.organization_member_id == ponente.member_id,
                )
            )
        ).all()
        assert len(filas) == 1


async def test_no_se_puede_invitar_a_un_evento_de_otra_organizacion(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    otra_organizacion: OrganizacionDePrueba,
) -> None:
    _, cabeceras_ajenas = await iniciar_sesion(cliente, otra_organizacion)
    evento_ajeno = await _crear_evento(cliente, cabeceras_ajenas, slug="evento-ajeno")

    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    respuesta = await cliente.post(
        f"{EVENTS}/{evento_ajeno['id']}/invitations",
        headers=cabeceras,
        json={"email": "quien-sea@example.com"},
    )
    assert respuesta.status_code == 404, respuesta.text


async def test_si_el_alta_en_roster_falla_la_membresia_no_queda_a_medias(
    organizacion: OrganizacionDePrueba,
) -> None:
    async with SessionMaintenance() as session:
        evento = Event(
            organization_id=organizacion.id,
            slug="evento-para-fallo",
            title="Evento",
            starts_at=AHORA,
            ends_at=AHORA + timedelta(days=1),
            location_mode="online",
        )
        session.add(evento)
        await session.flush()
        rol_speaker = await _role_id(organizacion, "speaker")
        resultado = await invitations_service.create_invitation(
            session,
            organization_id=organizacion.id,
            actor_id=organizacion.owner_id,
            actor_permissions=set(Permission),
            email="falla-roster@example.com",
            role_id=rol_speaker,
            event_id=evento.id,
        )
        await session.commit()
    assert resultado.token is not None
    token = resultado.token

    with patch(
        "app.modules.organizations.invitations_service._add_to_event_roster_if_needed",
        side_effect=RuntimeError("fallo simulado del roster"),
    ):
        async with SessionMaintenance() as session:
            with pytest.raises(RuntimeError):
                await invitations_service.accept_invitation(
                    session,
                    token=token,
                    first_name="Falla",
                    last_name="Roster",
                    password=CONTRASENA_ACEPTAR,
                )
            # Sin commit: como en una petición real, una excepción no confirma nada.

    async with SessionMaintenance() as session:
        usuario = await session.scalar(select(User).where(User.email == "falla-roster@example.com"))
        assert usuario is not None
        assert usuario.password_hash is None
        miembro = await session.scalar(
            select(OrganizationMember).where(OrganizationMember.user_id == usuario.id)
        )
        assert miembro is None


def test_la_ficha_del_ponente_no_gana_campos_nuevos() -> None:
    """Regla de la fase 3: la ficha de `speaker` ya cubre lo que hace falta;
    cualquier campo nuevo tiene que justificarse aparte."""
    claves = {campo.key for campo in SPEAKER.profile_fields}
    assert claves == {"bio", "titular", "empresa", "curriculum", "web", "contacto"}
    (bio,) = [c for c in SPEAKER.profile_fields if c.key == "bio"]
    assert bio.is_required is True
