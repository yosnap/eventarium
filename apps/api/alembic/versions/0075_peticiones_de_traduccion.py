"""Peticiones de traducción con IA

Cola de trabajo en base de datos: una fila por ámbito (un evento, o lo que es de
la organización) e idioma. Al guardar un texto se crea o se renueva la fila; un
barrido periódico la procesa cuando lleva un rato quieta, así varias ediciones
seguidas acaban en una sola traducción. Vive en base de datos, no en Redis: si
Redis cae, no se pierde nada pendiente.

Solo la usa el rol de mantenimiento (el barrido y quien encola desde el
servidor); `app_user` no tiene acceso.

Revision ID: 0075_peticiones_de_traduccion
Revises: 0074_traducciones_de_contenido
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0075_peticiones_de_traduccion"
down_revision: str | None = "0074_traducciones_de_contenido"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLA = "translation_requests"


def upgrade() -> None:
    op.create_table(
        _TABLA,
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        # `NULL`: lo que es de la organización (perfiles, etiquetas, políticas…).
        sa.Column("event_id", sa.UUID(), nullable=True),
        sa.Column("locale", sa.String(10), nullable=False),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_translation_requests_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["event_id", "organization_id"],
            ["events.id", "events.organization_id"],
            name="fk_translation_requests_event_id_organization_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_translation_requests"),
        sa.CheckConstraint("locale IN ('es-ES', 'en-US')", name="locale"),
    )
    # Una fila por ámbito e idioma; `event_id` nulo cuenta como un valor más.
    op.execute(
        f"CREATE UNIQUE INDEX uq_translation_requests_ambito ON {_TABLA} "
        "(organization_id, COALESCE(event_id, '00000000-0000-0000-0000-000000000000'::uuid), "
        "locale)"
    )
    op.create_index("ix_translation_requests_requested_at", _TABLA, ["requested_at"])
    op.execute(f"REVOKE ALL ON {_TABLA} FROM app_user")


def downgrade() -> None:
    op.drop_index("ix_translation_requests_requested_at", table_name=_TABLA)
    op.execute("DROP INDEX IF EXISTS uq_translation_requests_ambito")
    op.drop_table(_TABLA)
