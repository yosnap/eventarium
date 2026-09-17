"""contenedor de Google Tag Manager en los ajustes de analítica

Cuarto proveedor de `platform_analytics_settings`: el identificador del
contenedor de GTM. Cuando está configurado, el cliente de scripts inyecta
el contenedor y omite el gtag directo de GA4 (la medición va dentro del
contenedor; ambos a la vez contarían las visitas por duplicado).

Columna nullable, sin backfill: `NULL` es «sin contenedor», el estado de
todas las instalaciones hasta que quien administra lo configure.

Revision ID: 0043_gtm_container_id
Revises: 0042_login_platform_role
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0043_gtm_container_id"
down_revision: str | None = "0042_login_platform_role"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "platform_analytics_settings",
        sa.Column("gtm_container_id", sa.String(length=100), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("platform_analytics_settings", "gtm_container_id")
