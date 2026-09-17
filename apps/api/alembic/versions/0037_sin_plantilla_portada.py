"""retira organization_branding.template_key

Fase 6 (cierre) del plan «organización sin dominio»
(`plans/260914-0741-organizacion-sin-dominio/plan.md`). Sin dominio propio,
la home pública deja de ser «de una organización» y pasa a ser el directorio
de eventos de toda la instalación: las plantillas de portada
(`template_key`: classic/minimal) dejan de existir en el frontend y el
selector se retira del panel de branding. La columna muere con ellas —
mantenerla «por si acaso» sería el mismo YAGNI incumplida que las tablas de
dominio retiradas en `0035`.

Nada más referenciaba la columna: `GET/PUT /organizations/me/branding` ya no
la expone (retirada del esquema Pydantic en el mismo cambio de código que
esta migración acompaña) y `GET /tenant/branding` perdió su bloque
`organization` entero en `0035`/el mismo cambio.

Revision ID: 0037_sin_plantilla_portada
Revises: 0036_organizaciones_sin_host
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0037_sin_plantilla_portada"
down_revision: str | None = "0036_organizaciones_sin_host"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("organization_branding", "template_key")


def downgrade() -> None:
    # Todas las filas vuelven al histórico «classic»: era el valor por defecto
    # y el único que el frontend llegaba a ofrecer como tal (la elección por
    # organización ya no se puede reconstruir, se perdió con la columna).
    op.add_column(
        "organization_branding",
        sa.Column("template_key", sa.String(length=40), nullable=False, server_default="classic"),
    )
    op.alter_column("organization_branding", "template_key", server_default=None)
