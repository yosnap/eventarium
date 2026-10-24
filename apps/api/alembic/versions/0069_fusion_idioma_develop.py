"""Fusiona la cabeza de idioma de cuenta con el resto de develop

Punto de fusión de Alembic, sin cambios de esquema: esta rama añadió
`0066_locale_en_alta_de_cuenta` y `0067_locale_en_invitacion` sobre
`0062_sin_enlaces_antiguos`, mientras `develop` avanzó por su cuenta con
`0066_sitios_cercanos` → `0067_direccion_y_redes_org` →
`0068_mis_eventos_calendario` desde el mismo punto. Tras el merge de git
hay dos cabezas; esta migración las junta en una sola para que
`alembic upgrade head` vuelva a tener un único destino.

Revision ID: 0069_fusion_idioma_develop
Revises: 0067_locale_en_invitacion, 0068_mis_eventos_calendario
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0069_fusion_idioma_develop"
down_revision: str | None = ("0067_locale_en_invitacion", "0068_mis_eventos_calendario")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
