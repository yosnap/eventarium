"""cuenta propia y recuperación

Tres funciones `SECURITY DEFINER` de alcance mínimo para la fase 5 del PRD:

- `app_change_user_email`: quien confirma un cambio de correo llega por un enlace de
  correo, sin sesión ni contexto de organización (`app_current_user()` vacío), así que
  no puede actualizar su propia fila por RLS normal — mismo problema que
  `app_verify_user_email` (fase 1) y la misma solución.
- `app_set_user_password`: mismo caso para quien completa una recuperación de
  contraseña (`/auth/reset-password`).
- `app_user_organizations`: `GET /users/me/organizations` no se puede resolver con una
  consulta RLS normal porque el contexto de organización lo fija el host, no el
  usuario — aquí hace falta listar las organizaciones de una persona con
  independencia del host desde el que pregunta. El parámetro `p_user_id` no permite
  consultar por un id arbitrario: la función solo devuelve resultado si coincide con
  `app_current_user()`, igual que si se hubiera limitado a un `SELECT` sin argumento.

Revision ID: 0008_cuenta_y_recuperacion
Revises: 0007_barrido_no_verificados
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0008_cuenta_y_recuperacion"
down_revision: str | None = "0007_barrido_no_verificados"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FUNCIONES = (
    """
CREATE OR REPLACE FUNCTION app_change_user_email(p_user_id uuid, p_new_email text)
RETURNS boolean
LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path = public AS $$
  WITH actualizado AS (
    UPDATE users SET email = lower(p_new_email)
    WHERE id = p_user_id
    RETURNING id
  )
  SELECT EXISTS (SELECT 1 FROM actualizado)
$$
    """,
    """
CREATE OR REPLACE FUNCTION app_set_user_password(p_user_id uuid, p_password_hash text)
RETURNS boolean
LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path = public AS $$
  WITH actualizado AS (
    UPDATE users SET password_hash = p_password_hash
    WHERE id = p_user_id
    RETURNING id
  )
  SELECT EXISTS (SELECT 1 FROM actualizado)
$$
    """,
    """
CREATE OR REPLACE FUNCTION app_user_organizations(p_user_id uuid)
RETURNS TABLE (organization_id uuid, slug text, name text, host text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT o.id, o.slug, o.name, d.host
  FROM organization_members m
  JOIN organizations o ON o.id = m.organization_id
  LEFT JOIN organization_domains d ON d.organization_id = o.id AND d.is_primary
  WHERE m.user_id = p_user_id
    -- Vacío (sesión sin usuario) en vez de NULL: NULLIF evita que el cast a uuid
    -- reviente con «invalid input syntax» y en su lugar no compara nunca a verdadero.
    AND p_user_id = NULLIF(current_setting('app.user_id', true), '')::uuid
  ORDER BY o.name
$$
    """,
)


def upgrade() -> None:
    for sentencia in FUNCIONES:
        op.execute(sentencia)

    op.execute("REVOKE ALL ON FUNCTION app_change_user_email(uuid, text) FROM PUBLIC")
    op.execute("REVOKE ALL ON FUNCTION app_set_user_password(uuid, text) FROM PUBLIC")
    op.execute("REVOKE ALL ON FUNCTION app_user_organizations(uuid) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION app_change_user_email(uuid, text) TO app_user")
    op.execute("GRANT EXECUTE ON FUNCTION app_set_user_password(uuid, text) TO app_user")
    op.execute("GRANT EXECUTE ON FUNCTION app_user_organizations(uuid) TO app_user")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS app_user_organizations(uuid)")
    op.execute("DROP FUNCTION IF EXISTS app_set_user_password(uuid, text)")
    op.execute("DROP FUNCTION IF EXISTS app_change_user_email(uuid, text)")
