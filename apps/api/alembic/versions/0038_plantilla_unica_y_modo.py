"""una sola plantilla de tema con su modo por defecto

Las dos plantillas sembradas por `0014` (`oscuro`/`claro`) llevan **el mismo
contenido** — cada una ya declara los dos modos completos en
`tokens->>{dark,light}` — así que son la misma plantilla duplicada, no dos
temas. El catálogo pasa a tener una única plantilla («Por defecto»), y cada
plantilla gana `default_mode` ('dark' | 'light'): el modo con el que abre
quien no ha elegido todavía (cookie de tema ausente). El conmutador del
visitante sigue decidiendo después.

La migración es idempotente frente al estado del catálogo:
- Si están `oscuro` y `claro`: las referencias (`platform_branding`,
  `organization_branding`, `events`) que apuntaban a `claro` se reasignan a la
  superviviente, `claro` se borra y la superviviente se renombra.
- Si solo queda `oscuro` (re-migración: se bajó hasta `0014` y se volvió a
  subir, y el `downgrade` de `0014` re-siembró pero esta ya consumió `claro`):
  solo se normaliza el nombre de la fila superviviente.
- Si el catálogo está vacío (instalaciones donde las filas de `0014` ya no
  existen): siembra la plantilla única con los tokens de `tokens.css`.

El `downgrade` solo retira la columna: no renombra, para que volver a subir
este mismo fichero normalice el estado sin pasos extra. Las referencias que
apuntaban a `claro` antes del merge no se pueden distinguir de las que
siempre apuntaron a la superviviente: se quedan.

Revision ID: 0038_plantilla_unica_y_modo
Revises: 0037_sin_plantilla_portada
"""

from __future__ import annotations

import json
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0038_plantilla_unica_y_modo"
down_revision: str | None = "0037_sin_plantilla_portada"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLAS_CON_PLANTILLA = ("platform_branding", "organization_branding", "events")

# Copia de `tokens.css` (los mismos valores que `0014` sembró y `0018` corrigió),
# para resembrar el catálogo cuando las filas originales ya no existen.
_TOKENS_OSCURO = {
    "bg": "oklch(13.44% 0 89.88)",
    "surface": "oklch(19.13% 0 89.88)",
    "surface-2": "oklch(16.84% 0 89.88)",
    "surface-hi": "oklch(23% 0 90)",
    "border": "oklch(25.2% 0 89.88)",
    "border-strong": "oklch(28.5% 0 89.88)",
    "fg": "oklch(95.51% 0 89.88)",
    "muted": "oklch(68.3% 0 89.88)",
    "faint": "oklch(44.95% 0 89.88)",
    "accent": "oklch(87.61% 0.2286 152.37)",
    "accent-hi": "oklch(94% 0.18 152.4)",
    "accent-dim": "oklch(87.61% 0.2286 152.37 / 0.1)",
    "on-accent": "oklch(13.44% 0 89.88)",
    "warn": "oklch(66.96% 0.222 37.42)",
    "warn-dim": "oklch(66.96% 0.222 37.42 / 0.14)",
    "danger": "oklch(67.32% 0.2143 24.47)",
    "danger-dim": "oklch(67.32% 0.2143 24.47 / 0.14)",
    "nav-bg": "oklch(13.4% 0 90 / 0.88)",
    "backdrop": "oklch(13.4% 0 90 / 0.72)",
    "shadow-md": "0 18px 40px oklch(0% 0 0 / 0.55)",
    "shadow-lg": "0 24px 60px oklch(0% 0 0 / 0.55)",
}
_TOKENS_CLARO = {
    "bg": "oklch(97.5% 0 90)",
    "surface": "oklch(95.8% 0 90)",
    "surface-2": "oklch(93.9% 0 90)",
    "surface-hi": "oklch(90.5% 0 90)",
    "border": "oklch(87% 0 90)",
    "border-strong": "oklch(80% 0 90)",
    "fg": "oklch(15% 0 90)",
    "muted": "oklch(42% 0 90)",
    "faint": "oklch(60% 0 90)",
    "accent": "oklch(45% 0.15 152.4)",
    "accent-hi": "oklch(52% 0.15 152.4)",
    "accent-dim": "oklch(45% 0.15 152.4 / 0.1)",
    "on-accent": "oklch(100% 0 0)",
    "warn": "oklch(48% 0.18 37.42)",
    "warn-dim": "oklch(48% 0.18 37.42 / 0.1)",
    "danger": "oklch(48% 0.17 24.47)",
    "danger-dim": "oklch(48% 0.17 24.47 / 0.1)",
    "nav-bg": "oklch(97.5% 0 90 / 0.88)",
    "backdrop": "oklch(19.5% 0 90 / 0.42)",
    "shadow-md": "0 18px 40px oklch(19.5% 0 90 / 0.14)",
    "shadow-lg": "0 24px 60px oklch(19.5% 0 90 / 0.18)",
}


def upgrade() -> None:
    op.add_column(
        "theme_templates",
        sa.Column("default_mode", sa.String(length=5), nullable=False, server_default="light"),
    )

    bind = op.get_bind()
    superviviente = bind.execute(
        sa.text("SELECT id FROM theme_templates WHERE key = 'oscuro'")
    ).scalar_one_or_none()
    descartada = bind.execute(
        sa.text("SELECT id FROM theme_templates WHERE key = 'claro'")
    ).scalar_one_or_none()
    hay_por_defecto = bind.execute(
        sa.text("SELECT count(*) FROM theme_templates WHERE key = 'por-defecto'")
    ).scalar_one()

    if superviviente is not None and descartada is not None:
        # El caso de `0014` intacto: dos filas idénticas que se fusionan.
        for tabla in TABLAS_CON_PLANTILLA:
            bind.execute(
                sa.text(
                    f"UPDATE {tabla} SET theme_template_id = :superviviente "
                    "WHERE theme_template_id = :descartada"
                ).bindparams(superviviente=superviviente, descartada=descartada)
            )
        bind.execute(sa.text("DELETE FROM theme_templates WHERE id = :id").bindparams(id=descartada))
        bind.execute(
            sa.text(
                "UPDATE theme_templates SET key = 'por-defecto', name = 'Por defecto', "
                "is_default = true, default_mode = 'light' WHERE id = :id"
            ).bindparams(id=superviviente)
        )
    elif superviviente is not None and not hay_por_defecto:
        # Re-migración (se bajó hasta `0014` y se volvió a subir): la fila
        # fusionada quedó renombrada por el downgrade anterior y `claro` ya no
        # existe. Solo se normaliza el nombre; no hay nada que fusionar.
        bind.execute(
            sa.text(
                "UPDATE theme_templates SET key = 'por-defecto', name = 'Por defecto', "
                "default_mode = 'light' WHERE id = :id"
            ).bindparams(id=superviviente)
        )
    elif bind.execute(sa.text("SELECT count(*) FROM theme_templates")).scalar_one() == 0:
        # Instalación sin catálogo (las filas de `0014` ya no están): siembra la
        # plantilla única con los tokens de `tokens.css`.
        bind.execute(
            sa.text(
                "INSERT INTO theme_templates (id, key, name, tokens, is_default, default_mode) "
                "VALUES (gen_random_uuid(), 'por-defecto', 'Por defecto', "
                "CAST(:tokens AS jsonb), true, 'light') "
                "ON CONFLICT (key) DO NOTHING"
            ).bindparams(tokens=json.dumps({"dark": _TOKENS_OSCURO, "light": _TOKENS_CLARO}))
        )

    # Garantía final: siempre hay exactamente una plantilla predeterminada.
    sin_default = bind.execute(
        sa.text("SELECT count(*) FROM theme_templates WHERE is_default")
    ).scalar_one()
    if sin_default == 0:
        bind.execute(
            sa.text(
                "UPDATE theme_templates SET is_default = true "
                "WHERE key = 'por-defecto' AND id = (SELECT id FROM theme_templates LIMIT 1)"
            )
        )


def downgrade() -> None:
    # El nombre de la fila superviviente se deja como esté: volver a subir esta
    # migración lo normaliza de nuevo a `por-defecto`. Las referencias que
    # apuntaban a `claro` antes del merge no se pueden distinguir de las que
    # siempre apuntaron a la superviviente: se quedan.
    op.drop_column("theme_templates", "default_mode")
