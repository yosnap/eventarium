"""locale en invitacion

Añade `p_locale` a `app_accept_invited_user` para que la aceptación de una
invitación (`POST /public/invitations/{token}/accept`) pueda fijar el idioma
de la cuenta, simétrico a lo que fase 1 hizo con `app_create_unverified_user`
en el registro.

La función cambia de **firma** (4 -> 5 parámetros): se elimina la versión
vieja antes de crear la nueva, mismo patrón que `0066_locale_en_alta_de_cuenta.py`
(y antes, `0005_nombre_y_apellidos.py`) al cambiar la firma de una función
`SECURITY DEFINER` ya existente (`CREATE OR REPLACE` no sustituye una función
con distinta firma, crea una sobrecarga adicional).

El cuerpo SQL del `UPDATE` (columnas `password_hash`, `first_name`,
`last_name`, `email_verified_at`) viene de `0028_estado_de_cuenta_invitada.py`
(primera creación de `app_accept_invited_user`, no cambio de firma — esa
migración solo es fuente del cuerpo, no precedente del patrón de migración).

Revision ID: 0067_locale_en_invitacion
Revises: 0066_locale_en_alta_de_cuenta
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0067_locale_en_invitacion"
down_revision: str | None = "0066_locale_en_alta_de_cuenta"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Firma nueva de 5 parámetros: misma identidad de los 4 argumentos
    # previos (`uuid,text,text,text`) más `p_locale`. `CREATE FUNCTION` sin
    # `OR REPLACE`: si por drift la firma antigua siguiera existiendo en
    # alguna base, un `CREATE OR REPLACE` la sustituiría conservando en
    # silencio su ACL/owner original; con `CREATE FUNCTION` simple, la
    # migración falla ruidosamente (`already exists`) en vez de absorber el
    # drift sin avisar.
    op.execute("DROP FUNCTION IF EXISTS app_accept_invited_user(uuid, text, text, text)")
    op.execute(
        """
CREATE FUNCTION app_accept_invited_user(
  p_user_id uuid, p_password_hash text, p_first_name text, p_last_name text,
  p_locale text DEFAULT 'es-ES'
)
RETURNS boolean
LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path = public AS $$
  WITH actualizado AS (
    UPDATE users
    SET password_hash = p_password_hash,
        first_name = p_first_name,
        last_name = p_last_name,
        locale = COALESCE(p_locale, 'es-ES'),
        email_verified_at = COALESCE(email_verified_at, now())
    WHERE id = p_user_id
    RETURNING id
  )
  SELECT EXISTS (SELECT 1 FROM actualizado)
$$
        """
    )
    op.execute(
        "REVOKE ALL ON FUNCTION app_accept_invited_user(uuid, text, text, text, text) FROM PUBLIC"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION app_accept_invited_user(uuid, text, text, text, text) "
        "TO app_user"
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS app_accept_invited_user(uuid, text, text, text, text)")
    op.execute(
        """
CREATE FUNCTION app_accept_invited_user(
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
    )
    op.execute("REVOKE ALL ON FUNCTION app_accept_invited_user(uuid, text, text, text) FROM PUBLIC")
    op.execute(
        "GRANT EXECUTE ON FUNCTION app_accept_invited_user(uuid, text, text, text) TO app_user"
    )
