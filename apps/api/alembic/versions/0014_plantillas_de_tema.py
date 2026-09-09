"""plantillas de tema

Fase 1 del plan de UX/UI (sistema de diseño Eventarium). Migración
**estrictamente aditiva**: no borra ni modifica ninguna tabla, columna ni
fila existente. La retirada de `organization_branding.colors`/`.fonts` es
una migración distinta y posterior (`0015`), con su propio backup.

Crea `theme_templates`, tabla de **instalación** (sin `organization_id` y
por tanto sin RLS: el catálogo es común a toda la instalación, no datos de
un tenant). Mismo patrón que `stripe_webhook_events`
(`0013_pagos_stripe_connect.py`): `ALTER DEFAULT PRIVILEGES`
(`infra/postgres/sql/roles.sql:50-51`) le concede a `app_user`
SELECT/INSERT/UPDATE/DELETE automáticamente sobre cualquier tabla nueva; el
`REVOKE` de aquí le deja solo `SELECT`. El endpoint público de branding
(`GET /tenant/branding`) necesita leerla con sesión de tenant; solo la
superadministración —con `get_maintenance_db`— debe poder escribirla.

Añade `organization_branding.theme_template_id` (uuid nullable, FK
`ON DELETE RESTRICT`): `NULL` significa «la plantilla marcada
`is_default`». Sin backfill: las organizaciones existentes se quedan en
`NULL` y por tanto ven «Oscuro», que es el comportamiento por defecto del
sistema.

Semilla de dos plantillas, «oscuro» (`is_default = true`) y «claro», copia
literal token por token de los dos bloques de
`apps/web/src/styles/tokens.css` (`:root` y `[data-theme='light']`, valor
final ya cerrado por la fase de cliente). Cada plantilla usa su propio
juego en los dos campos (`dark`/`light` de `tokens`): son los dos temas ya
diseñados en esta fase, no un par oscuro/claro para alternar dentro de la
misma plantilla — de ahí que las dos filas sean deliberadamente distintas
entre sí. Los literales van aquí, no importados de la aplicación: una
migración es un registro histórico.

Los pares críticos de las dos plantillas se han verificado con
`app/modules/theme_templates/contrast.py` antes de fijar estos literales
(los siete pares de `PARES_CRITICOS`, en los dos modos, todos ≥4,5:1); al
repetir cada juego en los dos campos de su plantilla, el resultado es el
mismo cálculo verificado dos veces, sin combinaciones nuevas que
comprobar.

Revision ID: 0014_plantillas_de_tema
Revises: 0013_pagos_stripe_connect
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0014_plantillas_de_tema"
down_revision: str | None = "0013_pagos_stripe_connect"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLAS_DE_INSTALACION = ("theme_templates",)

# Tokens del modo oscuro. Copia literal, token por token, del bloque `:root` de
# `apps/web/src/styles/tokens.css` (fase 1 del plan de UX/UI, valor final de
# cliente). Los alias `--color-*`, radios y espaciado de ese fichero son de
# plataforma y no entran en el catálogo de plantillas.
_TOKENS_OSCURO: dict[str, str] = {
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
    "warn-dim": "oklch(66.96% 0.222 37.42 / 0.1)",
    "danger": "oklch(67.32% 0.2143 24.47)",
    "danger-dim": "oklch(67.32% 0.2143 24.47 / 0.1)",
    "nav-bg": "oklch(16.84% 0 89.88)",
    "backdrop": "oklch(0% 0 0 / 0.6)",
    "shadow-md": "0 4px 12px oklch(0% 0 0 / 0.35)",
    "shadow-lg": "0 12px 32px oklch(0% 0 0 / 0.45)",
}

# Tokens del modo claro. Copia literal, token por token, del bloque
# `[data-theme='light']` de `apps/web/src/styles/tokens.css` (mismo origen que el
# bloque oscuro de arriba).
_TOKENS_CLARO: dict[str, str] = {
    "bg": "oklch(97% 0 90)",
    "surface": "oklch(100% 0 0)",
    "surface-2": "oklch(96% 0 90)",
    "surface-hi": "oklch(93% 0 90)",
    "border": "oklch(88% 0 90)",
    "border-strong": "oklch(78% 0 90)",
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
    "nav-bg": "oklch(96% 0 90)",
    "backdrop": "oklch(0% 0 0 / 0.5)",
    "shadow-md": "0 4px 12px oklch(0% 0 0 / 0.12)",
    "shadow-lg": "0 12px 32px oklch(0% 0 0 / 0.16)",
}


def upgrade() -> None:
    _crear_tabla()
    _restringir_tabla_de_instalacion()
    _sembrar_plantillas()
    _anadir_columna_branding()


def _crear_tabla() -> None:
    op.create_table(
        "theme_templates",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("key", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("tokens", JSONB(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_theme_templates")),
        sa.UniqueConstraint("key", name=op.f("uq_theme_templates_key")),
    )
    # Como mucho una plantilla por defecto.
    op.create_index(
        "uq_theme_templates_is_default",
        "theme_templates",
        ["is_default"],
        unique=True,
        postgresql_where=sa.text("is_default IS TRUE"),
    )


def _restringir_tabla_de_instalacion() -> None:
    """`ALTER DEFAULT PRIVILEGES` concede a `app_user` INSERT/UPDATE/DELETE
    sobre toda tabla nueva automáticamente. Sin este `REVOKE`, cualquier
    sesión de organización podría escribir el catálogo de temas que ve toda
    la instalación. Deja `SELECT`, que sí hace falta para el endpoint público
    de branding. Mismo patrón que `stripe_webhook_events` (`0013:527-540`)."""
    for tabla in TABLAS_DE_INSTALACION:
        op.execute(f"REVOKE INSERT, UPDATE, DELETE ON {tabla} FROM app_user")


def _sembrar_plantillas() -> None:
    tabla = sa.table(
        "theme_templates",
        sa.column("id", sa.UUID()),
        sa.column("key", sa.String()),
        sa.column("name", sa.String()),
        sa.column("tokens", JSONB()),
        sa.column("is_default", sa.Boolean()),
    )
    op.bulk_insert(
        tabla,
        [
            {
                "id": "018fbb2f-0000-7000-8000-000000000001",
                "key": "oscuro",
                "name": "Oscuro",
                # El juego oscuro en los dos campos: esta plantilla es el tema oscuro
                # ya diseñado en la fase 1, no un par oscuro/claro para alternar.
                "tokens": {"dark": _TOKENS_OSCURO, "light": _TOKENS_OSCURO},
                "is_default": True,
            },
            {
                "id": "018fbb2f-0000-7000-8000-000000000002",
                "key": "claro",
                "name": "Claro",
                # El juego claro en los dos campos: el otro tema ya diseñado en la
                # fase 1. Debe ser distinto de la plantilla «oscuro» de arriba.
                "tokens": {"dark": _TOKENS_CLARO, "light": _TOKENS_CLARO},
                "is_default": False,
            },
        ],
    )


def _anadir_columna_branding() -> None:
    op.add_column(
        "organization_branding",
        sa.Column("theme_template_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_organization_branding_theme_template_id_theme_templates",
        "organization_branding",
        "theme_templates",
        ["theme_template_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_organization_branding_theme_template_id_theme_templates",
        "organization_branding",
        type_="foreignkey",
    )
    op.drop_column("organization_branding", "theme_template_id")

    for tabla in TABLAS_DE_INSTALACION:
        op.execute(f"GRANT INSERT, UPDATE, DELETE ON {tabla} TO app_user")

    op.drop_index("uq_theme_templates_is_default", table_name="theme_templates")
    op.drop_table("theme_templates")
