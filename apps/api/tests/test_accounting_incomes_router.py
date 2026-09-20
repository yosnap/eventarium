"""Endpoints HTTP de ingresos y datos de cobro de patrocinio (fase 2 de
trabajo). Aislamiento cruzado entre organizaciones vía la API real, no solo a
nivel de modelo (ese ya lo cubre `test_accounting_rls_isolation.py`)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient

from app.core.database import SessionMaintenance
from app.modules.events.models import Event
from app.modules.sponsors.models import Sponsor, SponsorTier
from tests.conftest import OrganizacionDePrueba, iniciar_sesion

AHORA = datetime.now(UTC).replace(microsecond=0)


async def _crear_evento_y_sponsor(
    organizacion: OrganizacionDePrueba,
) -> tuple[uuid.UUID, uuid.UUID]:
    async with SessionMaintenance() as session:
        evento = Event(
            organization_id=organizacion.id,
            slug=f"evento-router-{uuid.uuid4().hex[:8]}",
            title="Evento del router",
            status="published",
            visibility="public",
            starts_at=AHORA,
            ends_at=AHORA + timedelta(days=1),
            location_mode="online",
        )
        session.add(evento)
        await session.flush()
        nivel = SponsorTier(organization_id=organizacion.id, name="Oro", display_order=1)
        session.add(nivel)
        await session.flush()
        patrocinador = Sponsor(
            event_id=evento.id,
            tier_id=nivel.id,
            organization_id=organizacion.id,
            name="Patrocinador",
            contribution_type="monetaria",
            contribution_amount=100,
        )
        session.add(patrocinador)
        await session.commit()
        return evento.id, patrocinador.id


async def test_listar_ingresos_de_un_evento_ajeno_da_404(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    otra_organizacion: OrganizacionDePrueba,
) -> None:
    event_id_ajeno, _ = await _crear_evento_y_sponsor(otra_organizacion)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    respuesta = await cliente.get(
        f"/api/v1/accounting/events/{event_id_ajeno}/incomes", headers=cabeceras
    )
    assert respuesta.status_code == 404, respuesta.text


async def test_dar_de_alta_ingreso_con_origin_invalido_da_422(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    event_id, _ = await _crear_evento_y_sponsor(organizacion)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    respuesta = await cliente.post(
        f"/api/v1/accounting/events/{event_id}/incomes",
        headers=cabeceras,
        json={"origin": "colaborador", "concept": "X", "amount_cents": 1000},
    )
    assert respuesta.status_code == 422, respuesta.text


async def test_dar_de_alta_y_leer_una_subvencion_cobrada(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    event_id, _ = await _crear_evento_y_sponsor(organizacion)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    alta = await cliente.post(
        f"/api/v1/accounting/events/{event_id}/incomes",
        headers=cabeceras,
        json={
            "origin": "subvencion",
            "concept": "Ayuntamiento",
            "amount_cents": 15_000,
            "status": "collected",
        },
    )
    assert alta.status_code == 200, alta.text
    income_id = alta.json()["id"]

    vista = await cliente.get(f"/api/v1/accounting/events/{event_id}/incomes", headers=cabeceras)
    assert vista.status_code == 200, vista.text
    cuerpo = vista.json()
    assert any(fila["referencia_id"] == income_id for fila in cuerpo["ingresos"])

    edicion = await cliente.patch(
        f"/api/v1/accounting/incomes/{income_id}",
        headers=cabeceras,
        json={"amount_cents": 16_000},
    )
    assert edicion.status_code == 200, edicion.text
    assert edicion.json()["amount_cents"] == 16_000


async def test_no_se_puede_editar_un_ingreso_de_otra_organizacion(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    otra_organizacion: OrganizacionDePrueba,
) -> None:
    event_id_ajeno, _ = await _crear_evento_y_sponsor(otra_organizacion)
    _, cabeceras_ajenas = await iniciar_sesion(cliente, otra_organizacion)
    alta = await cliente.post(
        f"/api/v1/accounting/events/{event_id_ajeno}/incomes",
        headers=cabeceras_ajenas,
        json={"origin": "subvencion", "concept": "Ajena", "amount_cents": 1_000},
    )
    assert alta.status_code == 200, alta.text
    income_id_ajeno = alta.json()["id"]

    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    respuesta = await cliente.patch(
        f"/api/v1/accounting/incomes/{income_id_ajeno}",
        headers=cabeceras,
        json={"amount_cents": 2_000},
    )
    assert respuesta.status_code == 404, respuesta.text


async def test_fijar_datos_de_cobro_de_un_patrocinador_ajeno_da_404(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    otra_organizacion: OrganizacionDePrueba,
) -> None:
    _, sponsor_id_ajeno = await _crear_evento_y_sponsor(otra_organizacion)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    respuesta = await cliente.put(
        f"/api/v1/accounting/sponsors/{sponsor_id_ajeno}/payment-details",
        headers=cabeceras,
        json={"contact_name": "Intruso"},
    )
    assert respuesta.status_code == 404, respuesta.text


async def test_fijar_y_leer_datos_de_cobro_propios(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    event_id, sponsor_id = await _crear_evento_y_sponsor(organizacion)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    respuesta = await cliente.put(
        f"/api/v1/accounting/sponsors/{sponsor_id}/payment-details",
        headers=cabeceras,
        json={"contact_name": "Persona de contacto"},
    )
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["contact_name"] == "Persona de contacto"
    assert respuesta.json()["collected_at"] is None

    vista = await cliente.get(f"/api/v1/accounting/events/{event_id}/incomes", headers=cabeceras)
    assert vista.status_code == 200, vista.text
    assert any(fila["referencia_id"] == str(sponsor_id) for fila in vista.json()["comprometido"])
