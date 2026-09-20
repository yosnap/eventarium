"""auditoria de impersonacion

Añade a `audit_log` las dos columnas que la auditoría de una suplantación
necesita y que no cabían en el esquema anterior:

- `subject_user_id`: la persona **sobre la que** se actúa cuando no es la misma
  que el actor. En una impersonación el actor es el administrador y el sujeto
  es el usuario suplantado; sin esta columna esa relación solo cabía en
  `detail` (JSONB, sin índice ni integridad referencial). `ondelete=SET NULL`
  por el mismo motivo que `actor_user_id`: conservar la fila de auditoría
  aunque el usuario se borre.
- `session_id`: agrupa las filas de una misma sesión de suplantación (entrada,
  acciones y salida) para poder reconstruirla y medir su duración.

Índice por `session_id`: es la consulta real («qué pasó en esta sesión»).

Revision ID: 0023_auditoria_impersonacion
Revises: 0022_identidad_plataforma
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0023_auditoria_impersonacion"
down_revision: str | None = "0022_identidad_plataforma"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLA = "audit_log"


def upgrade() -> None:
    op.add_column(_TABLA, sa.Column("subject_user_id", sa.UUID(), nullable=True))
    op.add_column(_TABLA, sa.Column("session_id", sa.String(length=64), nullable=True))

    op.create_foreign_key(
        "fk_audit_log_subject_user_id_users",
        _TABLA,
        "users",
        ["subject_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_audit_log_session_id", _TABLA, ["session_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_audit_log_session_id", table_name=_TABLA)
    op.drop_constraint("fk_audit_log_subject_user_id_users", _TABLA, type_="foreignkey")
    op.drop_column(_TABLA, "session_id")
    op.drop_column(_TABLA, "subject_user_id")
