"""Emisión y revocación automática de entradas QR.

Fase 4 del PRD, fase 1 de trabajo. Mismo patrón que
`test_registrations_public.py`/`test_registrations_organizer.py`: cliente
HTTP real, `Host` para resolver la organización, y las tareas de email
mockeadas (no se prueba la entrega).
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
from app.core.tasks import (
    send_registration_confirmed_email,
    send_registration_verification_email,
    send_waitlist_promotion_email,
)
from app.modules.auth.verification import (
    PROPOSITO_PROMOCION_LISTA_ESPERA,
    PROPOSITO_VERIFICACION_INSCRIPCION,
    generate_token,
)
from app.modules.events.models import Event
from app.modules.registrations.models import EventRegistration
from app.modules.tickets.models import EventTicket
from app.modules.tickets.service import emitir_entrada, generar_token_qr
from tests.conftest import OrganizacionDePrueba, iniciar_sesion

EVENTS = "/api/v1/events"
VERIFY = "/api/v1/public/registrations/verify"
CONFIRM_PROMOTION = "/api/v1/public/registrations/confirm-waitlist-promotion"
AHORA = datetime.now(UTC).replace(microsecond=0)


@pytest.fixture(autouse=True)
def _tareas_de_email_mockeadas():
    parches = [
        patch.object(send_registration_verification_email, "kiq", new_callable=AsyncMock),
        patch.object(send_registration_confirmed_email, "kiq", new_callable=AsyncMock),
        patch.object(send_waitlist_promotion_email, "kiq", new_callable=AsyncMock),
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


async def _inscribir(cliente: AsyncClient, host: str, slug: str, **overrides: object):
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
    return await cliente.post(
        f"/api/v1/public/events/{slug}/registrations", headers={"Host": host}, json=payload
    )


async def _crear_inscripcion(
    organizacion: OrganizacionDePrueba, evento: dict, *, email: str, status: str
) -> str:
    """Inserta una inscripción directamente, saltándose el formulario público
    (mismo helper que `test_registrations_organizer.py`)."""
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


async def _registration_id(event_id: str, email: str) -> str:
    async with SessionMaintenance() as session:
        valor = await session.scalar(
            text("SELECT id FROM event_registrations WHERE event_id = :e AND email = :m"),
            {"e": event_id, "m": email},
        )
    assert valor is not None
    return str(valor)


async def _ticket_de(registration_id: str) -> dict | None:
    async with SessionMaintenance() as session:
        fila = (
            await session.execute(
                text(
                    "SELECT id, revoked_at FROM event_tickets WHERE registration_id = :id"
                ),
                {"id": registration_id},
            )
        ).mappings().first()
    return dict(fila) if fila is not None else None


async def _contar_tickets(registration_id: str) -> int:
    async with SessionMaintenance() as session:
        total = await session.scalar(
            text("SELECT count(*) FROM event_tickets WHERE registration_id = :id"),
            {"id": registration_id},
        )
    return int(total or 0)


async def test_verificar_una_inscripcion_confirmada_emite_una_entrada(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_y_publicar_evento(cliente, cabeceras, "verificar-emite", capacity=5)
    await _inscribir(cliente, organizacion.host, "verificar-emite")
    registration_id = await _registration_id(evento["id"], "asistente@example.com")
    token = await generate_token(PROPOSITO_VERIFICACION_INSCRIPCION, registration_id)

    respuesta = await cliente.post(
        VERIFY, headers={"Host": organizacion.host}, json={"token": token}
    )

    assert respuesta.status_code == 200, respuesta.text
    ticket = await _ticket_de(registration_id)
    assert ticket is not None
    assert ticket["revoked_at"] is None


async def test_aprobar_una_inscripcion_pendiente_emite_una_entrada(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_y_publicar_evento(
        cliente, cabeceras, "aprobar-emite", registration_mode="approval", capacity=5
    )
    registration_id = await _crear_inscripcion(
        organizacion, evento, email="pendiente@example.com", status="pending_approval"
    )

    respuesta = await cliente.post(
        f"{EVENTS}/{evento['id']}/registrations/{registration_id}/approve", headers=cabeceras
    )

    assert respuesta.status_code == 200, respuesta.text
    assert await _ticket_de(registration_id) is not None


async def test_promover_desde_lista_de_espera_emite_una_entrada(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_y_publicar_evento(cliente, cabeceras, "promover-emite", capacity=1)
    confirmada_id = await _crear_inscripcion(
        organizacion, evento, email="confirmado@example.com", status="confirmed"
    )
    en_espera_id = await _crear_inscripcion(
        organizacion, evento, email="espera@example.com", status="waitlisted"
    )
    await cliente.post(
        f"{EVENTS}/{evento['id']}/registrations/{confirmada_id}/cancel", headers=cabeceras
    )
    token = await generate_token(PROPOSITO_PROMOCION_LISTA_ESPERA, en_espera_id)

    respuesta = await cliente.post(
        CONFIRM_PROMOTION, headers={"Host": organizacion.host}, json={"token": token}
    )

    assert respuesta.status_code == 200, respuesta.text
    assert await _ticket_de(en_espera_id) is not None


async def test_cancelar_una_confirmada_con_entrada_la_revoca(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_y_publicar_evento(cliente, cabeceras, "cancelar-revoca", capacity=5)
    await _inscribir(cliente, organizacion.host, "cancelar-revoca")
    registration_id = await _registration_id(evento["id"], "asistente@example.com")
    token = await generate_token(PROPOSITO_VERIFICACION_INSCRIPCION, registration_id)
    await cliente.post(VERIFY, headers={"Host": organizacion.host}, json={"token": token})
    assert (await _ticket_de(registration_id))["revoked_at"] is None

    respuesta = await cliente.post(
        f"{EVENTS}/{evento['id']}/registrations/{registration_id}/cancel", headers=cabeceras
    )

    assert respuesta.status_code == 200, respuesta.text
    ticket = await _ticket_de(registration_id)
    assert ticket is not None
    assert ticket["revoked_at"] is not None


async def test_cancelar_una_en_lista_de_espera_sin_entrada_no_falla(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_y_publicar_evento(cliente, cabeceras, "cancelar-sin-entrada", capacity=1)
    en_espera_id = await _crear_inscripcion(
        organizacion, evento, email="espera@example.com", status="waitlisted"
    )

    respuesta = await cliente.post(
        f"{EVENTS}/{evento['id']}/registrations/{en_espera_id}/cancel", headers=cabeceras
    )

    assert respuesta.status_code == 200, respuesta.text
    assert await _ticket_de(en_espera_id) is None


async def _crear_evento_directo(organizacion: OrganizacionDePrueba) -> Event:
    async with SessionMaintenance() as session:
        evento = Event(
            organization_id=organizacion.id,
            slug=f"evento-tickets-{uuid.uuid4().hex[:8]}",
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


async def test_emitir_entrada_dos_veces_no_crea_una_segunda_fila(
    organizacion: OrganizacionDePrueba,
) -> None:
    evento = await _crear_evento_directo(organizacion)
    async with SessionMaintenance() as session:
        inscripcion = EventRegistration(
            event_id=evento.id,
            organization_id=organizacion.id,
            email="doble@example.com",
            full_name="Asistente de Prueba",
            status="confirmed",
            confirmed_at=datetime.now(UTC),
        )
        session.add(inscripcion)
        await session.commit()
        await session.refresh(inscripcion)

        primera = await emitir_entrada(session, inscripcion)
        segunda = await emitir_entrada(session, inscripcion)
        await session.commit()

    assert primera.id == segunda.id
    assert await _contar_tickets(str(inscripcion.id)) == 1


async def test_generar_token_qr_es_verificable_con_el_mismo_secreto(
    organizacion: OrganizacionDePrueba,
) -> None:
    evento = await _crear_evento_directo(organizacion)
    ticket = EventTicket(
        event_id=evento.id, organization_id=organizacion.id, registration_id=uuid.uuid4()
    )
    ticket.event = evento

    token = generar_token_qr(ticket)

    settings = get_settings()
    payload = jwt.decode(token, settings.ticket_qr_secret, algorithms=[settings.jwt_algorithm])
    assert payload["tid"] == str(ticket.id)
    assert payload["eid"] == str(evento.id)
    assert "email" not in payload
    assert "name" not in payload

    with pytest.raises(jwt.PyJWTError):
        jwt.decode(token, "otro-secreto-cualquiera-de-mas-de-32-caracteres", algorithms=["HS256"])
