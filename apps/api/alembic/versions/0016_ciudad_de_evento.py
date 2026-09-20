"""ciudad de evento

Fase de fidelidad visual del listado público (`descubrir-eventos.html`): el
prototipo real muestra la ciudad de cada evento en el select de filtro, dato
que hasta ahora no existía en `events`. Columna nullable, sin backfill
obligatorio: los eventos ya creados quedan con `city IS NULL` (se tratan como
"sin ciudad" en el listado público) hasta que se editen desde el panel admin.

Revision ID: 0016_ciudad_de_evento
Revises: 0015_retirada_colores_branding
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0016_ciudad_de_evento"
down_revision: str | None = "0015_retirada_colores_branding"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("events", sa.Column("city", sa.String(length=120), nullable=True))


def downgrade() -> None:
    op.drop_column("events", "city")
