"""Aislamiento entre organizaciones para las tablas de eventos, agenda y ponentes.

Dos comprobaciones por tabla: que una organización no **lee** filas de otra
(RLS) y, para las tablas hijas, que tampoco puede **escribir** una fila propia
que apunte al recurso padre de otra organización (las FK compuestas contra
`(id, organization_id)`, no la política RLS, son las que lo impiden — la
integridad referencial de PostgreSQL no pasa por RLS).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.database import SessionApp, SessionMaintenance, set_organization_context
from app.modules.events.models import (
    Event,
    EventMember,
    EventSession,
    EventSessionParticipant,
    SpeakerPublicProfile,
)
from app.modules.organizations.repository import unsafe_select_all
from tests.conftest import OrganizacionDePrueba

TABLAS_CON_ORGANIZACION = (Event, EventSession, EventMember, EventSessionParticipant)

AHORA = datetime.now(UTC)


class DatosDePrueba:
    """IDs de un evento, sesión, miembro y participante ya creados para una org."""

    __slots__ = ("event_id", "session_id", "event_member_id")

    def __init__(self, *, event_id: uuid.UUID, session_id: uuid.UUID, event_member_id: uuid.UUID):
        self.event_id = event_id
        self.session_id = session_id
        self.event_member_id = event_member_id


async def _crear_datos_de_prueba(organizacion: OrganizacionDePrueba) -> DatosDePrueba:
    """Crea evento, sesión, miembro de evento y participante bajo el rol de mantenimiento."""
    async with SessionMaintenance() as session:
        miembro_id = await session.scalar(
            text(
                "SELECT id FROM organization_members "
                "WHERE organization_id = :org_id AND user_id = :user_id"
            ),
            {"org_id": organizacion.id, "user_id": organizacion.owner_id},
        )
        assert miembro_id is not None

        evento = Event(
            organization_id=organizacion.id,
            slug=f"evento-{organizacion.slug}",
            title="Evento de prueba",
            status="published",
            visibility="public",
            starts_at=AHORA,
            ends_at=AHORA + timedelta(days=1),
            location_mode="online",
        )
        session.add(evento)
        await session.flush()

        sesion = EventSession(
            event_id=evento.id,
            organization_id=organizacion.id,
            session_type="talk",
            title="Charla de prueba",
            starts_at=AHORA,
            ends_at=AHORA + timedelta(hours=1),
        )
        session.add(sesion)
        await session.flush()

        miembro_evento = EventMember(
            event_id=evento.id,
            organization_id=organizacion.id,
            organization_member_id=miembro_id,
        )
        session.add(miembro_evento)
        await session.flush()

        participante = EventSessionParticipant(
            session_id=sesion.id,
            event_member_id=miembro_evento.id,
            organization_id=organizacion.id,
            role_key="speaker",
        )
        session.add(participante)

        perfil = SpeakerPublicProfile(
            organization_id=organizacion.id,
            user_id=organizacion.owner_id,
            public_slug=f"ponente-{organizacion.slug}",
            source_organization_member_id=miembro_id,
        )
        session.add(perfil)

        await session.commit()
        return DatosDePrueba(
            event_id=evento.id, session_id=sesion.id, event_member_id=miembro_evento.id
        )


@pytest.mark.parametrize("modelo", TABLAS_CON_ORGANIZACION)
async def test_una_sesion_solo_ve_las_filas_de_su_organizacion(
    organizacion: OrganizacionDePrueba,
    otra_organizacion: OrganizacionDePrueba,
    modelo: type,
) -> None:
    await _crear_datos_de_prueba(organizacion)
    await _crear_datos_de_prueba(otra_organizacion)

    async with SessionApp() as session:
        async with session.begin():
            await set_organization_context(session, organizacion.id)
            filas = await unsafe_select_all(session, modelo)

    assert filas, f"debería ver sus propias filas de {modelo.__tablename__}"
    ajenas = [f for f in filas if f.organization_id != organizacion.id]
    assert not ajenas, f"{modelo.__tablename__} filtró filas de otra organización"


async def test_speaker_public_profiles_esta_aislado_por_organizacion(
    organizacion: OrganizacionDePrueba, otra_organizacion: OrganizacionDePrueba
) -> None:
    await _crear_datos_de_prueba(organizacion)
    await _crear_datos_de_prueba(otra_organizacion)

    async with SessionApp() as session:
        async with session.begin():
            await set_organization_context(session, organizacion.id)
            filas = await unsafe_select_all(session, SpeakerPublicProfile)

    assert [f.organization_id for f in filas] == [organizacion.id]


async def test_no_se_puede_crear_una_sesion_de_un_evento_ajeno(
    organizacion: OrganizacionDePrueba, otra_organizacion: OrganizacionDePrueba
) -> None:
    """La FK compuesta rechaza una sesión cuyo `event_id` es de otra organización."""
    datos_ajenos = await _crear_datos_de_prueba(otra_organizacion)

    with pytest.raises(DBAPIError):
        async with SessionApp() as session:
            async with session.begin():
                await set_organization_context(session, organizacion.id)
                session.add(
                    EventSession(
                        event_id=datos_ajenos.event_id,
                        organization_id=organizacion.id,
                        session_type="talk",
                        title="Sesión intrusa",
                        starts_at=AHORA,
                        ends_at=AHORA + timedelta(hours=1),
                    )
                )
                await session.flush()

    async with SessionMaintenance() as session:
        encontrada = await session.scalar(
            text("SELECT count(*) FROM event_sessions WHERE title = 'Sesión intrusa'")
        )
    assert encontrada == 0


async def test_no_se_puede_asignar_un_miembro_ajeno_al_roster(
    organizacion: OrganizacionDePrueba, otra_organizacion: OrganizacionDePrueba
) -> None:
    """La FK compuesta rechaza un `event_member` cuyo evento es de otra organización."""
    datos_propios = await _crear_datos_de_prueba(organizacion)
    datos_ajenos = await _crear_datos_de_prueba(otra_organizacion)

    with pytest.raises(DBAPIError):
        async with SessionApp() as session:
            async with session.begin():
                await set_organization_context(session, organizacion.id)
                session.add(
                    EventSessionParticipant(
                        session_id=datos_propios.session_id,
                        event_member_id=datos_ajenos.event_member_id,
                        organization_id=organizacion.id,
                        role_key="moderator",
                    )
                )
                await session.flush()


async def test_quitar_del_roster_con_participaciones_activas_falla_por_integridad(
    organizacion: OrganizacionDePrueba,
) -> None:
    """Sin `ondelete` en `event_session_participants.event_member_id`: `RESTRICT`
    por defecto. El servicio de la fase 3 traduce esto a 409 antes de llegar aquí;
    esta prueba confirma que la base de datos también lo bloquea por su cuenta."""
    datos = await _crear_datos_de_prueba(organizacion)

    with pytest.raises(DBAPIError):
        async with SessionMaintenance() as session:
            await session.execute(
                text("DELETE FROM event_members WHERE id = :id"), {"id": datos.event_member_id}
            )
            await session.commit()


async def test_no_se_puede_leer_el_roster_de_otra_organizacion(
    organizacion: OrganizacionDePrueba, otra_organizacion: OrganizacionDePrueba
) -> None:
    await _crear_datos_de_prueba(organizacion)
    datos_ajenos = await _crear_datos_de_prueba(otra_organizacion)

    async with SessionApp() as session:
        async with session.begin():
            await set_organization_context(session, organizacion.id)
            fila = await session.get(EventMember, datos_ajenos.event_member_id)
    assert fila is None
