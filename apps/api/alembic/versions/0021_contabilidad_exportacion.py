"""contabilidad exportacion

Fase 7 del PRD, fase 5 de trabajo. Una tabla nueva
(`accounting_export_snapshots`), snapshot inmutable de cada exportación de
balance (decisión de `validate`, Sesión 1, plan.md): el CSV/PDF generado se
guarda en el almacén privado de justificantes (mismo tratamiento de acceso
que la migración `0020`) y esta fila conserva la clave del objeto para
redescargarlo tal cual, sin recalcular nada.

Mismo patrón de FK **compuesta** contra `(events.id, events.organization_id)`
y RLS `tenant_accounting_export_snapshots` que el resto del módulo
`accounting` (`0020`). `ondelete="RESTRICT"` explícito hacia `events`, no el
`NO ACTION` implícito (plan.md Decisión #19): un evento con exportaciones no
se borra sin borrar antes su contabilidad.

Revision ID: 0021_contabilidad_exportacion
Revises: 0020_contabilidad_evento
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0021_contabilidad_exportacion"
down_revision: str | None = "0020_contabilidad_evento"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLA = "accounting_export_snapshots"


def upgrade() -> None:
    op.create_table(
        _TABLA,
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("event_id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("format", sa.String(length=10), nullable=False),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("generated_by_member_id", sa.UUID(), nullable=False),
        sa.Column("payload_object_key", sa.String(length=500), nullable=False),
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
            name="fk_accounting_export_snapshots_event_id_organization_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_accounting_export_snapshots")),
        sa.UniqueConstraint(
            "id", "organization_id", name="uq_accounting_export_snapshots_id_organization_id"
        ),
        sa.CheckConstraint(
            "format IN ('csv', 'pdf')", name="ck_accounting_export_snapshots_format"
        ),
    )
    op.create_index(
        op.f("ix_accounting_export_snapshots_event_id"), _TABLA, ["event_id"], unique=False
    )

    _verificar_privilegios_de_app_user()
    op.execute(f"ALTER TABLE {_TABLA} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {_TABLA} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_{_TABLA} ON {_TABLA} "
        "USING (organization_id = app_current_organization()) "
        "WITH CHECK (organization_id = app_current_organization())"
    )


def _verificar_privilegios_de_app_user() -> None:
    """Mismo patrón que `0020`: falla aquí, no en runtime."""
    conexion = op.get_bind()
    concedido = conexion.execute(
        sa.text("SELECT has_table_privilege('app_user', :tabla, 'SELECT')"),
        {"tabla": _TABLA},
    ).scalar()
    if not concedido:
        raise RuntimeError(
            f"El rol «app_user» no tiene SELECT sobre «{_TABLA}». Ejecuta "
            "infra/scripts/ensure-roles.sh para aplicar ALTER DEFAULT PRIVILEGES."
        )


def downgrade() -> None:
    op.execute(f"DROP POLICY IF EXISTS tenant_{_TABLA} ON {_TABLA}")
    op.execute(f"ALTER TABLE {_TABLA} NO FORCE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {_TABLA} DISABLE ROW LEVEL SECURITY")
    op.drop_index(op.f("ix_accounting_export_snapshots_event_id"), table_name=_TABLA)
    op.drop_table(_TABLA)
