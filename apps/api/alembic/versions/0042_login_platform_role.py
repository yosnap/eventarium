"""platform_role en la búsqueda de usuario del login

Amplía `app_find_user_for_login` (`0031`) con la columna `platform_role`:
la respuesta del login (`UserSummary`) la necesita para que el guard del
panel de plataforma sepa quién es `soporte` nada más entrar, sin esperar a
un `/users/me` extra (fase 3 del plan
`260916-2246-cookies-analitica-externa`). Sin ella, un `soporte` que inicia
sesión en una pestaña fresca sería rebotado del panel por el frontend
aunque el backend (`require_platform_staff`) le dejaría entrar.

PostgreSQL exige que el row type de los OUT parámetros coincida
**exactamente** en un CREATE OR REPLACE — añadir una columna se rechaza con
«cannot change return type of existing function» (comprobado en PG 16) —,
así que la función va con DROP + CREATE, reaplicando los permisos
(`REVOKE ALL ... FROM PUBLIC` / `GRANT EXECUTE ... TO app_user`) que la
`0031` impuso y que el DROP habría perdido.

Revision ID: 0042_login_platform_role
Revises: 0041_analytics_settings
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0042_login_platform_role"
down_revision: str | None = "0041_analytics_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DROP_FUNCION = "DROP FUNCTION IF EXISTS app_find_user_for_login(p_email text);"

_CON_PLATFORM_ROLE = """
CREATE FUNCTION app_find_user_for_login(p_email text)
RETURNS TABLE (
  id uuid, email text, first_name text, last_name text,
  password_hash text, is_active boolean, is_superadmin boolean,
  platform_role text
)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT u.id, u.email, u.first_name, u.last_name, u.password_hash, u.is_active,
         u.is_superadmin, u.platform_role
  FROM users u
  WHERE lower(u.email) = lower(p_email)
$$
"""

_SIN_PLATFORM_ROLE = """
CREATE FUNCTION app_find_user_for_login(p_email text)
RETURNS TABLE (
  id uuid, email text, first_name text, last_name text,
  password_hash text, is_active boolean, is_superadmin boolean
)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT u.id, u.email, u.first_name, u.last_name, u.password_hash, u.is_active,
         u.is_superadmin
  FROM users u
  WHERE lower(u.email) = lower(p_email)
$$
"""


def upgrade() -> None:
    # PostgreSQL exige que el row type de los OUT parámetros coincida
    # exactamente en un CREATE OR REPLACE: añadir la columna exige DROP antes
    # (fallaba con «cannot change return type of existing function»). No hay
    # vistas ni políticas que dependan de esta función (solo la llama la API
    # en runtime), así que el DROP es seguro. Y asyncpg no admite varias
    # sentencias por execute(): cada sentencia va separada.
    op.execute(_DROP_FUNCION)
    op.execute(_CON_PLATFORM_ROLE)
    # El DROP+CREATE pierde el hardening de permisos que la `0031` impuso:
    # la función recreada nace con EXECUTE a PUBLIC y es SECURITY DEFINER
    # (devuelve `password_hash` por email) — REVOKE + GRANT otra vez, en
    # upgrade y downgrade (code-review de la fase 3, C-1).
    op.execute("REVOKE ALL ON FUNCTION app_find_user_for_login(text) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION app_find_user_for_login(text) TO app_user")


def downgrade() -> None:
    op.execute(_DROP_FUNCION)
    op.execute(_SIN_PLATFORM_ROLE)
    op.execute("REVOKE ALL ON FUNCTION app_find_user_for_login(text) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION app_find_user_for_login(text) TO app_user")
