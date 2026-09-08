"""Superadmin: auditoría, exportación y borrado RGPD.

Fase 5 del PRD, fase 4 de trabajo. Mismo patrón que `tests/modules/test_admin.py`
y `tests/test_registrations_emails_and_cancellation.py`: cliente HTTP real,
`Host` para resolver la organización, tareas de email mockeadas.
"""

from __future__ import annotations

import csv
import io
import uuid
import zipfile
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text

from app.core.database import SessionMaintenance
from app.core.tasks import (
    send_registration_confirmed_email,
    send_registration_verification_email,
    send_waitlist_promotion_email,
)
from app.modules.auth.verification import PROPOSITO_VERIFICACION_INSCRIPCION, generate_token
from app.modules.tickets.models import EventTicket, EventTicketScan
from app.modules.users.models import User
from tests.conftest import OrganizacionDePrueba, iniciar_sesion

ADMIN_ORGS = "/api/v1/admin/organizations"
AUDIT_LOG = "/api/v1/admin/audit-log"
EVENTS = "/api/v1/events"
VERIFY = "/api/v1/public/registrations/verify"
AHORA = datetime.now(UTC).replace(microsecond=0)


async def _hacer_superadmin(email: str) -> None:
    async with SessionMaintenance() as session:
        usuario = await session.scalar(select(User).where(User.email == email))
        assert usuario is not None
        usuario.is_superadmin = True
        await session.commit()


@pytest.fixture(autouse=True)
def _tareas_de_email_mockeadas():
    parches = {
        nombre: patch.object(tarea, "kiq", new_callable=AsyncMock)
        for nombre, tarea in {
            "verificacion": send_registration_verification_email,
            "confirmada": send_registration_confirmed_email,
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


async def _inscribir_y_confirmar(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    evento: dict,
    email: str,
    *,
    answers: list[dict] | None = None,
) -> str:
    payload = {
        "email": email,
        "full_name": "Asistente de Prueba",
        "answers": answers or [],
        "data_processing_accepted": True,
        "marketing_accepted": False,
        "recording_accepted": False,
        "turnstile_token": "token-de-prueba",
    }
    respuesta = await cliente.post(
        f"/api/v1/public/events/{evento['slug']}/registrations",
        headers={"Host": organizacion.host},
        json=payload,
    )
    assert respuesta.status_code == 202, respuesta.text

    async with SessionMaintenance() as session:
        registration_id = await session.scalar(
            text("SELECT id FROM event_registrations WHERE event_id = :e AND email = :m"),
            {"e": evento["id"], "m": email},
        )
    token = await generate_token(PROPOSITO_VERIFICACION_INSCRIPCION, str(registration_id))
    verificacion = await cliente.post(
        VERIFY, headers={"Host": organizacion.host}, json={"token": token}
    )
    assert verificacion.status_code == 200, verificacion.text
    return str(registration_id)


async def _inscribir_sin_verificar(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, evento: dict, email: str
) -> None:
    """Deja la inscripción en `pending_verification` (aforo ya lleno arriba),
    para poblar la lista de espera sin confirmar de más."""
    payload = {
        "email": email,
        "full_name": "En espera",
        "answers": [],
        "data_processing_accepted": True,
        "marketing_accepted": False,
        "recording_accepted": False,
        "turnstile_token": "token-de-prueba",
    }
    respuesta = await cliente.post(
        f"/api/v1/public/events/{evento['slug']}/registrations",
        headers={"Host": organizacion.host},
        json=payload,
    )
    assert respuesta.status_code == 202, respuesta.text
    async with SessionMaintenance() as session:
        registration_id = await session.scalar(
            text("SELECT id FROM event_registrations WHERE event_id = :e AND email = :m"),
            {"e": evento["id"], "m": email},
        )
    token = await generate_token(PROPOSITO_VERIFICACION_INSCRIPCION, str(registration_id))
    verificacion = await cliente.post(
        VERIFY, headers={"Host": organizacion.host}, json={"token": token}
    )
    assert verificacion.status_code == 200, verificacion.text
    assert verificacion.json()["status"] == "waitlisted"


async def _escanear_ticket(
    cliente: AsyncClient,
    cabeceras: dict[str, str],
    evento: dict,
    registration_id: str,
) -> uuid.UUID:
    """Genera un escaneo real (`EventTicketScan`) para el ticket de esa
    inscripción, vía el endpoint de check-in del organizador."""
    from app.modules.tickets.service import generar_token_qr

    async with SessionMaintenance() as session:
        ticket = await session.scalar(
            select(EventTicket).where(EventTicket.registration_id == uuid.UUID(registration_id))
        )
        assert ticket is not None
        token = generar_token_qr(ticket)
        ticket_id = ticket.id

    respuesta = await cliente.post(
        f"{EVENTS}/{evento['id']}/tickets/scan",
        headers=cabeceras,
        json={
            "token": token,
            "client_scan_id": str(uuid.uuid4()),
            "client_scanned_at": AHORA.isoformat(),
        },
    )
    assert respuesta.status_code == 200, respuesta.text
    return ticket_id


async def _crear_pregunta_texto_libre(
    cliente: AsyncClient, cabeceras: dict[str, str], evento: dict, *, label: str
) -> str:
    respuesta = await cliente.post(
        f"{EVENTS}/{evento['id']}/registration-questions",
        headers=cabeceras,
        json={"type": "short_text", "label": label, "required": False, "sort_order": 0},
    )
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()["id"]


class TestAccesoSuperadmin:
    async def test_organizador_recibe_403_en_los_tres_endpoints_nuevos(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        _, cabeceras = await iniciar_sesion(cliente, organizacion)

        auditoria = await cliente.get(AUDIT_LOG, headers=cabeceras)
        assert auditoria.status_code == 403

        export = await cliente.request(
            "POST",
            f"/api/v1/admin/events/{uuid.uuid4()}/rgpd-export",
            headers=cabeceras,
            json={"password": "lo que sea"},
        )
        assert export.status_code == 403

        borrado = await cliente.request(
            "DELETE",
            "/api/v1/admin/registrations/by-email",
            headers=cabeceras,
            json={
                "event_id": str(uuid.uuid4()),
                "email": "quien-sea@example.com",
                "password": "lo que sea",
            },
        )
        assert borrado.status_code == 403


class TestAuditoria:
    async def test_alta_de_organizacion_y_dominio_quedan_en_audit_log(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        await _hacer_superadmin(organizacion.owner_email)
        _, cabeceras = await iniciar_sesion(cliente, organizacion)

        creacion = await cliente.post(
            ADMIN_ORGS,
            headers=cabeceras,
            json={"slug": "auditada", "name": "Auditada", "host": "auditada.example"},
        )
        assert creacion.status_code == 201, creacion.text
        nueva_id = creacion.json()["id"]

        dominio = await cliente.post(
            f"{ADMIN_ORGS}/{nueva_id}/domains",
            headers=cabeceras,
            json={"host": "otro.example", "is_primary": False},
        )
        assert dominio.status_code == 201, dominio.text

        listado = await cliente.get(
            AUDIT_LOG, headers=cabeceras, params={"organization_id": nueva_id}
        )
        assert listado.status_code == 200, listado.text
        acciones = {fila["action"] for fila in listado.json()["items"]}
        assert "organization.created" in acciones
        assert "organization_domain.created" in acciones

    async def test_cambio_de_permisos_de_rol_queda_en_audit_log(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        await _hacer_superadmin(organizacion.owner_email)
        _, cabeceras = await iniciar_sesion(cliente, organizacion)

        roles = await cliente.get("/api/v1/roles", headers=cabeceras)
        assert roles.status_code == 200
        organizer = next(r for r in roles.json() if r["key"] == "organizer")

        actualizacion = await cliente.patch(
            f"/api/v1/roles/{organizer['id']}",
            headers=cabeceras,
            json={"permissions": ["events:read"]},
        )
        assert actualizacion.status_code == 200, actualizacion.text

        listado = await cliente.get(
            AUDIT_LOG,
            headers=cabeceras,
            params={"organization_id": organizacion.id, "action": "role.permissions_changed"},
        )
        assert listado.status_code == 200
        assert listado.json()["total"] == 1
        detail = listado.json()["items"][0]["detail"]
        assert detail["role_key"] == "organizer"
        assert detail["permissions_after"] == ["events:read"]

    async def test_filtro_por_rango_de_fechas_excluye_filas_fuera_de_rango(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        await _hacer_superadmin(organizacion.owner_email)
        _, cabeceras = await iniciar_sesion(cliente, organizacion)

        await cliente.post(
            ADMIN_ORGS,
            headers=cabeceras,
            json={"slug": "fecha", "name": "Fecha", "host": "fecha.example"},
        )

        futuro = (datetime.now(UTC) + timedelta(days=1)).isoformat()
        fuera_de_rango = await cliente.get(
            AUDIT_LOG, headers=cabeceras, params={"date_from": futuro}
        )
        assert fuera_de_rango.status_code == 200
        assert fuera_de_rango.json()["total"] == 0

        pasado = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        dentro_de_rango = await cliente.get(
            AUDIT_LOG, headers=cabeceras, params={"date_from": pasado, "date_to": futuro}
        )
        assert dentro_de_rango.status_code == 200
        assert dentro_de_rango.json()["total"] >= 1


class TestExportacionRgpd:
    async def test_export_neutraliza_formulas_y_coincide_con_la_bd(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        await _hacer_superadmin(organizacion.owner_email)
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _crear_y_publicar_evento(cliente, cabeceras, "export-rgpd", capacity=5)
        pregunta_id = await _crear_pregunta_texto_libre(
            cliente, cabeceras, evento, label="Comentario"
        )

        respuesta_peligrosa = "=cmd|' /C calc'!A1"
        registration_id = await _inscribir_y_confirmar(
            cliente,
            organizacion,
            evento,
            "riesgo@example.com",
            answers=[{"question_id": pregunta_id, "value": respuesta_peligrosa}],
        )

        export = await cliente.request(
            "POST",
            f"/api/v1/admin/events/{evento['id']}/rgpd-export",
            headers=cabeceras,
            json={"password": organizacion.owner_password},
        )
        assert export.status_code == 200, export.text
        assert export.headers["content-type"] == "application/zip"

        with zipfile.ZipFile(io.BytesIO(export.content)) as zf:
            contenido_inscripciones = zf.read("inscripciones.csv").decode("utf-8")
            contenido_entradas = zf.read("entradas.csv").decode("utf-8")

        filas = list(csv.DictReader(io.StringIO(contenido_inscripciones)))
        fila = next(f for f in filas if f["registration_id"] == registration_id)
        assert fila["email"] == "riesgo@example.com"
        assert fila["question"] == "Comentario"
        # Neutralizada con el prefijo `'`: ni Excel ni LibreOffice la
        # interpretan como fórmula.
        assert fila["answer"] == f"'{respuesta_peligrosa}"

        async with SessionMaintenance() as session:
            fila_bd = (
                (
                    await session.execute(
                        text(
                            "SELECT email, full_name, status "
                            "FROM event_registrations WHERE id = :id"
                        ),
                        {"id": registration_id},
                    )
                )
                .mappings()
                .one()
            )
        assert fila["email"] == fila_bd["email"]
        assert fila["full_name"] == fila_bd["full_name"]
        assert fila["status"] == fila_bd["status"]

        filas_entradas = list(csv.DictReader(io.StringIO(contenido_entradas)))
        entrada = next(f for f in filas_entradas if f["registration_id"] == registration_id)
        assert entrada["status"] == "issued"
        # Nunca el JWT del QR: solo metadatos.
        assert set(entrada.keys()) == {
            "registration_id",
            "issued_at",
            "used_at",
            "revoked_at",
            "status",
        }

        auditoria = await cliente.get(
            AUDIT_LOG, headers=cabeceras, params={"action": "registration.rgpd_export"}
        )
        assert auditoria.json()["total"] == 1

    async def test_export_sin_reautenticacion_correcta_devuelve_401(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        await _hacer_superadmin(organizacion.owner_email)
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _crear_y_publicar_evento(cliente, cabeceras, "export-sin-reauth")

        export = await cliente.request(
            "POST",
            f"/api/v1/admin/events/{evento['id']}/rgpd-export",
            headers=cabeceras,
            json={"password": "contraseña-incorrecta"},
        )
        assert export.status_code == 401


class TestBorradoRgpd:
    async def test_borra_confirmed_con_lista_de_espera_y_anonimiza_escaneos(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba, _tareas_de_email_mockeadas
    ) -> None:
        await _hacer_superadmin(organizacion.owner_email)
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _crear_y_publicar_evento(cliente, cabeceras, "borrado-rgpd", capacity=1)

        registration_id = await _inscribir_y_confirmar(
            cliente, organizacion, evento, "confirmado@example.com"
        )
        await _inscribir_sin_verificar(cliente, organizacion, evento, "en-espera@example.com")

        ticket_id = await _escanear_ticket(cliente, cabeceras, evento, registration_id)

        borrado = await cliente.request(
            "DELETE",
            "/api/v1/admin/registrations/by-email",
            headers=cabeceras,
            json={
                "event_id": evento["id"],
                "email": "confirmado@example.com",
                "password": organizacion.owner_password,
            },
        )
        assert borrado.status_code == 204, borrado.text

        # La lista de espera fue promovida, igual que una cancelación normal.
        assert _tareas_de_email_mockeadas["promocion"].await_count == 1

        async with SessionMaintenance() as session:
            existe = await session.scalar(
                text("SELECT 1 FROM event_registrations WHERE id = :id"),
                {"id": registration_id},
            )
            assert existe is None

            scan = await session.scalar(
                select(EventTicketScan).where(EventTicketScan.ticket_id == ticket_id)
            )
            assert scan is None  # ya no apunta al ticket borrado

            total_scans = await session.scalar(text("SELECT count(*) FROM event_ticket_scans"))
            assert total_scans == 1  # el escaneo sigue existiendo, anonimizado

        auditoria = await cliente.get(
            AUDIT_LOG, headers=cabeceras, params={"action": "registration.rgpd_delete"}
        )
        assert auditoria.status_code == 200
        entradas = auditoria.json()["items"]
        assert len(entradas) == 1
        detail = entradas[0]["detail"]
        assert "confirmado@example.com" not in str(detail)
        assert detail["registration_id"] == registration_id
        assert "email_hash" in detail

    async def test_borrado_de_inscripcion_inexistente_devuelve_404(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        await _hacer_superadmin(organizacion.owner_email)
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _crear_y_publicar_evento(cliente, cabeceras, "borrado-404")

        borrado = await cliente.request(
            "DELETE",
            "/api/v1/admin/registrations/by-email",
            headers=cabeceras,
            json={
                "event_id": evento["id"],
                "email": "no-existe@example.com",
                "password": organizacion.owner_password,
            },
        )
        assert borrado.status_code == 404

    async def test_borrado_sin_reautenticacion_correcta_devuelve_401(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        await _hacer_superadmin(organizacion.owner_email)
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _crear_y_publicar_evento(cliente, cabeceras, "borrado-sin-reauth")

        borrado = await cliente.request(
            "DELETE",
            "/api/v1/admin/registrations/by-email",
            headers=cabeceras,
            json={
                "event_id": evento["id"],
                "email": "quien-sea@example.com",
                "password": "contraseña-incorrecta",
            },
        )
        assert borrado.status_code == 401


class TestRateLimit:
    async def test_rgpd_export_supera_el_limite_por_ip(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        await _hacer_superadmin(organizacion.owner_email)
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento_id = str(uuid.uuid4())

        respuestas = [
            await cliente.request(
            "POST",
                f"/api/v1/admin/events/{evento_id}/rgpd-export",
                headers=cabeceras,
                json={"password": "lo que sea"},
            )
            for _ in range(11)
        ]
        assert respuestas[-1].status_code == 429
