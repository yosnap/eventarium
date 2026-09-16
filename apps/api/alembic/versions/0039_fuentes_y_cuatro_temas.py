"""selector de tipografía y cuatro juegos de plantillas

Dos novedades juntas porque comparten la misma tabla:

1. Los tokens de plantilla ganan `font-display` y `font-body`: la familia
   tipográfica pasa a ser elegible por plantilla, de entre las autoalojadas
   (`styles/font-faces.css`). La plantilla por defecto conserva su pareja
   actual (Bebas Neue + DM Sans).
2. Cuatro juegos nuevos de plantillas, cada uno con sus dos modos, pensados
   para ambientes distintos y validados contra los pares críticos de
   contraste AA antes de escribirse: Neón (nocturno/tech), Editorial
   (cultural), Festival (cálido) y Bosque (natural).

Ninguna es predeterminada: la única `is_default` sigue siendo la que fusionó
`0038`.

Revision ID: 0039_fuentes_y_cuatro_temas
Revises: 0038_plantilla_unica_y_modo
"""

from __future__ import annotations

import json
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0039_fuentes_y_cuatro_temas"
down_revision: str | None = "0038_plantilla_unica_y_modo"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FUENTES_POR_DEFECTO = {"font-display": "Bebas Neue", "font-body": "DM Sans"}

_PLANTILLAS_NUEVAS = [
    {
        'key': 'neon',
        'name': 'Neón',
        'default_mode': 'dark',
        'tokens': {
                'dark': {
                    'bg': 'oklch(16% 0.045 285)',
                    'surface': 'oklch(20% 0.055 285)',
                    'surface-2': 'oklch(18% 0.05 285)',
                    'surface-hi': 'oklch(25% 0.06 285)',
                    'border': 'oklch(29% 0.05 285)',
                    'border-strong': 'oklch(33% 0.06 285)',
                    'fg': 'oklch(96% 0.015 285)',
                    'muted': 'oklch(74% 0.035 285)',
                    'faint': 'oklch(48% 0.04 285)',
                    'accent': 'oklch(86% 0.17 195)',
                    'accent-hi': 'oklch(93% 0.12 195)',
                    'accent-dim': 'oklch(86% 0.17 195 / 0.12)',
                    'on-accent': 'oklch(18% 0.05 285)',
                    'warn': 'oklch(82% 0.16 95)',
                    'warn-dim': 'oklch(82% 0.16 95 / 0.14)',
                    'danger': 'oklch(70% 0.2 22)',
                    'danger-dim': 'oklch(70% 0.2 22 / 0.14)',
                    'nav-bg': 'oklch(16% 0.045 285 / 0.88)',
                    'backdrop': 'oklch(16% 0.045 285 / 0.72)',
                    'shadow-md': '0 18px 40px oklch(0% 0 0 / 0.55)',
                    'shadow-lg': '0 24px 60px oklch(0% 0 0 / 0.55)',
                    'font-display': 'Archivo Black',
                    'font-body': 'Inter',
                },
                'light': {
                    'bg': 'oklch(98% 0.008 285)',
                    'surface': 'oklch(96% 0.015 285)',
                    'surface-2': 'oklch(94% 0.018 285)',
                    'surface-hi': 'oklch(91% 0.02 285)',
                    'border': 'oklch(87% 0.02 285)',
                    'border-strong': 'oklch(80% 0.025 285)',
                    'fg': 'oklch(24% 0.05 285)',
                    'muted': 'oklch(42% 0.04 285)',
                    'faint': 'oklch(60% 0.035 285)',
                    'accent': 'oklch(50% 0.2 262)',
                    'accent-hi': 'oklch(58% 0.19 262)',
                    'accent-dim': 'oklch(50% 0.2 262 / 0.1)',
                    'on-accent': 'oklch(98% 0.01 285)',
                    'warn': 'oklch(48% 0.16 80)',
                    'warn-dim': 'oklch(48% 0.16 80 / 0.1)',
                    'danger': 'oklch(50% 0.2 25)',
                    'danger-dim': 'oklch(50% 0.2 25 / 0.1)',
                    'nav-bg': 'oklch(98% 0.008 285 / 0.88)',
                    'backdrop': 'oklch(98% 0.008 285 / 0.72)',
                    'shadow-md': '0 18px 40px oklch(0% 0 0 / 0.14)',
                    'shadow-lg': '0 24px 60px oklch(0% 0 0 / 0.14)',
                    'font-display': 'Archivo Black',
                    'font-body': 'Inter',
                },
        },
    },
    {
        'key': 'editorial',
        'name': 'Editorial',
        'default_mode': 'light',
        'tokens': {
                'dark': {
                    'bg': 'oklch(19% 0.018 55)',
                    'surface': 'oklch(23% 0.022 55)',
                    'surface-2': 'oklch(21% 0.02 55)',
                    'surface-hi': 'oklch(28% 0.025 55)',
                    'border': 'oklch(32% 0.025 55)',
                    'border-strong': 'oklch(36% 0.028 55)',
                    'fg': 'oklch(93% 0.025 85)',
                    'muted': 'oklch(72% 0.03 80)',
                    'faint': 'oklch(50% 0.03 70)',
                    'accent': 'oklch(80% 0.11 80)',
                    'accent-hi': 'oklch(88% 0.08 80)',
                    'accent-dim': 'oklch(80% 0.11 80 / 0.12)',
                    'on-accent': 'oklch(20% 0.02 55)',
                    'warn': 'oklch(80% 0.13 85)',
                    'warn-dim': 'oklch(80% 0.13 85 / 0.14)',
                    'danger': 'oklch(68% 0.17 22)',
                    'danger-dim': 'oklch(68% 0.17 22 / 0.14)',
                    'nav-bg': 'oklch(19% 0.018 55 / 0.88)',
                    'backdrop': 'oklch(19% 0.018 55 / 0.72)',
                    'shadow-md': '0 18px 40px oklch(0% 0 0 / 0.5)',
                    'shadow-lg': '0 24px 60px oklch(0% 0 0 / 0.5)',
                    'font-display': 'Playfair Display',
                    'font-body': 'Lora',
                },
                'light': {
                    'bg': 'oklch(97% 0.02 85)',
                    'surface': 'oklch(94.5% 0.025 85)',
                    'surface-2': 'oklch(92.5% 0.028 85)',
                    'surface-hi': 'oklch(89% 0.03 85)',
                    'border': 'oklch(85% 0.03 80)',
                    'border-strong': 'oklch(78% 0.035 80)',
                    'fg': 'oklch(26% 0.035 55)',
                    'muted': 'oklch(44% 0.035 60)',
                    'faint': 'oklch(58% 0.03 60)',
                    'accent': 'oklch(40% 0.12 28)',
                    'accent-hi': 'oklch(48% 0.12 28)',
                    'accent-dim': 'oklch(40% 0.12 28 / 0.1)',
                    'on-accent': 'oklch(97% 0.02 85)',
                    'warn': 'oklch(45% 0.12 60)',
                    'warn-dim': 'oklch(45% 0.12 60 / 0.1)',
                    'danger': 'oklch(48% 0.17 25)',
                    'danger-dim': 'oklch(48% 0.17 25 / 0.1)',
                    'nav-bg': 'oklch(97% 0.02 85 / 0.88)',
                    'backdrop': 'oklch(97% 0.02 85 / 0.72)',
                    'shadow-md': '0 18px 40px oklch(0% 0 0 / 0.14)',
                    'shadow-lg': '0 24px 60px oklch(0% 0 0 / 0.14)',
                    'font-display': 'Playfair Display',
                    'font-body': 'Lora',
                },
        },
    },
    {
        'key': 'festival',
        'name': 'Festival',
        'default_mode': 'light',
        'tokens': {
                'dark': {
                    'bg': 'oklch(17% 0.035 40)',
                    'surface': 'oklch(21% 0.045 40)',
                    'surface-2': 'oklch(19% 0.04 40)',
                    'surface-hi': 'oklch(26% 0.05 40)',
                    'border': 'oklch(30% 0.045 40)',
                    'border-strong': 'oklch(34% 0.05 40)',
                    'fg': 'oklch(95% 0.025 70)',
                    'muted': 'oklch(73% 0.045 55)',
                    'faint': 'oklch(48% 0.045 45)',
                    'accent': 'oklch(78% 0.15 55)',
                    'accent-hi': 'oklch(86% 0.11 60)',
                    'accent-dim': 'oklch(78% 0.15 55 / 0.14)',
                    'on-accent': 'oklch(18% 0.04 40)',
                    'warn': 'oklch(80% 0.15 90)',
                    'warn-dim': 'oklch(80% 0.15 90 / 0.14)',
                    'danger': 'oklch(68% 0.19 22)',
                    'danger-dim': 'oklch(68% 0.19 22 / 0.14)',
                    'nav-bg': 'oklch(17% 0.035 40 / 0.88)',
                    'backdrop': 'oklch(17% 0.035 40 / 0.72)',
                    'shadow-md': '0 18px 40px oklch(0% 0 0 / 0.5)',
                    'shadow-lg': '0 24px 60px oklch(0% 0 0 / 0.5)',
                    'font-display': 'Oswald',
                    'font-body': 'DM Sans',
                },
                'light': {
                    'bg': 'oklch(97.5% 0.025 75)',
                    'surface': 'oklch(95.5% 0.03 70)',
                    'surface-2': 'oklch(93.5% 0.032 70)',
                    'surface-hi': 'oklch(90% 0.035 70)',
                    'border': 'oklch(86% 0.035 65)',
                    'border-strong': 'oklch(79% 0.04 65)',
                    'fg': 'oklch(26% 0.06 40)',
                    'muted': 'oklch(44% 0.055 45)',
                    'faint': 'oklch(58% 0.05 45)',
                    'accent': 'oklch(49% 0.2 33)',
                    'accent-hi': 'oklch(56% 0.19 38)',
                    'accent-dim': 'oklch(49% 0.2 33 / 0.1)',
                    'on-accent': 'oklch(98% 0.02 75)',
                    'warn': 'oklch(45% 0.14 80)',
                    'warn-dim': 'oklch(45% 0.14 80 / 0.1)',
                    'danger': 'oklch(48% 0.19 25)',
                    'danger-dim': 'oklch(48% 0.19 25 / 0.1)',
                    'nav-bg': 'oklch(97.5% 0.025 75 / 0.88)',
                    'backdrop': 'oklch(97.5% 0.025 75 / 0.72)',
                    'shadow-md': '0 18px 40px oklch(0% 0 0 / 0.14)',
                    'shadow-lg': '0 24px 60px oklch(0% 0 0 / 0.14)',
                    'font-display': 'Oswald',
                    'font-body': 'DM Sans',
                },
        },
    },
    {
        'key': 'bosque',
        'name': 'Bosque',
        'default_mode': 'dark',
        'tokens': {
                'dark': {
                    'bg': 'oklch(17% 0.028 150)',
                    'surface': 'oklch(21% 0.033 150)',
                    'surface-2': 'oklch(19% 0.03 150)',
                    'surface-hi': 'oklch(26% 0.036 150)',
                    'border': 'oklch(30% 0.033 150)',
                    'border-strong': 'oklch(34% 0.036 150)',
                    'fg': 'oklch(94% 0.02 130)',
                    'muted': 'oklch(72% 0.035 140)',
                    'faint': 'oklch(48% 0.035 145)',
                    'accent': 'oklch(83% 0.16 128)',
                    'accent-hi': 'oklch(90% 0.12 128)',
                    'accent-dim': 'oklch(83% 0.16 128 / 0.14)',
                    'on-accent': 'oklch(19% 0.03 150)',
                    'warn': 'oklch(81% 0.14 110)',
                    'warn-dim': 'oklch(81% 0.14 110 / 0.14)',
                    'danger': 'oklch(68% 0.18 22)',
                    'danger-dim': 'oklch(68% 0.18 22 / 0.14)',
                    'nav-bg': 'oklch(17% 0.028 150 / 0.88)',
                    'backdrop': 'oklch(17% 0.028 150 / 0.72)',
                    'shadow-md': '0 18px 40px oklch(0% 0 0 / 0.5)',
                    'shadow-lg': '0 24px 60px oklch(0% 0 0 / 0.5)',
                    'font-display': 'Oswald',
                    'font-body': 'Lora',
                },
                'light': {
                    'bg': 'oklch(97% 0.018 130)',
                    'surface': 'oklch(95% 0.022 130)',
                    'surface-2': 'oklch(93% 0.025 130)',
                    'surface-hi': 'oklch(89.5% 0.028 130)',
                    'border': 'oklch(85% 0.028 130)',
                    'border-strong': 'oklch(78% 0.032 130)',
                    'fg': 'oklch(26% 0.045 150)',
                    'muted': 'oklch(43% 0.04 150)',
                    'faint': 'oklch(57% 0.035 150)',
                    'accent': 'oklch(44% 0.12 152)',
                    'accent-hi': 'oklch(52% 0.12 152)',
                    'accent-dim': 'oklch(44% 0.12 152 / 0.1)',
                    'on-accent': 'oklch(98% 0.015 130)',
                    'warn': 'oklch(44% 0.12 100)',
                    'warn-dim': 'oklch(44% 0.12 100 / 0.1)',
                    'danger': 'oklch(48% 0.18 25)',
                    'danger-dim': 'oklch(48% 0.18 25 / 0.1)',
                    'nav-bg': 'oklch(97% 0.018 130 / 0.88)',
                    'backdrop': 'oklch(97% 0.018 130 / 0.72)',
                    'shadow-md': '0 18px 40px oklch(0% 0 0 / 0.14)',
                    'shadow-lg': '0 24px 60px oklch(0% 0 0 / 0.14)',
                    'font-display': 'Oswald',
                    'font-body': 'Lora',
                },
        },
    },
]


def upgrade() -> None:
    bind = op.get_bind()

    # La plantilla por defecto gana sus tokens tipográficos (su pareja actual),
    # en los dos modos: la tipografía no cambia con el tema.
    fila = bind.execute(
        sa.text("SELECT tokens FROM theme_templates WHERE key = 'por-defecto'")
    ).scalar_one_or_none()
    if fila is not None:
        for modo in ("dark", "light"):
            fila[modo].update(_FUENTES_POR_DEFECTO)
        bind.execute(
            sa.text("UPDATE theme_templates SET tokens = CAST(:tokens AS jsonb) WHERE key = 'por-defecto'")
            .bindparams(tokens=json.dumps(fila))
        )

    for plantilla in _PLANTILLAS_NUEVAS:
        bind.execute(
            sa.text(
                "INSERT INTO theme_templates (id, key, name, tokens, is_default, default_mode) "
                "VALUES (gen_random_uuid(), :key, :name, CAST(:tokens AS jsonb), false, :default_mode) "
                "ON CONFLICT (key) DO NOTHING"
            ).bindparams(
                key=plantilla["key"],
                name=plantilla["name"],
                tokens=json.dumps(plantilla["tokens"]),
                default_mode=plantilla["default_mode"],
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    for plantilla in _PLANTILLAS_NUEVAS:
        bind.execute(
            sa.text("DELETE FROM theme_templates WHERE key = :key").bindparams(
                key=plantilla["key"]
            )
        )
    fila = bind.execute(
        sa.text("SELECT tokens FROM theme_templates WHERE key = 'por-defecto'")
    ).scalar_one_or_none()
    if fila is not None:
        for modo in ("dark", "light"):
            fila[modo].pop("font-display", None)
            fila[modo].pop("font-body", None)
        bind.execute(
            sa.text("UPDATE theme_templates SET tokens = CAST(:tokens AS jsonb) WHERE key = 'por-defecto'")
            .bindparams(tokens=json.dumps(fila))
        )
