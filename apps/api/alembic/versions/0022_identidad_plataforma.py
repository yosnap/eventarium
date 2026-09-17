"""identidad de plataforma

Fase 1 del plan de interfaz de plataforma. Migración **estrictamente
aditiva**. Crea tres tablas de **instalación** (sin `organization_id` y por
tanto sin RLS: describen a la plataforma entera, no a un tenant):

- `platform_branding`: identidad de la web de la instalación (nombre, logo,
  favicon, redes, plantilla de tema). Una sola fila, garantizado por una PK
  de valor fijo (`singleton`), no por convención de aplicación.
- `platform_domains`: hosts que sirven la web de la plataforma. Es lo que
  permite que un host sin organización deje de ser un 404 y pase a servir la
  identidad y las páginas legales de la instalación.
- `platform_legal_pages`: textos legales de la plataforma por tipo de página
  (aviso legal, privacidad, cookies). Sin fila = plantilla por defecto.

Mismo patrón de privilegios que `theme_templates` (`0014`) y
`stripe_webhook_events` (`0013`): `ALTER DEFAULT PRIVILEGES`
(`infra/postgres/sql/roles.sql`) concede a `app_user` DML completo sobre toda
tabla nueva, así que aquí se retira el DML y se deja **solo `SELECT`**, que sí
hace falta para los endpoints públicos. Sin este `REVOKE`, cualquier sesión de
organización podría reescribir el logo de la plataforma y —peor— los textos
legales que se sirven a toda la instalación, e incluso borrar la identidad.

Semilla: una fila de identidad con el nombre «Eventarium». Sin semilla, el
endpoint público responde igualmente (el repositorio cae a un objeto en
memoria con ese nombre), pero sembrarla deja el estado explícito y editable.

Revision ID: 0022_identidad_plataforma
Revises: 0021_contabilidad_exportacion
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0022_identidad_plataforma"
down_revision: str | None = "0021_contabilidad_exportacion"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLAS_DE_INSTALACION = ("platform_branding", "platform_domains", "platform_legal_pages")


def upgrade() -> None:
    op.create_table(
        "platform_branding",
        sa.Column("singleton", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("logo_object_key", sa.String(length=500), nullable=True),
        sa.Column("favicon_object_key", sa.String(length=500), nullable=True),
        sa.Column("theme_template_id", sa.UUID(), nullable=True),
        sa.Column("social_links", sa.dialects.postgresql.JSONB(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["theme_template_id"],
            ["theme_templates.id"],
            name="fk_platform_branding_theme_template_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("singleton", name="pk_platform_branding"),
        sa.CheckConstraint("singleton = 'default'", name="ck_platform_branding_singleton"),
    )

    op.create_table(
        "platform_domains",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("host", sa.String(length=255), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name="pk_platform_domains"),
        sa.UniqueConstraint("host", name="uq_platform_domains_host"),
    )

    op.create_table(
        "platform_legal_pages",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name="pk_platform_legal_pages"),
        sa.UniqueConstraint("kind", name="uq_platform_legal_pages_kind"),
        sa.CheckConstraint(
            "kind IN ('aviso-legal', 'privacidad', 'cookies')",
            name="ck_platform_legal_pages_kind",
        ),
    )

    _restringir_tablas_de_instalacion()
    _sembrar_identidad()


def _restringir_tablas_de_instalacion() -> None:
    """Deja a `app_user` solo `SELECT` sobre las tablas de plataforma.

    `ALTER DEFAULT PRIVILEGES` concede INSERT/UPDATE/DELETE automáticamente
    sobre toda tabla nueva; sin este `REVOKE`, una sesión de organización
    podría sobrescribir la identidad de la plataforma y sus textos legales, o
    borrarlos. `SELECT` se conserva porque los endpoints públicos leen con
    sesión de organización (branding y páginas legales).
    """
    for tabla in TABLAS_DE_INSTALACION:
        op.execute(f"REVOKE INSERT, UPDATE, DELETE ON {tabla} FROM app_user")


def _sembrar_identidad() -> None:
    """Crea la fila única de identidad con el nombre de la plataforma."""
    op.execute(
        sa.text(
            "INSERT INTO platform_branding (singleton, name, social_links) "
            "VALUES ('default', 'Eventarium', '[]'::jsonb)"
        )
    )


def downgrade() -> None:
    op.drop_table("platform_legal_pages")
    op.drop_table("platform_domains")
    op.drop_table("platform_branding")
