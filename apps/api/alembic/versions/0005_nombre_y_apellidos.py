"""nombre y apellidos

Sustituye `users.full_name` (una sola cadena, ambigua para repartir en nombre y
apellidos después) por `first_name` y `last_name`, ambas nulas. El registro público
(fase 1) no pide nombre: se exige más tarde, en el punto donde de verdad hace falta —
crear una organización (fase 2), inscribirse a un evento (fase 3) — no en el alta de
la cuenta.

`app_create_unverified_user` pierde el parámetro `p_full_name`: el registro ya no lo
recibe. Como el número de parámetros cambia, la función antigua se elimina antes de
crear la nueva (`CREATE OR REPLACE` no sustituye una función con distinta firma, crea
una sobrecarga adicional).

Revision ID: 0005_nombre_y_apellidos
Revises: 0004_correo_y_verificacion
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_nombre_y_apellidos"
down_revision: str | None = "0004_correo_y_verificacion"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("first_name", sa.String(length=100), nullable=True))
    op.add_column("users", sa.Column("last_name", sa.String(length=100), nullable=True))

    # Reparto aproximado de los `full_name` ya existentes (seed, datos de prueba):
    # la primera palabra a `first_name`, el resto a `last_name`. Es una heurística, no
    # una fuente de verdad; nadie pierde acceso por que quede repartido de más o de
    # menos, y quien quiera puede corregirlo desde su perfil en una fase posterior.
    op.execute(
        """
        UPDATE users SET
          first_name = NULLIF(split_part(trim(full_name), ' ', 1), ''),
          last_name = NULLIF(trim(substring(trim(full_name) from length(split_part(trim(full_name), ' ', 1)) + 1)), '')
        WHERE full_name IS NOT NULL AND trim(full_name) <> ''
        """
    )

    op.drop_column("users", "full_name")

    # `app_create_unverified_user` cambia de firma (pierde `p_full_name`): la versión
    # de 4 parámetros se elimina antes de crear la de 3, no se sustituye en el sitio.
    op.execute("DROP FUNCTION IF EXISTS app_create_unverified_user(uuid, text, text, text)")
    op.execute(
        """
CREATE OR REPLACE FUNCTION app_create_unverified_user(p_id uuid, p_email text, p_password_hash text)
RETURNS void
LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path = public AS $$
  -- `locale` e `is_superadmin` no tienen `server_default`: su valor por defecto solo
  -- existe en el ORM, así que un INSERT en SQL crudo tiene que fijarlos a mano o
  -- viola el NOT NULL. `first_name`/`last_name` quedan nulos: el registro no los pide.
  INSERT INTO users (id, email, password_hash, locale, is_active, is_superadmin, email_verified_at)
  VALUES (p_id, lower(p_email), p_password_hash, 'es-ES', true, false, NULL)
$$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION app_create_unverified_user(uuid, text, text) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION app_create_unverified_user(uuid, text, text) TO app_user")


def downgrade() -> None:
    # `full_name` tiene que volver a existir antes de que la función de abajo pueda
    # insertar en ella: recrear la función primero fallaría con «column does not exist».
    op.add_column(
        "users", sa.Column("full_name", sa.String(length=200), nullable=False, server_default="")
    )
    op.execute(
        "UPDATE users SET full_name = trim(concat_ws(' ', first_name, last_name)) "
        "WHERE first_name IS NOT NULL OR last_name IS NOT NULL"
    )
    op.alter_column("users", "full_name", server_default=None)
    op.drop_column("users", "last_name")
    op.drop_column("users", "first_name")

    op.execute("DROP FUNCTION IF EXISTS app_create_unverified_user(uuid, text, text)")
    op.execute(
        """
CREATE OR REPLACE FUNCTION app_create_unverified_user(
  p_id uuid, p_email text, p_password_hash text, p_full_name text
)
RETURNS void
LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path = public AS $$
  INSERT INTO users (id, email, password_hash, full_name, locale, is_active, is_superadmin, email_verified_at)
  VALUES (p_id, lower(p_email), p_password_hash, p_full_name, 'es-ES', true, false, NULL)
$$
        """
    )
    op.execute(
        "REVOKE ALL ON FUNCTION app_create_unverified_user(uuid, text, text, text) FROM PUBLIC"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION app_create_unverified_user(uuid, text, text, text) TO app_user"
    )
