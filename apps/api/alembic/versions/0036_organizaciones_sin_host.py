"""app_user_organizations deja de depender de organization_domains

Fase 6 (cierre) del plan «organización sin dominio»
(`plans/260914-0741-organizacion-sin-dominio/plan.md`). `0035` retiró
`organization_domains` pero dejó `app_user_organizations` (creada en `0031`)
sin redefinir: seguía haciendo `LEFT JOIN organization_domains`, así que
cualquier llamada (login, `GET /users/me/organizations`) rompía con
`UndefinedTableError` en cuanto la tabla desaparecía — lo confirmó la suite
completa en rojo tras aplicar `0035`. La columna `host` que devolvía no tenía
ya ningún consumidor real en el backend (el selector de organización del
panel usa `organization_id`; el frontend documenta explícitamente que el
host "ya no determina nada"), así que se retira del todo en vez de dejarla
siempre a `NULL` — mismo criterio que el bloque `organization` ya retirado
de `GET /tenant/branding`.

Cambiar el tipo de retorno de una función exige `DROP` + `CREATE`, no
`CREATE OR REPLACE` (mismo motivo que `0028`/`0031`).

Revision ID: 0036_organizaciones_sin_host
Revises: 0035_retira_dominios
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0036_organizaciones_sin_host"
down_revision: str | None = "0035_retira_dominios"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SIN_HOST = """
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

_CON_HOST = """
CREATE FUNCTION app_user_organizations(p_user_id uuid)
RETURNS TABLE (organization_id uuid, slug text, name text, host text, last_seen_at timestamptz)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT o.id, o.slug, o.name, d.host, m.last_seen_at
  FROM organization_members m
  JOIN organizations o ON o.id = m.organization_id
  LEFT JOIN organization_domains d ON d.organization_id = o.id AND d.is_primary
  WHERE m.user_id = p_user_id
    AND p_user_id = NULLIF(current_setting('app.user_id', true), '')::uuid
  ORDER BY o.name
$$
"""


def upgrade() -> None:
    op.execute("DROP FUNCTION app_user_organizations(uuid)")
    op.execute(_SIN_HOST)
    op.execute("REVOKE ALL ON FUNCTION app_user_organizations(uuid) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION app_user_organizations(uuid) TO app_user")


def downgrade() -> None:
    # `organization_domains` ya no existe en este punto de la cadena (la
    # retiró `0035`, anterior a esta): el `downgrade` solo puede restaurar la
    # firma con `host`, no su `LEFT JOIN` — devuelve siempre `NULL`. Quien
    # baje hasta `0035` recupera la tabla y, con ella, el join real.
    op.execute("DROP FUNCTION app_user_organizations(uuid)")
    op.execute(
        _CON_HOST.replace(
            "LEFT JOIN organization_domains d ON d.organization_id = o.id AND d.is_primary",
            "LEFT JOIN (SELECT NULL::uuid AS organization_id, NULL::text AS host) d "
            "ON d.organization_id = o.id",
        )
    )
    op.execute("REVOKE ALL ON FUNCTION app_user_organizations(uuid) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION app_user_organizations(uuid) TO app_user")
