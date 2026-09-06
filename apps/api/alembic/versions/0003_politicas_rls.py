"""Políticas de Row-Level Security, fail-closed.

Principios:

1. `ENABLE` + `FORCE` en todas las tablas de dominio. `FORCE` es imprescindible:
   sin él, el propietario de la tabla (`app_maintainer`) se saltaría las políticas
   incluso sin `BYPASSRLS`.
2. Sin contexto fijado no se ve **ninguna** fila, y no se produce ningún error. Un
   error 500 sería un fallo ruidoso; devolver cero filas es el comportamiento seguro
   y además hace que un olvido se detecte en los tests, no en producción.
3. No existe ningún GUC de «bypass». Las operaciones transversales usan el rol
   `app_maintainer`, que es auditable a nivel de conexión.
4. La resolución del tenant por host ocurre *antes* de que exista contexto, así que
   se expone mediante dos funciones `SECURITY DEFINER` de alcance mínimo en lugar de
   abrir las tablas de organizaciones a lecturas sin contexto.

Revision ID: 0003_politicas_rls
Revises: 0002_esquema_base
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003_politicas_rls"
down_revision: str | None = "0002_esquema_base"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Tablas con columna `organization_id`: la política es idéntica en todas.
TABLAS_CON_ORGANIZACION = (
    "organization_domains",
    "organization_branding",
    "organization_members",
    "roles",
    "role_permissions",
    "role_profile_fields",
)

TODAS_LAS_TABLAS = (*TABLAS_CON_ORGANIZACION, "organizations", "users", "user_social_links")

FUNCIONES_CONTEXTO = (
    """
CREATE OR REPLACE FUNCTION app_current_organization() RETURNS uuid
LANGUAGE sql STABLE AS $$
  -- NULLIF convierte la cadena vacía en NULL: sin contexto, toda comparación es
  -- NULL y por tanto falsa, así que no se devuelve ninguna fila.
  SELECT NULLIF(current_setting('app.organization_id', true), '')::uuid
$$
    """,
    """
CREATE OR REPLACE FUNCTION app_current_user() RETURNS uuid
LANGUAGE sql STABLE AS $$
  SELECT NULLIF(current_setting('app.user_id', true), '')::uuid
$$
    """,
)

FUNCIONES_RESOLUCION = (
    """
CREATE OR REPLACE FUNCTION app_resolve_organization(p_host text)
RETURNS TABLE (id uuid, slug text, is_active boolean)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT o.id, o.slug::text, o.is_active
  FROM organization_domains d
  JOIN organizations o ON o.id = d.organization_id
  WHERE d.host = lower(p_host)
$$
    """,
    """
CREATE OR REPLACE FUNCTION app_resolve_organization_by_slug(p_slug text)
RETURNS TABLE (id uuid, slug text, is_active boolean)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT o.id, o.slug::text, o.is_active
  FROM organizations o
  WHERE o.slug = lower(p_slug)
$$
    """,
)

POLITICAS_USUARIOS = (
    # Una persona se ve a sí misma, o a quien comparta organización con ella.
    """
CREATE POLICY tenant_users ON users
  USING (
    id = app_current_user()
    OR EXISTS (
      SELECT 1 FROM organization_members m
      WHERE m.user_id = users.id AND m.organization_id = app_current_organization()
    )
  )
  WITH CHECK (
    id = app_current_user()
    OR EXISTS (
      SELECT 1 FROM organization_members m
      WHERE m.user_id = users.id AND m.organization_id = app_current_organization()
    )
  )
    """,
    # Dar de alta a alguien crea primero la fila de `users` y después la membresía,
    # así que en el momento del INSERT todavía no comparte organización con nadie.
    # Las políticas permisivas se combinan con OR, de modo que esta habilita ese caso
    # sin ampliar la visibilidad: la fila solo será legible cuando exista la membresía.
    """
CREATE POLICY tenant_users_insert ON users
  FOR INSERT
  WITH CHECK (app_current_organization() IS NOT NULL)
    """,
    """
CREATE POLICY tenant_user_social_links ON user_social_links
  USING (
    EXISTS (
      SELECT 1 FROM users u
      WHERE u.id = user_social_links.user_id
        AND (
          u.id = app_current_user()
          OR EXISTS (
            SELECT 1 FROM organization_members m
            WHERE m.user_id = u.id AND m.organization_id = app_current_organization()
          )
        )
    )
  )
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM users u
      WHERE u.id = user_social_links.user_id
        AND (
          u.id = app_current_user()
          OR EXISTS (
            SELECT 1 FROM organization_members m
            WHERE m.user_id = u.id AND m.organization_id = app_current_organization()
          )
        )
    )
  )
    """,
)


def upgrade() -> None:
    for sentencia in (*FUNCIONES_CONTEXTO, *FUNCIONES_RESOLUCION):
        op.execute(sentencia)

    # Las funciones de resolución son SECURITY DEFINER: se restringe quién las llama.
    op.execute("REVOKE ALL ON FUNCTION app_resolve_organization(text) FROM PUBLIC")
    op.execute("REVOKE ALL ON FUNCTION app_resolve_organization_by_slug(text) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION app_resolve_organization(text) TO app_user")
    op.execute("GRANT EXECUTE ON FUNCTION app_resolve_organization_by_slug(text) TO app_user")

    for tabla in TODAS_LAS_TABLAS:
        op.execute(f"ALTER TABLE {tabla} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {tabla} FORCE ROW LEVEL SECURITY")

    for tabla in TABLAS_CON_ORGANIZACION:
        op.execute(
            f"CREATE POLICY tenant_{tabla} ON {tabla} "
            "USING (organization_id = app_current_organization()) "
            "WITH CHECK (organization_id = app_current_organization())"
        )

    op.execute(
        "CREATE POLICY tenant_organizations ON organizations "
        "USING (id = app_current_organization()) "
        "WITH CHECK (id = app_current_organization())"
    )

    for sentencia in POLITICAS_USUARIOS:
        op.execute(sentencia)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_user_social_links ON user_social_links")
    op.execute("DROP POLICY IF EXISTS tenant_users_insert ON users")
    op.execute("DROP POLICY IF EXISTS tenant_users ON users")
    op.execute("DROP POLICY IF EXISTS tenant_organizations ON organizations")
    for tabla in TABLAS_CON_ORGANIZACION:
        op.execute(f"DROP POLICY IF EXISTS tenant_{tabla} ON {tabla}")

    for tabla in TODAS_LAS_TABLAS:
        op.execute(f"ALTER TABLE {tabla} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {tabla} DISABLE ROW LEVEL SECURITY")

    op.execute("DROP FUNCTION IF EXISTS app_resolve_organization_by_slug(text)")
    op.execute("DROP FUNCTION IF EXISTS app_resolve_organization(text)")
    op.execute("DROP FUNCTION IF EXISTS app_current_user()")
    op.execute("DROP FUNCTION IF EXISTS app_current_organization()")
