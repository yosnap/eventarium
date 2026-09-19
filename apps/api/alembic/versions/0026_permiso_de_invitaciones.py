"""permiso de invitaciones

Fase 0 del PRD de invitaciones (plan.md): añade `invitations:manage` al
enum de `Permission` y lo concede al rol `organizer`.

Backfill a cualquier rol con `organizations:write` (mismo criterio que
`0010`-`0013`/`0020`), más la plantilla `ORGANIZER` actualizada en
`app/modules/roles/system_roles.py` para las organizaciones creadas después
de esta migración. Es el mismo bug que ya se ha corregido cuatro veces
(`registrations`, `sponsors`, `payments`, `accounting`): hacer solo el
backfill deja sin el permiso a toda organización creada después de esta
migración y antes de la siguiente que lo note.

No se toca ningún endpoint: este permiso todavía no protege nada (lo usan
las fases 1-3 del plan).

Revision ID: 0026_permiso_de_invitaciones
Revises: 0025_plantilla_por_evento
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0026_permiso_de_invitaciones"
down_revision: str | None = "0025_plantilla_por_evento"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Ancla al permiso, no al nombre del rol (mismo criterio que `0010`-`0020`): un
# rol a medida con `organizations:write` también necesita `invitations:manage`,
# exista o no con la clave `owner`/`organizer`.
_BACKFILL_INVITACIONES = """
INSERT INTO role_permissions (role_id, permission, organization_id)
SELECT r.id, 'invitations:manage', r.organization_id
FROM roles r
WHERE EXISTS (
  SELECT 1 FROM role_permissions rp
  WHERE rp.role_id = r.id AND rp.permission = 'organizations:write'
)
AND NOT EXISTS (
  SELECT 1 FROM role_permissions rp2
  WHERE rp2.role_id = r.id AND rp2.permission = 'invitations:manage'
)
"""


def upgrade() -> None:
    op.execute(_BACKFILL_INVITACIONES)


def downgrade() -> None:
    op.execute(
        "DELETE FROM role_permissions "
        "WHERE permission = 'invitations:manage' "
        "AND role_id IN ("
        "  SELECT r.id FROM roles r "
        "  WHERE EXISTS ("
        "    SELECT 1 FROM role_permissions rp "
        "    WHERE rp.role_id = r.id AND rp.permission = 'organizations:write'"
        "  )"
        ")"
    )
