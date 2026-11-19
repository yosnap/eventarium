"""Idioma de cada inscripción

Guarda el idioma en que se hizo la inscripción. Los correos de esa inscripción
(verificación, entrada, lista de espera, pago) van en ese idioma, también para
quien se inscribe sin cuenta, y los enlaces de vuelta a la web llevan su prefijo.
Las inscripciones existentes quedan en español, el único idioma que había.

Revision ID: 0073_idioma_de_inscripcion
Revises: 0072_idiomas_de_plataforma
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0073_idioma_de_inscripcion"
down_revision: str | None = "0072_idiomas_de_plataforma"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "event_registrations",
        sa.Column("locale", sa.String(10), nullable=False, server_default="es-ES"),
    )
    op.create_check_constraint(
        "locale",
        "event_registrations",
        "locale IN ('es-ES', 'en-US')",
    )


def downgrade() -> None:
    # Por su nombre literal, con y sin el prefijo duplicado de una versión
    # anterior de esta migración: la base puede tener cualquiera de los dos.
    op.execute(
        "ALTER TABLE event_registrations DROP CONSTRAINT IF EXISTS ck_event_registrations_locale"
    )
    op.execute(
        "ALTER TABLE event_registrations "
        "DROP CONSTRAINT IF EXISTS ck_event_registrations_ck_event_registrations_locale"
    )
    op.drop_column("event_registrations", "locale")
