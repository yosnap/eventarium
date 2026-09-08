"""Constraints de base de datos de `event_registrations`/`event_registration_questions`.

Una inscripción por `(event_id, email)` y `options` obligatorio/no vacío solo
en preguntas de opción son garantías a nivel de base de datos, no solo del
servicio — ver `plan.md` de la fase 3 del PRD, fase de trabajo 1.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.database import SessionMaintenance
from app.modules.events.models import Event
from app.modules.registrations.models import (
    EventRegistration,
    EventRegistrationAnswer,
    EventRegistrationQuestion,
)
from tests.conftest import OrganizacionDePrueba

AHORA = datetime.now(UTC)


async def _crear_evento(organizacion: OrganizacionDePrueba) -> Event:
    async with SessionMaintenance() as session:
        evento = Event(
            organization_id=organizacion.id,
            slug=f"evento-constraints-{organizacion.slug}-{uuid.uuid4().hex[:8]}",
            title="Evento de prueba",
            status="published",
            visibility="public",
            starts_at=AHORA,
            ends_at=AHORA + timedelta(days=1),
            location_mode="online",
        )
        session.add(evento)
        await session.commit()
        await session.refresh(evento)
        return evento


async def test_no_se_puede_inscribir_dos_veces_el_mismo_email_al_mismo_evento(
    organizacion: OrganizacionDePrueba,
) -> None:
    evento = await _crear_evento(organizacion)

    async with SessionMaintenance() as session:
        session.add(
            EventRegistration(
                event_id=evento.id,
                organization_id=organizacion.id,
                email="duplicado@example.com",
                full_name="Primera vez",
                status="pending_verification",
            )
        )
        await session.commit()

    with pytest.raises(IntegrityError):
        async with SessionMaintenance() as session:
            session.add(
                EventRegistration(
                    event_id=evento.id,
                    organization_id=organizacion.id,
                    email="duplicado@example.com",
                    full_name="Segunda vez",
                    status="pending_verification",
                )
            )
            await session.commit()


async def test_el_mismo_email_puede_inscribirse_a_eventos_distintos(
    organizacion: OrganizacionDePrueba,
) -> None:
    evento_1 = await _crear_evento(organizacion)
    evento_2 = await _crear_evento(organizacion)

    async with SessionMaintenance() as session:
        session.add_all(
            [
                EventRegistration(
                    event_id=evento_1.id,
                    organization_id=organizacion.id,
                    email="misma-persona@example.com",
                    full_name="Misma persona",
                    status="pending_verification",
                ),
                EventRegistration(
                    event_id=evento_2.id,
                    organization_id=organizacion.id,
                    email="misma-persona@example.com",
                    full_name="Misma persona",
                    status="pending_verification",
                ),
            ]
        )
        await session.commit()


@pytest.mark.parametrize(
    "type_, options",
    [
        ("single_choice", None),
        ("single_choice", []),
        ("multiple_choice", None),
        ("short_text", ["opción sobrante"]),
    ],
)
async def test_options_invalido_para_el_tipo_falla(
    organizacion: OrganizacionDePrueba, type_: str, options: list[str] | None
) -> None:
    evento = await _crear_evento(organizacion)

    with pytest.raises(IntegrityError):
        async with SessionMaintenance() as session:
            session.add(
                EventRegistrationQuestion(
                    event_id=evento.id,
                    organization_id=organizacion.id,
                    type=type_,
                    label="Pregunta inválida",
                    required=False,
                    sort_order=0,
                    options=options,
                )
            )
            await session.commit()


@pytest.mark.parametrize(
    "type_, options",
    [
        ("short_text", None),
        ("single_choice", ["sí", "no"]),
        ("multiple_choice", ["a", "b", "c"]),
    ],
)
async def test_options_valido_para_el_tipo_funciona(
    organizacion: OrganizacionDePrueba, type_: str, options: list[str] | None
) -> None:
    evento = await _crear_evento(organizacion)

    async with SessionMaintenance() as session:
        session.add(
            EventRegistrationQuestion(
                event_id=evento.id,
                organization_id=organizacion.id,
                type=type_,
                label="Pregunta válida",
                required=False,
                sort_order=0,
                options=options,
            )
        )
        await session.commit()


async def test_no_se_puede_responder_dos_veces_a_la_misma_pregunta(
    organizacion: OrganizacionDePrueba,
) -> None:
    evento = await _crear_evento(organizacion)

    async with SessionMaintenance() as session:
        pregunta = EventRegistrationQuestion(
            event_id=evento.id,
            organization_id=organizacion.id,
            type="short_text",
            label="¿Empresa?",
            required=False,
            sort_order=0,
        )
        inscripcion = EventRegistration(
            event_id=evento.id,
            organization_id=organizacion.id,
            email="responde-dos-veces@example.com",
            full_name="Responde dos veces",
            status="pending_verification",
        )
        session.add_all([pregunta, inscripcion])
        await session.flush()

        session.add(
            EventRegistrationAnswer(
                registration_id=inscripcion.id,
                question_id=pregunta.id,
                organization_id=organizacion.id,
                value="Acme",
            )
        )
        await session.commit()

        pregunta_id, inscripcion_id, organization_id = pregunta.id, inscripcion.id, organizacion.id

    with pytest.raises(IntegrityError):
        async with SessionMaintenance() as session:
            session.add(
                EventRegistrationAnswer(
                    registration_id=inscripcion_id,
                    question_id=pregunta_id,
                    organization_id=organization_id,
                    value="Acme, S.L.",
                )
            )
            await session.commit()
