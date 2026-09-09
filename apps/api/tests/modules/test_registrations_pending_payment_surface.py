"""Superficie de API del estado `pending_payment` (fase 6 del PRD, fase 1 de
trabajo, hallazgo #6 del red-team): añadir el estado a la base de datos sin
actualizar `RegistrationStatus`/`RegistrationStats` en el mismo cambio rompe
con 500 el listado y las estadísticas de inscripciones en cuanto exista una
compra en curso.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient

from app.core.database import SessionMaintenance
from app.modules.events.models import Event
from app.modules.registrations.models import EventRegistration
from tests.conftest import OrganizacionDePrueba, iniciar_sesion

EVENTS = "/api/v1/events"

AHORA = datetime.now(UTC).replace(microsecond=0)


async def _crear_evento_de_pago(organizacion: OrganizacionDePrueba) -> Event:
    async with SessionMaintenance() as session:
        evento = Event(
            organization_id=organizacion.id,
            slug="evento-pending-payment",
            title="Evento de pago",
            status="published",
            visibility="public",
            starts_at=AHORA,
            ends_at=AHORA + timedelta(days=1),
            location_mode="online",
            registration_mode="paid",
        )
        session.add(evento)
        await session.commit()
        await session.refresh(evento)
    return evento


async def _crear_inscripcion_pending_payment(evento: Event) -> None:
    async with SessionMaintenance() as session:
        session.add(
            EventRegistration(
                event_id=evento.id,
                organization_id=evento.organization_id,
                email="comprador@example.com",
                full_name="Comprador de Prueba",
                status="pending_payment",
                payment_expires_at=AHORA + timedelta(minutes=30),
            )
        )
        await session.commit()


async def test_listado_de_inscripciones_no_da_500_con_pending_payment(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    evento = await _crear_evento_de_pago(organizacion)
    await _crear_inscripcion_pending_payment(evento)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    respuesta = await cliente.get(f"{EVENTS}/{evento.id}/registrations", headers=cabeceras)
    assert respuesta.status_code == 200, respuesta.text
    estados = {fila["status"] for fila in respuesta.json()["items"]}
    assert "pending_payment" in estados


async def test_estadisticas_no_dan_500_y_cuentan_pending_payment(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    evento = await _crear_evento_de_pago(organizacion)
    await _crear_inscripcion_pending_payment(evento)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    respuesta = await cliente.get(f"{EVENTS}/{evento.id}/registrations/stats", headers=cabeceras)
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["pending_payment"] == 1
