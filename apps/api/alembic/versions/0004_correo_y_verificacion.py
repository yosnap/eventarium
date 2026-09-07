"""correo y verificación

Añade `email_verified_at` a `users` y su índice parcial para el barrido periódico de
cuentas no verificadas (fase 2). Incluye además tres funciones `SECURITY DEFINER` de
alcance mínimo, en el mismo patrón que `app_resolve_organization`:

El registro público ocurre *antes* de que la persona comparta organización con nadie,
así que la política `tenant_users` (visible solo a uno mismo o a quien comparte
organización) le impide ver, crear o actualizar su propia fila por la vía normal.
En vez de dar `BYPASSRLS` al rol de la API, se exponen tres funciones de superficie
mínima —buscar por correo, crear sin verificar, marcar como verificado— igual que ya
se hizo para resolver la organización por host.

Revision ID: 0004_correo_y_verificacion
Revises: 0003_politicas_rls
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_correo_y_verificacion"
down_revision: str | None = "0003_politicas_rls"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FUNCIONES_REGISTRO = (
    """
CREATE OR REPLACE FUNCTION app_find_user_by_email(p_email text)
RETURNS TABLE (id uuid, email_verified_at timestamptz)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  -- Solo lo que necesitan sus dos llamadores (comprobar existencia y estado de
  -- verificación): ni password_hash ni is_active tienen consumidor aquí, y
  -- exponerlos invitaría a que un futuro llamador los usara para autenticar sin
  -- pasar por `authenticate()`, saltándose la comprobación de membresía.
  SELECT u.id, u.email_verified_at
  FROM users u
  WHERE lower(u.email) = lower(p_email)
$$
    """,
    """
CREATE OR REPLACE FUNCTION app_create_unverified_user(
  p_id uuid, p_email text, p_password_hash text, p_full_name text
)
RETURNS void
LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path = public AS $$
  -- `locale` e `is_superadmin` no tienen `server_default`: su valor por defecto solo
  -- existe en el ORM, así que un INSERT en SQL crudo tiene que fijarlos a mano o
  -- viola el NOT NULL.
  INSERT INTO users (id, email, password_hash, full_name, locale, is_active, is_superadmin, email_verified_at)
  VALUES (p_id, lower(p_email), p_password_hash, p_full_name, 'es-ES', true, false, NULL)
$$
    """,
    """
CREATE OR REPLACE FUNCTION app_verify_user_email(p_user_id uuid)
RETURNS boolean
LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path = public AS $$
  WITH actualizado AS (
    UPDATE users SET email_verified_at = now()
    WHERE id = p_user_id AND email_verified_at IS NULL
    RETURNING id
  )
  SELECT EXISTS (SELECT 1 FROM actualizado)
$$
    """,
)


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True)
    )

    # Los usuarios de test y de seed ya existentes se consideran verificados: si no,
    # quedarían bloqueados por futuras comprobaciones que exijan correo verificado.
    op.execute("UPDATE users SET email_verified_at = created_at WHERE email_verified_at IS NULL")

    # Índice parcial: el barrido periódico de cuentas no verificadas (fase 2) filtra
    # por `email_verified_at IS NULL`, y sin este índice recorrería la tabla entera.
    op.create_index(
        "ix_users_unverified_created_at",
        "users",
        ["created_at"],
        unique=False,
        postgresql_where=sa.text("email_verified_at IS NULL"),
    )

    for sentencia in FUNCIONES_REGISTRO:
        op.execute(sentencia)

    op.execute("REVOKE ALL ON FUNCTION app_find_user_by_email(text) FROM PUBLIC")
    op.execute(
        "REVOKE ALL ON FUNCTION app_create_unverified_user(uuid, text, text, text) FROM PUBLIC"
    )
    op.execute("REVOKE ALL ON FUNCTION app_verify_user_email(uuid) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION app_find_user_by_email(text) TO app_user")
    op.execute(
        "GRANT EXECUTE ON FUNCTION app_create_unverified_user(uuid, text, text, text) TO app_user"
    )
    op.execute("GRANT EXECUTE ON FUNCTION app_verify_user_email(uuid) TO app_user")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS app_verify_user_email(uuid)")
    op.execute("DROP FUNCTION IF EXISTS app_create_unverified_user(uuid, text, text, text)")
    op.execute("DROP FUNCTION IF EXISTS app_find_user_by_email(text)")
    op.drop_index("ix_users_unverified_created_at", table_name="users")
    op.drop_column("users", "email_verified_at")
