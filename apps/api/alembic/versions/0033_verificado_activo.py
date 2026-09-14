"""app_find_user_by_id expone is_active

Hallazgo del code-review de la fase 4 del plan «organización sin dominio»:
`require_verified_user` (autoservicio de creación de organizaciones) no
comprobaba `is_active`, y desde esta fase ese endpoint emite una sesión
completa (access token + cookie de refresco) en vez de solo datos — antes el
daño estaba acotado porque `/auth/login` sí comprobaba `is_active`, pero
ahora una cuenta desactivada con un access token de verificación todavía
vivo podría acuñar una sesión nueva directamente. El daño real ya estaba
contenido (`get_current_user`/`refresh`/`switch_organization` revalidan
`is_active` en cuanto se usa la sesión), pero es un endurecimiento barato y
fail-closed que corresponde hacer ahora que el endpoint acuña sesiones.

Cambia el tipo de retorno de `app_find_user_by_id` (gana `is_active`), así
que exige `DROP` + `CREATE`, no `CREATE OR REPLACE` (mismo motivo que la
`0028`).

Revision ID: 0033_verificado_activo
Revises: 0032_resolucion_por_recurso
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0033_verificado_activo"
down_revision: str | None = "0032_resolucion_por_recurso"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ORIGINAL = """
CREATE OR REPLACE FUNCTION app_find_user_by_id(p_id uuid)
RETURNS TABLE (id uuid, email text, email_verified_at timestamptz)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT u.id, u.email, u.email_verified_at FROM users u WHERE u.id = p_id
$$
"""

_CON_ACTIVO = """
CREATE FUNCTION app_find_user_by_id(p_id uuid)
RETURNS TABLE (id uuid, email text, email_verified_at timestamptz, is_active boolean)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT u.id, u.email, u.email_verified_at, u.is_active FROM users u WHERE u.id = p_id
$$
"""


def upgrade() -> None:
    op.execute("DROP FUNCTION app_find_user_by_id(uuid)")
    op.execute(_CON_ACTIVO)
    op.execute("REVOKE ALL ON FUNCTION app_find_user_by_id(uuid) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION app_find_user_by_id(uuid) TO app_user")


def downgrade() -> None:
    op.execute("DROP FUNCTION app_find_user_by_id(uuid)")
    op.execute(_ORIGINAL)
    op.execute("REVOKE ALL ON FUNCTION app_find_user_by_id(uuid) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION app_find_user_by_id(uuid) TO app_user")
