"""organización activa en la sesión, no en el host

Fase 1 del plan «organización sin dominio»
(`plans/260914-0741-organizacion-sin-dominio/plan.md`). El login deja de
exigir pertenecer a la organización del host visitado (ya no hay host que la
determine): valida identidad globalmente y después elige qué organización
queda activa en el token.

Dos funciones `SECURITY DEFINER` de alcance mínimo, mismo patrón que las ya
existentes de `0004`/`0006`/`0008`/`0028`:

- `app_find_user_for_login`: el login necesita el hash de la contraseña para
  verificarla, algo que ninguna función existente expone (`app_find_user_by_email`
  deliberadamente no lo hace). Sin organización todavía, `tenant_users` no deja
  leer la fila por la vía normal.

- `app_user_organizations` gana una columna, `last_seen_at`: el login la
  necesita para elegir la organización de acceso más reciente cuando la
  persona pertenece a varias. Cambiar el tipo de retorno de una función exige
  `DROP` + `CREATE`, no `CREATE OR REPLACE` (mismo motivo que `0028`).

Revision ID: 0031_organizacion_activa_sesion
Revises: 0030_slugs_unicos_globales
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0031_organizacion_activa_sesion"
down_revision: str | None = "0030_slugs_unicos_globales"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FIND_USER_FOR_LOGIN = """
CREATE FUNCTION app_find_user_for_login(p_email text)
RETURNS TABLE (
  id uuid, email text, first_name text, last_name text,
  password_hash text, is_active boolean, is_superadmin boolean
)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT u.id, u.email, u.first_name, u.last_name, u.password_hash, u.is_active, u.is_superadmin
  FROM users u
  WHERE lower(u.email) = lower(p_email)
$$
"""

_USER_ORGANIZATIONS_ORIGINAL = """
CREATE OR REPLACE FUNCTION app_user_organizations(p_user_id uuid)
RETURNS TABLE (organization_id uuid, slug text, name text, host text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT o.id, o.slug, o.name, d.host
  FROM organization_members m
  JOIN organizations o ON o.id = m.organization_id
  LEFT JOIN organization_domains d ON d.organization_id = o.id AND d.is_primary
  WHERE m.user_id = p_user_id
    AND p_user_id = NULLIF(current_setting('app.user_id', true), '')::uuid
  ORDER BY o.name
$$
"""

_USER_ORGANIZATIONS_CON_ULTIMO_ACCESO = """
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
    op.execute(_FIND_USER_FOR_LOGIN)
    op.execute("DROP FUNCTION app_user_organizations(uuid)")
    op.execute(_USER_ORGANIZATIONS_CON_ULTIMO_ACCESO)

    op.execute("REVOKE ALL ON FUNCTION app_find_user_for_login(text) FROM PUBLIC")
    op.execute("REVOKE ALL ON FUNCTION app_user_organizations(uuid) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION app_find_user_for_login(text) TO app_user")
    op.execute("GRANT EXECUTE ON FUNCTION app_user_organizations(uuid) TO app_user")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS app_find_user_for_login(text)")
    op.execute("DROP FUNCTION app_user_organizations(uuid)")
    op.execute(_USER_ORGANIZATIONS_ORIGINAL)
    op.execute("REVOKE ALL ON FUNCTION app_user_organizations(uuid) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION app_user_organizations(uuid) TO app_user")
