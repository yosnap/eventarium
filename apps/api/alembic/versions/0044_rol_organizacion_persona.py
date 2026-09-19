"""app_user_organizations devuelve el rol de la persona en cada organización

Fase 1 del plan «selector de espacio de trabajo»
(`plans/260918-0358-selector-espacio-trabajo/plan.md`). La pantalla de
selección de espacio necesita mostrar, junto al nombre de cada organización,
el rol que la persona tiene en ella (`roles.name`, clonado por organización).
Se agrega con `string_agg` en vez de duplicar la fila cuando la persona tiene
más de un rol en la misma organización (la unique constraint de
`organization_members` es `(organization_id, user_id, role_id)`, no
`(organization_id, user_id)`).

`LEFT JOIN roles`, no `INNER JOIN`: el join solo ve los roles de todas las
organizaciones porque quien ejecuta la función (`app_maintainer`) tiene
`BYPASSRLS` — `roles` lleva RLS `FORCE` con política sobre la organización
activa. Si esa condición cambiara, un `INNER JOIN` haría desaparecer en
silencio organizaciones enteras; con `LEFT JOIN` solo se pierde el nombre del
rol.

El `ORDER BY` interno de esta función no se propaga de forma garantizada a
través del `SELECT` externo de `list_my_organizations` (mismo motivo por el
que `authenticate()` ya pone su propio `ORDER BY` sobre esta función en vez de
confiar en el de aquí) — el `SELECT` del router añade su propio `ORDER BY`.

Cambiar el tipo de retorno de una función exige `DROP` + `CREATE`, no
`CREATE OR REPLACE` (mismo motivo que `0028`/`0031`/`0036`).

Revision ID: 0044_rol_organizacion_persona
Revises: 0043_gtm_container_id
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0044_rol_organizacion_persona"
down_revision: str | None = "0043_gtm_container_id"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CON_ROL = """
CREATE FUNCTION app_user_organizations(p_user_id uuid)
RETURNS TABLE (
    organization_id uuid,
    slug text,
    name text,
    role_name text,
    last_seen_at timestamptz
)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT
    o.id,
    o.slug,
    o.name,
    string_agg(r.name, ', ' ORDER BY r.name) AS role_name,
    MAX(m.last_seen_at) AS last_seen_at
  FROM organization_members m
  JOIN organizations o ON o.id = m.organization_id
  LEFT JOIN roles r ON r.id = m.role_id
  WHERE m.user_id = p_user_id
    AND p_user_id = NULLIF(current_setting('app.user_id', true), '')::uuid
  GROUP BY o.id, o.slug, o.name
  ORDER BY MAX(m.last_seen_at) DESC NULLS LAST, o.name
$$
"""

_SIN_ROL = """
CREATE FUNCTION app_user_organizations(p_user_id uuid)
RETURNS TABLE (organization_id uuid, slug text, name text, last_seen_at timestamptz)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT o.id, o.slug, o.name, m.last_seen_at
  FROM organization_members m
  JOIN organizations o ON o.id = m.organization_id
  WHERE m.user_id = p_user_id
    AND p_user_id = NULLIF(current_setting('app.user_id', true), '')::uuid
  ORDER BY o.name
$$
"""


def upgrade() -> None:
    op.execute("DROP FUNCTION app_user_organizations(uuid)")
    op.execute(_CON_ROL)
    op.execute("REVOKE ALL ON FUNCTION app_user_organizations(uuid) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION app_user_organizations(uuid) TO app_user")


def downgrade() -> None:
    op.execute("DROP FUNCTION app_user_organizations(uuid)")
    op.execute(_SIN_ROL)
    op.execute("REVOKE ALL ON FUNCTION app_user_organizations(uuid) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION app_user_organizations(uuid) TO app_user")
