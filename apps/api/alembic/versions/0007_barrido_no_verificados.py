"""barrido de cuentas no verificadas

Añade `users.verification_warning_sent_at`: sin ella, el barrido horario reenviaría el
aviso de los 5 días en cada pasada mientras la cuenta siga sin verificar, en vez de una
sola vez.

Revision ID: 0007_barrido_no_verificados
Revises: 0006_autoservicio_organizaciones
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007_barrido_no_verificados"
down_revision: str | None = "0006_autoservicio_organizaciones"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("verification_warning_sent_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "verification_warning_sent_at")
