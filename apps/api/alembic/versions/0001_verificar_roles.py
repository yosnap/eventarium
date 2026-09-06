"""Verifica que existen los roles de aplicación antes de crear nada.

Los roles se crean fuera de Alembic (`infra/postgres/init/01-roles.sh`), porque
`CREATE ROLE` es global al clúster y no se puede revertir de forma segura desde una
migración. Esta primera revisión solo comprueba que el entorno está bien preparado y
falla pronto con un mensaje claro si no lo está.

Revision ID: 0001_verificar_roles
Revises:
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001_verificar_roles"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MENSAJE = (
    "Falta el rol de base de datos «{rol}». Ejecuta infra/scripts/ensure-roles.sh "
    "o recrea el contenedor de PostgreSQL para que corra infra/postgres/init/01-roles.sh."
)


def upgrade() -> None:
    conexion = op.get_bind()
    for rol in ("app_user", "app_maintainer"):
        existe = conexion.execute(
            sa.text("SELECT 1 FROM pg_roles WHERE rolname = :rol"), {"rol": rol}
        ).scalar()
        if not existe:
            raise RuntimeError(MENSAJE.format(rol=rol))

    bypass = conexion.execute(
        sa.text("SELECT rolbypassrls FROM pg_roles WHERE rolname = 'app_user'")
    ).scalar()
    if bypass:
        raise RuntimeError(
            "El rol «app_user» tiene BYPASSRLS: con él las políticas RLS no protegerían "
            "nada. Corrígelo con ALTER ROLE app_user NOBYPASSRLS."
        )


def downgrade() -> None:
    # Nada que revertir: esta revisión no crea objetos.
    pass
