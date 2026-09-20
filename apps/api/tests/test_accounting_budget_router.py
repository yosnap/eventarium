"""Endpoints HTTP de presupuesto, gastos y valoración en especie (fase 3 de
trabajo). Cubre lo que solo se puede probar a nivel de API real: concurrencia
verdadera (dos peticiones simultáneas, no dos llamadas de servicio en la
misma sesión), aislamiento cruzado entre organizaciones, y que la auditoría
deja fila real en `audit_log` tras la petición (no solo que se invoca la
función, hueco W6 que dejó abierto la fase 2)."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import func, select

from app.core.audit import AuditLog
from app.core.database import SessionMaintenance
from app.modules.events.models import Event
from app.modules.sponsors.models import Sponsor, SponsorTier
from tests.conftest import OrganizacionDePrueba, iniciar_sesion

AHORA = datetime.now(UTC).replace(microsecond=0)
BASE = "/api/v1/accounting"


async def _crear_evento(organizacion: OrganizacionDePrueba) -> uuid.UUID:
    async with SessionMaintenance() as session:
        evento = Event(
            organization_id=organizacion.id,
            slug=f"evento-presupuesto-router-{uuid.uuid4().hex[:8]}",
            title="Evento del router de presupuesto",
            status="published",
            visibility="public",
            starts_at=AHORA,
            ends_at=AHORA + timedelta(days=1),
            location_mode="online",
        )
        session.add(evento)
        await session.commit()
        return evento.id


async def _crear_sponsor_en_especie(
    organizacion: OrganizacionDePrueba, event_id: uuid.UUID
) -> uuid.UUID:
    async with SessionMaintenance() as session:
        nivel = SponsorTier(
            organization_id=organizacion.id, name=f"Nivel {uuid.uuid4().hex[:6]}", display_order=1
        )
        session.add(nivel)
        await session.flush()
        patrocinador = Sponsor(
            event_id=event_id,
            tier_id=nivel.id,
            organization_id=organizacion.id,
            name="Patrocinador en especie",
            contribution_type="en_especie",
        )
        session.add(patrocinador)
        await session.commit()
        return patrocinador.id


async def _contar_auditoria(action: str, entity_id: str) -> int:
    async with SessionMaintenance() as session:
        total = await session.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.action == action, AuditLog.entity_id == entity_id)
        )
    return total or 0


# --- Concurrencia real de la aprobación de presupuesto -----------------------


async def test_dos_aprobaciones_concurrentes_producen_una_sola_aprobacion(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    """El `SELECT ... FOR UPDATE` sobre `Event` (no sobre las partidas)
    serializa dos aprobaciones concurrentes: la segunda debe ver
    `budget_approved_at` ya informado y responder 409, sin corromper
    `contingency_fund_cents`."""
    event_id = await _crear_evento(organizacion)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    await cliente.post(
        f"{BASE}/events/{event_id}/budget-lines",
        headers=cabeceras,
        json={"name": "Catering", "budgeted_cents": 100_000},
    )

    respuestas = await asyncio.gather(
        cliente.post(f"{BASE}/events/{event_id}/budget/approve", headers=cabeceras),
        cliente.post(f"{BASE}/events/{event_id}/budget/approve", headers=cabeceras),
    )
    estados = sorted(respuesta.status_code for respuesta in respuestas)
    assert estados == [200, 409], [r.text for r in respuestas]

    exitosa = next(r for r in respuestas if r.status_code == 200)
    assert exitosa.json()["contingency_fund_cents"] is not None

    resumen = await cliente.get(f"{BASE}/events/{event_id}/budget/summary", headers=cabeceras)
    assert resumen.status_code == 200, resumen.text
    # 5% (por defecto) de 100_000 — sin corrupción por la doble petición.
    assert resumen.json()["contingency_fund_cents"] == 5_000


async def test_alta_de_partida_concurrente_con_aprobacion_nunca_deja_estado_inconsistente(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    """`_asegurar_presupuesto_editable` bloqueaba `Event` con una lectura sin
    `FOR UPDATE`: una alta de partida podía colarse a mitad de una
    aprobación concurrente e insertarse **después** de que `aprobar_presupuesto`
    ya hubiera calculado el total y fijado `contingency_fund_cents`, dejando
    una partida "fantasma" que ni el presupuesto aprobado contempla ni un 409
    rechaza — el fondo dotado deja de corresponder a la suma real de partidas.

    Con el bloqueo correcto solo hay dos desenlaces válidos, según qué
    transacción gane la carrera por la fila `Event`, y ambos son
    consistentes por construcción — no hay una única secuencia "correcta"
    que forzar, así que el test comprueba la invariante (el fondo dotado
    siempre corresponde a la suma real de partidas en ese instante), no un
    orden de llegada concreto:
    - la alta se resuelve **antes** de que la aprobación tome el bloqueo →
      ambas 200, y el total aprobado incluye la partida nueva; o
    - la aprobación toma el bloqueo primero → 200, y la alta que llega
      después ve `budget_approved_at` ya informado → 409.
    Lo que este bloqueo hace imposible es una tercera secuencia: que la
    partida se inserte **mientras** la aprobación ya ha leído el total pero
    aún no ha comprometido `contingency_fund_cents` — ahí es donde antes
    aparecía la partida fantasma."""
    event_id = await _crear_evento(organizacion)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    await cliente.post(
        f"{BASE}/events/{event_id}/budget-lines",
        headers=cabeceras,
        json={"name": "Catering", "budgeted_cents": 100_000},
    )

    aprobar, alta = await asyncio.gather(
        cliente.post(f"{BASE}/events/{event_id}/budget/approve", headers=cabeceras),
        cliente.post(
            f"{BASE}/events/{event_id}/budget-lines",
            headers=cabeceras,
            json={"name": "Seguridad", "budgeted_cents": 900_000},
        ),
    )
    assert aprobar.status_code == 200, aprobar.text
    assert alta.status_code in (200, 409), alta.text

    lineas = await cliente.get(f"{BASE}/events/{event_id}/budget-lines", headers=cabeceras)
    assert lineas.status_code == 200, lineas.text
    total_real = sum(linea["budgeted_cents"] for linea in lineas.json())

    resumen = await cliente.get(f"{BASE}/events/{event_id}/budget/summary", headers=cabeceras)
    assert resumen.status_code == 200, resumen.text
    cuerpo = resumen.json()
    # Invariante que el bloqueo garantiza pase lo que pase con la carrera:
    # el total y el fondo dotado siempre corresponden a las partidas que
    # realmente existían en el instante de aprobar — nunca a una cifra que
    # ignore una partida ya insertada, ni a una partida insertada después
    # que el fondo no contempló.
    assert cuerpo["total_budgeted_cents"] == total_real
    assert cuerpo["contingency_fund_cents"] == round(total_real * 5 / 100)
    if alta.status_code == 200:
        assert total_real == 1_000_000
    else:
        assert total_real == 100_000


async def test_reabrir_y_reaprobar_recalcula_contingencia(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    event_id = await _crear_evento(organizacion)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    alta = await cliente.post(
        f"{BASE}/events/{event_id}/budget-lines",
        headers=cabeceras,
        json={"name": "Catering", "budgeted_cents": 100_000},
    )
    linea_id = alta.json()["id"]

    sin_motivo = await cliente.post(
        f"{BASE}/events/{event_id}/budget/reopen", headers=cabeceras, json={"motivo": ""}
    )
    assert sin_motivo.status_code == 422, sin_motivo.text

    aprobar = await cliente.post(f"{BASE}/events/{event_id}/budget/approve", headers=cabeceras)
    assert aprobar.status_code == 200, aprobar.text

    editar_bloqueada = await cliente.patch(
        f"{BASE}/budget-lines/{linea_id}", headers=cabeceras, json={"budgeted_cents": 999}
    )
    assert editar_bloqueada.status_code == 409, editar_bloqueada.text

    reabrir = await cliente.post(
        f"{BASE}/events/{event_id}/budget/reopen",
        headers=cabeceras,
        json={"motivo": "Corrección de importe"},
    )
    assert reabrir.status_code == 200, reabrir.text
    assert reabrir.json()["budget_approved_at"] is None

    await cliente.patch(
        f"{BASE}/budget-lines/{linea_id}", headers=cabeceras, json={"budgeted_cents": 200_000}
    )
    reaprobar = await cliente.post(f"{BASE}/events/{event_id}/budget/approve", headers=cabeceras)
    assert reaprobar.status_code == 200, reaprobar.text
    assert reaprobar.json()["contingency_fund_cents"] == 10_000  # 5% de 200_000


# --- `EventUpdate` no puede alterar el presupuesto ---------------------------


async def test_patch_event_no_puede_escribir_budget_approved_at_ni_contingency_fund_cents(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    event_id = await _crear_evento(organizacion)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    await cliente.post(
        f"{BASE}/events/{event_id}/budget-lines",
        headers=cabeceras,
        json={"name": "Catering", "budgeted_cents": 10_000},
    )
    aprobar = await cliente.post(f"{BASE}/events/{event_id}/budget/approve", headers=cabeceras)
    assert aprobar.status_code == 200, aprobar.text

    intento = await cliente.patch(
        f"/api/v1/events/{event_id}",
        headers=cabeceras,
        json={"budget_approved_at": None, "contingency_fund_cents": 999_999_999},
    )
    assert intento.status_code == 200, intento.text
    # Ambos campos no están en `EventUpdate`: se ignoran, no anulan la aprobación.
    assert intento.json()["budget_approved_at"] is not None
    assert intento.json()["contingency_fund_cents"] != 999_999_999


async def test_contingency_fund_percent_no_editable_con_presupuesto_aprobado(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    event_id = await _crear_evento(organizacion)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    await cliente.post(f"{BASE}/events/{event_id}/budget/approve", headers=cabeceras)

    respuesta = await cliente.patch(
        f"/api/v1/events/{event_id}",
        headers=cabeceras,
        json={"contingency_fund_percent": "12.50"},
    )
    assert respuesta.status_code == 409, respuesta.text


# --- Aislamiento entre organizaciones -----------------------------------------


async def test_editar_partida_de_otra_organizacion_da_404(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    otra_organizacion: OrganizacionDePrueba,
) -> None:
    event_id_ajeno = await _crear_evento(otra_organizacion)
    _, cabeceras_ajenas = await iniciar_sesion(cliente, otra_organizacion)
    alta = await cliente.post(
        f"{BASE}/events/{event_id_ajeno}/budget-lines",
        headers=cabeceras_ajenas,
        json={"name": "Ajena", "budgeted_cents": 1_000},
    )
    linea_id_ajena = alta.json()["id"]

    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    respuesta = await cliente.patch(
        f"{BASE}/budget-lines/{linea_id_ajena}",
        headers=cabeceras,
        json={"budgeted_cents": 2_000},
    )
    assert respuesta.status_code == 404, respuesta.text


async def test_aprobar_presupuesto_de_un_evento_ajeno_da_404(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    otra_organizacion: OrganizacionDePrueba,
) -> None:
    event_id_ajeno = await _crear_evento(otra_organizacion)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    respuesta = await cliente.post(
        f"{BASE}/events/{event_id_ajeno}/budget/approve", headers=cabeceras
    )
    assert respuesta.status_code == 404, respuesta.text


async def test_fijar_valoracion_en_especie_de_sponsor_ajeno_da_404(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    otra_organizacion: OrganizacionDePrueba,
) -> None:
    event_id_ajeno = await _crear_evento(otra_organizacion)
    sponsor_id_ajeno = await _crear_sponsor_en_especie(otra_organizacion, event_id_ajeno)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    respuesta = await cliente.put(
        f"{BASE}/sponsors/{sponsor_id_ajeno}/in-kind-valuation",
        headers=cabeceras,
        json={"valoracion_cents": 1_000, "budget_line_id": str(uuid.uuid4())},
    )
    assert respuesta.status_code == 404, respuesta.text


# --- Auditoría: fila real en `audit_log`, no solo la llamada -----------------


async def test_aprobar_presupuesto_deja_fila_en_audit_log(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    event_id = await _crear_evento(organizacion)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    aprobar = await cliente.post(f"{BASE}/events/{event_id}/budget/approve", headers=cabeceras)
    assert aprobar.status_code == 200, aprobar.text

    assert await _contar_auditoria("accounting.budget.approved", str(event_id)) == 1


async def test_reabrir_presupuesto_deja_fila_en_audit_log(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    event_id = await _crear_evento(organizacion)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    await cliente.post(f"{BASE}/events/{event_id}/budget/approve", headers=cabeceras)
    reabrir = await cliente.post(
        f"{BASE}/events/{event_id}/budget/reopen",
        headers=cabeceras,
        json={"motivo": "Corrección"},
    )
    assert reabrir.status_code == 200, reabrir.text

    assert await _contar_auditoria("accounting.budget.reopened", str(event_id)) == 1


async def test_dar_de_alta_un_gasto_deja_fila_en_audit_log(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    event_id = await _crear_evento(organizacion)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    alta = await cliente.post(
        f"{BASE}/events/{event_id}/expenses",
        headers=cabeceras,
        json={
            "provider_name": "Catering S.L.",
            "expense_date": AHORA.isoformat(),
            "base_cents": 1_000,
            "vat_cents": 210,
            "total_cents": 1_210,
        },
    )
    assert alta.status_code == 200, alta.text
    gasto_id = alta.json()["id"]

    assert await _contar_auditoria("accounting_expense.created", gasto_id) == 1


async def test_total_cents_inconsistente_con_base_mas_iva_da_422(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    event_id = await _crear_evento(organizacion)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    respuesta = await cliente.post(
        f"{BASE}/events/{event_id}/expenses",
        headers=cabeceras,
        json={
            "provider_name": "Catering S.L.",
            "expense_date": AHORA.isoformat(),
            "base_cents": 1_000,
            "vat_cents": 210,
            "total_cents": 1_000,
        },
    )
    assert respuesta.status_code == 422, respuesta.text
