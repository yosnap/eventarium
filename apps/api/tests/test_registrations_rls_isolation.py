"""Aislamiento entre organizaciones para las tablas de inscripción de asistentes.

Mismo patrón que `test_events_rls_isolation.py` de la fase 2 del PRD: que una
organización no **lee** filas de otra (RLS) y que tampoco puede **escribir**
una fila propia que apunte al recurso padre de otra organización (las FK
compuestas, no la política RLS, son las que lo impiden).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import DBAPIError

from app.core.database import SessionApp, SessionMaintenance, set_organization_context
from app.modules.events.models import Event
from app.modules.organizations.repository import unsafe_select_all
from app.modules.registrations.models import (
    EventRegistration,
    EventRegistrationAnswer,
    EventRegistrationConsent,
    EventRegistrationQuestion,
)
from tests.conftest import OrganizacionDePrueba

TABLAS_CON_ORGANIZACION = (
    EventRegistrationQuestion,
    EventRegistration,
    EventRegistrationAnswer,
    EventRegistrationConsent,
)

AHORA = datetime.now(UTC)


class DatosDePrueba:
    """IDs de un evento, pregunta, inscripción, respuesta y consentimiento."""

    __slots__ = ("event_id", "question_id", "registration_id")

    def __init__(self, *, event_id: uuid.UUID, question_id: uuid.UUID, registration_id: uuid.UUID):
        self.event_id = event_id
        self.question_id = question_id
        self.registration_id = registration_id


async def _crear_datos_de_prueba(organizacion: OrganizacionDePrueba) -> DatosDePrueba:
    """Crea evento, pregunta, inscripción, respuesta y consentimiento bajo el rol
    de mantenimiento."""
    async with SessionMaintenance() as session:
        evento = Event(
            organization_id=organizacion.id,
            slug=f"evento-inscripcion-{organizacion.slug}",
            title="Evento de prueba",
            status="published",
            visibility="public",
            starts_at=AHORA,
            ends_at=AHORA + timedelta(days=1),
            location_mode="online",
        )
        session.add(evento)
        await session.flush()

        pregunta = EventRegistrationQuestion(
            event_id=evento.id,
            organization_id=organizacion.id,
            type="short_text",
            label="¿Empresa?",
            required=False,
            sort_order=0,
        )
        session.add(pregunta)
        await session.flush()

        inscripcion = EventRegistration(
            event_id=evento.id,
            organization_id=organizacion.id,
            email=f"asistente-{organizacion.slug}@example.com",
            full_name="Asistente de prueba",
            status="pending_verification",
        )
        session.add(inscripcion)
        await session.flush()

        respuesta = EventRegistrationAnswer(
            registration_id=inscripcion.id,
            question_id=pregunta.id,
            organization_id=organizacion.id,
            value="Acme",
        )
        session.add(respuesta)

        consentimiento = EventRegistrationConsent(
            registration_id=inscripcion.id,
            organization_id=organizacion.id,
            data_processing_accepted_at=AHORA,
        )
        session.add(consentimiento)

        await session.commit()
        return DatosDePrueba(
            event_id=evento.id, question_id=pregunta.id, registration_id=inscripcion.id
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


async def test_no_se_puede_crear_una_pregunta_de_un_evento_ajeno(
    organizacion: OrganizacionDePrueba, otra_organizacion: OrganizacionDePrueba
) -> None:
    datos_ajenos = await _crear_datos_de_prueba(otra_organizacion)

    with pytest.raises(DBAPIError):
        async with SessionApp() as session:
            async with session.begin():
                await set_organization_context(session, organizacion.id)
                session.add(
                    EventRegistrationQuestion(
                        event_id=datos_ajenos.event_id,
                        organization_id=organizacion.id,
                        type="short_text",
                        label="Pregunta intrusa",
                        required=False,
                        sort_order=0,
                    )
                )
                await session.flush()


async def test_no_se_puede_crear_una_inscripcion_de_un_evento_ajeno(
    organizacion: OrganizacionDePrueba, otra_organizacion: OrganizacionDePrueba
) -> None:
    datos_ajenos = await _crear_datos_de_prueba(otra_organizacion)

    with pytest.raises(DBAPIError):
        async with SessionApp() as session:
            async with session.begin():
                await set_organization_context(session, organizacion.id)
                session.add(
                    EventRegistration(
                        event_id=datos_ajenos.event_id,
                        organization_id=organizacion.id,
                        email="intrusa@example.com",
                        full_name="Intrusa",
                        status="pending_verification",
                    )
                )
                await session.flush()


async def test_no_se_puede_responder_a_una_pregunta_ajena(
    organizacion: OrganizacionDePrueba, otra_organizacion: OrganizacionDePrueba
) -> None:
    datos_propios = await _crear_datos_de_prueba(organizacion)
    datos_ajenos = await _crear_datos_de_prueba(otra_organizacion)

    with pytest.raises(DBAPIError):
        async with SessionApp() as session:
            async with session.begin():
                await set_organization_context(session, organizacion.id)
                session.add(
                    EventRegistrationAnswer(
                        registration_id=datos_propios.registration_id,
                        question_id=datos_ajenos.question_id,
                        organization_id=organizacion.id,
                        value="valor intruso",
                    )
                )
                await session.flush()


async def test_no_se_puede_adjuntar_consentimiento_a_una_inscripcion_ajena(
    organizacion: OrganizacionDePrueba, otra_organizacion: OrganizacionDePrueba
) -> None:
    datos_ajenos = await _crear_datos_de_prueba(otra_organizacion)

    with pytest.raises(DBAPIError):
        async with SessionApp() as session:
            async with session.begin():
                await set_organization_context(session, organizacion.id)
                session.add(
                    EventRegistrationConsent(
                        registration_id=datos_ajenos.registration_id,
                        organization_id=organizacion.id,
                        data_processing_accepted_at=AHORA,
                    )
                )
                await session.flush()
