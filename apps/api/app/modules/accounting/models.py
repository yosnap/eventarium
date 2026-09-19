"""Modelos del libro contable de un evento.

PRD fase 7, fase 1 de trabajo. Mismo patrón que `payments/models.py`:
`organization_id` denormalizado y FK **compuestas** contra `(id,
organization_id)` del padre, nunca FK simples.

Solo modelo + integridad de esquema en esta fase — la lógica de negocio
(aprobar presupuesto, confirmar drafts de OCR, calcular el panel) llega en
las fases 2-5. No existe tabla ni columna de enlace para aportaciones en
especie: el enlace es `AccountingExpense.sponsor_id`, con
`UNIQUE(sponsor_id) WHERE sponsor_id IS NOT NULL` (plan.md Decisión #3,
corregido tras red-team — no hay `in_kind_pair_id`).

Todas las FK hacia `events` (y entre tablas de este módulo) llevan
`ondelete="RESTRICT"` **explícito**, no el `NO ACTION` implícito de omitir
el parámetro: `NO ACTION` es aplazable al final de la transacción, `RESTRICT`
no. Un evento con libro contable no se puede borrar sin borrar antes esa
contabilidad, a diferencia del `CASCADE` que domina hacia `events` en el
resto del esquema (plan.md Decisión #19).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin
from app.shared.identifiers import new_uuid7


class AccountingBudgetLine(Base, TimestampMixin):
    """Partida de presupuesto de un evento."""

    __tablename__ = "accounting_budget_lines"
    __table_args__ = (
        ForeignKeyConstraint(
            ["event_id", "organization_id"],
            ["events.id", "events.organization_id"],
            name="fk_accounting_budget_lines_event_id_organization_id",
            ondelete="RESTRICT",
        ),
        # Objetivo de la FK compuesta de `AccountingExpense.budget_line_id`.
        UniqueConstraint(
            "id", "organization_id", name="uq_accounting_budget_lines_id_organization_id"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_uuid7)
    event_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    budgeted_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class AccountingIncome(Base, TimestampMixin):
    """Ingreso manual de un evento.

    `origin` es un `CHECK` de un único valor permitido hoy (`subvencion`), no
    un enum abierto: no existe ningún "colaborador" que no sea ya un
    `Sponsor` (plan.md Decisión #1) — los patrocinios cobrados salen de una
    vista compuesta en la fase 2 de trabajo, nunca de esta tabla.
    """

    __tablename__ = "accounting_incomes"
    __table_args__ = (
        ForeignKeyConstraint(
            ["event_id", "organization_id"],
            ["events.id", "events.organization_id"],
            name="fk_accounting_incomes_event_id_organization_id",
            ondelete="RESTRICT",
        ),
        CheckConstraint("origin IN ('subvencion')", name="ck_accounting_incomes_origin"),
        CheckConstraint("status IN ('pending', 'collected')", name="ck_accounting_incomes_status"),
        # Mismo patrón que el resto de tablas de esta fase, aunque hoy
        # ninguna FK compuesta apunte todavía a `accounting_incomes`: sin
        # esta constraint, la primera tabla hija que la necesite no podría
        # crearse (PostgreSQL exige un índice único exacto sobre las
        # columnas referenciadas).
        UniqueConstraint("id", "organization_id", name="uq_accounting_incomes_id_organization_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_uuid7)
    event_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    origin: Mapped[str] = mapped_column(String(20), nullable=False)
    concept: Mapped[str] = mapped_column(String(200), nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    expected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    collected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AccountingExpense(Base, TimestampMixin):
    """Gasto de un evento, en metálico o en especie (enlazado a un patrocinador).

    `sponsor_id` **es** el enlace con la aportación en especie de un
    patrocinador (sin tabla/columna de enlace aparte, plan.md Decisión #3):
    `UNIQUE(sponsor_id) WHERE sponsor_id IS NOT NULL` porque un patrocinador
    en especie tiene como máximo un gasto en especie. El `CHECK` obliga a que
    todo gasto en especie tenga partida — resuelve parcialmente la deuda de
    "a qué se destina" de `sponsor-page.ts`. `draft_id` enlaza con el draft de
    OCR que lo originó (fase 4 de trabajo); `UNIQUE` evita que confirmar el
    mismo draft dos veces duplique el gasto.
    """

    __tablename__ = "accounting_expenses"
    __table_args__ = (
        ForeignKeyConstraint(
            ["event_id", "organization_id"],
            ["events.id", "events.organization_id"],
            name="fk_accounting_expenses_event_id_organization_id",
            ondelete="RESTRICT",
        ),
        # `RESTRICT` explícito, no el `NO ACTION` implícito de omitir
        # `ondelete`: `NO ACTION` es aplazable al final de la transacción,
        # `RESTRICT` no — una transacción que borrara la partida y después
        # el gasto pasaría con `NO ACTION` y debe seguir fallando.
        ForeignKeyConstraint(
            ["budget_line_id", "organization_id"],
            ["accounting_budget_lines.id", "accounting_budget_lines.organization_id"],
            name="fk_accounting_expenses_budget_line_id_organization_id",
            ondelete="RESTRICT",
        ),
        # No se borra un patrocinador con un gasto en especie enlazado.
        ForeignKeyConstraint(
            ["sponsor_id", "organization_id"],
            ["sponsors.id", "sponsors.organization_id"],
            name="fk_accounting_expenses_sponsor_id_organization_id",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["draft_id", "organization_id"],
            ["accounting_expense_drafts.id", "accounting_expense_drafts.organization_id"],
            name="fk_accounting_expenses_draft_id_organization_id",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("id", "organization_id", name="uq_accounting_expenses_id_organization_id"),
        # Un gasto en especie siempre tiene partida (plan.md Decisión #3).
        CheckConstraint(
            "budget_line_id IS NOT NULL OR sponsor_id IS NULL",
            name="ck_accounting_expenses_en_especie_con_partida",
        ),
        Index(
            "uq_accounting_expenses_sponsor_id",
            "sponsor_id",
            unique=True,
            postgresql_where=text("sponsor_id IS NOT NULL"),
        ),
        Index(
            "uq_accounting_expenses_draft_id",
            "draft_id",
            unique=True,
            postgresql_where=text("draft_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_uuid7)
    event_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    budget_line_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    sponsor_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    provider_name: Mapped[str] = mapped_column(String(200), nullable=False)
    expense_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    base_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    # `NULL` = exento de IVA.
    vat_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    receipt_object_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Sin `CHECK` todavía: el catálogo de valores lo fija el servicio de la
    # fase 3/4 de trabajo, no el modelo de esta fase.
    receipt_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    draft_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)


class AccountingExpenseDraft(Base, TimestampMixin):
    """Borrador de gasto extraído por OCR de un justificante, pendiente de confirmar.

    El OCR nunca autoconfirma (plan.md Decisión #13): `confirmed_expense_id`/
    `confirmed_by_member_id`/`confirmed_at` quedan como columnas sueltas, sin
    FK compuesta — `AccountingExpense.draft_id` es la dirección real del
    enlace (evita una FK circular entre ambas tablas) y la escribe el
    servicio de confirmación de la fase 4 de trabajo.
    """

    __tablename__ = "accounting_expense_drafts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["event_id", "organization_id"],
            ["events.id", "events.organization_id"],
            name="fk_accounting_expense_drafts_event_id_organization_id",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "id", "organization_id", name="uq_accounting_expense_drafts_id_organization_id"
        ),
        CheckConstraint(
            "status IN ('pending_extraction', 'pending_review', 'extraction_failed', "
            "'confirmed', 'discarded')",
            name="ck_accounting_expense_drafts_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_uuid7)
    event_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    receipt_object_key: Mapped[str] = mapped_column(String(500), nullable=False)
    ocr_provider: Mapped[str] = mapped_column(String(60), nullable=False)
    # Límite de tamaño aplicado en el servicio (fase 4 de trabajo), no aquí:
    # es el resultado crudo del proveedor de OCR, tratado como entrada no
    # confiable (plan.md Decisión #13).
    extracted_fields: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    field_confidence: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending_extraction")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    confirmed_expense_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), nullable=True
    )
    confirmed_by_member_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), nullable=True
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SponsorPaymentDetail(Base, TimestampMixin):
    """Datos de cobro de un patrocinador: 1:1 por patrocinador de esta edición.

    Tabla separada de `sponsors` a propósito (plan.md Decisión #21): permite
    un rol a medida con `sponsors:write` y sin `accounting:read`. Sin
    `payment_method` (retirado tras red-team, no correspondía a ningún hueco
    real documentado). Un patrocinador cuenta como ingreso del evento **si y
    solo si** existe esta fila con `collected_at IS NOT NULL` (plan.md
    Decisión #2) — la vista compuesta que lo calcula llega en la fase 2 de
    trabajo.
    """

    __tablename__ = "sponsor_payment_details"
    __table_args__ = (
        ForeignKeyConstraint(
            ["sponsor_id", "organization_id"],
            ["sponsors.id", "sponsors.organization_id"],
            name="fk_sponsor_payment_details_sponsor_id_organization_id",
            ondelete="CASCADE",
        ),
        UniqueConstraint("sponsor_id", name="uq_sponsor_payment_details_sponsor_id"),
        UniqueConstraint(
            "id", "organization_id", name="uq_sponsor_payment_details_id_organization_id"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_uuid7)
    sponsor_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    collected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    contact_name: Mapped[str | None] = mapped_column(Text, nullable=True)
