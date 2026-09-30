"""se retiran los enlaces antiguos de evento

Los enlaces `/eventos/{slug}` anteriores a que la organización entrara en la
URL eran direcciones de prueba: ya no se traducen (van a la portada). Se
eliminan la tabla congelada `legacy_event_slugs` y la función que la leía.

`downgrade()` las recrea **vacías** (los enlaces que contenía no se recuperan) y la
función con el filtro de eventos eliminados que añadió la `0060`.

Revision ID: 0062_sin_enlaces_antiguos
Revises: 0061_categorias_etiquetas
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0062_sin_enlaces_antiguos"
down_revision: str | None = "0061_categorias_etiquetas"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FUNCION = "app_resolve_legacy_event(text, boolean)"


def upgrade() -> None:
    op.execute(f"DROP FUNCTION IF EXISTS {_FUNCION}")
    op.execute("DROP TABLE IF EXISTS legacy_event_slugs")


def downgrade() -> None:
    op.execute(
        """
CREATE TABLE legacy_event_slugs (
    slug text PRIMARY KEY,
    event_id uuid NOT NULL REFERENCES events (id) ON DELETE CASCADE,
    organization_id uuid NOT NULL REFERENCES organizations (id) ON DELETE CASCADE
)
        """
    )
    op.execute("CREATE INDEX ix_legacy_event_slugs_event_id ON legacy_event_slugs (event_id)")
    op.execute("ALTER TABLE legacy_event_slugs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE legacy_event_slugs FORCE ROW LEVEL SECURITY")
    op.execute("REVOKE ALL ON legacy_event_slugs FROM app_user")
    op.execute(
        """
CREATE OR REPLACE FUNCTION app_resolve_legacy_event(p_slug text, p_para_mostrar boolean)
RETURNS TABLE (id uuid, organization_id uuid, organization_slug text, slug text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT e.id, e.organization_id, o.slug, e.slug
  FROM legacy_event_slugs l
  JOIN events e ON e.id = l.event_id
  JOIN organizations o ON o.id = e.organization_id
  WHERE l.slug = p_slug
    AND e.status = ANY (
      CASE WHEN p_para_mostrar THEN ARRAY['published', 'cancelled'] ELSE ARRAY['published'] END
    )
    AND e.visibility = 'public'
    AND e.deleted_at IS NULL
    AND o.is_active
$$
        """
    )
    op.execute(f"REVOKE ALL ON FUNCTION {_FUNCION} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {_FUNCION} TO app_user")
