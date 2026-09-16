"""rol de plataforma y preferencia de notificaciones

Dos columnas nuevas en `users`, base de la fase 0 del plan
`plans/260916-0810-usuarios-y-permisos-plataforma/`:

- `platform_role`: catálogo pequeño y aditivo, distinto de `is_superadmin`.
  Hoy solo admite `'soporte'`; `NULL` es el caso normal. Sin `CHECK` en base
  de datos a propósito (catálogo validado en el schema Pydantic que lo
  escribe, mismo criterio que otros catálogos pequeños del proyecto).
- `notify_similar_events`: preferencia self-service, sin motor de envío
  todavía.

Revision ID: 0040_roles_plataforma
Revises: 0039_fuentes_y_cuatro_temas
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0040_roles_plataforma"
down_revision: str | None = "0039_fuentes_y_cuatro_temas"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("platform_role", sa.String(length=20), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "notify_similar_events",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "notify_similar_events")
    op.drop_column("users", "platform_role")
