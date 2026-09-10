"""Esquemas de ingresos y datos de cobro de patrocinio (fase 2 de trabajo).

`origin` de `AccountingIncomeCreate` es `Literal["subvencion"]`: el `CHECK`
de BD ya lo impide (`models.py:89`), pero el esquema lo deja explícito en el
contrato de la API en vez de esperar a que llegue un `IntegrityError` sin
traducir — el servicio (`service.py`) igualmente revalida por si en el
futuro el `Literal` se relaja sin tocar el `CHECK`.

Todo campo de céntimos lleva `le=2_147_483_647` (el máximo de `Integer` en
Postgres): sin esa cota, un importe mayor no lo rechaza Pydantic sino un
`asyncpg.DataError` que ningún `try/except` del servicio captura — un 500
en vez de un 422, sobre entrada no confiable.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

IncomeOrigin = Literal["subvencion"]
IncomeStatus = Literal["pending", "collected"]


class IncomeLineOut(BaseModel):
    """Una fila de "Ingresos" o "Comprometido" en el panel."""

    origen: Literal["patrocinio", "entradas", "subvencion"]
    concepto: str
    importe_cents: int
    fecha: datetime | None
    # Solo relevante en "Ingresos"; `null` en "Comprometido" (plan.md: no
    # tiene sentido un peso sobre compromisos todavía no cobrados).
    peso_sobre_el_total: Annotated[Decimal, Field(decimal_places=6)] | None
    referencia_id: str


class IncomesViewOut(BaseModel):
    """Vista compuesta de `GET /accounting/events/{event_id}/incomes`."""

    ingresos: list[IncomeLineOut]
    comprometido: list[IncomeLineOut]
    total_ingresos_cents: int
    moneda: str
    ingresos_excluidos_por_moneda: int


class AccountingIncomeCreate(BaseModel):
    """Alta de un ingreso manual. Único `origin` admitido: `subvencion`
    (plan.md Decisión #1 — no existe ya `colaborador`, un colaborador es un
    `Sponsor` en especie)."""

    origin: IncomeOrigin
    concept: Annotated[str, Field(min_length=1, max_length=200)]
    amount_cents: Annotated[int, Field(gt=0, le=2_147_483_647)]
    status: IncomeStatus = "pending"
    expected_at: datetime | None = None
    collected_at: datetime | None = None


class AccountingIncomeUpdate(BaseModel):
    """Campos editables de un ingreso manual. Parcial (`PATCH`)."""

    concept: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    amount_cents: Annotated[int, Field(gt=0, le=2_147_483_647)] | None = None
    status: IncomeStatus | None = None
    expected_at: datetime | None = None
    collected_at: datetime | None = None


class AccountingIncomeOut(BaseModel):
    id: str
    event_id: str
    origin: IncomeOrigin
    concept: str
    amount_cents: int
    status: IncomeStatus
    expected_at: datetime | None
    collected_at: datetime | None


class SponsorPaymentDetailUpsert(BaseModel):
    """Alta/edición de los datos de cobro de un patrocinador.
    `UNIQUE(sponsor_id)`: como máximo una fila por patrocinador (un
    patrocinador que paga en dos plazos registra dos fechas dentro de la
    misma fila, no dos filas — plan.md Decisión #21)."""

    collected_at: datetime | None = None
    contact_name: Annotated[str, Field(max_length=4000)] | None = None


class SponsorPaymentDetailOut(BaseModel):
    id: str
    sponsor_id: str
    collected_at: datetime | None
    contact_name: str | None


# --- Presupuesto: partidas, aprobación y contingencia (fase 3 de trabajo) ----


class BudgetLineCreate(BaseModel):
    """Alta de una partida de presupuesto. Rechazada por el servicio (409)
    mientras `budget_approved_at IS NOT NULL`."""

    name: Annotated[str, Field(min_length=1, max_length=160)]
    budgeted_cents: Annotated[int, Field(ge=0, le=2_147_483_647)]
    sort_order: int = 0


class BudgetLineUpdate(BaseModel):
    """Campos editables de una partida. Parcial (`PATCH`)."""

    name: Annotated[str, Field(min_length=1, max_length=160)] | None = None
    budgeted_cents: Annotated[int, Field(ge=0, le=2_147_483_647)] | None = None
    sort_order: int | None = None


class BudgetLineOut(BaseModel):
    id: str
    event_id: str
    name: str
    budgeted_cents: int
    sort_order: int


class BudgetApprovalOut(BaseModel):
    """Respuesta de aprobar/reabrir el presupuesto."""

    event_id: str
    budget_approved_at: datetime | None
    contingency_fund_cents: int | None
    total_budgeted_cents: int


class BudgetReopenIn(BaseModel):
    """Reapertura del presupuesto: exige un motivo no vacío (plan.md
    Decisión #5) — sin flujo de revisión en dos pasos, es una acción de
    `accounting:write` con motivo obligatorio."""

    motivo: Annotated[str, Field(min_length=1, max_length=2000)]

    @field_validator("motivo")
    @classmethod
    def _motivo_no_en_blanco(cls, valor: str) -> str:
        limpio = valor.strip()
        if not limpio:
            raise ValueError("El motivo de la reapertura no puede estar en blanco.")
        return limpio


class ContingencyLineOut(BaseModel):
    """Consumo de contingencia de una partida (`budget_line_id=null` es la
    fila "Sin partida")."""

    budget_line_id: str | None
    ejecutado_cents: int
    budgeted_cents: int
    exceso_cents: int


class BudgetSummaryOut(BaseModel):
    """Resumen numérico de presupuesto/contingencia de un evento — insumo del
    panel de la fase 5, expuesto ya en esta fase (plan.md, arquitectura de la
    fase 3: "expuestos en el endpoint de resumen")."""

    event_id: str
    budget_approved_at: datetime | None
    total_budgeted_cents: int
    contingency_fund_percent: Decimal
    contingency_fund_cents: int | None
    consumido_contingencia_cents: int
    disponible_contingencia_cents: int | None
    gasto_sin_partida_cents: int
    # Gastos en especie de patrocinadores (`sponsor_id IS NOT NULL`): nunca
    # entran en `consumido_contingencia_cents` ni en `por_partida` (plan.md
    # Decisión #4). Cifra separada, no oculta.
    ejecutado_en_especie_cents: int
    por_partida: list[ContingencyLineOut]


class ExpenseCreate(BaseModel):
    """Alta de un gasto manual. Sin `sponsor_id`: ese campo es exclusivo de
    `fijar_valoracion_en_especie` (plan.md Decisión #3), nunca se informa
    desde este endpoint — ni siquiera existe en este esquema."""

    budget_line_id: str | None = None
    provider_name: Annotated[str, Field(min_length=1, max_length=200)]
    expense_date: datetime
    base_cents: Annotated[int, Field(ge=0, le=2_147_483_647)]
    vat_cents: Annotated[int, Field(ge=0, le=2_147_483_647)] | None = None
    total_cents: Annotated[int, Field(ge=0, le=2_147_483_647)]

    @model_validator(mode="after")
    def _total_coincide_con_base_mas_iva(self) -> ExpenseCreate:
        esperado = self.base_cents + (self.vat_cents or 0)
        if self.total_cents != esperado:
            raise ValueError(
                "`total_cents` debe ser `base_cents + vat_cents` (o `base_cents` si exento)."
            )
        return self


class ExpenseUpdate(BaseModel):
    """Campos editables de un gasto manual. Parcial (`PATCH`). Sin
    `sponsor_id` por el mismo motivo que `ExpenseCreate`."""

    budget_line_id: str | None = None
    provider_name: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    expense_date: datetime | None = None
    base_cents: Annotated[int, Field(ge=0, le=2_147_483_647)] | None = None
    vat_cents: Annotated[int, Field(ge=0, le=2_147_483_647)] | None = None
    total_cents: Annotated[int, Field(ge=0, le=2_147_483_647)] | None = None


class ExpenseOut(BaseModel):
    id: str
    event_id: str
    budget_line_id: str | None
    sponsor_id: str | None
    provider_name: str
    expense_date: datetime
    base_cents: int
    vat_cents: int | None
    total_cents: int
    receipt_object_key: str | None
    receipt_status: str | None


class InKindValuationIn(BaseModel):
    """Fija (o borra, con `null`) la valoración en especie de un
    patrocinador. `budget_line_id` obligatorio salvo cuando se borra la
    valoración (plan.md Decisión #3)."""

    valoracion_cents: Annotated[int, Field(ge=0, le=2_147_483_647)] | None
    budget_line_id: str | None = None


class InKindValuationOut(BaseModel):
    sponsor_id: str
    in_kind_valuation_cents: int | None
    expense_id: str | None
