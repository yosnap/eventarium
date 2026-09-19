"""events.theme_overrides: personalización de color/fuente por evento

Fase 1 del plan «diseño del evento»
(`plans/260918-0600-diseno-evento-plantilla/plan.md`). Cada evento hereda su
plantilla visual (`theme_template_id`, ya existente desde el plan de
organización sin dominio), y ahora además puede ajustarla con un color de
acento y dos fuentes propias, sin necesidad de una plantilla completa nueva
en el catálogo. `theme_overrides` es un objeto plano opcional
(`{accent?, font-display?, font-body?}`), NUNCA la forma `{dark:{...},
light:{...}}` de una plantilla: el color de acento se deriva a los 8 valores
finales (accent/accent-hi/accent-dim/on-accent × claro/oscuro) en el momento
de resolver el tema (`app/modules/theme_templates/accent_palette.py`), no se
guardan resueltos.

ADVERTENCIA (`downgrade`): retirar la columna borra irreversiblemente la
personalización de todos los eventos que la usen. Sin export previo.

Revision ID: 0045_event_theme_overrides
Revises: 0044_rol_organizacion_persona
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0045_event_theme_overrides"
down_revision: str | None = "0044_rol_organizacion_persona"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "events",
        sa.Column("theme_overrides", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("events", "theme_overrides")
