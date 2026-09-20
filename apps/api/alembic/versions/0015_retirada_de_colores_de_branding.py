"""retirada de colores de branding

Fase 1 del plan de UX/UI (sistema de diseño Eventarium), decisión B de la
tercera sesión de validación. Con el catálogo de plantillas de tema en
marcha (`0014_plantillas_de_tema`), nadie lee ya `organization_branding.colors`
ni `.fonts`: se retiran las dos columnas.

**Migración destructiva en contenido.** `upgrade()` borra las dos columnas
y, con ellas, cualquier personalización de color o tipografía que una
organización tuviera guardada. No hay backfill posible ni deseado: la
plataforma ya no admite esa personalización, la sustituye el catálogo de
plantillas.

Ejecutada solo después de que el sistema de plantillas esté completo y
verificado (paso 13 de la fase 1: suite de `apps/api` y `pnpm test` en
verde, comprobación manual de que una organización de prueba ve su
plantilla en los dos modos) y solo con backup previo, completo y dirigido
a estas dos columnas (`docs/despliegue.md`, `infra/scripts/backup.sh`).

**El `downgrade()` NO recupera los datos.** Vuelve a crear las dos
columnas `JSONB NOT NULL DEFAULT '{}'`, pero vacías: recupera el esquema
para que una fila nueva pueda insertarse sin fallar por `NOT NULL`, nunca
el contenido que tenía cada organización antes del `upgrade()`. La única
vía de recuperar esos datos es restaurar el backup tomado antes de aplicar
esta migración.

Revision ID: 0015_retirada_colores_branding
Revises: 0014_plantillas_de_tema
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0015_retirada_colores_branding"
down_revision: str | None = "0014_plantillas_de_tema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("organization_branding", "colors")
    op.drop_column("organization_branding", "fonts")


def downgrade() -> None:
    # Recupera el esquema, no los datos: ambas columnas vuelven vacías. Los
    # valores que tenía cada organización antes del `upgrade()` solo se
    # recuperan restaurando el backup tomado antes de aplicar esta migración.
    op.add_column(
        "organization_branding",
        sa.Column(
            "colors", JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'")
        ),
    )
    op.add_column(
        "organization_branding",
        sa.Column(
            "fonts", JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'")
        ),
    )
