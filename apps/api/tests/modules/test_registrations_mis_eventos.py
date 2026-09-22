"""«Mis eventos»: magic-link por email, listado de inscripciones sin cuenta.

Fase 1 del plan «mis-eventos-asistente». Mismo patrón que
`test_registrations_public.py`/`test_password_reset.py`: cliente HTTP real,
organización resuelta por el propio recurso (aquí, el email dentro del
token), y la tarea de envío de correo mockeada — no se prueba la entrega,
solo que se encola (o no) con los argumentos correctos.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.core.database import SessionMaintenance
from app.core.ratelimit import MIS_EVENTOS_SOLICITAR_POR_IP
from app.core.tasks import send_mis_eventos_access_email
from app.modules.auth.verification import PROPOSITO_MIS_EVENTOS_ACCESO, generate_token
from app.modules.registrations.models import EventRegistration
from tests.conftest import OrganizacionDePrueba, iniciar_sesion

EVENTS = "/api/v1/events"
SOLICITAR = "/api/v1/public/mis-eventos/solicitar"
VER = "/api/v1/public/mis-eventos/ver"
AHORA = datetime.now(UTC).replace(microsecond=0)


def _payload_solicitar(**overrides: object) -> dict:
    payload = {"email": "nadie@example.com", "turnstile_token": "token-de-prueba"}
    payload.update(overrides)
    return payload


@pytest.fixture(autouse=True)
def _tarea_de_email_mockeada():
    with patch.object(send_mis_eventos_access_email, "kiq", new_callable=AsyncMock) as mock:
        yield mock


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


async def _crear_inscripcion(
    organizacion: OrganizacionDePrueba, evento: dict, *, email: str, status: str = "confirmed"
) -> None:
    async with SessionMaintenance() as session:
        session.add(
            EventRegistration(
                event_id=uuid.UUID(evento["id"]),
                organization_id=organizacion.id,
                email=email,
                full_name="Asistente de Prueba",
                status=status,
                confirmed_at=AHORA if status == "confirmed" else None,
            )
        )
        await session.commit()


class TestSolicitar:
    async def test_email_sin_inscripciones_responde_200_pero_no_encola_correo(
        self, cliente: AsyncClient, _tarea_de_email_mockeada
    ) -> None:
        respuesta = await cliente.post(SOLICITAR, json=_payload_solicitar())

        assert respuesta.status_code == 200, respuesta.text
        assert _tarea_de_email_mockeada.await_count == 0

    async def test_email_con_inscripcion_responde_200_y_encola_el_correo(
        self,
        cliente: AsyncClient,
        organizacion: OrganizacionDePrueba,
        _tarea_de_email_mockeada,
    ) -> None:
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _crear_y_publicar_evento(cliente, cabeceras, "mis-eventos-solicitar")
        await _crear_inscripcion(organizacion, evento, email="asistente@example.com")

        respuesta = await cliente.post(
            SOLICITAR, json=_payload_solicitar(email="asistente@example.com")
        )

        assert respuesta.status_code == 200, respuesta.text
        assert _tarea_de_email_mockeada.await_count == 1
        assert _tarea_de_email_mockeada.await_args.args[0] == "asistente@example.com"

    async def test_email_con_mayusculas_distintas_encuentra_la_inscripcion(
        self,
        cliente: AsyncClient,
        organizacion: OrganizacionDePrueba,
        _tarea_de_email_mockeada,
    ) -> None:
        """`event_registrations.email` se guarda siempre en minúsculas
        (`submit_registration`); sin normalizar aquí, escribir el correo con
        mayúsculas distintas a como se registró no encontraría la inscripción
        y respondería 200 sin encolar ningún correo, indistinguible de "no
        tiene inscripciones" desde el propio formulario."""
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _crear_y_publicar_evento(cliente, cabeceras, "mis-eventos-mayusculas")
        await _crear_inscripcion(organizacion, evento, email="asistente@example.com")

        respuesta = await cliente.post(
            SOLICITAR, json=_payload_solicitar(email="Asistente@Example.com")
        )

        assert respuesta.status_code == 200, respuesta.text
        assert _tarea_de_email_mockeada.await_count == 1
        assert _tarea_de_email_mockeada.await_args.args[0] == "asistente@example.com"

    async def test_se_bloquea_tras_superar_el_limite_por_ip(self, cliente: AsyncClient) -> None:
        for _ in range(MIS_EVENTOS_SOLICITAR_POR_IP):
            respuesta = await cliente.post(SOLICITAR, json=_payload_solicitar())
            assert respuesta.status_code == 200

        bloqueada = await cliente.post(SOLICITAR, json=_payload_solicitar())
        assert bloqueada.status_code == 429


class TestVer:
    async def test_token_valido_devuelve_las_inscripciones_de_dos_organizaciones(
        self,
        cliente: AsyncClient,
        organizacion: OrganizacionDePrueba,
        otra_organizacion: OrganizacionDePrueba,
    ) -> None:
        email = "cruzado@example.com"
        _, cabeceras_a = await iniciar_sesion(cliente, organizacion)
        _, cabeceras_b = await iniciar_sesion(cliente, otra_organizacion)
        evento_a = await _crear_y_publicar_evento(cliente, cabeceras_a, "mis-eventos-org-a")
        evento_b = await _crear_y_publicar_evento(cliente, cabeceras_b, "mis-eventos-org-b")
        await _crear_inscripcion(organizacion, evento_a, email=email)
        await _crear_inscripcion(otra_organizacion, evento_b, email=email)

        token = await generate_token(PROPOSITO_MIS_EVENTOS_ACCESO, email)
        respuesta = await cliente.post(VER, json={"token": token})

        assert respuesta.status_code == 200, respuesta.text
        inscripciones = respuesta.json()["registrations"]
        assert {fila["event_slug"] for fila in inscripciones} == {
            "mis-eventos-org-a",
            "mis-eventos-org-b",
        }
        assert {fila["organization_name"] for fila in inscripciones} == {
            await _nombre(organizacion.id),
            await _nombre(otra_organizacion.id),
        }

    async def test_token_sin_inscripciones_devuelve_lista_vacia(self, cliente: AsyncClient) -> None:
        token = await generate_token(PROPOSITO_MIS_EVENTOS_ACCESO, "sin-inscripciones@example.com")

        respuesta = await cliente.post(VER, json={"token": token})

        assert respuesta.status_code == 200, respuesta.text
        assert respuesta.json()["registrations"] == []

    async def test_token_usado_dos_veces_la_segunda_falla(self, cliente: AsyncClient) -> None:
        token = await generate_token(PROPOSITO_MIS_EVENTOS_ACCESO, "reuso@example.com")

        primera = await cliente.post(VER, json={"token": token})
        segunda = await cliente.post(VER, json={"token": token})

        assert primera.status_code == 200, primera.text
        assert segunda.status_code == 422, segunda.text

    async def test_token_caducado_falla(self, cliente: AsyncClient) -> None:
        token = await generate_token(
            PROPOSITO_MIS_EVENTOS_ACCESO, "caducado@example.com", ttl=timedelta(seconds=1)
        )
        await asyncio.sleep(1.2)

        respuesta = await cliente.post(VER, json={"token": token})

        assert respuesta.status_code == 422, respuesta.text

    async def test_token_invalido_falla(self, cliente: AsyncClient) -> None:
        respuesta = await cliente.post(VER, json={"token": "no-existe"})

        assert respuesta.status_code == 422, respuesta.text


async def _nombre(organization_id: uuid.UUID) -> str:
    async with SessionMaintenance() as session:
        return await session.scalar(
            text("SELECT name FROM organizations WHERE id = :id"), {"id": organization_id}
        )
