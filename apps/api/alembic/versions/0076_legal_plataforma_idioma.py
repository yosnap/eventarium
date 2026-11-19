"""Páginas legales de plataforma por idioma

Cada página legal puede tener una versión por idioma, escrita a mano por el
superadmin (sin IA). La española sigue cayendo a la plantilla por defecto si no
se ha editado; una versión en otro idioma solo existe si se ha escrito, y si
falta se sirve la española con aviso.

Revision ID: 0076_legal_plataforma_idioma
Revises: 0075_peticiones_de_traduccion
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0076_legal_plataforma_idioma"
down_revision: str | None = "0075_peticiones_de_traduccion"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLA = "platform_legal_pages"


def upgrade() -> None:
    op.add_column(
        _TABLA,
        sa.Column("locale", sa.String(10), nullable=False, server_default="es-ES"),
    )
    op.create_check_constraint("locale", _TABLA, "locale IN ('es-ES', 'en-US')")
    op.drop_constraint("uq_platform_legal_pages_kind", _TABLA, type_="unique")
    op.create_unique_constraint("uq_platform_legal_pages_kind_locale", _TABLA, ["kind", "locale"])


def downgrade() -> None:
    # Las versiones en otros idiomas no caben en el esquema anterior.
    op.execute(f"DELETE FROM {_TABLA} WHERE locale <> 'es-ES'")
    op.drop_constraint("uq_platform_legal_pages_kind_locale", _TABLA, type_="unique")
    op.create_unique_constraint("uq_platform_legal_pages_kind", _TABLA, ["kind"])
    op.execute(f"ALTER TABLE {_TABLA} DROP CONSTRAINT IF EXISTS ck_{_TABLA}_locale")
    op.drop_column(_TABLA, "locale")
