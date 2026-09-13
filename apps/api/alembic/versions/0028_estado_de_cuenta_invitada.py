"""estado de cuenta invitada

Fase 2 del plan de invitaciones (plan.md). Dos funciones `SECURITY DEFINER`
más, mismo patrón que `0004_correo_y_verificacion`/`0008_cuenta_y_recuperacion`:
la pantalla pública de aceptación (`GET`/`POST /public/invitations/{token}`)
actúa sobre una persona que **todavía no comparte organización con nadie**, así
que `tenant_users` (RLS) le impide leer o completar su propia fila por la vía
normal.

- `app_find_user_by_email` gana una columna, `has_password`: la pantalla
  pública necesita saber si la cuenta invitada ya tiene contraseña (caso
  anómalo — la fase 1 no emite token si la tenía al invitar, pero pudo
  ganarla después por otra vía) sin exponer el hash. Cambiar el tipo de
  retorno de una función exige `DROP` + `CREATE`, no `CREATE OR REPLACE`.
- `app_accept_invited_user` fija contraseña, nombre y apellidos, y marca el
  correo verificado si no lo estaba — en una sola llamada atómica, en vez de
  encadenar `app_set_user_password` + `app_verify_user_email` más un tercer
  `UPDATE` para el nombre que no existía.

Revision ID: 0028_estado_de_cuenta_invitada
Revises: 0027_invitaciones_de_equipo
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0028_estado_de_cuenta_invitada"
down_revision: str | None = "0027_invitaciones_de_equipo"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FIND_USER_BY_EMAIL_ORIGINAL = """
CREATE FUNCTION app_find_user_by_email(p_email text)
RETURNS TABLE (id uuid, email_verified_at timestamptz)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT u.id, u.email_verified_at
  FROM users u
  WHERE lower(u.email) = lower(p_email)
$$
"""

_FIND_USER_BY_EMAIL_CON_CONTRASENA = """
CREATE FUNCTION app_find_user_by_email(p_email text)
RETURNS TABLE (id uuid, email_verified_at timestamptz, has_password boolean)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  -- `has_password`, no el hash: la pantalla pública de invitación solo
  -- necesita saber si ya hay una, nunca cuál es.
  SELECT u.id, u.email_verified_at, (u.password_hash IS NOT NULL)
  FROM users u
  WHERE lower(u.email) = lower(p_email)
$$
"""

_ACCEPT_INVITED_USER = """
CREATE OR REPLACE FUNCTION app_accept_invited_user(
  p_user_id uuid, p_password_hash text, p_first_name text, p_last_name text
)
RETURNS boolean
LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path = public AS $$
  WITH actualizado AS (
    UPDATE users
    SET password_hash = p_password_hash,
        first_name = p_first_name,
        last_name = p_last_name,
        email_verified_at = COALESCE(email_verified_at, now())
    WHERE id = p_user_id
    RETURNING id
  )
  SELECT EXISTS (SELECT 1 FROM actualizado)
$$
"""


def upgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS app_find_user_by_email(text)")
    op.execute(_FIND_USER_BY_EMAIL_CON_CONTRASENA)
    op.execute(_ACCEPT_INVITED_USER)

    op.execute("REVOKE ALL ON FUNCTION app_find_user_by_email(text) FROM PUBLIC")
    op.execute(
        "REVOKE ALL ON FUNCTION app_accept_invited_user(uuid, text, text, text) FROM PUBLIC"
    )
    op.execute("GRANT EXECUTE ON FUNCTION app_find_user_by_email(text) TO app_user")
    op.execute("GRANT EXECUTE ON FUNCTION app_accept_invited_user(uuid, text, text, text) TO app_user")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS app_accept_invited_user(uuid, text, text, text)")
    op.execute("DROP FUNCTION IF EXISTS app_find_user_by_email(text)")
    op.execute(_FIND_USER_BY_EMAIL_ORIGINAL)
    op.execute("REVOKE ALL ON FUNCTION app_find_user_by_email(text) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION app_find_user_by_email(text) TO app_user")
