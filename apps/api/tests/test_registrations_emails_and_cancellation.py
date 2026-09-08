"""Emails transaccionales y autocancelación de inscripciones.

Fase 3 del PRD, fase 4 de trabajo. Mismo patrón que
`test_registrations_public.py` y `test_registrations_organizer.py`: cliente
HTTP real, `Host` para resolver la organización, y cada tarea de email
mockeada con `AsyncMock` — no se prueba la entrega, solo que se encola con
los argumentos correctos en cada transición de estado.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.core.database import SessionMaintenance
from app.core.tasks import (
    send_registration_cancelled_email,
    send_registration_confirmed_email,
    send_registration_rejected_email,
    send_registration_verification_email,
    send_registration_waitlisted_email,
    send_waitlist_promotion_email,
)
from app.modules.auth.verification import PROPOSITO_CANCELACION_INSCRIPCION, generate_token
from app.modules.registrations.models import EventRegistration
from tests.conftest import OrganizacionDePrueba, iniciar_sesion

EVENTS = "/api/v1/events"
CANCEL = "/api/v1/public/registrations/cancel"
AHORA = datetime.now(UTC).replace(microsecond=0)


@pytest.fixture(autouse=True)
def _tareas_de_email_mockeadas():
    parches = {
        nombre: patch.object(tarea, "kiq", new_callable=AsyncMock)
        for nombre, tarea in {
            "verificacion": send_registration_verification_email,
            "confirmada": send_registration_confirmed_email,
            "lista_espera": send_registration_waitlisted_email,
            "rechazada": send_registration_rejected_email,
            "cancelada": send_registration_cancelled_email,
            "promocion": send_waitlist_promotion_email,
        }.items()
    }
    mocks = {nombre: parche.start() for nombre, parche in parches.items()}
    yield mocks
    for parche in parches.values():
        parche.stop()


def _payload_evento(slug: str, **overrides: object) -> dict:
    payload = {
        "slug": slug,
        "title": f"Evento {slug}",
        "starts_at": AHORA.isoformat(),
        "ends_at": (AHORA + timedelta(days=2)).isoformat(),
        "location_mode": "in_person",
    }
    payload.update(overrides)
    return payload


async def _crear_y_publicar_evento(
    cliente: AsyncClient, cabeceras: dict[str, str], slug: str, **overrides: object
) -> dict:
    creacion = await cliente.post(
        EVENTS, headers=cabeceras, json=_payload_evento(slug, **overrides)
    )
    assert creacion.status_code == 201, creacion.text
    evento = creacion.json()
    publicacion = await cliente.patch(
        f"{EVENTS}/{evento['id']}",
        headers=cabeceras,
        json={"status": "published", "visibility": "public"},
    )
    assert publicacion.status_code == 200, publicacion.text
    return publicacion.json()


def _payload_inscripcion(**overrides: object) -> dict:
    payload = {
        "email": "asistente@example.com",
        "full_name": "Asistente de Prueba",
        "answers": [],
        "data_processing_accepted": True,
        "marketing_accepted": False,
        "recording_accepted": False,
        "turnstile_token": "token-de-prueba",
    }
    payload.update(overrides)
    return payload


async def _inscribir(cliente: AsyncClient, host: str, slug: str, **overrides: object):
    return await cliente.post(
        f"/api/v1/public/events/{slug}/registrations",
        headers={"Host": host},
        json=_payload_inscripcion(**overrides),
    )


async def _crear_inscripcion(
    organizacion: OrganizacionDePrueba,
    evento: dict,
    *,
    email: str,
    status: str = "confirmed",
) -> str:
    ahora = datetime.now(UTC)
    async with SessionMaintenance() as session:
        inscripcion = EventRegistration(
            event_id=uuid.UUID(evento["id"]),
            organization_id=organizacion.id,
            email=email,
            full_name="Asistente de Prueba",
            status=status,
            confirmed_at=ahora if status == "confirmed" else None,
        )
        session.add(inscripcion)
        await session.commit()
        await session.refresh(inscripcion)
        return str(inscripcion.id)


async def _estado(registration_id: str) -> str | None:
    async with SessionMaintenance() as session:
        return await session.scalar(
            text("SELECT status FROM event_registrations WHERE id = :id"), {"id": registration_id}
        )


class TestEmailsPorTransicion:
    async def test_verificar_con_aforo_libre_encola_email_de_confirmacion(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba, _tareas_de_email_mockeadas
    ) -> None:
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        await _crear_y_publicar_evento(cliente, cabeceras, "verificar-confirma", capacity=5)
        await _inscribir(cliente, organizacion.host, "verificar-confirma")

        registration_id = await _registration_id("asistente@example.com")
        token = await generate_token("registration_email_verify", registration_id)
        respuesta = await cliente.post(
            "/api/v1/public/registrations/verify",
            headers={"Host": organizacion.host},
            json={"token": token},
        )

        assert respuesta.status_code == 200, respuesta.text
        assert _tareas_de_email_mockeadas["confirmada"].await_count == 1
        assert _tareas_de_email_mockeadas["lista_espera"].await_count == 0

    async def test_verificar_con_aforo_agotado_encola_email_de_lista_de_espera(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba, _tareas_de_email_mockeadas
    ) -> None:
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        await _crear_y_publicar_evento(cliente, cabeceras, "verificar-espera", capacity=1)
        await _inscribir(
            cliente, organizacion.host, "verificar-espera", email="primero@example.com"
        )
        await _inscribir(
            cliente, organizacion.host, "verificar-espera", email="segundo@example.com"
        )

        for email in ("primero@example.com", "segundo@example.com"):
            registration_id = await _registration_id(email)
            token = await generate_token("registration_email_verify", registration_id)
            await cliente.post(
                "/api/v1/public/registrations/verify",
                headers={"Host": organizacion.host},
                json={"token": token},
            )

        assert _tareas_de_email_mockeadas["confirmada"].await_count == 1
        assert _tareas_de_email_mockeadas["lista_espera"].await_count == 1

    async def test_alta_sin_verificacion_encola_email_directamente(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba, _tareas_de_email_mockeadas
    ) -> None:
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        await _crear_y_publicar_evento(
            cliente,
            cabeceras,
            "sin-verificacion-email",
            email_verification_required=False,
            capacity=5,
        )

        respuesta = await _inscribir(cliente, organizacion.host, "sin-verificacion-email")

        assert respuesta.status_code == 202, respuesta.text
        assert _tareas_de_email_mockeadas["confirmada"].await_count == 1
        assert _tareas_de_email_mockeadas["verificacion"].await_count == 0

    async def test_aprobar_encola_email_de_confirmacion(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba, _tareas_de_email_mockeadas
    ) -> None:
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _crear_y_publicar_evento(
            cliente, cabeceras, "aprobar-email", registration_mode="approval", capacity=5
        )
        registration_id = await _crear_inscripcion(
            organizacion, evento, email="pendiente@example.com", status="pending_approval"
        )

        respuesta = await cliente.post(
            f"{EVENTS}/{evento['id']}/registrations/{registration_id}/approve", headers=cabeceras
        )

        assert respuesta.status_code == 200, respuesta.text
        assert _tareas_de_email_mockeadas["confirmada"].await_count == 1

    async def test_rechazar_encola_email_de_rechazo(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba, _tareas_de_email_mockeadas
    ) -> None:
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _crear_y_publicar_evento(
            cliente, cabeceras, "rechazar-email", registration_mode="approval"
        )
        registration_id = await _crear_inscripcion(
            organizacion, evento, email="pendiente@example.com", status="pending_approval"
        )

        respuesta = await cliente.post(
            f"{EVENTS}/{evento['id']}/registrations/{registration_id}/reject", headers=cabeceras
        )

        assert respuesta.status_code == 200, respuesta.text
        assert _tareas_de_email_mockeadas["rechazada"].await_count == 1

    async def test_cancelar_por_organizador_encola_email_de_cancelacion_y_promocion(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba, _tareas_de_email_mockeadas
    ) -> None:
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _crear_y_publicar_evento(cliente, cabeceras, "cancelar-email", capacity=1)
        confirmada_id = await _crear_inscripcion(
            organizacion, evento, email="confirmado@example.com", status="confirmed"
        )
        await _crear_inscripcion(
            organizacion, evento, email="espera@example.com", status="waitlisted"
        )

        respuesta = await cliente.post(
            f"{EVENTS}/{evento['id']}/registrations/{confirmada_id}/cancel", headers=cabeceras
        )

        assert respuesta.status_code == 200, respuesta.text
        assert _tareas_de_email_mockeadas["cancelada"].await_count == 1
        assert _tareas_de_email_mockeadas["promocion"].await_count == 1


class TestAutocancelacionPublica:
    async def test_cancelar_por_token_cancela_y_promueve(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba, _tareas_de_email_mockeadas
    ) -> None:
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _crear_y_publicar_evento(cliente, cabeceras, "autocancelar", capacity=1)
        confirmada_id = await _crear_inscripcion(
            organizacion, evento, email="confirmado@example.com", status="confirmed"
        )
        await _crear_inscripcion(
            organizacion, evento, email="espera@example.com", status="waitlisted"
        )
        token = await generate_token(PROPOSITO_CANCELACION_INSCRIPCION, confirmada_id)

        respuesta = await cliente.post(
            CANCEL, headers={"Host": organizacion.host}, json={"token": token}
        )

        assert respuesta.status_code == 200, respuesta.text
        assert await _estado(confirmada_id) == "cancelled"
        assert _tareas_de_email_mockeadas["cancelada"].await_count == 1
        assert _tareas_de_email_mockeadas["promocion"].await_count == 1

    async def test_cancelar_una_ya_cancelada_es_idempotente(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba, _tareas_de_email_mockeadas
    ) -> None:
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _crear_y_publicar_evento(cliente, cabeceras, "autocancelar-idempotente")
        registration_id = await _crear_inscripcion(
            organizacion, evento, email="cancelado@example.com", status="cancelled"
        )
        token = await generate_token(PROPOSITO_CANCELACION_INSCRIPCION, registration_id)

        respuesta = await cliente.post(
            CANCEL, headers={"Host": organizacion.host}, json={"token": token}
        )

        assert respuesta.status_code == 200, respuesta.text
        assert _tareas_de_email_mockeadas["cancelada"].await_count == 0

    async def test_token_invalido_da_error_generico(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        respuesta = await cliente.post(
            CANCEL, headers={"Host": organizacion.host}, json={"token": "inventado"}
        )
        assert respuesta.status_code == 422

    async def test_reutilizar_el_token_falla(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _crear_y_publicar_evento(cliente, cabeceras, "token-un-solo-uso")
        registration_id = await _crear_inscripcion(
            organizacion, evento, email="confirmado@example.com", status="confirmed"
        )
        token = await generate_token(PROPOSITO_CANCELACION_INSCRIPCION, registration_id)

        primera = await cliente.post(
            CANCEL, headers={"Host": organizacion.host}, json={"token": token}
        )
        segunda = await cliente.post(
            CANCEL, headers={"Host": organizacion.host}, json={"token": token}
        )

        assert primera.status_code == 200, primera.text
        assert segunda.status_code == 422


async def _registration_id(email: str) -> str:
    async with SessionMaintenance() as session:
        valor = await session.scalar(
            text(
                "SELECT id FROM event_registrations WHERE email = :email "
                "ORDER BY created_at DESC LIMIT 1"
            ),
            {"email": email},
        )
    assert valor is not None
    return str(valor)
