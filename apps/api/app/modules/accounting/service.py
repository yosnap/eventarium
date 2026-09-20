"""Servicios de ingresos y datos de cobro de patrocinio (fase 2 de trabajo).

Toda mutación registra auditoría (plan.md Decisión #17) como `BackgroundTask`
—verificado: corre tras el `commit` real de la transacción principal, porque
`core/deps.py` declara la sesión con `scope="function"` y su salida se
adelanta a las tareas de fondo—, nunca inline dentro de la transacción de la
petición: si el
`commit` fallara después de escribir la auditoría (o la propia respuesta
fallara al serializarse), quedaría una entrada describiendo un cambio
financiero que nunca ocurrió. Mismo patrón que
`roles/service.py:_registrar_cambio_de_permisos`, no el que sugiere leer
`registrar_auditoria`/`maintenance_session` a secas.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from fastapi import BackgroundTasks
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import registrar_auditoria
from app.core.database import maintenance_session
from app.modules.accounting import repository
from app.modules.accounting.models import (
    AccountingBudgetLine,
    AccountingExpense,
    AccountingIncome,
    SponsorPaymentDetail,
)
from app.modules.accounting.repository import LineaConsumoContingencia, PuntoSerieTemporal
from app.modules.events import repository as events_repository
from app.modules.events.models import Event
from app.modules.sponsors.models import Sponsor
from app.shared.errors import ConflictError, NotFoundError, ValidationDomainError

# Único valor admitido por el `CHECK` de BD (`models.py:89`) — el servicio
# devuelve un 422 legible en vez de dejar que un `origin` distinto llegue a
# provocar un `IntegrityError` crudo (500 sin traducir).
_ORIGENES_PERMITIDOS = ("subvencion",)


async def auditar(
    *,
    actor_user_id: uuid.UUID,
    organization_id: uuid.UUID,
    action: str,
    entity_type: str,
    entity_id: str,
    detail: dict[str, Any],
) -> None:
    """Cuerpo de la `BackgroundTask` de auditoría de todo el módulo (también de
    `drafts_service.py`, de ahí que sea pública y no `_auditar`): abre su propia sesión de
    mantenimiento porque `audit_log` tiene `REVOKE ALL ... FROM app_user`
    (`core/audit.py:13-20`) y ya se ejecuta fuera del ciclo de vida de la
    sesión de la petición."""
    async with maintenance_session() as auditoria:
        await registrar_auditoria(
            auditoria,
            actor_user_id=actor_user_id,
            organization_id=organization_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            detail=detail,
        )


async def crear_ingreso_manual(
    session: AsyncSession,
    background_tasks: BackgroundTasks,
    *,
    actor_user_id: uuid.UUID,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    datos: dict[str, Any],
) -> AccountingIncome:
    if datos["origin"] not in _ORIGENES_PERMITIDOS:
        raise ValidationDomainError(
            "El único origen admitido para un ingreso manual es «subvencion»."
        )

    ingreso = AccountingIncome(event_id=event_id, organization_id=organization_id, **datos)
    session.add(ingreso)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError("No se ha podido dar de alta el ingreso.") from exc

    background_tasks.add_task(
        auditar,
        actor_user_id=actor_user_id,
        organization_id=organization_id,
        action="accounting_income.created",
        entity_type="accounting_income",
        entity_id=str(ingreso.id),
        detail={"origin": ingreso.origin, "amount_cents": ingreso.amount_cents},
    )
    return ingreso


async def editar_ingreso_manual(
    session: AsyncSession,
    background_tasks: BackgroundTasks,
    *,
    actor_user_id: uuid.UUID,
    organization_id: uuid.UUID,
    income_id: uuid.UUID,
    datos: dict[str, Any],
) -> AccountingIncome:
    ingreso = await repository.get_income(session, organization_id, income_id)
    if ingreso is None:
        raise NotFoundError("Ese ingreso no existe.")

    valores_anteriores = {
        "concept": ingreso.concept,
        "amount_cents": ingreso.amount_cents,
        "status": ingreso.status,
    }
    for campo, valor in datos.items():
        setattr(ingreso, campo, valor)

    try:
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError("No se han podido guardar los cambios del ingreso.") from exc

    background_tasks.add_task(
        auditar,
        actor_user_id=actor_user_id,
        organization_id=organization_id,
        action="accounting_income.updated",
        entity_type="accounting_income",
        entity_id=str(ingreso.id),
        detail={"antes": valores_anteriores, "despues": datos},
    )
    return ingreso


async def fijar_datos_de_cobro_de_patrocinador(
    session: AsyncSession,
    background_tasks: BackgroundTasks,
    *,
    actor_user_id: uuid.UUID,
    organization_id: uuid.UUID,
    sponsor_id: uuid.UUID,
    datos: dict[str, Any],
) -> SponsorPaymentDetail:
    """Alta/edición en una única fila (`UNIQUE(sponsor_id)`, plan.md Decisión
    #21): upsert explícito en vez de un `INSERT ... ON CONFLICT` para poder
    distinguir alta de edición en la auditoría, igual que el resto del
    proyecto trata sus upserts de una sola fila (p. ej. `SponsorPaymentDetail`
    no tiene ningún volumen que justifique la escritura atómica de BD)."""
    detalle = await repository.get_sponsor_payment_detail(session, organization_id, sponsor_id)
    accion = "accounting_sponsor_payment_detail.updated"
    if detalle is None:
        detalle = SponsorPaymentDetail(sponsor_id=sponsor_id, organization_id=organization_id)
        session.add(detalle)
        accion = "accounting_sponsor_payment_detail.created"

    for campo, valor in datos.items():
        setattr(detalle, campo, valor)

    try:
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError(
            "No se han podido guardar los datos de cobro del patrocinador."
        ) from exc

    background_tasks.add_task(
        auditar,
        actor_user_id=actor_user_id,
        organization_id=organization_id,
        action=accion,
        entity_type="sponsor_payment_detail",
        entity_id=str(detalle.id),
        detail={
            "sponsor_id": str(sponsor_id),
            "collected_at": detalle.collected_at.isoformat() if detalle.collected_at else None,
        },
    )
    return detalle


# --- Presupuesto: aprobación, reapertura y partidas (fase 3 de trabajo) ------


async def _asegurar_presupuesto_editable(
    session: AsyncSession, organization_id: uuid.UUID, event_id: uuid.UUID
) -> None:
    """Bloquea `Event` con el mismo `FOR UPDATE` que `aprobar_presupuesto`
    (nunca una lectura simple): sin este bloqueo, un alta/edición/borrado de
    partida puede colarse a mitad de una aprobación concurrente y dejar una
    partida en un presupuesto ya aprobado sin que ninguna de las dos
    transacciones lo detecte — el mismo `INSERT` fantasma que la Decisión #5
    ya advertía y que sin este bloqueo seguía reproduciéndose 6/6 veces
    (hallazgo del red-team de esta fase)."""
    evento = await repository.get_event_for_update(session, organization_id, event_id)
    if evento is None:
        raise NotFoundError("El evento no existe.")
    if evento.budget_approved_at is not None:
        raise ConflictError(
            "El presupuesto ya está aprobado; las partidas son de solo lectura hasta que se reabra."
        )


async def aprobar_presupuesto(
    session: AsyncSession,
    background_tasks: BackgroundTasks,
    *,
    actor_user_id: uuid.UUID,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
) -> Event:
    """Bloquea la fila `Event` completa **antes** de comprobar
    `budget_approved_at` (plan.md Decisión #5): es lo que serializa dos
    aprobaciones concurrentes — la segunda espera el `FOR UPDATE` de la
    primera y, al obtenerlo, ve `budget_approved_at` ya informado."""
    evento = await repository.get_event_for_update(session, organization_id, event_id)
    if evento is None:
        raise NotFoundError("El evento no existe.")
    if evento.budget_approved_at is not None:
        raise ConflictError("El presupuesto de este evento ya está aprobado.")

    total_budgeted_cents = await repository.sum_budgeted_cents(session, organization_id, event_id)
    contingencia_cents = int(
        (Decimal(total_budgeted_cents) * evento.contingency_fund_percent / Decimal(100)).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )
    evento.contingency_fund_cents = contingencia_cents
    evento.budget_approved_at = datetime.now(UTC)

    await session.flush()

    background_tasks.add_task(
        auditar,
        actor_user_id=actor_user_id,
        organization_id=organization_id,
        action="accounting.budget.approved",
        entity_type="event",
        entity_id=str(event_id),
        detail={
            "total_budgeted_cents": total_budgeted_cents,
            "contingency_fund_percent": str(evento.contingency_fund_percent),
            "contingency_fund_cents": contingencia_cents,
        },
    )
    return evento


async def reabrir_presupuesto(
    session: AsyncSession,
    background_tasks: BackgroundTasks,
    *,
    actor_user_id: uuid.UUID,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    motivo: str,
) -> Event:
    """No borra `contingency_fund_cents` (queda con el último valor dotado
    hasta la siguiente aprobación, que lo recalcula desde cero) — plan.md
    Decisión #5. Revalida el motivo aquí, no solo en el esquema de entrada:
    esta función también se llama directamente desde tests de servicio, que
    no pasan por `BudgetReopenIn`."""
    if not motivo or not motivo.strip():
        raise ValidationDomainError("El motivo de la reapertura es obligatorio.")

    evento = await repository.get_event_for_update(session, organization_id, event_id)
    if evento is None:
        raise NotFoundError("El evento no existe.")
    if evento.budget_approved_at is None:
        raise ConflictError("El presupuesto de este evento no está aprobado.")

    evento.budget_approved_at = None
    await session.flush()

    background_tasks.add_task(
        auditar,
        actor_user_id=actor_user_id,
        organization_id=organization_id,
        action="accounting.budget.reopened",
        entity_type="event",
        entity_id=str(event_id),
        detail={"motivo": motivo.strip()},
    )
    return evento


async def crear_partida_presupuesto(
    session: AsyncSession,
    background_tasks: BackgroundTasks,
    *,
    actor_user_id: uuid.UUID,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    datos: dict[str, Any],
) -> AccountingBudgetLine:
    await _asegurar_presupuesto_editable(session, organization_id, event_id)

    linea = AccountingBudgetLine(event_id=event_id, organization_id=organization_id, **datos)
    session.add(linea)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError("No se ha podido dar de alta la partida de presupuesto.") from exc

    background_tasks.add_task(
        auditar,
        actor_user_id=actor_user_id,
        organization_id=organization_id,
        action="accounting_budget_line.created",
        entity_type="accounting_budget_line",
        entity_id=str(linea.id),
        detail={"name": linea.name, "budgeted_cents": linea.budgeted_cents},
    )
    return linea


async def editar_partida_presupuesto(
    session: AsyncSession,
    background_tasks: BackgroundTasks,
    *,
    actor_user_id: uuid.UUID,
    organization_id: uuid.UUID,
    budget_line_id: uuid.UUID,
    datos: dict[str, Any],
) -> AccountingBudgetLine:
    linea = await repository.get_budget_line(session, organization_id, budget_line_id)
    if linea is None:
        raise NotFoundError("Esa partida de presupuesto no existe.")
    await _asegurar_presupuesto_editable(session, organization_id, linea.event_id)

    valores_anteriores = {"name": linea.name, "budgeted_cents": linea.budgeted_cents}
    for campo, valor in datos.items():
        setattr(linea, campo, valor)

    try:
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError("No se han podido guardar los cambios de la partida.") from exc

    background_tasks.add_task(
        auditar,
        actor_user_id=actor_user_id,
        organization_id=organization_id,
        action="accounting_budget_line.updated",
        entity_type="accounting_budget_line",
        entity_id=str(linea.id),
        detail={"antes": valores_anteriores, "despues": datos},
    )
    return linea


async def borrar_partida_presupuesto(
    session: AsyncSession,
    background_tasks: BackgroundTasks,
    *,
    actor_user_id: uuid.UUID,
    organization_id: uuid.UUID,
    budget_line_id: uuid.UUID,
) -> None:
    linea = await repository.get_budget_line(session, organization_id, budget_line_id)
    if linea is None:
        raise NotFoundError("Esa partida de presupuesto no existe.")
    await _asegurar_presupuesto_editable(session, organization_id, linea.event_id)

    event_id = linea.event_id
    nombre = linea.name
    await session.delete(linea)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError("No se puede borrar: la partida tiene gastos enlazados.") from exc

    background_tasks.add_task(
        auditar,
        actor_user_id=actor_user_id,
        organization_id=organization_id,
        action="accounting_budget_line.deleted",
        entity_type="accounting_budget_line",
        entity_id=str(budget_line_id),
        detail={"event_id": str(event_id), "name": nombre},
    )


@dataclass(frozen=True, slots=True)
class ResumenPresupuesto:
    """Insumo numérico del panel (fase 5): presupuesto, contingencia
    consumida/disponible y "gasto sin partida" — expuesto ya en esta fase
    (plan.md, arquitectura de la fase 3)."""

    event_id: uuid.UUID
    budget_approved_at: datetime | None
    total_budgeted_cents: int
    contingency_fund_percent: Decimal
    contingency_fund_cents: int | None
    consumido_contingencia_cents: int
    disponible_contingencia_cents: int | None
    gasto_sin_partida_cents: int
    ejecutado_en_especie_cents: int
    por_partida: list[LineaConsumoContingencia]
    # Evolución temporal (fase 5 de trabajo, plan.md §4.8: requisito literal
    # ausente en las fases 1-3): nunca revienta con un evento sin movimientos,
    # `repository.serie_temporal` devuelve lista vacía en ese caso.
    serie_temporal: list[PuntoSerieTemporal]

    @property
    def ejecutado_metalico_cents(self) -> int:
        """Ejecutado en metálico total: suma de `por_partida`, que **ya**
        incluye la fila "sin partida" (`budget_line_id is None`) — sumar
        `gasto_sin_partida_cents` aparte lo contaría dos veces (hallazgo
        Crítico C1 del code review de la fase 5). Única definición del módulo;
        `export.py` la reutiliza en vez de recalcularla por su cuenta."""
        return sum(linea.ejecutado_cents for linea in self.por_partida)


def saldo_cents(resumen: ResumenPresupuesto, total_ingresos_cents: int) -> int:
    """Saldo de caja del evento: ingresos ya cobrados (incluida la valoración
    en especie, que plan.md Decisión #3 computa como ingreso desde que se
    valora) menos todo lo ejecutado, en metálico **y** en especie —
    simétrico con "Ingresos", que también suma la especie.

    Única función del módulo que calcula el saldo: el panel y `export.py`
    deben reutilizarla siempre con el mismo `total_ingresos_cents`
    (`repository.listar_ingresos(...).total_ingresos_cents`), nunca
    reimplementar la resta por separado (hallazgo Crítico C1 del code review
    de la fase 5: la fórmula de `export.py` restaba `gasto_sin_partida_cents`
    dos veces y nunca restaba la especie)."""
    return total_ingresos_cents - (
        resumen.ejecutado_metalico_cents + resumen.ejecutado_en_especie_cents
    )


async def resumen_presupuesto(
    session: AsyncSession, *, organization_id: uuid.UUID, event_id: uuid.UUID
) -> ResumenPresupuesto:
    evento = await events_repository.get_event(session, organization_id, event_id)
    if evento is None:
        raise NotFoundError("El evento no existe.")

    total_budgeted_cents = await repository.sum_budgeted_cents(session, organization_id, event_id)
    lineas_consumo = await repository.consumo_contingencia(
        session, organization_id=organization_id, event_id=event_id
    )
    consumido_total = sum(linea.exceso_cents for linea in lineas_consumo)
    gasto_sin_partida_cents = next(
        (linea.ejecutado_cents for linea in lineas_consumo if linea.budget_line_id is None), 0
    )
    ejecutado_en_especie_cents = await repository.ejecutado_en_especie_cents(
        session, organization_id=organization_id, event_id=event_id
    )
    disponible = (
        evento.contingency_fund_cents - consumido_total
        if evento.contingency_fund_cents is not None
        else None
    )
    serie = await repository.serie_temporal(
        session,
        organization_id=organization_id,
        event_id=event_id,
        moneda_evento=evento.accounting_currency,
        starts_at=evento.starts_at,
        ends_at=evento.ends_at,
    )

    return ResumenPresupuesto(
        event_id=event_id,
        budget_approved_at=evento.budget_approved_at,
        total_budgeted_cents=total_budgeted_cents,
        contingency_fund_percent=evento.contingency_fund_percent,
        contingency_fund_cents=evento.contingency_fund_cents,
        consumido_contingencia_cents=consumido_total,
        disponible_contingencia_cents=disponible,
        gasto_sin_partida_cents=gasto_sin_partida_cents,
        ejecutado_en_especie_cents=ejecutado_en_especie_cents,
        por_partida=lineas_consumo,
        serie_temporal=serie,
    )


# --- Gastos manuales (sin `sponsor_id`, fase 3 de trabajo) -------------------


async def _validar_partida_del_evento(
    session: AsyncSession,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    budget_line_id: uuid.UUID | None,
) -> None:
    if budget_line_id is None:
        return
    linea = await repository.get_budget_line(session, organization_id, budget_line_id)
    if linea is None or linea.event_id != event_id:
        raise ValidationDomainError("Esa partida de presupuesto no existe en este evento.")


async def crear_gasto(
    session: AsyncSession,
    background_tasks: BackgroundTasks,
    *,
    actor_user_id: uuid.UUID,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    datos: dict[str, Any],
) -> AccountingExpense:
    await _validar_partida_del_evento(
        session, organization_id, event_id, datos.get("budget_line_id")
    )

    gasto = AccountingExpense(
        event_id=event_id, organization_id=organization_id, sponsor_id=None, **datos
    )
    session.add(gasto)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError("No se ha podido dar de alta el gasto.") from exc

    background_tasks.add_task(
        auditar,
        actor_user_id=actor_user_id,
        organization_id=organization_id,
        action="accounting_expense.created",
        entity_type="accounting_expense",
        entity_id=str(gasto.id),
        detail={"provider_name": gasto.provider_name, "total_cents": gasto.total_cents},
    )
    return gasto


async def editar_gasto(
    session: AsyncSession,
    background_tasks: BackgroundTasks,
    *,
    actor_user_id: uuid.UUID,
    organization_id: uuid.UUID,
    expense_id: uuid.UUID,
    datos: dict[str, Any],
) -> AccountingExpense:
    gasto = await repository.get_expense(session, organization_id, expense_id)
    if gasto is None:
        raise NotFoundError("Ese gasto no existe.")
    if gasto.sponsor_id is not None:
        raise ConflictError(
            "Un gasto en especie se edita fijando la valoración del patrocinador, "
            "no por este endpoint."
        )
    await _validar_partida_del_evento(
        session, organization_id, gasto.event_id, datos.get("budget_line_id")
    )

    valores_anteriores = {"provider_name": gasto.provider_name, "total_cents": gasto.total_cents}
    for campo, valor in datos.items():
        setattr(gasto, campo, valor)

    # `ExpenseUpdate` es parcial (`PATCH`): la coherencia `total = base + iva`
    # no se puede validar en el schema porque un campo no informado hereda el
    # valor ya guardado en BD, no uno que el schema pueda ver. Se valida aquí,
    # sobre el estado resultante tras aplicar los cambios — mismo criterio que
    # `ExpenseCreate._total_coincide_con_base_mas_iva`, para que un `PATCH`
    # parcial no pueda dejar un gasto con un importe que no cuadra (ese
    # `total_cents` es justo lo que consume el fondo de contingencia).
    esperado = gasto.base_cents + (gasto.vat_cents or 0)
    if gasto.total_cents != esperado:
        raise ValidationDomainError(
            "`total_cents` debe ser `base_cents + vat_cents` (o `base_cents` si exento)."
        )

    try:
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError("No se han podido guardar los cambios del gasto.") from exc

    background_tasks.add_task(
        auditar,
        actor_user_id=actor_user_id,
        organization_id=organization_id,
        action="accounting_expense.updated",
        entity_type="accounting_expense",
        entity_id=str(gasto.id),
        detail={"antes": valores_anteriores, "despues": datos},
    )
    return gasto


async def borrar_gasto(
    session: AsyncSession,
    background_tasks: BackgroundTasks,
    *,
    actor_user_id: uuid.UUID,
    organization_id: uuid.UUID,
    expense_id: uuid.UUID,
) -> None:
    gasto = await repository.get_expense(session, organization_id, expense_id)
    if gasto is None:
        raise NotFoundError("Ese gasto no existe.")
    if gasto.sponsor_id is not None:
        raise ConflictError(
            "Un gasto en especie se borra poniendo la valoración del patrocinador "
            "a null, no por este endpoint."
        )

    detalle = {"provider_name": gasto.provider_name, "total_cents": gasto.total_cents}
    await session.delete(gasto)
    await session.flush()

    background_tasks.add_task(
        auditar,
        actor_user_id=actor_user_id,
        organization_id=organization_id,
        action="accounting_expense.deleted",
        entity_type="accounting_expense",
        entity_id=str(expense_id),
        detail=detalle,
    )


# --- Valoración en especie de un patrocinador (fase 3 de trabajo) -----------


@dataclass(frozen=True, slots=True)
class ValoracionEnEspecie:
    sponsor: Sponsor
    gasto: AccountingExpense | None


async def fijar_valoracion_en_especie(
    session: AsyncSession,
    background_tasks: BackgroundTasks,
    *,
    actor_user_id: uuid.UUID,
    organization_id: uuid.UUID,
    sponsor_id: uuid.UUID,
    valoracion_cents: int | None,
    budget_line_id: uuid.UUID | None,
) -> ValoracionEnEspecie:
    """Transacción única (plan.md Decisión #3): `UPDATE sponsors.
    in_kind_valuation_cents` + upsert real del gasto enlazado, aprovechando
    `UNIQUE(sponsor_id)` — nunca dos filas para el mismo patrocinador. Poner
    la valoración a `None` borra el gasto enlazado, si existe."""
    sponsor = await repository.get_sponsor_by_id(session, organization_id, sponsor_id)
    if sponsor is None:
        raise NotFoundError("Ese patrocinador no existe.")
    if sponsor.contribution_type != "en_especie":
        raise ValidationDomainError(
            "Solo un patrocinador con aportación «en especie» puede tener valoración en especie."
        )

    gasto_existente = await repository.get_expense_by_sponsor(session, organization_id, sponsor_id)

    if valoracion_cents is None:
        sponsor.in_kind_valuation_cents = None
        expense_id_borrado = str(gasto_existente.id) if gasto_existente is not None else None
        if gasto_existente is not None:
            await session.delete(gasto_existente)
        await session.flush()

        background_tasks.add_task(
            auditar,
            actor_user_id=actor_user_id,
            organization_id=organization_id,
            action="accounting_sponsor_in_kind_valuation.cleared",
            entity_type="sponsor",
            entity_id=str(sponsor_id),
            detail={"expense_id_borrado": expense_id_borrado},
        )
        return ValoracionEnEspecie(sponsor=sponsor, gasto=None)

    if budget_line_id is None:
        raise ValidationDomainError(
            "La valoración en especie exige una partida de presupuesto a la que imputarla."
        )
    linea = await repository.get_budget_line(session, organization_id, budget_line_id)
    if linea is None or linea.event_id != sponsor.event_id:
        raise ValidationDomainError(
            "Esa partida de presupuesto no existe en el evento de este patrocinador."
        )

    sponsor.in_kind_valuation_cents = valoracion_cents
    accion = "accounting_sponsor_in_kind_valuation.updated"
    if gasto_existente is None:
        accion = "accounting_sponsor_in_kind_valuation.created"
        gasto_existente = AccountingExpense(
            event_id=sponsor.event_id,
            organization_id=organization_id,
            sponsor_id=sponsor_id,
            budget_line_id=budget_line_id,
            provider_name=sponsor.name,
            expense_date=datetime.now(UTC),
            base_cents=valoracion_cents,
            vat_cents=None,
            total_cents=valoracion_cents,
        )
        session.add(gasto_existente)
    else:
        gasto_existente.budget_line_id = budget_line_id
        gasto_existente.provider_name = sponsor.name
        gasto_existente.base_cents = valoracion_cents
        gasto_existente.total_cents = valoracion_cents

    try:
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError("No se ha podido fijar la valoración en especie.") from exc

    background_tasks.add_task(
        auditar,
        actor_user_id=actor_user_id,
        organization_id=organization_id,
        action=accion,
        entity_type="sponsor",
        entity_id=str(sponsor_id),
        detail={
            "valoracion_cents": valoracion_cents,
            "budget_line_id": str(budget_line_id),
            "expense_id": str(gasto_existente.id),
        },
    )
    return ValoracionEnEspecie(sponsor=sponsor, gasto=gasto_existente)
