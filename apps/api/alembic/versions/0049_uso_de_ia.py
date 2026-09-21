"""pasarela de ia: registro de uso y mutex de periodo

Fase 2 del plan `260911-0325-prd-pasarela-ia-multiproveedor`. Dos tablas, las
dos de organización y por tanto con `FORCE ROW LEVEL SECURITY` y su
`CREATE POLICY tenant_<tabla>`, igual que `0048`:

- `ai_usage_records`: una fila por llamada a un proveedor. `cost_usd` es
  `NOT NULL` desde el `INSERT` de la reserva: una fila sin importe no sumaría
  al gasto del periodo y dejaría el límite ciego (hallazgo V-1, Critical).
  Va en **dólares** con seis decimales, no en céntimos enteros: el coste de
  una llamada son fracciones de céntimo y un entero las redondearía a cero.

- `ai_usage_periods`: una fila por `(organización, periodo)`, sin totales. Es
  el mutex de la reserva. Existe siempre —se crea con `ON CONFLICT DO
  NOTHING` en la primera llamada del periodo—, también para la organización
  que hereda la configuración de plataforma, que es justo el caso donde
  bloquear `organization_ai_settings` no serializaba nada porque esa
  organización no tiene fila.

Los dos índices de `ai_usage_records` no son decorativos: `(organization_id,
created_at)` sostiene la suma del gasto del periodo, que corre **bajo el
bloqueo** en cada llamada, y `(organization_id, status)` el barrido de
reservas colgadas.

El `CHECK` de `error_code` replica la taxonomía cerrada de
`app/modules/ai_gateway/errores.py`: sin él, una escritura futura podría
dejar en la columna un código que el panel no sabe traducir, y esa columna es
la única pista de diagnóstico que existe (el detalle de llamadas es un
no-objetivo del PRD).

Revision ID: 0049_uso_de_ia
Revises: 0048_pasarela_ia_configuracion
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0049_uso_de_ia"
down_revision: str | None = "0048_pasarela_ia_configuracion"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLAS = ("ai_usage_periods", "ai_usage_records")

#: Espejo de `models.ESTADOS_DE_USO`.
_ESTADOS = ("reservado", "liquidado", "fallido")

#: Espejo de `errores.CODIGOS_DE_ERROR`, ordenado para que el `CHECK` que
#: queda en la base de datos sea estable entre ejecuciones.
_CODIGOS_DE_ERROR = (
    "clave_rechazada",
    "credencial_ilegible",
    "limite_superado",
    "modelo_sin_vision",
    "payload_invalido",
    "proveedor_error",
    "reserva_abandonada",
    "servicio_desactivado",
    "sin_configuracion",
)


def _lista(valores: tuple[str, ...]) -> str:
    return ", ".join(f"'{valor}'" for valor in valores)


def upgrade() -> None:
    op.create_table(
        "ai_usage_periods",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("periodo", sa.String(length=7), nullable=False),
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
            ["organization_id"],
            ["organizations.id"],
            name="fk_ai_usage_periods_organization_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("organization_id", "periodo", name="pk_ai_usage_periods"),
    )

    op.create_table(
        "ai_usage_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("use_case", sa.String(length=60), nullable=False),
        # `provider`/`model` copiados, no resueltos por join: la
        # configuración cambia y el histórico tiene que seguir diciendo con
        # qué se hizo cada llamada.
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        # NOT NULL: ver el encabezado (V-1). En USD, no en céntimos.
        sa.Column("cost_usd", sa.Numeric(precision=14, scale=6), nullable=False),
        sa.Column("cost_auditable", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("error_code", sa.String(length=40), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
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
            ["organization_id"],
            ["organizations.id"],
            name="fk_ai_usage_records_organization_id",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(f"status IN ({_lista(_ESTADOS)})", name="ck_ai_usage_records_status"),
        sa.CheckConstraint(
            f"error_code IS NULL OR error_code IN ({_lista(_CODIGOS_DE_ERROR)})",
            name="ck_ai_usage_records_error_code",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_usage_records")),
    )
    op.create_index(
        "ix_ai_usage_records_organization_id_created_at",
        "ai_usage_records",
        ["organization_id", "created_at"],
    )
    op.create_index(
        "ix_ai_usage_records_organization_id_status",
        "ai_usage_records",
        ["organization_id", "status"],
    )

    _verificar_privilegios_de_app_user()
    _activar_rls_de_dominio()


def _verificar_privilegios_de_app_user() -> None:
    """Mismo patrón que `0048`: falla aquí, no en runtime.

    `app_user` necesita `SELECT`, `INSERT` y `UPDATE` sobre las dos tablas:
    el cliente de IA escribe la reserva y la liquidación con el rol de la
    aplicación, nunca con el de mantenimiento, porque también lo llaman los
    workers de taskiq (que no tienen petición HTTP) y RLS es lo único que
    impide escribir el uso en la organización equivocada.
    """
    conexion = op.get_bind()
    for tabla in _TABLAS:
        for privilegio in ("SELECT", "INSERT", "UPDATE"):
            concedido = conexion.execute(
                sa.text("SELECT has_table_privilege('app_user', :tabla, :privilegio)"),
                {"tabla": tabla, "privilegio": privilegio},
            ).scalar()
            if not concedido:
                raise RuntimeError(
                    f"El rol «app_user» no tiene {privilegio} sobre «{tabla}». Ejecuta "
                    "infra/scripts/ensure-roles.sh para aplicar ALTER DEFAULT PRIVILEGES."
                )


def _activar_rls_de_dominio() -> None:
    for tabla in _TABLAS:
        op.execute(f"ALTER TABLE {tabla} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {tabla} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_{tabla} ON {tabla} "
            "USING (organization_id = app_current_organization()) "
            "WITH CHECK (organization_id = app_current_organization())"
        )


def downgrade() -> None:
    for tabla in reversed(_TABLAS):
        op.execute(f"DROP POLICY IF EXISTS tenant_{tabla} ON {tabla}")
        op.execute(f"ALTER TABLE {tabla} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {tabla} DISABLE ROW LEVEL SECURITY")

    op.drop_index("ix_ai_usage_records_organization_id_status", table_name="ai_usage_records")
    op.drop_index("ix_ai_usage_records_organization_id_created_at", table_name="ai_usage_records")
    op.drop_table("ai_usage_records")
    op.drop_table("ai_usage_periods")
