"""plantilla de tema por evento

Añade `events.theme_template_id`, para que cada evento pueda verse distinto
dentro del catálogo que cura la plataforma.

El caso real: un organizador lleva una semana técnica y una gala benéfica, y
quiere que cada una tenga su identidad visual. Hasta ahora la plantilla era de la
organización entera, así que las dos se veían igual.

**Con herencia, y en tres niveles:** si el evento no elige, usa la de su
organización; si la organización tampoco, la marcada por defecto en el catálogo.
`NULL` significa «hereda», no «sin tema» — por eso la columna es nullable y no
hay backfill: las filas que ya existen heredan lo que heredaban antes.

La FK es simple contra `theme_templates.id` y no compuesta con la organización:
`theme_templates` es una tabla de **instalación**, sin `organization_id` ni RLS
(el catálogo es común y lo cura el admin), así que no hay nada que cruzar.

`ON DELETE SET NULL`: borrar una plantilla del catálogo devuelve los eventos que
la usaban a heredar, en vez de impedir el borrado o dejarlos apuntando a nada.

Revision ID: 0025_plantilla_por_evento
Revises: 0024_ultimo_acceso_por_membresia
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0025_plantilla_por_evento"
down_revision: str | None = "0024_ultimo_acceso_por_membresia"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "events",
        sa.Column("theme_template_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_events_theme_template_id",
        "events",
        "theme_templates",
        ["theme_template_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_events_theme_template_id", "events", type_="foreignkey")
    op.drop_column("events", "theme_template_id")
