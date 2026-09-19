"""Exportación de balance (CSV/PDF) del libro contable de un evento, fase 5 de trabajo.

Snapshot inmutable de exportación (decisión de `validate`, Sesión 1, plan.md):
cada llamada a `generar_snapshot_csv`/`generar_snapshot_pdf` persiste el
fichero generado en el almacén privado de justificantes (mismo tratamiento de
acceso que la Decisión #7 — nunca `public_url`) y una fila en
`accounting_export_snapshots` **antes** de devolver la respuesta. Un balance
ya exportado se puede volver a descargar tal cual desde
`GET .../export/{snapshot_id}` sin recalcular nada, aunque después se edite
un patrocinador o se reabra el presupuesto.

Toda celda de texto de origen externo (`provider_name`, `concept`, campos
extraídos por OCR) pasa por `sanear_celda_csv` antes de escribirse en el CSV
(plan.md Decisión #20): un valor que empiece por `=+-@` o un tabulador/retorno
de carro se prefija con `'`, para que un lector de hojas de cálculo nunca lo
interprete como fórmula.
"""

from __future__ import annotations

import csv
import io
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from fastapi import BackgroundTasks
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    String,
    UniqueConstraint,
    select,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.audit import registrar_auditoria
from app.core.database import Base, TimestampMixin, maintenance_session
from app.core.storage import build_object_key, get_storage
from app.modules.accounting import repository
from app.modules.accounting.models import AccountingBudgetLine, AccountingExpense
from app.modules.accounting.repository import (
    LineaConsumoContingencia,
    LineaIngreso,
    PuntoSerieTemporal,
)
from app.modules.accounting.service import ResumenPresupuesto, resumen_presupuesto
from app.modules.accounting.service import saldo_cents as _saldo_cents
from app.modules.events.models import Event
from app.shared.errors import NotFoundError
from app.shared.identifiers import new_uuid7

ExportFormat = Literal["csv", "pdf"]

# Caracteres que un lector de hojas de cálculo interpreta como inicio de
# fórmula (`=`, `+`, `-`, `@`) o que rompen el formato CSV (tabulador, retorno
# de carro) si van al principio de una celda. Prefijar con `'` los neutraliza
# sin alterar el valor visible para quien lo abre.
_PREFIJOS_PELIGROSOS = ("=", "+", "-", "@", "\t", "\r")


def sanear_celda_csv(valor: str) -> str:
    """Neutraliza una celda de texto de origen externo contra inyección de
    fórmulas (plan.md Decisión #20). Único punto de saneado del módulo —
    cualquier exportación futura debe reutilizarlo, no reimplementarlo."""
    if valor.startswith(_PREFIJOS_PELIGROSOS):
        return f"'{valor}"
    return valor


class AccountingExportSnapshot(Base, TimestampMixin):
    """Una exportación de balance ya generada, inmutable tras crearse.

    `payload_object_key` apunta al fichero (CSV/PDF) tal y como se generó en
    ese instante, guardado en el mismo almacén privado que los justificantes
    de gasto (Decisión #7): nunca se recalcula al redescargarlo.
    """

    __tablename__ = "accounting_export_snapshots"
    __table_args__ = (
        ForeignKeyConstraint(
            ["event_id", "organization_id"],
            ["events.id", "events.organization_id"],
            name="fk_accounting_export_snapshots_event_id_organization_id",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "id", "organization_id", name="uq_accounting_export_snapshots_id_organization_id"
        ),
        CheckConstraint("format IN ('csv', 'pdf')", name="ck_accounting_export_snapshots_format"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_uuid7)
    event_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    format: Mapped[str] = mapped_column(String(10), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    generated_by_member_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    payload_object_key: Mapped[str] = mapped_column(String(500), nullable=False)


CONTENT_TYPES: dict[ExportFormat, str] = {
    "csv": "text/csv; charset=utf-8",
    "pdf": "application/pdf",
}


async def get_export_snapshot(
    session: AsyncSession, organization_id: uuid.UUID, snapshot_id: uuid.UUID
) -> AccountingExportSnapshot | None:
    resultado: AccountingExportSnapshot | None = await session.scalar(
        select(AccountingExportSnapshot).where(
            AccountingExportSnapshot.id == snapshot_id,
            AccountingExportSnapshot.organization_id == organization_id,
        )
    )
    return resultado


def _euros(cents: int) -> str:
    return f"{cents / 100:.2f}"


def _euros_opcional(cents: int | None) -> str:
    """`None` es "fondo de contingencia no definido", no "cero disponible" —
    mismo criterio que el panel (`event-accounting.ts`: muestra "—"), nunca
    `0.00` en un documento contable exportable (hallazgo M4 del code review
    de la fase 5)."""
    return "—" if cents is None else _euros(cents)


def _fecha(valor: datetime | None) -> str:
    return valor.date().isoformat() if valor is not None else ""


@dataclass(frozen=True, slots=True)
class _DatosBalance:
    """Mismo insumo para CSV y PDF: una sola consulta compuesta, reutilizando
    los repositorios de las fases 2-3 (nunca reimplementados aquí)."""

    resumen: ResumenPresupuesto
    ingresos: list[LineaIngreso]
    comprometido: list[LineaIngreso]
    moneda: str
    partidas_por_id: dict[uuid.UUID, AccountingBudgetLine]
    gastos: list[AccountingExpense]


async def _cargar_datos_balance(
    session: AsyncSession, *, organization_id: uuid.UUID, event_id: uuid.UUID, evento: Event
) -> _DatosBalance:
    resumen = await resumen_presupuesto(session, organization_id=organization_id, event_id=event_id)
    vista_ingresos = await repository.listar_ingresos(
        session,
        organization_id=organization_id,
        event_id=event_id,
        moneda_evento=evento.accounting_currency,
    )
    partidas = await repository.list_budget_lines(session, organization_id, event_id)
    gastos = await repository.list_expenses(session, organization_id, event_id)
    return _DatosBalance(
        resumen=resumen,
        ingresos=vista_ingresos.ingresos,
        comprometido=vista_ingresos.comprometido,
        moneda=vista_ingresos.moneda,
        partidas_por_id={partida.id: partida for partida in partidas},
        gastos=gastos,
    )


def _construir_csv(datos: _DatosBalance) -> bytes:
    buffer = io.StringIO()
    escritor = csv.writer(buffer)
    r = datos.resumen

    escritor.writerow(["Balance del evento — KPI"])
    escritor.writerow(["Presupuesto", _euros(r.total_budgeted_cents), datos.moneda])
    escritor.writerow(["Ejecutado en metálico", _euros(r.ejecutado_metalico_cents), datos.moneda])
    escritor.writerow(["Ejecutado en especie", _euros(r.ejecutado_en_especie_cents), datos.moneda])
    escritor.writerow(
        [
            "Ejecutado total",
            _euros(r.ejecutado_metalico_cents + r.ejecutado_en_especie_cents),
            datos.moneda,
        ]
    )
    total_ingresos = sum(linea.importe_cents for linea in datos.ingresos)
    escritor.writerow(["Ingresos", _euros(total_ingresos), datos.moneda])
    total_comprometido = sum(linea.importe_cents for linea in datos.comprometido)
    escritor.writerow(["Comprometido", _euros(total_comprometido), datos.moneda])
    escritor.writerow(["Saldo", _euros(_saldo_cents(r, total_ingresos)), datos.moneda])
    escritor.writerow(
        [
            "Contingencia disponible",
            _euros_opcional(r.disponible_contingencia_cents),
            datos.moneda,
        ]
    )
    escritor.writerow([])

    escritor.writerow(["Presupuesto frente a ejecutado"])
    escritor.writerow(["Partida", "Presupuesto", "Ejecutado", "% ejecutado"])
    for consumo in r.por_partida:
        nombre = (
            sanear_celda_csv(datos.partidas_por_id[consumo.budget_line_id].name)
            if consumo.budget_line_id is not None
            else "Sin partida"
        )
        pct = (
            f"{(consumo.ejecutado_cents / consumo.budgeted_cents * 100):.0f}%"
            if consumo.budgeted_cents > 0
            else "—"
        )
        escritor.writerow(
            [nombre, _euros(consumo.budgeted_cents), _euros(consumo.ejecutado_cents), pct]
        )
    escritor.writerow([])

    escritor.writerow(["Ingresos"])
    escritor.writerow(["Origen", "Concepto", "Fecha", "Importe"])
    for linea in datos.ingresos:
        escritor.writerow(
            [
                linea.origen,
                sanear_celda_csv(linea.concepto),
                _fecha(linea.fecha),
                _euros(linea.importe_cents),
            ]
        )
    escritor.writerow([])

    escritor.writerow(["Comprometido (pendiente de cobro)"])
    escritor.writerow(["Origen", "Concepto", "Fecha", "Importe"])
    for linea in datos.comprometido:
        escritor.writerow(
            [
                linea.origen,
                sanear_celda_csv(linea.concepto),
                _fecha(linea.fecha),
                _euros(linea.importe_cents),
            ]
        )
    escritor.writerow([])

    escritor.writerow(["Gastos"])
    escritor.writerow(["Proveedor", "Partida", "Fecha", "Base", "IVA", "Total", "En especie"])
    for gasto in datos.gastos:
        nombre_partida = (
            sanear_celda_csv(datos.partidas_por_id[gasto.budget_line_id].name)
            if gasto.budget_line_id is not None and gasto.budget_line_id in datos.partidas_por_id
            else "Sin partida"
        )
        escritor.writerow(
            [
                sanear_celda_csv(gasto.provider_name),
                nombre_partida,
                _fecha(gasto.expense_date),
                _euros(gasto.base_cents),
                _euros(gasto.vat_cents) if gasto.vat_cents is not None else "exento",
                _euros(gasto.total_cents),
                "sí" if gasto.sponsor_id is not None else "no",
            ]
        )
    escritor.writerow([])

    escritor.writerow(["Evolución temporal"])
    escritor.writerow(["Periodo", "Ingresos", "Gastos"])
    for punto in r.serie_temporal:
        escritor.writerow([punto.periodo, _euros(punto.ingresos_cents), _euros(punto.gastos_cents)])

    return buffer.getvalue().encode("utf-8-sig")


# --- Generador de PDF mínimo, sin dependencias externas ---------------------
#
# El proyecto no tiene ninguna librería de generación de PDF en
# `pyproject.toml` (verificado: sin `reportlab`/`weasyprint`/`fpdf` ni
# ningún otro generador de PDF en el resto del backend). En vez de añadir una
# dependencia nueva para un balance de texto plano, se construye a mano un
# PDF 1.4 válido (texto monoespaciado, Helvetica estándar, sin imágenes ni
# fuentes embebidas) — suficiente para "el balance exportado en PDF", sin
# pretender maquetación.


def _pdf_escapar(texto: str) -> str:
    return texto.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _pdf_generar(titulo: str, lineas: list[str]) -> bytes:
    todas = [titulo, ""] + lineas
    lineas_por_pagina = 58
    paginas = [
        todas[i : i + lineas_por_pagina] for i in range(0, len(todas), lineas_por_pagina)
    ] or [[""]]
    n = len(paginas)

    # Numeración de objetos: 1 Catalog, 2 Pages, 3..(2+n) Page, (3+n)..(2+2n)
    # Content, (3+2n) Font.
    id_catalogo = 1
    id_pages = 2
    ids_paginas = [3 + i for i in range(n)]
    ids_contenidos = [3 + n + i for i in range(n)]
    id_fuente = 3 + 2 * n

    objetos: dict[int, bytes] = {}
    objetos[id_catalogo] = f"<< /Type /Catalog /Pages {id_pages} 0 R >>".encode()
    kids = " ".join(f"{pid} 0 R" for pid in ids_paginas)
    objetos[id_pages] = f"<< /Type /Pages /Kids [{kids}] /Count {n} >>".encode()
    objetos[id_fuente] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>"

    for indice, (id_pagina, id_contenido, texto_pagina) in enumerate(
        zip(ids_paginas, ids_contenidos, paginas, strict=True)
    ):
        objetos[id_pagina] = (
            f"<< /Type /Page /Parent {id_pages} 0 R "
            f"/Resources << /Font << /F1 {id_fuente} 0 R >> >> "
            f"/MediaBox [0 0 612 792] /Contents {id_contenido} 0 R >>"
        ).encode()

        partes = ["BT", "/F1 9 Tf", "10 TL", "40 760 Td"]
        for j, linea in enumerate(texto_pagina):
            texto = _pdf_escapar(linea)
            if j == 0:
                partes.append(f"({texto}) Tj")
            else:
                partes.append(f"T* ({texto}) Tj")
        partes.append("ET")
        contenido_stream = "\n".join(partes).encode("latin-1", errors="replace")
        objetos[id_contenido] = (
            f"<< /Length {len(contenido_stream)} >>\nstream\n".encode()
            + contenido_stream
            + b"\nendstream"
        )
        del indice  # solo para claridad del bucle, no se usa

    salida = bytearray(b"%PDF-1.4\n")
    offsets: dict[int, int] = {}
    for id_obj in sorted(objetos):
        offsets[id_obj] = len(salida)
        salida += f"{id_obj} 0 obj\n".encode()
        salida += objetos[id_obj]
        salida += b"\nendobj\n"

    inicio_xref = len(salida)
    total_objetos = max(objetos) + 1
    salida += f"xref\n0 {total_objetos}\n".encode()
    salida += b"0000000000 65535 f \n"
    for id_obj in range(1, total_objetos):
        offset = offsets.get(id_obj, 0)
        salida += f"{offset:010d} 00000 n \n".encode()
    salida += (
        f"trailer\n<< /Size {total_objetos} /Root {id_catalogo} 0 R >>\n"
        f"startxref\n{inicio_xref}\n%%EOF"
    ).encode()
    return bytes(salida)


def _construir_pdf(datos: _DatosBalance) -> bytes:
    r = datos.resumen
    lineas: list[str] = []
    total_ingresos = sum(linea.importe_cents for linea in datos.ingresos)
    total_comprometido = sum(linea.importe_cents for linea in datos.comprometido)

    lineas.append("KPI")
    lineas.append(f"  Presupuesto: {_euros(r.total_budgeted_cents)} {datos.moneda}")
    lineas.append(f"  Ejecutado en metalico: {_euros(r.ejecutado_metalico_cents)} {datos.moneda}")
    lineas.append(f"  Ejecutado en especie: {_euros(r.ejecutado_en_especie_cents)} {datos.moneda}")
    lineas.append(
        f"  Ejecutado total: "
        f"{_euros(r.ejecutado_metalico_cents + r.ejecutado_en_especie_cents)} {datos.moneda}"
    )
    lineas.append(f"  Ingresos: {_euros(total_ingresos)} {datos.moneda}")
    lineas.append(f"  Comprometido: {_euros(total_comprometido)} {datos.moneda}")
    lineas.append(f"  Saldo: {_euros(_saldo_cents(r, total_ingresos))} {datos.moneda}")
    lineas.append(
        f"  Contingencia disponible: "
        f"{_euros_opcional(r.disponible_contingencia_cents)} {datos.moneda}"
    )
    lineas.append("")

    lineas.append("Presupuesto frente a ejecutado")
    for consumo in r.por_partida:
        nombre = (
            datos.partidas_por_id[consumo.budget_line_id].name
            if consumo.budget_line_id is not None
            else "Sin partida"
        )
        pct = (
            f"{(consumo.ejecutado_cents / consumo.budgeted_cents * 100):.0f}%"
            if consumo.budgeted_cents > 0
            else "-"
        )
        lineas.append(
            f"  {nombre}: {_euros(consumo.budgeted_cents)} presupuestado / "
            f"{_euros(consumo.ejecutado_cents)} ejecutado ({pct})"
        )
    lineas.append("")

    lineas.append("Ingresos")
    for linea in datos.ingresos:
        lineas.append(f"  {linea.origen} - {linea.concepto}: {_euros(linea.importe_cents)}")
    lineas.append("")

    lineas.append("Gastos")
    for gasto in datos.gastos:
        lineas.append(
            f"  {gasto.provider_name} ({_fecha(gasto.expense_date)}): {_euros(gasto.total_cents)}"
        )
    lineas.append("")

    lineas.append("Evolucion temporal")
    for punto in r.serie_temporal:
        lineas.append(
            f"  {punto.periodo}: ingresos {_euros(punto.ingresos_cents)} / "
            f"gastos {_euros(punto.gastos_cents)}"
        )

    return _pdf_generar("Balance del evento", lineas)


async def _auditar_exportacion(
    *,
    actor_user_id: uuid.UUID,
    organization_id: uuid.UUID,
    action: str,
    entity_id: str,
    detail: dict[str, object],
) -> None:
    async with maintenance_session() as auditoria:
        await registrar_auditoria(
            auditoria,
            actor_user_id=actor_user_id,
            organization_id=organization_id,
            action=action,
            entity_type="accounting_export_snapshot",
            entity_id=entity_id,
            detail=detail,
        )


async def _generar_snapshot(
    session: AsyncSession,
    background_tasks: BackgroundTasks,
    *,
    actor_user_id: uuid.UUID,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    evento: Event,
    formato: ExportFormat,
) -> tuple[AccountingExportSnapshot, bytes]:
    datos = await _cargar_datos_balance(
        session, organization_id=organization_id, event_id=event_id, evento=evento
    )
    contenido = _construir_csv(datos) if formato == "csv" else _construir_pdf(datos)

    almacen = get_storage()
    extension = "csv" if formato == "csv" else "pdf"
    clave = build_object_key(organization_id, "accounting-exports", extension)
    await almacen.put_object(
        clave, contenido, CONTENT_TYPES[formato], content_disposition="attachment"
    )

    snapshot = AccountingExportSnapshot(
        event_id=event_id,
        organization_id=organization_id,
        format=formato,
        generated_by_member_id=actor_user_id,
        payload_object_key=clave,
    )
    session.add(snapshot)
    await session.flush()

    background_tasks.add_task(
        _auditar_exportacion,
        actor_user_id=actor_user_id,
        organization_id=organization_id,
        action="accounting_export_snapshot.created",
        entity_id=str(snapshot.id),
        detail={"format": formato, "event_id": str(event_id)},
    )
    return snapshot, contenido


async def generar_snapshot_csv(
    session: AsyncSession,
    background_tasks: BackgroundTasks,
    *,
    actor_user_id: uuid.UUID,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    evento: Event,
) -> tuple[AccountingExportSnapshot, bytes]:
    return await _generar_snapshot(
        session,
        background_tasks,
        actor_user_id=actor_user_id,
        organization_id=organization_id,
        event_id=event_id,
        evento=evento,
        formato="csv",
    )


async def generar_snapshot_pdf(
    session: AsyncSession,
    background_tasks: BackgroundTasks,
    *,
    actor_user_id: uuid.UUID,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    evento: Event,
) -> tuple[AccountingExportSnapshot, bytes]:
    return await _generar_snapshot(
        session,
        background_tasks,
        actor_user_id=actor_user_id,
        organization_id=organization_id,
        event_id=event_id,
        evento=evento,
        formato="pdf",
    )


async def redescargar_snapshot(
    session: AsyncSession, *, organization_id: uuid.UUID, snapshot_id: uuid.UUID
) -> tuple[AccountingExportSnapshot, bytes]:
    """Lee `payload_object_key` tal cual: no recalcula ninguna cifra, así que
    editar un patrocinador o reabrir el presupuesto después de exportar no
    cambia lo que devuelve esta función."""
    snapshot = await get_export_snapshot(session, organization_id, snapshot_id)
    if snapshot is None:
        raise NotFoundError("Ese balance exportado no existe.")
    almacen = get_storage()
    contenido, _content_type = await almacen.get_object(snapshot.payload_object_key)
    return snapshot, contenido


__all__ = [
    "AccountingExportSnapshot",
    "CONTENT_TYPES",
    "ExportFormat",
    "PuntoSerieTemporal",
    "LineaConsumoContingencia",
    "generar_snapshot_csv",
    "generar_snapshot_pdf",
    "get_export_snapshot",
    "redescargar_snapshot",
    "sanear_celda_csv",
]
