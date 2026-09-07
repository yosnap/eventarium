"""autoservicio de organizaciones

Tres funciones `SECURITY DEFINER` de alcance mínimo para el registro libre de
organizaciones:

- `app_create_organization_row`: la política `tenant_organizations` exige
  `id = app_current_organization()`, así que ninguna sesión con contexto RLS podría
  insertar la primerísima fila de una organización que aún no existe (problema del
  huevo y la gallina, igual que con `users` en la fase 1). Se resuelve con el mismo
  patrón: una función de superficie mínima que solo inserta esa fila.

  El resto del alta —clonar roles, dominio, branding, membresía del propietario— NO
  necesita ninguna función nueva: en cuanto la organización existe, basta con fijar el
  contexto RLS a su id (`set_organization_context`) y reutilizar el código Python ya
  existente (`organization_service.clone_system_roles`, etc.) bajo RLS normal, sin
  `BYPASSRLS`. Es la misma lógica que usa el alta por superadmin, no una reimplementada
  en SQL — así no hay dos caminos que puedan divergir.

- `app_check_slug_available`: comprobación de disponibilidad para `check-slug`, sin
  exponer más que un booleano.

- `app_find_user_by_id`: la persona que acaba de verificar su correo no comparte
  organización con nadie todavía, así que no puede leer su propia fila de `users` por
  la vía normal cuando llama al endpoint de creación con un token sin organización
  (ver `require_verified_user` en `core/deps.py`).

Revision ID: 0006_autoservicio_organizaciones
Revises: 0005_nombre_y_apellidos
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0006_autoservicio_organizaciones"
down_revision: str | None = "0005_nombre_y_apellidos"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FUNCIONES = (
    """
CREATE OR REPLACE FUNCTION app_create_organization_row(p_id uuid, p_slug text, p_name text)
RETURNS void
LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path = public AS $$
  INSERT INTO organizations (id, slug, name, is_active)
  VALUES (p_id, lower(p_slug), p_name, true)
$$
    """,
    """
CREATE OR REPLACE FUNCTION app_check_slug_available(p_slug text)
RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT NOT EXISTS (SELECT 1 FROM organizations WHERE slug = lower(p_slug))
$$
    """,
    """
CREATE OR REPLACE FUNCTION app_find_user_by_id(p_id uuid)
RETURNS TABLE (id uuid, email text, email_verified_at timestamptz)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT u.id, u.email, u.email_verified_at FROM users u WHERE u.id = p_id
$$
    """,
)


def upgrade() -> None:
    for sentencia in FUNCIONES:
        op.execute(sentencia)

    op.execute("REVOKE ALL ON FUNCTION app_create_organization_row(uuid, text, text) FROM PUBLIC")
    op.execute("REVOKE ALL ON FUNCTION app_check_slug_available(text) FROM PUBLIC")
    op.execute("REVOKE ALL ON FUNCTION app_find_user_by_id(uuid) FROM PUBLIC")
    op.execute(
        "GRANT EXECUTE ON FUNCTION app_create_organization_row(uuid, text, text) TO app_user"
    )
    op.execute("GRANT EXECUTE ON FUNCTION app_check_slug_available(text) TO app_user")
    op.execute("GRANT EXECUTE ON FUNCTION app_find_user_by_id(uuid) TO app_user")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS app_find_user_by_id(uuid)")
    op.execute("DROP FUNCTION IF EXISTS app_check_slug_available(text)")
    op.execute("DROP FUNCTION IF EXISTS app_create_organization_row(uuid, text, text)")
