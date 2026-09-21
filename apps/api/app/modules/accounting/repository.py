"""Acceso a datos de ingresos y datos de cobro de patrocinio (fase 2 de trabajo).

`listar_ingresos` compone tres orígenes de dinero que hoy viven en tres
tablas distintas (`sponsors`/`sponsor_payment_details`, `event_payments`,
`accounting_incomes`) sin una vista SQL — se resuelve con tres consultas
independientes (nunca N+1 por fila: cada bloque es una única consulta) y se
combina en Python, igual que `payments/refunds_service.listar_pagos_del_evento`
combina varias tablas por evento sin una vista materializada.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.accounting.models import (
    AccountingBudgetLine,
    AccountingExpense,
    AccountingExpenseDraft,
    AccountingIncome,
    SponsorPaymentDetail,
)
from app.modules.events.models import Event
from app.modules.organizations.models import OrganizationMember
from app.modules.payments import repository as payments_repository
from app.modules.payments.models import EventPayment
from app.modules.sponsors.models import Sponsor


def helper_euros_a_centimos(valor: Decimal) -> int:
    """Único punto de conversión euros -> céntimos de todo el módulo
    (plan.md Decisión #15). `ROUND_HALF_UP`, no el `ROUND_HALF_EVEN` por
    defecto de `Decimal`: una factura de `10.005` € debe redondear a `1001`
    céntimos de forma predecible para quien lee un balance, no según la
    paridad del céntimo anterior."""
    return int((valor * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


@dataclass(frozen=True, slots=True)
class LineaIngreso:
    """Una fila de "Ingresos" o "Comprometido" en la vista compuesta."""

    origen: str  # patrocinio | entradas | subvencion
    concepto: str
    importe_cents: int
    fecha: datetime | None
    peso_sobre_el_total: Decimal | None
    referencia_id: str
    # True solo en las valoraciones en especie: cuenta como ingreso (Decisión
    # #3) pero nunca pasa por el banco, así que quien suma "cobrado" para una
    # foto de caja la excluye con esta marca en vez de adivinarla por el
    # concepto o por `fecha`.
    en_especie: bool = False


@dataclass(frozen=True, slots=True)
class VistaDeIngresos:
    ingresos: list[LineaIngreso]
    comprometido: list[LineaIngreso]
    total_ingresos_cents: int
    moneda: str
    ingresos_excluidos_por_moneda: int


async def _lineas_de_patrocinio(
    session: AsyncSession, organization_id: uuid.UUID, event_id: uuid.UUID
) -> tuple[list[LineaIngreso], list[LineaIngreso]]:
    """Patrocinios cobrados y comprometidos.

    `en_especie` cuenta siempre como cobrado (plan.md Decisión #3: una
    aportación en especie no tiene fecha de cobro real, se computa como
    ingreso desde que se valora) usando `in_kind_valuation_cents`.
    `monetaria` solo cuenta como cobrado si existe `SponsorPaymentDetail.
    collected_at` — nunca por la mera existencia del patrocinador (plan.md
    Decisión #2)."""
    filas = (
        await session.execute(
            select(Sponsor, SponsorPaymentDetail)
            .outerjoin(SponsorPaymentDetail, SponsorPaymentDetail.sponsor_id == Sponsor.id)
            .where(Sponsor.organization_id == organization_id, Sponsor.event_id == event_id)
        )
    ).all()

    cobrados: list[LineaIngreso] = []
    comprometidos: list[LineaIngreso] = []
    for patrocinador, detalle_cobro in filas:
        if patrocinador.contribution_type == "en_especie":
            importe = patrocinador.in_kind_valuation_cents
            if importe is None:
                # Aportación en especie sin valorar todavía: no hay importe que
                # mostrar en ningún bloque (el servicio de la fase 3 exige
                # valoración antes de generar el gasto enlazado; aquí solo se
                # lee, nunca se inventa un importe).
                continue
            cobrados.append(
                LineaIngreso(
                    origen="patrocinio",
                    concepto=f"Patrocinio en especie — {patrocinador.name}",
                    importe_cents=importe,
                    fecha=None,
                    peso_sobre_el_total=None,
                    referencia_id=str(patrocinador.id),
                    en_especie=True,
                )
            )
            continue

        # `monetaria`: `contribution_amount` está en euros (`Numeric(12,2)`,
        # ver `sponsors/models.py:98`), se normaliza aquí al único formato de
        # dinero del libro contable (céntimos enteros).
        if patrocinador.contribution_amount is None:
            continue
        importe = helper_euros_a_centimos(patrocinador.contribution_amount)
        linea = LineaIngreso(
            origen="patrocinio",
            concepto=f"Patrocinio — {patrocinador.name}",
            importe_cents=importe,
            fecha=detalle_cobro.collected_at if detalle_cobro is not None else None,
            peso_sobre_el_total=None,
            referencia_id=str(patrocinador.id),
        )
        if detalle_cobro is not None and detalle_cobro.collected_at is not None:
            cobrados.append(linea)
        else:
            comprometidos.append(linea)

    return cobrados, comprometidos


async def _lineas_de_entradas(
    session: AsyncSession,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    moneda_evento: str,
) -> tuple[list[LineaIngreso], int]:
    """Entradas pagadas, netas de reembolsos confirmados y en curso.

    `payments_repository.reembolsos_en_curso_por_pago` agrega el mismo
    predicado que `suma_reembolsos_en_curso` (plan.md Decisión #14) para
    **todo el evento en una sola consulta** — llamar a la función por-pago
    dentro de este bucle sería un N+1 real con eventos de miles de entradas
    (hallazgo del red-team de esta fase), así que se reutiliza la variante
    agregada, no la de un solo pago. Se excluyen (con recuento del aviso)
    los pagos en una moneda distinta a `events.accounting_currency`: sumarlos
    sería tratar unidades distintas como si fueran la misma (Decisión #15).
    """
    pagos = (
        await session.execute(
            select(EventPayment).where(
                EventPayment.organization_id == organization_id,
                EventPayment.event_id == event_id,
                EventPayment.status.in_(("paid", "partially_refunded")),
            )
        )
    ).scalars()
    pagos_lista = list(pagos)

    reembolsos_en_curso = await payments_repository.reembolsos_en_curso_por_pago(
        session, organization_id, event_id
    )

    lineas: list[LineaIngreso] = []
    excluidos = 0
    for pago in pagos_lista:
        if pago.currency != moneda_evento:
            excluidos += 1
            continue
        en_curso = reembolsos_en_curso.get(pago.id, 0)
        neto = pago.amount_cents - pago.refunded_cents - en_curso
        if neto <= 0:
            continue
        lineas.append(
            LineaIngreso(
                origen="entradas",
                concepto="Entrada",
                importe_cents=neto,
                fecha=pago.paid_at,
                peso_sobre_el_total=None,
                referencia_id=str(pago.id),
            )
        )
    return lineas, excluidos


async def _lineas_de_subvenciones(
    session: AsyncSession, organization_id: uuid.UUID, event_id: uuid.UUID
) -> tuple[list[LineaIngreso], list[LineaIngreso]]:
    """`AccountingIncome` es hoy solo `origin = 'subvencion'` (único valor que
    admite el `CHECK` del modelo — no existe `colaborador`, plan.md
    Decisión #1)."""
    filas = (
        await session.execute(
            select(AccountingIncome).where(
                AccountingIncome.organization_id == organization_id,
                AccountingIncome.event_id == event_id,
            )
        )
    ).scalars()

    cobrados: list[LineaIngreso] = []
    comprometidos: list[LineaIngreso] = []
    for ingreso in filas:
        linea = LineaIngreso(
            origen="subvencion",
            concepto=ingreso.concept,
            importe_cents=ingreso.amount_cents,
            fecha=ingreso.collected_at or ingreso.expected_at,
            peso_sobre_el_total=None,
            referencia_id=str(ingreso.id),
        )
        if ingreso.status == "collected":
            cobrados.append(linea)
        else:
            comprometidos.append(linea)
    return cobrados, comprometidos


_PRECISION_PESO_SOBRE_EL_TOTAL = Decimal("0.000001")


def _con_peso_sobre_el_total(lineas: list[LineaIngreso], total_cents: int) -> list[LineaIngreso]:
    """ "Peso sobre el total" solo tiene sentido sobre "Ingresos" (plan.md:
    "no tiene sentido para uno «Comprometido»") y nunca se guarda — se
    calcula aquí, en la respuesta, cada vez que se pide.

    Cuantizado a 6 decimales (`IncomeLineOut.peso_sobre_el_total` lo exige):
    una división de enteros produce hasta 28 decimales por defecto, y tres
    ingresos iguales (1/3 = 0,3333...) revientan la validación del schema de
    salida con un 500 si no se trunca aquí antes de construir la respuesta.
    """
    if total_cents <= 0:
        return lineas
    return [
        LineaIngreso(
            origen=linea.origen,
            concepto=linea.concepto,
            importe_cents=linea.importe_cents,
            fecha=linea.fecha,
            peso_sobre_el_total=(Decimal(linea.importe_cents) / Decimal(total_cents)).quantize(
                _PRECISION_PESO_SOBRE_EL_TOTAL, rounding=ROUND_HALF_UP
            ),
            referencia_id=linea.referencia_id,
            en_especie=linea.en_especie,
        )
        for linea in lineas
    ]


async def listar_ingresos(
    session: AsyncSession, *, organization_id: uuid.UUID, event_id: uuid.UUID, moneda_evento: str
) -> VistaDeIngresos:
    """Vista compuesta de ingresos de un evento: "Ingresos" (ya cobrado) y
    "Comprometido" (todavía no). Tres orígenes, tres consultas — sin N+1 por
    fila (Non-functional de la fase)."""
    patrocinio_cobrado, patrocinio_comprometido = await _lineas_de_patrocinio(
        session, organization_id, event_id
    )
    entradas_netas, excluidos_por_moneda = await _lineas_de_entradas(
        session, organization_id, event_id, moneda_evento
    )
    subvenciones_cobradas, subvenciones_comprometidas = await _lineas_de_subvenciones(
        session, organization_id, event_id
    )

    ingresos = patrocinio_cobrado + entradas_netas + subvenciones_cobradas
    comprometido = patrocinio_comprometido + subvenciones_comprometidas
    total_ingresos_cents = sum(linea.importe_cents for linea in ingresos)

    return VistaDeIngresos(
        ingresos=_con_peso_sobre_el_total(ingresos, total_ingresos_cents),
        comprometido=comprometido,
        total_ingresos_cents=total_ingresos_cents,
        moneda=moneda_evento,
        ingresos_excluidos_por_moneda=excluidos_por_moneda,
    )


async def get_income(
    session: AsyncSession, organization_id: uuid.UUID, income_id: uuid.UUID
) -> AccountingIncome | None:
    resultado: AccountingIncome | None = await session.scalar(
        select(AccountingIncome).where(
            AccountingIncome.id == income_id, AccountingIncome.organization_id == organization_id
        )
    )
    return resultado


async def get_sponsor_payment_detail(
    session: AsyncSession, organization_id: uuid.UUID, sponsor_id: uuid.UUID
) -> SponsorPaymentDetail | None:
    resultado: SponsorPaymentDetail | None = await session.scalar(
        select(SponsorPaymentDetail).where(
            SponsorPaymentDetail.sponsor_id == sponsor_id,
            SponsorPaymentDetail.organization_id == organization_id,
        )
    )
    return resultado


# --- Presupuesto: partidas, aprobación y contingencia (fase 3 de trabajo) ----


async def get_event_for_update(
    session: AsyncSession, organization_id: uuid.UUID, event_id: uuid.UUID
) -> Event | None:
    """Bloquea la fila `Event` completa (`SELECT ... FOR UPDATE`), nunca las
    partidas hijas (plan.md Decisión #5, hallazgo Crítico del red-team): es lo
    único que hace imposible una doble aprobación concurrente o un `INSERT`
    fantasma de una partida a mitad de transacción. Mismo patrón que
    `registrations/repository.get_registration_for_update` —
    `organization_id` explícito en el `WHERE`, no solo confiado a RLS.

    `populate_existing=True` es obligatorio aquí: `EventoDep`
    (`accounting/router.py`) ya deja este mismo `Event` cargado en el mapa de
    identidad de la sesión con una lectura sin bloqueo, antes de llegar a este
    servicio. Sin `populate_existing`, SQLAlchemy detecta que el objeto ya
    está en el mapa de identidad y **descarta la fila recién leída bajo
    bloqueo**, devolviendo el objeto Python obsoleto — la segunda petición
    concurrente queda bloqueada correctamente a nivel de PostgreSQL, se
    desbloquea después del `COMMIT` de la primera, pero sin este flag lee
    `budget_approved_at` todavía como `None` y aprueba una segunda vez.
    Verificado con `echo=True`: la fila SQL ya viene con el valor correcto
    tras desbloquear, es la capa ORM la que la ignoraba."""
    resultado: Event | None = await session.scalar(
        select(Event)
        .where(Event.id == event_id, Event.organization_id == organization_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return resultado


async def sum_budgeted_cents(
    session: AsyncSession, organization_id: uuid.UUID, event_id: uuid.UUID
) -> int:
    total = await session.scalar(
        select(func.coalesce(func.sum(AccountingBudgetLine.budgeted_cents), 0)).where(
            AccountingBudgetLine.organization_id == organization_id,
            AccountingBudgetLine.event_id == event_id,
        )
    )
    return int(total or 0)


async def list_budget_lines(
    session: AsyncSession, organization_id: uuid.UUID, event_id: uuid.UUID
) -> list[AccountingBudgetLine]:
    filas = (
        await session.execute(
            select(AccountingBudgetLine)
            .where(
                AccountingBudgetLine.organization_id == organization_id,
                AccountingBudgetLine.event_id == event_id,
            )
            .order_by(AccountingBudgetLine.sort_order, AccountingBudgetLine.name)
        )
    ).scalars()
    return list(filas)


async def get_budget_line(
    session: AsyncSession, organization_id: uuid.UUID, budget_line_id: uuid.UUID
) -> AccountingBudgetLine | None:
    resultado: AccountingBudgetLine | None = await session.scalar(
        select(AccountingBudgetLine).where(
            AccountingBudgetLine.id == budget_line_id,
            AccountingBudgetLine.organization_id == organization_id,
        )
    )
    return resultado


async def list_expenses(
    session: AsyncSession, organization_id: uuid.UUID, event_id: uuid.UUID
) -> list[AccountingExpense]:
    filas = (
        await session.execute(
            select(AccountingExpense)
            .where(
                AccountingExpense.organization_id == organization_id,
                AccountingExpense.event_id == event_id,
            )
            .order_by(AccountingExpense.expense_date.desc())
        )
    ).scalars()
    return list(filas)


async def get_expense(
    session: AsyncSession, organization_id: uuid.UUID, expense_id: uuid.UUID
) -> AccountingExpense | None:
    resultado: AccountingExpense | None = await session.scalar(
        select(AccountingExpense).where(
            AccountingExpense.id == expense_id, AccountingExpense.organization_id == organization_id
        )
    )
    return resultado


async def get_expense_by_sponsor(
    session: AsyncSession, organization_id: uuid.UUID, sponsor_id: uuid.UUID
) -> AccountingExpense | None:
    resultado: AccountingExpense | None = await session.scalar(
        select(AccountingExpense).where(
            AccountingExpense.sponsor_id == sponsor_id,
            AccountingExpense.organization_id == organization_id,
        )
    )
    return resultado


async def get_sponsor_by_id(
    session: AsyncSession, organization_id: uuid.UUID, sponsor_id: uuid.UUID
) -> Sponsor | None:
    """Igual que `sponsors.repository.get_sponsor`, pero sin exigir
    `event_id`: la fijación de valoración en especie cuelga de
    `/accounting/sponsors/{sponsor_id}/...`, sin evento en la URL."""
    resultado: Sponsor | None = await session.scalar(
        select(Sponsor).where(Sponsor.id == sponsor_id, Sponsor.organization_id == organization_id)
    )
    return resultado


@dataclass(frozen=True, slots=True)
class LineaConsumoContingencia:
    """Consumo de contingencia de una partida (o de "sin partida",
    `budget_line_id is None`). `exceso_cents = MAX(0, ejecutado - budgeted)`
    — una partida gastada por debajo de lo presupuestado no "libera"
    contingencia a otra partida, solo dejar de consumirla (plan.md
    Decisión #4)."""

    budget_line_id: uuid.UUID | None
    ejecutado_cents: int
    budgeted_cents: int
    exceso_cents: int


async def consumo_contingencia(
    session: AsyncSession, *, organization_id: uuid.UUID, event_id: uuid.UUID
) -> list[LineaConsumoContingencia]:
    """`sponsor_id IS NULL` excluye los gastos en especie del cómputo (plan.md
    Decisión #4): una aportación en especie no sale nunca de caja real, así
    que no puede "gastar" el fondo de contingencia. La fila con
    `budget_line_id IS NULL` es el gasto "sin partida" (fase 5 Requirements:
    fila propia del resumen, nunca oculta): sin partida que la ampare, su
    `budgeted_cents` es 0 y por tanto consume contingencia por su importe
    íntegro."""
    filas = (
        await session.execute(
            select(AccountingExpense.budget_line_id, func.sum(AccountingExpense.total_cents))
            .where(
                AccountingExpense.organization_id == organization_id,
                AccountingExpense.event_id == event_id,
                AccountingExpense.sponsor_id.is_(None),
            )
            .group_by(AccountingExpense.budget_line_id)
        )
    ).all()
    if not filas:
        return []

    partidas = await list_budget_lines(session, organization_id, event_id)
    presupuestado_por_partida = {partida.id: partida.budgeted_cents for partida in partidas}

    resultado: list[LineaConsumoContingencia] = []
    for budget_line_id, ejecutado_bruto in filas:
        ejecutado = int(ejecutado_bruto or 0)
        presupuestado = presupuestado_por_partida.get(budget_line_id, 0) if budget_line_id else 0
        resultado.append(
            LineaConsumoContingencia(
                budget_line_id=budget_line_id,
                ejecutado_cents=ejecutado,
                budgeted_cents=presupuestado,
                exceso_cents=max(0, ejecutado - presupuestado),
            )
        )
    return resultado


# --- Evolución temporal (fase 5 de trabajo) ----------------------------------


@dataclass(frozen=True, slots=True)
class PuntoSerieTemporal:
    """Un punto de la evolución temporal del panel: ingresos y gastos
    confirmados agregados en el mismo periodo (plan.md §4.8, requisito
    literal ausente en las fases 1-3)."""

    periodo: str
    ingresos_cents: int
    gastos_cents: int


def _clave_periodo(fecha: datetime, granularidad: str) -> str:
    if granularidad == "semana":
        anio_iso, semana_iso, _ = fecha.isocalendar()
        return f"{anio_iso}-W{semana_iso:02d}"
    return fecha.strftime("%Y-%m")


async def serie_temporal(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    moneda_evento: str,
    starts_at: datetime,
    ends_at: datetime,
) -> list[PuntoSerieTemporal]:
    """Agrega ingresos cobrados (con fecha conocida) y gastos por semana o
    mes, según la duración del evento — el propio endpoint decide la
    granularidad (plan.md, arquitectura de la fase 5). Nunca revienta con un
    evento sin ingresos ni gastos: devuelve una lista vacía.

    Decisión (hallazgo Alto A2 del code review de la fase 5): esta serie es
    una vista de **caja real**, simétrica en ambos lados. Toda aportación en
    especie tiene `fecha=None` en el lado de ingresos (`_lineas_de_patrocinio`,
    arriba) porque no representa un cobro real — por eso se excluye también
    del lado de gastos (`sponsor_id IS NOT NULL`), el mismo filtro que ya usa
    `consumo_contingencia` para el mismo motivo. Sin este filtro simétrico, la
    serie sumaba el gasto en especie sin sumar nunca el ingreso en especie que
    lo compensa, exagerando el gasto de un periodo (reproducido: serie
    1.000 €/350 € frente a KPI 1.200 €/150 € en metálico). La especie sigue
    visible, íntegra, en el KPI "Ejecutado en especie" — solo desaparece de
    esta serie temporal."""
    duracion_dias = (ends_at - starts_at).days
    granularidad = "semana" if duracion_dias <= 60 else "mes"

    vista_ingresos = await listar_ingresos(
        session, organization_id=organization_id, event_id=event_id, moneda_evento=moneda_evento
    )
    gastos = await list_expenses(session, organization_id, event_id)

    acumulado: dict[str, dict[str, int]] = {}
    for linea in vista_ingresos.ingresos:
        if linea.fecha is None:
            continue
        clave = _clave_periodo(linea.fecha, granularidad)
        fila = acumulado.setdefault(clave, {"ingresos": 0, "gastos": 0})
        fila["ingresos"] += linea.importe_cents
    for gasto in gastos:
        if gasto.sponsor_id is not None:
            continue
        clave = _clave_periodo(gasto.expense_date, granularidad)
        fila = acumulado.setdefault(clave, {"ingresos": 0, "gastos": 0})
        fila["gastos"] += gasto.total_cents

    return [
        PuntoSerieTemporal(
            periodo=clave, ingresos_cents=valores["ingresos"], gastos_cents=valores["gastos"]
        )
        for clave, valores in sorted(acumulado.items())
    ]


# --- Borradores de gasto extraídos por OCR (fase 4 de trabajo) --------------


async def list_drafts(
    session: AsyncSession,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    *,
    estados: tuple[str, ...] | None = None,
) -> list[AccountingExpenseDraft]:
    """Borradores de un evento, del más reciente al más antiguo.

    Sin `estados`, todos: la pantalla de revisión necesita ver en la misma
    lista lo pendiente de extraer, lo pendiente de revisar y lo que falló con
    su motivo, que es justo lo que distingue «presupuesto de IA agotado» de
    «extracción fallida»."""
    consulta = select(AccountingExpenseDraft).where(
        AccountingExpenseDraft.organization_id == organization_id,
        AccountingExpenseDraft.event_id == event_id,
    )
    if estados is not None:
        consulta = consulta.where(AccountingExpenseDraft.status.in_(estados))
    filas = (
        await session.execute(consulta.order_by(AccountingExpenseDraft.created_at.desc()))
    ).scalars()
    return list(filas)


async def get_draft(
    session: AsyncSession, organization_id: uuid.UUID, draft_id: uuid.UUID
) -> AccountingExpenseDraft | None:
    resultado: AccountingExpenseDraft | None = await session.scalar(
        select(AccountingExpenseDraft).where(
            AccountingExpenseDraft.id == draft_id,
            AccountingExpenseDraft.organization_id == organization_id,
        )
    )
    return resultado


async def get_draft_for_update(
    session: AsyncSession, organization_id: uuid.UUID, draft_id: uuid.UUID
) -> AccountingExpenseDraft | None:
    """Bloquea la fila del borrador (`SELECT ... FOR UPDATE`).

    Es la primera de las dos barreras contra una doble confirmación; la
    segunda es el índice único parcial `uq_accounting_expenses_draft_id`.
    `populate_existing=True` por el mismo motivo que
    `get_event_for_update`: sin él, un borrador ya cargado en el mapa de
    identidad de la sesión se devolvería con el estado obsoleto y la segunda
    confirmación vería `pending_review` después de que la primera hubiera
    escrito `confirmed`."""
    resultado: AccountingExpenseDraft | None = await session.scalar(
        select(AccountingExpenseDraft)
        .where(
            AccountingExpenseDraft.id == draft_id,
            AccountingExpenseDraft.organization_id == organization_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return resultado


async def get_member_id(
    session: AsyncSession, organization_id: uuid.UUID, user_id: uuid.UUID
) -> uuid.UUID | None:
    """Membresía de quien confirma, para `confirmed_by_member_id`.

    Una persona puede tener varias membresías en la misma organización (una
    por rol): se queda con la más antigua, que es la estable — basta con dejar
    constancia de **quién** confirmó, no con qué rol lo hizo."""
    resultado: uuid.UUID | None = await session.scalar(
        select(OrganizationMember.id)
        .where(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.user_id == user_id,
        )
        .order_by(OrganizationMember.created_at)
        .limit(1)
    )
    return resultado


async def drafts_reencolables(
    session: AsyncSession,
    *,
    minutos: int,
    max_intentos: int,
    error_code_reintentable: str,
    limite: int,
) -> list[tuple[uuid.UUID, uuid.UUID]]:
    """`(draft_id, organization_id)` de lo que el barrido debe reencolar.

    Tres conjuntos, y **solo** esos tres:

    - lo que lleva demasiado tiempo en `pending_extraction` (la tarea nunca
      llegó a arrancar — se perdió de la cola antes de que
      `_reservar_intento` la tocara);
    - lo que lleva demasiado tiempo en `en_extraccion` (arrancó y el worker
      murió a mitad de la llamada al modelo);
    - lo que falló con el único código transitorio (`proveedor_error`).

    Deliberadamente **no** incluye `limite_superado`: con el límite todavía
    agotado, cada pasada del barrido consumiría una reserva, fallaría y
    quemaría cuota llenando `ai_usage_records` de filas fallidas. Ese estado
    se reencola solo por acción explícita del organizador. El resto de
    códigos (`payload_invalido`, `modelo_sin_vision`, `clave_rechazada`,
    `credencial_ilegible`, `sin_configuracion`) tampoco: repetir la misma
    llamada daría el mismo resultado.

    Consulta de solo lectura y transversal a organizaciones: la escritura
    posterior va organización a organización bajo RLS.

    `limite` acota el lote de una pasada: tras una caída larga del proveedor
    puede haber cientos de borradores atascados, y reencolarlos todos de
    golpe descargaría sobre la cola —y sobre el presupuesto de IA— todo el
    atasco de una vez. Se atiende lo más antiguo primero y el resto espera a
    la pasada siguiente."""
    corte = datetime.now(UTC) - timedelta(minutes=minutos)
    filas = await session.execute(
        select(AccountingExpenseDraft.id, AccountingExpenseDraft.organization_id)
        .where(
            AccountingExpenseDraft.attempts < max_intentos,
            or_(
                and_(
                    AccountingExpenseDraft.status == "pending_extraction",
                    AccountingExpenseDraft.updated_at < corte,
                ),
                and_(
                    AccountingExpenseDraft.status == "en_extraccion",
                    AccountingExpenseDraft.updated_at < corte,
                ),
                and_(
                    AccountingExpenseDraft.status == "extraction_failed",
                    AccountingExpenseDraft.error_code == error_code_reintentable,
                    AccountingExpenseDraft.updated_at < corte,
                ),
            ),
        )
        .order_by(AccountingExpenseDraft.created_at)
        .limit(limite)
    )
    return [(fila[0], fila[1]) for fila in filas.all()]


async def contar_drafts_agotados(session: AsyncSession, *, max_intentos: int, minutos: int) -> int:
    """Cuántas extracciones ya no se van a reintentar solas.

    Incluye `en_extraccion` además de `extraction_failed`: un borrador puede
    agotar sus intentos sin llegar nunca a `extraction_failed` si el worker
    muere antes de que `_marcar_fallo` escriba nada — sin esto, ese caso
    quedaría invisible para esta alerta aunque `drafts_reencolables` ya haya
    dejado de reencolarlo (`attempts >= max_intentos`).

    Para `en_extraccion` exige además `updated_at` viejo (`minutos`, mismo
    corte que `drafts_reencolables`): un borrador en su último intento
    permitido puede seguir legítimamente en curso —la llamada al modelo
    tarda hasta ~120 s— y sin este filtro se contaría como agotado mientras
    todavía procesa con normalidad, disparando un `ERROR` de plataforma
    falso. `extraction_failed` no necesita el filtro: ese estado solo se
    alcanza cuando el procesamiento ya ha terminado.

    El barrido lo escala a log `ERROR`: es el único aviso de que hay
    justificantes esperando una acción humana."""
    corte = datetime.now(UTC) - timedelta(minutes=minutos)
    total = await session.scalar(
        select(func.count())
        .select_from(AccountingExpenseDraft)
        .where(
            AccountingExpenseDraft.attempts >= max_intentos,
            or_(
                AccountingExpenseDraft.status == "extraction_failed",
                and_(
                    AccountingExpenseDraft.status == "en_extraccion",
                    AccountingExpenseDraft.updated_at < corte,
                ),
            ),
        )
    )
    return int(total or 0)


async def ejecutado_en_especie_cents(
    session: AsyncSession, *, organization_id: uuid.UUID, event_id: uuid.UUID
) -> int:
    """Suma de los gastos en especie (`sponsor_id IS NOT NULL`) del evento —
    el complemento exacto del filtro de `consumo_contingencia`. Se muestra
    como cifra separada del ejecutado en metálico (plan.md Decisión #4: "el
    panel muestra 'Ejecutado en metálico' y 'Ejecutado en especie' como dos
    cifras, sumadas solo en el 'Ejecutado total' informativo, nunca en la
    comparación contra el presupuesto por partida")."""
    total = await session.scalar(
        select(func.coalesce(func.sum(AccountingExpense.total_cents), 0)).where(
            AccountingExpense.organization_id == organization_id,
            AccountingExpense.event_id == event_id,
            AccountingExpense.sponsor_id.is_not(None),
        )
    )
    return int(total or 0)
