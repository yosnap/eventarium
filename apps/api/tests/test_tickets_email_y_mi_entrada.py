"""Email de entrada, `/mi-entrada` y flujo end-to-end completo.

Fase 4 del PRD, fase 4 de trabajo. Mismo patrón que
`tests/modules/test_tickets_scan.py`: cliente HTTP real, `Host` para resolver
la organización, tareas de email mockeadas.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import jwt
import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.core.config import get_settings
from app.core.database import SessionMaintenance
from app.core.email import EmailAttachment
from app.core.tasks import send_registration_confirmed_email, send_registration_verification_email
from app.modules.auth.verification import PROPOSITO_VERIFICACION_INSCRIPCION, generate_token
from tests.conftest import OrganizacionDePrueba, iniciar_sesion

EVENTS = "/api/v1/events"
VERIFY = "/api/v1/public/registrations/verify"
MY_TICKET = "/api/v1/public/registrations/my-ticket"
MY_TICKET_QR = "/api/v1/public/registrations/my-ticket/qr"
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


async def test_confirmar_encola_email_con_qr_adjunto(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_y_publicar_evento(cliente, cabeceras, "email-con-qr", capacity=5)

    await _inscribir_y_confirmar(cliente, organizacion, evento, "asistente@example.com")

    llamada = send_registration_confirmed_email.kiq.call_args
    assert llamada is not None
    to_email, organization_id, cancel_token, qr_token = llamada.args
    assert to_email == "asistente@example.com"
    assert organization_id == str(organizacion.id)
    assert isinstance(cancel_token, str) and cancel_token
    # El JWT del QR decodifica con el secreto de la API — es el mismo firmado
    # por `generar_token_qr`, no un valor inventado.
    settings = get_settings()
    payload = jwt.decode(qr_token, settings.ticket_qr_secret, algorithms=[settings.jwt_algorithm])
    assert "tid" in payload and "eid" in payload
    assert "email" not in payload


async def test_send_registration_confirmed_email_adjunta_un_png() -> None:
    with patch("app.core.tasks.get_email_provider") as proveedor_mock:
        proveedor = AsyncMock()
        proveedor_mock.return_value = proveedor
        with patch("app.core.tasks.base_url_de_organizacion", return_value="https://acme.test"):
            token = jwt.encode(
                {"tid": str(uuid.uuid4()), "eid": str(uuid.uuid4())},
                "secreto-de-prueba-de-mas-de-treinta-y-dos-caracteres",
                algorithm="HS256",
            )
            await send_registration_confirmed_email.original_func(
                "persona@example.com", str(uuid.uuid4()), "cancel-token", token
            )
    proveedor.send.assert_awaited_once()
    _args, kwargs = proveedor.send.call_args
    adjuntos = kwargs["attachments"]
    assert len(adjuntos) == 1
    adjunto = adjuntos[0]
    assert isinstance(adjunto, EmailAttachment)
    assert adjunto.filename == "entrada.png"
    assert adjunto.content.startswith(b"\x89PNG")
    assert "mi-entrada?token=cancel-token" in kwargs["body"]


async def test_flujo_completo_confirmar_escanear_duplicar_cancelar_revocar(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    """Test end-to-end de cierre de la fase 4 del PRD (Validation del plan)."""
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_y_publicar_evento(cliente, cabeceras, "flujo-completo", capacity=5)
    registration_id = await _inscribir_y_confirmar(
        cliente, organizacion, evento, "asistente@example.com"
    )

    async with SessionMaintenance() as session:
        ticket_id = await session.scalar(
            text("SELECT id FROM event_tickets WHERE registration_id = :id"),
            {"id": registration_id},
        )
    assert ticket_id is not None

    _, _, _, qr_token = send_registration_confirmed_email.kiq.call_args.args

    def _escanear() -> dict:
        return {
            "token": qr_token,
            "client_scan_id": str(uuid.uuid4()),
            "client_scanned_at": AHORA.isoformat(),
        }

    primero = await cliente.post(
        f"{EVENTS}/{evento['id']}/tickets/scan", headers=cabeceras, json=_escanear()
    )
    assert primero.status_code == 200, primero.text
    assert primero.json()["result"] == "valid"

    segundo = await cliente.post(
        f"{EVENTS}/{evento['id']}/tickets/scan", headers=cabeceras, json=_escanear()
    )
    assert segundo.json()["result"] == "duplicate"

    cancelacion = await cliente.post(
        f"{EVENTS}/{evento['id']}/registrations/{registration_id}/cancel", headers=cabeceras
    )
    assert cancelacion.status_code == 200, cancelacion.text

    async with SessionMaintenance() as session:
        revoked_at = await session.scalar(
            text("SELECT revoked_at FROM event_tickets WHERE id = :id"), {"id": ticket_id}
        )
    assert revoked_at is not None

    tercero = await cliente.post(
        f"{EVENTS}/{evento['id']}/tickets/scan", headers=cabeceras, json=_escanear()
    )
    assert tercero.json()["result"] == "revoked"


async def test_mi_entrada_confirmada_muestra_qr(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_y_publicar_evento(cliente, cabeceras, "mi-entrada-confirmada", capacity=5)
    await _inscribir_y_confirmar(cliente, organizacion, evento, "asistente@example.com")
    _, _, cancel_token, _ = send_registration_confirmed_email.kiq.call_args.args

    respuesta = await cliente.get(
        MY_TICKET, headers={"Host": organizacion.host}, params={"token": cancel_token}
    )

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["status"] == "confirmed"
    assert cuerpo["has_qr"] is True

    imagen = await cliente.get(
        MY_TICKET_QR, headers={"Host": organizacion.host}, params={"token": cancel_token}
    )
    assert imagen.status_code == 200, imagen.text
    assert imagen.headers["content-type"] == "image/png"
    assert imagen.content.startswith(b"\x89PNG")


async def test_mi_entrada_cancelada_no_muestra_qr(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_y_publicar_evento(cliente, cabeceras, "mi-entrada-cancelada", capacity=5)
    registration_id = await _inscribir_y_confirmar(
        cliente, organizacion, evento, "asistente@example.com"
    )
    _, _, cancel_token, _ = send_registration_confirmed_email.kiq.call_args.args

    cancelacion = await cliente.post(
        f"{EVENTS}/{evento['id']}/registrations/{registration_id}/cancel", headers=cabeceras
    )
    assert cancelacion.status_code == 200, cancelacion.text

    respuesta = await cliente.get(
        MY_TICKET, headers={"Host": organizacion.host}, params={"token": cancel_token}
    )

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["status"] == "cancelled"
    assert cuerpo["has_qr"] is False

    imagen = await cliente.get(
        MY_TICKET_QR, headers={"Host": organizacion.host}, params={"token": cancel_token}
    )
    assert imagen.status_code == 422


async def test_mi_entrada_con_token_invalido_falla(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    respuesta = await cliente.get(
        MY_TICKET, headers={"Host": organizacion.host}, params={"token": "inventado"}
    )
    assert respuesta.status_code == 422


async def test_mi_entrada_no_consume_el_token_de_cancelacion(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    """`peek_token`, no `consume_token`: consultar `/mi-entrada` no debe
    invalidar el enlace de cancelar que llegó en el mismo correo."""
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_y_publicar_evento(cliente, cabeceras, "mi-entrada-no-consume", capacity=5)
    registration_id = await _inscribir_y_confirmar(
        cliente, organizacion, evento, "asistente@example.com"
    )
    _, _, cancel_token, _ = send_registration_confirmed_email.kiq.call_args.args

    for _ in range(3):
        respuesta = await cliente.get(
            MY_TICKET, headers={"Host": organizacion.host}, params={"token": cancel_token}
        )
        assert respuesta.status_code == 200, respuesta.text

    cancelacion = await cliente.post(
        "/api/v1/public/registrations/cancel",
        headers={"Host": organizacion.host},
        json={"token": cancel_token},
    )
    assert cancelacion.status_code == 200, cancelacion.text

    async with SessionMaintenance() as session:
        estado = await session.scalar(
            text("SELECT status FROM event_registrations WHERE id = :id"),
            {"id": registration_id},
        )
    assert estado == "cancelled"
