"""Endpoints HTTP de exportación de balance (fase 5 de trabajo).

Cubre los criterios de éxito propios de esta fase: saneado de inyección de
fórmulas en CSV, snapshot inmutable (redescargar tras editar un patrocinador
no cambia el contenido), aislamiento cruzado entre organizaciones,
comprobación explícita de organización, auditoría real en `audit_log`, y que
la evolución temporal no revienta con un evento sin movimientos.
"""

from __future__ import annotations

import csv
import io
import uuid
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import func, select

from app.core.audit import AuditLog
from app.core.database import SessionMaintenance
from app.core.permissions import Permission
from app.modules.accounting.export import AccountingExportSnapshot
from app.modules.events.models import Event
from app.modules.sponsors.models import Sponsor, SponsorTier
from tests.conftest import (
    OrganizacionDePrueba,
    crear_miembro,
    crear_rol,
    iniciar_sesion,
    iniciar_sesion_con,
)

AHORA = datetime.now(UTC).replace(microsecond=0)
BASE = "/api/v1/accounting"


async def _crear_evento(organizacion: OrganizacionDePrueba, *, dias: int = 10) -> uuid.UUID:
    async with SessionMaintenance() as session:
        evento = Event(
            organization_id=organizacion.id,
            slug=f"evento-export-{uuid.uuid4().hex[:8]}",
            title="Evento de exportación",
            status="published",
            visibility="public",
            starts_at=AHORA,
            ends_at=AHORA + timedelta(days=dias),
            location_mode="online",
        )
        session.add(evento)
        await session.commit()
        return evento.id


async def _contar_snapshots(event_id: uuid.UUID) -> int:
    async with SessionMaintenance() as session:
        total = await session.scalar(
            select(func.count())
            .select_from(AccountingExportSnapshot)
            .where(AccountingExportSnapshot.event_id == event_id)
        )
    return total or 0


async def _contar_auditoria(action: str) -> int:
    async with SessionMaintenance() as session:
        total = await session.scalar(
            select(func.count()).select_from(AuditLog).where(AuditLog.action == action)
        )
    return total or 0


async def test_export_csv_sanea_inyeccion_de_formulas(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    event_id = await _crear_evento(organizacion)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    linea = await cliente.post(
        f"{BASE}/events/{event_id}/budget-lines",
        headers=cabeceras,
        json={"name": "Producción", "budgeted_cents": 500_00},
    )
    assert linea.status_code == 200, linea.text
    budget_line_id = linea.json()["id"]

    gasto = await cliente.post(
        f"{BASE}/events/{event_id}/expenses",
        headers=cabeceras,
        json={
            "budget_line_id": budget_line_id,
            "provider_name": "=1+1",
            "expense_date": AHORA.isoformat(),
            "base_cents": 100_00,
            "vat_cents": 21_00,
            "total_cents": 121_00,
        },
    )
    assert gasto.status_code == 200, gasto.text

    ingreso = await cliente.post(
        f"{BASE}/events/{event_id}/incomes",
        headers=cabeceras,
        json={
            "origin": "subvencion",
            "concept": '=HYPERLINK("http://evil.example")',
            "amount_cents": 1_000_00,
            "status": "collected",
            "collected_at": AHORA.isoformat(),
        },
    )
    assert ingreso.status_code == 200, ingreso.text

    respuesta = await cliente.get(f"{BASE}/events/{event_id}/export.csv", headers=cabeceras)
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.headers["content-type"].startswith("text/csv")

    texto = respuesta.content.decode("utf-8-sig")
    filas = list(csv.reader(io.StringIO(texto)))
    aplanado = [celda for fila in filas for celda in fila]

    # Ninguna celda que empezaba por `=` sobrevive sin el prefijo `'`: si el
    # saneado fallara, el texto crudo `=1+1` o `=HYPERLINK(...)` aparecería
    # tal cual en el CSV, interpretable como fórmula al abrirlo.
    assert "=1+1" not in aplanado
    assert any(celda == "'=1+1" for celda in aplanado), aplanado
    assert not any(celda.startswith("=HYPERLINK") for celda in aplanado)
    assert any(celda.startswith("'=HYPERLINK") for celda in aplanado), aplanado


async def test_cada_exportacion_crea_un_snapshot_nuevo(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    event_id = await _crear_evento(organizacion)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    assert await _contar_snapshots(event_id) == 0

    r1 = await cliente.get(f"{BASE}/events/{event_id}/export.csv", headers=cabeceras)
    assert r1.status_code == 200, r1.text
    r2 = await cliente.get(f"{BASE}/events/{event_id}/export.pdf", headers=cabeceras)
    assert r2.status_code == 200, r2.text
    assert r2.headers["content-type"].startswith("application/pdf")
    # Un PDF hecho a mano pero sintácticamente válido: cabecera y EOF reales.
    assert r2.content.startswith(b"%PDF-1.4")
    assert r2.content.rstrip().endswith(b"%%EOF")

    assert await _contar_snapshots(event_id) == 2
    assert (
        r1.headers["X-Accounting-Export-Snapshot-Id"]
        != r2.headers["X-Accounting-Export-Snapshot-Id"]
    )


async def test_redescargar_snapshot_no_cambia_tras_editar_un_patrocinador(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    event_id = await _crear_evento(organizacion)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    linea = await cliente.post(
        f"{BASE}/events/{event_id}/budget-lines",
        headers=cabeceras,
        json={"name": "Espacio", "budgeted_cents": 200_00},
    )
    budget_line_id = linea.json()["id"]

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
        sponsor_id = patrocinador.id

    valoracion = await cliente.put(
        f"{BASE}/sponsors/{sponsor_id}/in-kind-valuation",
        headers=cabeceras,
        json={"valoracion_cents": 50_00, "budget_line_id": budget_line_id},
    )
    assert valoracion.status_code == 200, valoracion.text

    exportacion = await cliente.get(f"{BASE}/events/{event_id}/export.csv", headers=cabeceras)
    assert exportacion.status_code == 200, exportacion.text
    snapshot_id = exportacion.headers["X-Accounting-Export-Snapshot-Id"]
    contenido_original = exportacion.content

    # Se cambia la valoración DESPUÉS de exportar: el snapshot ya generado no
    # debe reflejar el cambio al redescargarlo.
    cambio = await cliente.put(
        f"{BASE}/sponsors/{sponsor_id}/in-kind-valuation",
        headers=cabeceras,
        json={"valoracion_cents": 9_999_00, "budget_line_id": budget_line_id},
    )
    assert cambio.status_code == 200, cambio.text

    redescarga = await cliente.get(
        f"{BASE}/events/{event_id}/export/{snapshot_id}", headers=cabeceras
    )
    assert redescarga.status_code == 200, redescarga.text
    assert redescarga.content == contenido_original

    # El panel en vivo (resumen), en cambio, sí refleja el cambio: confirma
    # que la diferencia es del snapshot, no de que el cambio no se aplicó.
    resumen = await cliente.get(f"{BASE}/events/{event_id}/budget/summary", headers=cabeceras)
    assert resumen.json()["ejecutado_en_especie_cents"] == 9_999_00


async def test_export_aislamiento_entre_organizaciones(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    otra_organizacion: OrganizacionDePrueba,
) -> None:
    event_id = await _crear_evento(organizacion)
    _, cabeceras_propias = await iniciar_sesion(cliente, organizacion)
    exportacion = await cliente.get(
        f"{BASE}/events/{event_id}/export.csv", headers=cabeceras_propias
    )
    assert exportacion.status_code == 200, exportacion.text
    snapshot_id = exportacion.headers["X-Accounting-Export-Snapshot-Id"]

    _, cabeceras_ajenas = await iniciar_sesion(cliente, otra_organizacion)

    sin_acceso_evento = await cliente.get(
        f"{BASE}/events/{event_id}/export.csv", headers=cabeceras_ajenas
    )
    assert sin_acceso_evento.status_code == 404, sin_acceso_evento.text

    sin_acceso_snapshot = await cliente.get(
        f"{BASE}/events/{event_id}/export/{snapshot_id}", headers=cabeceras_ajenas
    )
    assert sin_acceso_snapshot.status_code == 404, sin_acceso_snapshot.text


async def test_export_sin_sesion_devuelve_401(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    event_id = await _crear_evento(organizacion)
    respuesta = await cliente.get(
        f"{BASE}/events/{event_id}/export.csv", headers={"Host": organizacion.host}
    )
    assert respuesta.status_code == 401, respuesta.text


async def test_export_con_sesion_sin_permiso_de_contabilidad_devuelve_403(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    """`M5` del code review de la fase 5: el 401 de sin-sesión no cubría el
    `require_permission` real de los tres endpoints nuevos — un miembro
    autenticado pero sin ningún permiso de contabilidad debe recibir 403, no
    401."""
    event_id = await _crear_evento(organizacion)
    await crear_rol(organizacion, key="sin_contabilidad", permisos=[])
    persona = await crear_miembro(organizacion, "sin_contabilidad")
    _, cabeceras = await iniciar_sesion_con(cliente, organizacion, persona.email, persona.password)

    respuesta = await cliente.get(f"{BASE}/events/{event_id}/export.csv", headers=cabeceras)
    assert respuesta.status_code == 403, respuesta.text


async def test_export_con_solo_permiso_de_lectura_devuelve_403(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    """`M1` del code review de la fase 5: exportar crea un snapshot (muta
    estado, sube un fichero al storage privado), así que debe exigir
    `accounting:write` igual que cualquier otra mutación del módulo — un rol
    con solo `accounting:read` no puede exportar, aunque sí puede leer el
    resumen del panel."""
    event_id = await _crear_evento(organizacion)
    await crear_rol(
        organizacion, key="contabilidad_solo_lectura", permisos=[Permission.ACCOUNTING_READ]
    )
    persona = await crear_miembro(organizacion, "contabilidad_solo_lectura")
    _, cabeceras = await iniciar_sesion_con(cliente, organizacion, persona.email, persona.password)

    resumen = await cliente.get(f"{BASE}/events/{event_id}/budget/summary", headers=cabeceras)
    assert resumen.status_code == 200, resumen.text

    exportacion = await cliente.get(f"{BASE}/events/{event_id}/export.csv", headers=cabeceras)
    assert exportacion.status_code == 403, exportacion.text

    exportacion_pdf = await cliente.get(f"{BASE}/events/{event_id}/export.pdf", headers=cabeceras)
    assert exportacion_pdf.status_code == 403, exportacion_pdf.text


async def test_export_con_snapshot_id_malformado_devuelve_422(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    event_id = await _crear_evento(organizacion)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    respuesta = await cliente.get(
        f"{BASE}/events/{event_id}/export/no-es-un-uuid", headers=cabeceras
    )
    assert respuesta.status_code == 422, respuesta.text


async def test_exportacion_deja_fila_de_auditoria(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    event_id = await _crear_evento(organizacion)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    antes = await _contar_auditoria("accounting_export_snapshot.created")
    respuesta = await cliente.get(f"{BASE}/events/{event_id}/export.pdf", headers=cabeceras)
    assert respuesta.status_code == 200, respuesta.text

    despues = await _contar_auditoria("accounting_export_snapshot.created")
    assert despues == antes + 1


async def test_evolucion_temporal_sin_movimientos_no_revienta(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    event_id = await _crear_evento(organizacion)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    resumen = await cliente.get(f"{BASE}/events/{event_id}/budget/summary", headers=cabeceras)
    assert resumen.status_code == 200, resumen.text
    assert resumen.json()["evolucion_temporal"] == []


async def test_evolucion_temporal_agrega_ingresos_y_gastos_confirmados(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    event_id = await _crear_evento(organizacion, dias=200)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    linea = await cliente.post(
        f"{BASE}/events/{event_id}/budget-lines",
        headers=cabeceras,
        json={"name": "Catering", "budgeted_cents": 500_00},
    )
    budget_line_id = linea.json()["id"]

    await cliente.post(
        f"{BASE}/events/{event_id}/expenses",
        headers=cabeceras,
        json={
            "budget_line_id": budget_line_id,
            "provider_name": "Proveedor real",
            "expense_date": AHORA.isoformat(),
            "base_cents": 100_00,
            "vat_cents": 21_00,
            "total_cents": 121_00,
        },
    )
    await cliente.post(
        f"{BASE}/events/{event_id}/incomes",
        headers=cabeceras,
        json={
            "origin": "subvencion",
            "concept": "Ayuntamiento",
            "amount_cents": 1_000_00,
            "status": "collected",
            "collected_at": AHORA.isoformat(),
        },
    )

    resumen = await cliente.get(f"{BASE}/events/{event_id}/budget/summary", headers=cabeceras)
    serie = resumen.json()["evolucion_temporal"]
    assert len(serie) >= 1
    # Evento de 200 días: granularidad mensual (`AAAA-MM`).
    assert all(len(punto["periodo"]) == 7 and punto["periodo"][4] == "-" for punto in serie)
    total_ingresos = sum(p["ingresos_cents"] for p in serie)
    total_gastos = sum(p["gastos_cents"] for p in serie)
    assert total_ingresos == 1_000_00
    assert total_gastos == 121_00


async def _dar_de_alta_escenario_de_saldo(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, cabeceras: dict[str, str]
) -> uuid.UUID:
    """Escenario exacto del hallazgo Crítico C1 del code review de la fase 5:
    gasto con partida 100 €, gasto sin partida 50 €, ingreso (subvención)
    1.000 €, aportación en especie 200 €. Saldo de caja esperado: 1.200 € de
    ingresos (1.000 + 200 en especie) menos 350 € ejecutado (150 en metálico
    + 200 en especie) = 850 €."""
    event_id = await _crear_evento(organizacion, dias=10)

    linea = await cliente.post(
        f"{BASE}/events/{event_id}/budget-lines",
        headers=cabeceras,
        json={"name": "Producción", "budgeted_cents": 500_00},
    )
    assert linea.status_code == 200, linea.text
    budget_line_id = linea.json()["id"]

    con_partida = await cliente.post(
        f"{BASE}/events/{event_id}/expenses",
        headers=cabeceras,
        json={
            "budget_line_id": budget_line_id,
            "provider_name": "Proveedor con partida",
            "expense_date": AHORA.isoformat(),
            "base_cents": 100_00,
            "vat_cents": None,
            "total_cents": 100_00,
        },
    )
    assert con_partida.status_code == 200, con_partida.text

    sin_partida = await cliente.post(
        f"{BASE}/events/{event_id}/expenses",
        headers=cabeceras,
        json={
            "budget_line_id": None,
            "provider_name": "Proveedor sin partida",
            "expense_date": AHORA.isoformat(),
            "base_cents": 50_00,
            "vat_cents": None,
            "total_cents": 50_00,
        },
    )
    assert sin_partida.status_code == 200, sin_partida.text

    ingreso = await cliente.post(
        f"{BASE}/events/{event_id}/incomes",
        headers=cabeceras,
        json={
            "origin": "subvencion",
            "concept": "Ayuntamiento",
            "amount_cents": 1_000_00,
            "status": "collected",
            "collected_at": AHORA.isoformat(),
        },
    )
    assert ingreso.status_code == 200, ingreso.text

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
        sponsor_id = patrocinador.id

    valoracion = await cliente.put(
        f"{BASE}/sponsors/{sponsor_id}/in-kind-valuation",
        headers=cabeceras,
        json={"valoracion_cents": 200_00, "budget_line_id": budget_line_id},
    )
    assert valoracion.status_code == 200, valoracion.text

    return event_id


async def test_saldo_del_export_coincide_con_el_del_resumen_del_panel(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    """Regresión del hallazgo Crítico C1 del code review de la fase 5: el
    "Saldo" del CSV restaba `gasto_sin_partida_cents` dos veces (ya incluido
    en `ejecutado_metalico_cents`) y nunca restaba la especie, dando
    1.000,00 € en vez de los 850,00 € correctos."""
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    event_id = await _dar_de_alta_escenario_de_saldo(cliente, organizacion, cabeceras)

    resumen = (
        await cliente.get(f"{BASE}/events/{event_id}/budget/summary", headers=cabeceras)
    ).json()
    ingresos = (await cliente.get(f"{BASE}/events/{event_id}/incomes", headers=cabeceras)).json()

    ejecutado_metalico = sum(linea["ejecutado_cents"] for linea in resumen["por_partida"])
    assert ejecutado_metalico == 150_00
    assert resumen["ejecutado_en_especie_cents"] == 200_00
    assert ingresos["total_ingresos_cents"] == 1_200_00
    saldo_esperado = ingresos["total_ingresos_cents"] - (
        ejecutado_metalico + resumen["ejecutado_en_especie_cents"]
    )
    assert saldo_esperado == 850_00

    exportacion = await cliente.get(f"{BASE}/events/{event_id}/export.csv", headers=cabeceras)
    assert exportacion.status_code == 200, exportacion.text
    texto = exportacion.content.decode("utf-8-sig")
    filas: dict[str, list[str]] = {}
    for fila in csv.reader(io.StringIO(texto)):
        if fila and fila[0] not in filas:
            filas[fila[0]] = fila

    assert filas["Saldo"][1] == f"{saldo_esperado / 100:.2f}"
    assert filas["Ingresos"][1] == f"{ingresos['total_ingresos_cents'] / 100:.2f}"
    assert filas["Ejecutado en metálico"][1] == f"{ejecutado_metalico / 100:.2f}"
    assert filas["Ejecutado en especie"][1] == "200.00"


async def test_evolucion_temporal_excluye_movimientos_en_especie_de_ambos_lados(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    """Regresión del hallazgo Alto A2 del code review de la fase 5: la serie
    temporal descartaba los ingresos en especie (`fecha is None`) pero sumaba
    igualmente el gasto en especie enlazado, dando una serie asimétrica
    (1.000 €/350 € en vez de los 1.000 €/150 € consistentes con "Ejecutado
    en metálico"). Se excluyen ambos lados de la serie (Decisión: la
    evolución temporal es una vista de caja real, igual que
    `consumo_contingencia`), y la especie sigue visible en su propio KPI."""
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    event_id = await _dar_de_alta_escenario_de_saldo(cliente, organizacion, cabeceras)

    resumen = (
        await cliente.get(f"{BASE}/events/{event_id}/budget/summary", headers=cabeceras)
    ).json()
    serie = resumen["evolucion_temporal"]

    total_ingresos_serie = sum(p["ingresos_cents"] for p in serie)
    total_gastos_serie = sum(p["gastos_cents"] for p in serie)
    ejecutado_metalico = sum(linea["ejecutado_cents"] for linea in resumen["por_partida"])

    # La subvención (1.000 €, con fecha) sí entra; la especie (200 €, sin
    # fecha real) no — igual que antes del fix.
    assert total_ingresos_serie == 1_000_00
    # Los gastos de la serie deben cuadrar con "Ejecutado en metálico"
    # (150 €): el gasto en especie enlazado (200 €) queda fuera, simétrico
    # con el lado de ingresos.
    assert total_gastos_serie == ejecutado_metalico == 150_00


async def test_export_muestra_contingencia_no_definida_como_guion(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    """Regresión del hallazgo Medio M4: sin fondo de contingencia dotado
    (presupuesto no aprobado), el CSV debe mostrar "—", no "0.00" — un
    balance exportado no puede inventar una cifra que el dato no tiene."""
    event_id = await _crear_evento(organizacion)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    exportacion = await cliente.get(f"{BASE}/events/{event_id}/export.csv", headers=cabeceras)
    assert exportacion.status_code == 200, exportacion.text
    texto = exportacion.content.decode("utf-8-sig")
    filas: dict[str, list[str]] = {}
    for fila in csv.reader(io.StringIO(texto)):
        if fila and fila[0] not in filas:
            filas[fila[0]] = fila
    assert filas["Contingencia disponible"][1] == "—"
