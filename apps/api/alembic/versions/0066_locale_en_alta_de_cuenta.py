"""locale en alta de cuenta

Añade `p_locale` a `app_create_unverified_user` para que el registro público
(`POST /auth/register`) pueda fijar el idioma de la cuenta desde el propio
alta, en vez de depender siempre del `DEFAULT 'es-ES'` de la columna.

La función cambia de **firma** (3 -> 4 parámetros): se elimina la versión
vieja antes de crear la nueva, igual que hizo `0005_nombre_y_apellidos.py`
al quitar `p_full_name` (`CREATE OR REPLACE` no sustituye una función con
distinta firma, crea una sobrecarga adicional).

Nota de numeración: `down_revision` fijado contra la cabeza real de este
worktree en el momento de escribir esta migración (`alembic heads` ->
`0062_sin_enlaces_antiguos`, única cabeza). `origin/develop` y `origin/main`
ya tienen migraciones `0063`-`0065` propias (sin relación con `locale`, no
mergeadas todavía en esta rama); se salta ese rango al numerar esta para no
reutilizar un número ya tomado por otra rama -- quien integre esta rama con
`develop` necesitará una revisión de fusión de Alembic (`alembic merge
heads`), algo normal con migraciones en ramas paralelas y fuera del alcance
de esta fase.

Revision ID: 0066_locale_en_alta_de_cuenta
Revises: 0062_sin_enlaces_antiguos
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0066_locale_en_alta_de_cuenta"
down_revision: str | None = "0062_sin_enlaces_antiguos"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Firma nueva de 4 parámetros: misma identidad de argumentos
    # (`uuid,text,text,text`) que tuvo la función vieja de
    # `0004_correo_y_verificacion.py` (con `p_full_name` como 4º parámetro en
    # vez de `p_locale`). Se usa `CREATE FUNCTION` sin `OR REPLACE`: si por
    # drift esa firma antigua siguiera existiendo en alguna base, un `CREATE
    # OR REPLACE` la sustituiría conservando en silencio su ACL/owner
    # original; con `CREATE FUNCTION` simple, la migración falla ruidosamente
    # (`already exists`) en vez de absorber el drift sin avisar.
    op.execute("DROP FUNCTION IF EXISTS app_create_unverified_user(uuid, text, text)")
    op.execute(
        """
CREATE FUNCTION app_create_unverified_user(
  p_id uuid, p_email text, p_password_hash text, p_locale text DEFAULT 'es-ES'
)
RETURNS void
LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path = public AS $$
  -- `is_superadmin` no tiene `server_default` (solo default de ORM): un INSERT en SQL
  -- crudo tiene que fijarlo a mano. `locale` llega del llamador (validado por Pydantic,
  -- `Literal`); el DEFAULT 'es-ES' cubre a los llamadores de 3 argumentos, el COALESCE
  -- cubre además un NULL explícito que saltaría ese DEFAULT y violaría el NOT NULL.
  INSERT INTO users (id, email, password_hash, locale, is_active, is_superadmin, email_verified_at)
  VALUES (p_id, lower(p_email), p_password_hash, COALESCE(p_locale, 'es-ES'), true, false, NULL)
$$
        """
    )
    op.execute(
        "REVOKE ALL ON FUNCTION app_create_unverified_user(uuid, text, text, text) FROM PUBLIC"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION app_create_unverified_user(uuid, text, text, text) TO app_user"
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS app_create_unverified_user(uuid, text, text, text)")
    op.execute(
        """
CREATE FUNCTION app_create_unverified_user(p_id uuid, p_email text, p_password_hash text)
RETURNS void
LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path = public AS $$
  INSERT INTO users (id, email, password_hash, locale, is_active, is_superadmin, email_verified_at)
  VALUES (p_id, lower(p_email), p_password_hash, 'es-ES', true, false, NULL)
$$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION app_create_unverified_user(uuid, text, text) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION app_create_unverified_user(uuid, text, text) TO app_user")
