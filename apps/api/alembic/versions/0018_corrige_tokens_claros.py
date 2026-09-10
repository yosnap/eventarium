"""corrige tokens claros de plantillas de tema

Las dos plantillas sembradas en 0014 llevan el modo claro con
`--surface: oklch(100% 0 0)` (blanco puro), más luminoso que `--bg`, en vez
de más oscuro — y `--surface-2`/`--surface-hi`/`--border`/`--border-strong`
con el mismo desajuste frente a la referencia real
(`eventarium.css:58-63`). `apps/web/src/styles/tokens.css` ya se corrigió a
esos valores reales, pero 0014 sembró una copia literal de tokens.css tal
y como estaba entonces: la migración no se actualiza sola cuando cambia el
fichero de origen.

Como el branding de organización siempre gana a `tokens.css` con la misma
especificidad (`apply-tokens.ts`), y toda organización sin plantilla propia
(`theme_template_id IS NULL`) resuelve a la plantilla por defecto, cualquier
corrección posterior en `tokens.css` quedaba sin efecto visible en modo
claro para todas las organizaciones: los tokens de la plantilla la pisaban
siempre.

Migración de datos, no de esquema: solo actualiza las claves afectadas
dentro de `tokens->'light'` en las dos filas sembradas por 0014
(`oscuro`/`claro`, hoy con el mismo contenido). El modo oscuro no cambia.

Revision ID: 0018_corrige_tokens_claros
Revises: 0017_sedes_multiples_de_evento
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0018_corrige_tokens_claros"
down_revision: str | None = "0017_sedes_multiples_de_evento"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CLAVES_ANTIGUAS = {
    "surface": "oklch(100% 0 0)",
    "surface-2": "oklch(96% 0 90)",
    "surface-hi": "oklch(93% 0 90)",
    "border": "oklch(88% 0 90)",
    "border-strong": "oklch(78% 0 90)",
}

_CLAVES_CORREGIDAS = {
    "surface": "oklch(95.8% 0 90)",
    "surface-2": "oklch(93.9% 0 90)",
    "surface-hi": "oklch(90.5% 0 90)",
    "border": "oklch(87% 0 90)",
    "border-strong": "oklch(80% 0 90)",
}


def _actualizar(valores: dict[str, str]) -> None:
    parche = ", ".join(f'"{clave}": "{valor}"' for clave, valor in valores.items())
    op.execute(
        f"""
        UPDATE theme_templates
        SET tokens = jsonb_set(tokens, '{{light}}', (tokens->'light') || '{{{parche}}}'::jsonb)
        WHERE key IN ('oscuro', 'claro')
        """
    )


def upgrade() -> None:
    _actualizar(_CLAVES_CORREGIDAS)


def downgrade() -> None:
    _actualizar(_CLAVES_ANTIGUAS)
