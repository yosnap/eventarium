"""Idiomas activos de la plataforma y visibilidad del selector

El superadmin decide qué idiomas del catálogo ofrece la web pública y si se ve el
selector de idioma en la cabecera y el pie. El idioma por defecto (`es-ES`) no se
puede desactivar: es el de las URL sin prefijo.

Revision ID: 0072_idiomas_de_plataforma
Revises: 0071_normaliza_locale_usuarios
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0072_idiomas_de_plataforma"
down_revision: str | None = "0071_normaliza_locale_usuarios"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "platform_branding",
        sa.Column(
            "enabled_locales",
            postgresql.ARRAY(sa.String(10)),
            nullable=False,
            server_default=sa.text("ARRAY['es-ES','en-US']::varchar[]"),
        ),
    )
    op.add_column(
        "platform_branding",
        sa.Column(
            "language_switcher_visible",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.create_check_constraint(
        "ck_platform_branding_enabled_locales",
        "platform_branding",
        "'es-ES' = ANY(enabled_locales) AND enabled_locales <@ ARRAY['es-ES','en-US']::varchar[]",
    )


def downgrade() -> None:
    op.drop_constraint("ck_platform_branding_enabled_locales", "platform_branding", type_="check")
    op.drop_column("platform_branding", "language_switcher_visible")
    op.drop_column("platform_branding", "enabled_locales")
