"""ajustes de analítica externa de la plataforma

Tabla `platform_analytics_settings`, misma forma que `platform_branding`
(`0022`): una sola fila (PK fija `'default'`) con los identificadores
semi-públicos de los proveedores externos de analítica (`ga4_measurement_id`,
`meta_pixel_id`, `cloudflare_analytics_token`) — ninguno es un secreto: los
tres viajan en el HTML público de cualquier sitio que los use.

Fase 0 del plan `260916-2246-cookies-analitica-externa`. La fila `'default'`
se siembra aquí, igual que la identidad de plataforma en `0022`.

Privilegios: `ALTER DEFAULT PRIVILEGES` (`infra/postgres/sql/roles.sql`)
concede a `app_user` DML completo sobre toda tabla nueva. A las otras tablas
de plataforma `0022` les retiró el DML dejando solo `SELECT` porque sus
endpoints públicos leen con sesión de organización; esta tabla **no** la lee
ningún endpoint público todavía (el banner la pedirá en la fase 4 del plan
por el mismo camino), así que se restringe igual por simetría: solo `SELECT`
para `app_user`, DML completo para el mantenimiento.

Revision ID: 0041_analytics_settings
Revises: 0040_roles_plataforma
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0041_analytics_settings"
down_revision: str | None = "0040_roles_plataforma"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "platform_analytics_settings",
        sa.Column("singleton", sa.String(length=20), nullable=False),
        sa.Column("ga4_measurement_id", sa.String(length=100), nullable=True),
        sa.Column("meta_pixel_id", sa.String(length=100), nullable=True),
        sa.Column("cloudflare_analytics_token", sa.String(length=100), nullable=True),
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
        sa.PrimaryKeyConstraint("singleton", name="pk_platform_analytics_settings"),
        sa.CheckConstraint(
            "singleton = 'default'", name="ck_platform_analytics_settings_singleton"
        ),
    )
    op.execute(
        sa.text(
            "INSERT INTO platform_analytics_settings (singleton) VALUES ('default')"
        )
    )
    op.execute("REVOKE INSERT, UPDATE, DELETE ON platform_analytics_settings FROM app_user")


def downgrade() -> None:
    op.drop_table("platform_analytics_settings")
