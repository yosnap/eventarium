"""contabilidad evento

Fase 7 del PRD, fase 1 de trabajo. Cinco tablas nuevas del módulo
`accounting` (`accounting_budget_lines`, `accounting_incomes`,
`accounting_expenses`, `accounting_expense_drafts`,
`sponsor_payment_details`), una columna en `sponsors`
(`in_kind_valuation_cents`), cuatro columnas en `events`
(`contingency_fund_percent`, `budget_approved_at`, `contingency_fund_cents`,
`accounting_currency`) y los permisos `accounting:read`/`accounting:write`.

Mismo patrón de FK **compuestas** contra `(id, organization_id)` del padre y
RLS `tenant_<tabla>` que el resto del esquema (`0012`, `0013`). Las FK hacia
`events` (y entre tablas de este módulo) llevan `ondelete="RESTRICT"`
**explícito**, no el `NO ACTION` implícito de omitir el parámetro (`NO
ACTION` es aplazable al final de la transacción, `RESTRICT` no): un evento
con libro contable no se borra sin borrar antes esa contabilidad (plan.md
Decisión #19).

`accounting_expenses.sponsor_id`/`draft_id` llevan índice único **parcial**
(`WHERE ... IS NOT NULL`), mismo mecanismo que
`uq_organization_stripe_accounts_activa` en `0013`: un patrocinador en
especie tiene como máximo un gasto en especie, y confirmar el mismo draft de
OCR dos veces no puede duplicar el gasto.

Backfill de `accounting:read`/`accounting:write` a cualquier rol con
`organizations:write` (mismo criterio que `0010`-`0013`), más la plantilla
`ORGANIZER` actualizada en `app/modules/roles/system_roles.py` para las
organizaciones creadas después de esta migración (plan.md Decisión #16).

Revision ID: 0020_contabilidad_evento
Revises: 0019_apertura_de_inscripcion
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0020_contabilidad_evento"
down_revision: str | None = "0019_apertura_de_inscripcion"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLAS_DE_DOMINIO = (
    "accounting_budget_lines",
    "accounting_incomes",
    "accounting_expenses",
    "accounting_expense_drafts",
    "sponsor_payment_details",
)


def upgrade() -> None:
    _crear_tablas()
    _anadir_columnas()
    _verificar_privilegios_de_app_user()
    _activar_rls_de_dominio()
    _backfill_permisos_de_contabilidad()


def _crear_tablas() -> None:
    op.create_table(
        "accounting_budget_lines",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("event_id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("budgeted_cents", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["event_id", "organization_id"],
            ["events.id", "events.organization_id"],
            name="fk_accounting_budget_lines_event_id_organization_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_accounting_budget_lines")),
        sa.UniqueConstraint(
            "id", "organization_id", name="uq_accounting_budget_lines_id_organization_id"
        ),
    )
    op.create_index(
        op.f("ix_accounting_budget_lines_event_id"),
        "accounting_budget_lines",
        ["event_id"],
        unique=False,
    )

    op.create_table(
        "accounting_incomes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("event_id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("origin", sa.String(length=20), nullable=False),
        sa.Column("concept", sa.String(length=200), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("expected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["event_id", "organization_id"],
            ["events.id", "events.organization_id"],
            name="fk_accounting_incomes_event_id_organization_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_accounting_incomes")),
        # `origin` es un único valor permitido hoy (`subvencion`), no un enum
        # abierto: no existe ningún "colaborador" que no sea ya un `Sponsor`
        # (plan.md Decisión #1).
        sa.CheckConstraint("origin IN ('subvencion')", name="ck_accounting_incomes_origin"),
        sa.CheckConstraint(
            "status IN ('pending', 'collected')", name="ck_accounting_incomes_status"
        ),
        # Mismo patrón que el resto de tablas de esta fase, para que la
        # primera FK compuesta que necesite apuntar aquí pueda crearse.
        sa.UniqueConstraint(
            "id", "organization_id", name="uq_accounting_incomes_id_organization_id"
        ),
    )
    op.create_index(
        op.f("ix_accounting_incomes_event_id"), "accounting_incomes", ["event_id"], unique=False
    )

    op.create_table(
        "accounting_expense_drafts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("event_id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("receipt_object_key", sa.String(length=500), nullable=False),
        sa.Column("ocr_provider", sa.String(length=60), nullable=False),
        sa.Column("extracted_fields", JSONB(), nullable=False, server_default="{}"),
        sa.Column("field_confidence", JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "status", sa.String(length=30), nullable=False, server_default="pending_extraction"
        ),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("confirmed_expense_id", sa.UUID(), nullable=True),
        sa.Column("confirmed_by_member_id", sa.UUID(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["event_id", "organization_id"],
            ["events.id", "events.organization_id"],
            name="fk_accounting_expense_drafts_event_id_organization_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_accounting_expense_drafts")),
        sa.UniqueConstraint(
            "id", "organization_id", name="uq_accounting_expense_drafts_id_organization_id"
        ),
        sa.CheckConstraint(
            "status IN ('pending_extraction', 'pending_review', 'extraction_failed', "
            "'confirmed', 'discarded')",
            name="ck_accounting_expense_drafts_status",
        ),
    )
    op.create_index(
        op.f("ix_accounting_expense_drafts_event_id"),
        "accounting_expense_drafts",
        ["event_id"],
        unique=False,
    )

    op.create_table(
        "accounting_expenses",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("event_id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("budget_line_id", sa.UUID(), nullable=True),
        sa.Column("sponsor_id", sa.UUID(), nullable=True),
        sa.Column("provider_name", sa.String(length=200), nullable=False),
        sa.Column("expense_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("base_cents", sa.Integer(), nullable=False),
        sa.Column("vat_cents", sa.Integer(), nullable=True),
        sa.Column("total_cents", sa.Integer(), nullable=False),
        sa.Column("receipt_object_key", sa.String(length=500), nullable=True),
        sa.Column("receipt_status", sa.String(length=30), nullable=True),
        sa.Column("draft_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["event_id", "organization_id"],
            ["events.id", "events.organization_id"],
            name="fk_accounting_expenses_event_id_organization_id",
            ondelete="RESTRICT",
        ),
        # No se borra una partida con gastos imputados.
        sa.ForeignKeyConstraint(
            ["budget_line_id", "organization_id"],
            ["accounting_budget_lines.id", "accounting_budget_lines.organization_id"],
            name="fk_accounting_expenses_budget_line_id_organization_id",
            ondelete="RESTRICT",
        ),
        # No se borra un patrocinador con un gasto en especie enlazado.
        sa.ForeignKeyConstraint(
            ["sponsor_id", "organization_id"],
            ["sponsors.id", "sponsors.organization_id"],
            name="fk_accounting_expenses_sponsor_id_organization_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["draft_id", "organization_id"],
            ["accounting_expense_drafts.id", "accounting_expense_drafts.organization_id"],
            name="fk_accounting_expenses_draft_id_organization_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_accounting_expenses")),
        sa.UniqueConstraint(
            "id", "organization_id", name="uq_accounting_expenses_id_organization_id"
        ),
        # Un gasto en especie siempre tiene partida (plan.md Decisión #3).
        sa.CheckConstraint(
            "budget_line_id IS NOT NULL OR sponsor_id IS NULL",
            name="ck_accounting_expenses_en_especie_con_partida",
        ),
    )
    op.create_index(
        op.f("ix_accounting_expenses_event_id"), "accounting_expenses", ["event_id"], unique=False
    )
    # Parciales: un patrocinador en especie tiene como máximo un gasto en
    # especie; confirmar el mismo draft de OCR dos veces no duplica el gasto
    # (mismo mecanismo que `uq_organization_stripe_accounts_activa`, `0013`).
    op.create_index(
        "uq_accounting_expenses_sponsor_id",
        "accounting_expenses",
        ["sponsor_id"],
        unique=True,
        postgresql_where=sa.text("sponsor_id IS NOT NULL"),
    )
    op.create_index(
        "uq_accounting_expenses_draft_id",
        "accounting_expenses",
        ["draft_id"],
        unique=True,
        postgresql_where=sa.text("draft_id IS NOT NULL"),
    )

    op.create_table(
        "sponsor_payment_details",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("sponsor_id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("contact_name", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["sponsor_id", "organization_id"],
            ["sponsors.id", "sponsors.organization_id"],
            name="fk_sponsor_payment_details_sponsor_id_organization_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sponsor_payment_details")),
        sa.UniqueConstraint("sponsor_id", name="uq_sponsor_payment_details_sponsor_id"),
        sa.UniqueConstraint(
            "id", "organization_id", name="uq_sponsor_payment_details_id_organization_id"
        ),
    )
    op.create_index(
        op.f("ix_sponsor_payment_details_sponsor_id"),
        "sponsor_payment_details",
        ["sponsor_id"],
        unique=False,
    )


def _anadir_columnas() -> None:
    op.add_column("sponsors", sa.Column("in_kind_valuation_cents", sa.Integer(), nullable=True))

    op.add_column(
        "events",
        sa.Column(
            "contingency_fund_percent",
            sa.Numeric(5, 2),
            nullable=False,
            server_default="5.00",
        ),
    )
    op.add_column(
        "events", sa.Column("budget_approved_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("events", sa.Column("contingency_fund_cents", sa.Integer(), nullable=True))
    op.add_column(
        "events",
        sa.Column("accounting_currency", sa.String(length=3), nullable=False, server_default="eur"),
    )


def _verificar_privilegios_de_app_user() -> None:
    """Mismo patrón que `0012`/`0013`: falla aquí, no en runtime."""
    conexion = op.get_bind()
    for tabla in TABLAS_DE_DOMINIO:
        concedido = conexion.execute(
            sa.text("SELECT has_table_privilege('app_user', :tabla, 'SELECT')"),
            {"tabla": tabla},
        ).scalar()
        if not concedido:
            raise RuntimeError(
                f"El rol «app_user» no tiene SELECT sobre «{tabla}». Ejecuta "
                "infra/scripts/ensure-roles.sh para aplicar ALTER DEFAULT PRIVILEGES."
            )


def _activar_rls_de_dominio() -> None:
    for tabla in TABLAS_DE_DOMINIO:
        op.execute(f"ALTER TABLE {tabla} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {tabla} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_{tabla} ON {tabla} "
            "USING (organization_id = app_current_organization()) "
            "WITH CHECK (organization_id = app_current_organization())"
        )


# Ancla al permiso, no al nombre del rol (mismo criterio que `0010`-`0013`): un
# rol a medida con `organizations:write` también necesita `accounting:*`,
# exista o no con la clave `owner`/`organizer`.
_BACKFILL_CONTABILIDAD = (
    """
INSERT INTO role_permissions (role_id, permission, organization_id)
SELECT r.id, 'accounting:read', r.organization_id
FROM roles r
WHERE EXISTS (
  SELECT 1 FROM role_permissions rp
  WHERE rp.role_id = r.id AND rp.permission = 'organizations:write'
)
AND NOT EXISTS (
  SELECT 1 FROM role_permissions rp2
  WHERE rp2.role_id = r.id AND rp2.permission = 'accounting:read'
)
    """,
    """
INSERT INTO role_permissions (role_id, permission, organization_id)
SELECT r.id, 'accounting:write', r.organization_id
FROM roles r
WHERE EXISTS (
  SELECT 1 FROM role_permissions rp
  WHERE rp.role_id = r.id AND rp.permission = 'organizations:write'
)
AND NOT EXISTS (
  SELECT 1 FROM role_permissions rp2
  WHERE rp2.role_id = r.id AND rp2.permission = 'accounting:write'
)
    """,
)


def _backfill_permisos_de_contabilidad() -> None:
    for sentencia in _BACKFILL_CONTABILIDAD:
        op.execute(sentencia)


def downgrade() -> None:
    # Destructivo a partir de aquí: revierte el backfill y borra las tablas
    # enteras con sus datos. Válido para revertir un despliegue fallido antes
    # de que existan datos reales — no para producción con datos.
    op.execute(
        "DELETE FROM role_permissions "
        "WHERE permission IN ('accounting:read', 'accounting:write') "
        "AND role_id IN ("
        "  SELECT r.id FROM roles r "
        "  WHERE EXISTS ("
        "    SELECT 1 FROM role_permissions rp "
        "    WHERE rp.role_id = r.id AND rp.permission = 'organizations:write'"
        "  )"
        ")"
    )

    for tabla in reversed(TABLAS_DE_DOMINIO):
        op.execute(f"DROP POLICY IF EXISTS tenant_{tabla} ON {tabla}")
        op.execute(f"ALTER TABLE {tabla} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {tabla} DISABLE ROW LEVEL SECURITY")

    op.drop_column("events", "accounting_currency")
    op.drop_column("events", "contingency_fund_cents")
    op.drop_column("events", "budget_approved_at")
    op.drop_column("events", "contingency_fund_percent")
    op.drop_column("sponsors", "in_kind_valuation_cents")

    op.drop_index(
        op.f("ix_sponsor_payment_details_sponsor_id"), table_name="sponsor_payment_details"
    )
    op.drop_table("sponsor_payment_details")

    op.drop_index("uq_accounting_expenses_draft_id", table_name="accounting_expenses")
    op.drop_index("uq_accounting_expenses_sponsor_id", table_name="accounting_expenses")
    op.drop_index(op.f("ix_accounting_expenses_event_id"), table_name="accounting_expenses")
    op.drop_table("accounting_expenses")

    op.drop_index(
        op.f("ix_accounting_expense_drafts_event_id"), table_name="accounting_expense_drafts"
    )
    op.drop_table("accounting_expense_drafts")

    op.drop_index(op.f("ix_accounting_incomes_event_id"), table_name="accounting_incomes")
    op.drop_table("accounting_incomes")

    op.drop_index(op.f("ix_accounting_budget_lines_event_id"), table_name="accounting_budget_lines")
    op.drop_table("accounting_budget_lines")
