"""categorías y etiquetas de eventos

Entrega B del plan «organización en la URL y categorías» (0.25.0).

- `event_categories`: catálogo de **instalación** (sin `organization_id` y por
  tanto sin RLS), con el mismo patrón que `theme_templates` (`0014`):
  `ALTER DEFAULT PRIVILEGES` (`infra/postgres/sql/roles.sql`) le concede a
  `app_user` todo sobre cualquier tabla nueva y el `REVOKE` de aquí le deja
  solo `SELECT`. Solo la superadministración escribe (`get_maintenance_db`).
  No se siembra aquí: las categorías las define el superadmin (o `db-seed`
  para desarrollo).
- `events.category_id`: una categoría por evento, FK `ON DELETE RESTRICT`
  (nunca se borra una categoría en uso; se desactiva).
- `events.tags text[] NOT NULL DEFAULT '{}'` con índice GIN, para filtrar por
  etiqueta en la propia consulta (`tags @> ARRAY[...]`).

Revision ID: 0061_categorias_etiquetas
Revises: 0060_evento_eliminado
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, UUID

from alembic import op

revision: str = "0061_categorias_etiquetas"
down_revision: str | None = "0060_evento_eliminado"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "event_categories",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("slug", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_event_categories")),
        sa.UniqueConstraint("slug", name=op.f("uq_event_categories_slug")),
    )
    # Tabla de instalación: la aplicación solo lee.
    op.execute("REVOKE INSERT, UPDATE, DELETE ON event_categories FROM app_user")

    op.add_column(
        "events",
        sa.Column("category_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_events_category_id_event_categories",
        "events",
        "event_categories",
        ["category_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_events_category_id", "events", ["category_id"])
    op.add_column(
        "events",
        sa.Column("tags", ARRAY(sa.Text()), nullable=False, server_default=sa.text("'{}'")),
    )
    op.create_index("ix_events_tags", "events", ["tags"], postgresql_using="gin")


def downgrade() -> None:
    op.drop_index("ix_events_tags", table_name="events")
    op.drop_column("events", "tags")
    op.drop_index("ix_events_category_id", table_name="events")
    op.drop_constraint("fk_events_category_id_event_categories", "events", type_="foreignkey")
    op.drop_column("events", "category_id")
    op.drop_table("event_categories")
