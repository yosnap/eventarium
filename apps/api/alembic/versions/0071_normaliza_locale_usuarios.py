"""Normaliza el idioma de las cuentas al catálogo

`users.locale` fue un texto libre hasta que la API lo restringió a los idiomas del
catálogo (`app/core/locale.py`). Las cuentas con un valor fuera del catálogo (por
ejemplo `es` o `en`) pasan al idioma que les corresponde, o a español si no se
reconoce, para que correos y paneles no tengan que adivinarlo.

El `downgrade` no restaura los valores anteriores: no se guardan, y ninguno era
válido para la aplicación.

Revision ID: 0071_normaliza_locale_usuarios
Revises: 0070_locale_en_invitacion
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0071_normaliza_locale_usuarios"
down_revision: str | None = "0070_locale_en_invitacion"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
UPDATE users
SET locale = CASE
  WHEN lower(split_part(locale, '-', 1)) = 'en' THEN 'en-US'
  ELSE 'es-ES'
END
WHERE locale NOT IN ('es-ES', 'en-US')
        """
    )


def downgrade() -> None:
    pass
