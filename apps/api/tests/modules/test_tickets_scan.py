"""Escaneo y check-in de entradas QR (API).

Fase 4 del PRD, fase 2 de trabajo. Mismo patrón que
`test_tickets_emision.py`/`test_registrations_organizer.py`: cliente HTTP
real, `Host` para resolver la organización, tareas de email mockeadas.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import jwt
import pytest
from httpx import AsyncClient
from sqlalchemy import select, text

from app.core.config import get_settings
from app.core.database import SessionMaintenance
from app.core.tasks import send_registration_confirmed_email, send_registration_verification_email
from app.modules.auth.verification import PROPOSITO_VERIFICACION_INSCRIPCION, generate_token
from app.modules.registrations.models import EventRegistration
from app.modules.tickets.models import EventTicket
from app.modules.tickets.service import generar_token_qr
from tests.conftest import OrganizacionDePrueba, iniciar_sesion

EVENTS = "/api/v1/events"
VERIFY = "/api/v1/public/registrations/verify"
AHORA = datetime.now(UTC).replace(microsecond=0)


@pytest.fixture(autouse=True)
def _tareas_de_email_mockeadas():
    parches = [
        patch.object(send_registration_verification_email, "kiq", new_callable=AsyncMock),
        patch.object(send_registration_confirmed_email, "kiq", new_callable=AsyncMock),
    ]
    mocks = [parche.start() for parche in parches]
    yield mocks
    for parche in parches:
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
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, evento: dict, email: str
) -> str:
    """Da de alta y verifica una inscripción (aforo libre → `confirmed`),
    devolviendo su `registration_id`. `emitir_entrada` (fase 1) ya deja el
    ticket creado al confirmar."""
    payload = {
        "email": email,
        "full_name": "Asistente de Prueba",
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
    assert verificacion.json()["status"] == "confirmed"
    return str(registration_id)


async def _ticket_qr(registration_id: str) -> tuple[EventTicket, str]:
    """Carga el `EventTicket` de una inscripción (con `event` ya cargado por
    `lazy="selectin"`) y genera su token QR real."""
    async with SessionMaintenance() as session:
        ticket = await session.scalar(
            select(EventTicket).where(EventTicket.registration_id == uuid.UUID(registration_id))
        )
        assert ticket is not None
        token = generar_token_qr(ticket)
        return ticket, token


def _token_manual(ticket_id: uuid.UUID, event_id: uuid.UUID, *, exp: datetime, secret: str) -> str:
    """Un JWT construido a mano, para casos que `generar_token_qr` no puede
    producir directamente (caducado, o firmado con otro secreto)."""
    payload = {
        "tid": str(ticket_id),
        "eid": str(event_id),
        "exp": int(exp.timestamp()),
        "jti": "test",
    }
    return jwt.encode(payload, secret, algorithm="HS256")


async def _fila_ticket(ticket_id: uuid.UUID) -> dict:
    async with SessionMaintenance() as session:
        fila = (
            (
                await session.execute(
                    text(
                        "SELECT used_at, used_by_event_member_id, revoked_at "
                        "FROM event_tickets WHERE id = :id"
                    ),
                    {"id": ticket_id},
                )
            )
            .mappings()
            .one()
        )
    return dict(fila)


async def _contar_scans(client_scan_id: uuid.UUID) -> int:
    async with SessionMaintenance() as session:
        total = await session.scalar(
            text("SELECT count(*) FROM event_ticket_scans WHERE client_scan_id = :id"),
            {"id": client_scan_id},
        )
    return int(total or 0)


async def test_escanear_un_qr_valido_marca_el_uso(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_y_publicar_evento(cliente, cabeceras, "scan-valido", capacity=5)
    registration_id = await _inscribir_y_confirmar(
        cliente, organizacion, evento, "asistente@example.com"
    )
    ticket, token = await _ticket_qr(registration_id)

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
    cuerpo = respuesta.json()
    assert cuerpo["result"] == "valid"
    assert cuerpo["full_name"] == "Asistente de Prueba"
    assert cuerpo["email"] == "asistente@example.com"
    fila = await _fila_ticket(ticket.id)
    assert fila["used_at"] is not None
    assert fila["used_by_event_member_id"] is not None


async def test_escanear_el_mismo_qr_dos_veces_es_duplicate(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_y_publicar_evento(cliente, cabeceras, "scan-duplicado", capacity=5)
    registration_id = await _inscribir_y_confirmar(
        cliente, organizacion, evento, "asistente@example.com"
    )
    ticket, token = await _ticket_qr(registration_id)

    async def _escanear() -> dict:
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
        return respuesta.json()

    primero = await _escanear()
    fila_tras_primero = await _fila_ticket(ticket.id)
    segundo = await _escanear()
    fila_tras_segundo = await _fila_ticket(ticket.id)

    assert primero["result"] == "valid"
    assert segundo["result"] == "duplicate"
    assert fila_tras_primero["used_at"] == fila_tras_segundo["used_at"]
    assert (
        fila_tras_primero["used_by_event_member_id"]
        == fila_tras_segundo["used_by_event_member_id"]
    )


async def test_escanear_una_entrada_revocada_es_revoked(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_y_publicar_evento(cliente, cabeceras, "scan-revocado", capacity=5)
    registration_id = await _inscribir_y_confirmar(
        cliente, organizacion, evento, "asistente@example.com"
    )
    _, token = await _ticket_qr(registration_id)

    cancelacion = await cliente.post(
        f"{EVENTS}/{evento['id']}/registrations/{registration_id}/cancel", headers=cabeceras
    )
    assert cancelacion.status_code == 200, cancelacion.text

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
    assert respuesta.json()["result"] == "revoked"


async def test_escanear_con_firma_invalida_es_invalid_signature(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_y_publicar_evento(cliente, cabeceras, "scan-firma-invalida", capacity=5)
    registration_id = await _inscribir_y_confirmar(
        cliente, organizacion, evento, "asistente@example.com"
    )
    ticket, _ = await _ticket_qr(registration_id)
    token_falso = _token_manual(
        ticket.id,
        uuid.UUID(evento["id"]),
        exp=AHORA + timedelta(days=10),
        secret="otro-secreto-cualquiera-de-mas-de-32-caracteres",
    )

    respuesta = await cliente.post(
        f"{EVENTS}/{evento['id']}/tickets/scan",
        headers=cabeceras,
        json={
            "token": token_falso,
            "client_scan_id": str(uuid.uuid4()),
            "client_scanned_at": AHORA.isoformat(),
        },
    )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["result"] == "invalid_signature"


async def test_escanear_un_token_caducado_es_expired(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_y_publicar_evento(cliente, cabeceras, "scan-caducado", capacity=5)
    registration_id = await _inscribir_y_confirmar(
        cliente, organizacion, evento, "asistente@example.com"
    )
    ticket, _ = await _ticket_qr(registration_id)
    settings = get_settings()
    token_caducado = _token_manual(
        ticket.id,
        uuid.UUID(evento["id"]),
        exp=AHORA - timedelta(hours=1),
        secret=settings.ticket_qr_secret,
    )

    respuesta = await cliente.post(
        f"{EVENTS}/{evento['id']}/tickets/scan",
        headers=cabeceras,
        json={
            "token": token_caducado,
            "client_scan_id": str(uuid.uuid4()),
            "client_scanned_at": AHORA.isoformat(),
        },
    )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["result"] == "expired"


async def test_dos_escaneos_simultaneos_del_mismo_qr_solo_uno_es_valido(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    """El `SELECT ... FOR UPDATE` sobre la fila de la entrada serializa dos
    escaneos casi simultáneos del mismo QR en dos dispositivos."""
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_y_publicar_evento(cliente, cabeceras, "scan-concurrencia", capacity=5)
    registration_id = await _inscribir_y_confirmar(
        cliente, organizacion, evento, "asistente@example.com"
    )
    _, token = await _ticket_qr(registration_id)

    def _payload() -> dict:
        return {
            "token": token,
            "client_scan_id": str(uuid.uuid4()),
            "client_scanned_at": AHORA.isoformat(),
        }

    respuestas = await asyncio.gather(
        cliente.post(f"{EVENTS}/{evento['id']}/tickets/scan", headers=cabeceras, json=_payload()),
        cliente.post(f"{EVENTS}/{evento['id']}/tickets/scan", headers=cabeceras, json=_payload()),
    )
    resultados = sorted(respuesta.json()["result"] for respuesta in respuestas)
    assert resultados == ["duplicate", "valid"]


async def test_reenviar_el_mismo_client_scan_id_no_cuenta_como_segundo_intento(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_y_publicar_evento(cliente, cabeceras, "scan-reintento", capacity=5)
    registration_id = await _inscribir_y_confirmar(
        cliente, organizacion, evento, "asistente@example.com"
    )
    _, token = await _ticket_qr(registration_id)
    client_scan_id = str(uuid.uuid4())
    payload = {
        "token": token,
        "client_scan_id": client_scan_id,
        "client_scanned_at": AHORA.isoformat(),
    }

    primero = await cliente.post(
        f"{EVENTS}/{evento['id']}/tickets/scan", headers=cabeceras, json=payload
    )
    segundo = await cliente.post(
        f"{EVENTS}/{evento['id']}/tickets/scan", headers=cabeceras, json=payload
    )

    assert primero.json()["result"] == "valid"
    assert segundo.json()["result"] == "valid"
    assert await _contar_scans(uuid.UUID(client_scan_id)) == 1


async def test_scan_batch_respeta_el_orden_de_client_scanned_at(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_y_publicar_evento(cliente, cabeceras, "scan-lote", capacity=5)
    registration_id = await _inscribir_y_confirmar(
        cliente, organizacion, evento, "asistente@example.com"
    )
    _, token = await _ticket_qr(registration_id)

    mas_tarde = str(uuid.uuid4())
    mas_temprano = str(uuid.uuid4())
    respuesta = await cliente.post(
        f"{EVENTS}/{evento['id']}/tickets/scan/batch",
        headers=cabeceras,
        json={
            "scans": [
                {
                    "token": token,
                    "client_scan_id": mas_tarde,
                    "client_scanned_at": (AHORA + timedelta(minutes=5)).isoformat(),
                },
                {
                    "token": token,
                    "client_scan_id": mas_temprano,
                    "client_scanned_at": AHORA.isoformat(),
                },
            ]
        },
    )

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert [fila["client_scan_id"] for fila in cuerpo] == [mas_temprano, mas_tarde]
    assert cuerpo[0]["result"] == "valid"
    assert cuerpo[1]["result"] == "duplicate"


async def test_search_solo_devuelve_confirmadas_con_entrada_vigente(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_y_publicar_evento(cliente, cabeceras, "buscar", capacity=5)
    await _inscribir_y_confirmar(cliente, organizacion, evento, "confirmada@example.com")

    async with SessionMaintenance() as session:
        session.add(
            EventRegistration(
                event_id=uuid.UUID(evento["id"]),
                organization_id=organizacion.id,
                email="pendiente@example.com",
                full_name="Pendiente de Aprobación",
                status="pending_approval",
            )
        )
        await session.commit()

    respuesta = await cliente.get(
        f"{EVENTS}/{evento['id']}/tickets/search", headers=cabeceras, params={"q": "example.com"}
    )

    assert respuesta.status_code == 200, respuesta.text
    correos = {fila["email"] for fila in respuesta.json()}
    assert correos == {"confirmada@example.com"}


async def test_check_in_manual_marca_el_uso_con_resultado_manual(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_y_publicar_evento(cliente, cabeceras, "check-in-manual", capacity=5)
    registration_id = await _inscribir_y_confirmar(
        cliente, organizacion, evento, "asistente@example.com"
    )
    ticket, _ = await _ticket_qr(registration_id)

    respuesta = await cliente.post(
        f"{EVENTS}/{evento['id']}/tickets/{ticket.id}/check-in-manual", headers=cabeceras
    )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["result"] == "manual"
    fila = await _fila_ticket(ticket.id)
    assert fila["used_at"] is not None


async def test_detalle_de_entrada_requiere_ticket_existente(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_y_publicar_evento(cliente, cabeceras, "detalle", capacity=5)
    registration_id = await _inscribir_y_confirmar(
        cliente, organizacion, evento, "asistente@example.com"
    )

    respuesta = await cliente.get(
        f"{EVENTS}/{evento['id']}/tickets/{registration_id}", headers=cabeceras
    )

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["full_name"] == "Asistente de Prueba"
    assert cuerpo["status"] == "confirmed"

    inexistente = await cliente.get(
        f"{EVENTS}/{evento['id']}/tickets/{uuid.uuid4()}", headers=cabeceras
    )
    assert inexistente.status_code == 404
