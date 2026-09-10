"""apertura de inscripción

Fase de fidelidad visual del listado público (`descubrir-eventos.html`): el
prototipo real distingue un evento «próximamente» (inscripción aún no
abierta) de uno «abierto», dato que hasta ahora no existía en `events` —
`chipFila` en `events-list-page.ts` solo distinguía abierto/completo/con
aprobación. Columna nullable, sin backfill: los eventos ya creados quedan con
`registration_opens_at IS NULL`, que se trata como «ya abierta» (mismo
comportamiento que tenían antes de este campo).

Revision ID: 0019_apertura_de_inscripcion
Revises: 0018_corrige_tokens_claros
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0019_apertura_de_inscripcion"
down_revision: str | None = "0018_corrige_tokens_claros"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "events", sa.Column("registration_opens_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("events", "registration_opens_at")
