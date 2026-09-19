"""marca de ultimo acceso por membresia

Añade `organization_members.last_seen_at`, la marca que el escritorio de
plataforma necesita para saber si alguien sigue entrando.

**Va por membresía y no en `users`**, que era lo primero que parecía razonable:
`users` es una fila por persona y una persona pertenece a varias
organizaciones, así que un acceso suyo en una haría «saltar» la marca de todas
las demás sin que nadie de ellas hubiera entrado. El dato que se quiere es «si
alguien de *esta* organización sigue entrando», y eso es la membresía.

Se escribe en el login (que ya resuelve la organización del host), **no en el
refresh**: una sesión mantenida semanas no actualiza la marca, y eso es
deliberado — mide acceso explícito, no actividad pasiva. La impersonación
tampoco la escribe: no es la persona entrando.

Nullable y sin `server_default`: las filas que ya existen no tienen marca, y
`None` significa «no consta», que es la verdad. Rellenarlas con `now()` diría
que todo el mundo entró justo cuando se aplicó la migración.

Revision ID: 0024_ultimo_acceso_por_membresia
Revises: 0023_auditoria_impersonacion
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0024_ultimo_acceso_por_membresia"
down_revision: str | None = "0023_auditoria_impersonacion"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "organization_members",
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("organization_members", "last_seen_at")
