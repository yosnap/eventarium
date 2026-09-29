"""página pública de organización (opt-in)

Decisión del dueño, 2026-09-29: la organización tiene una página pública en
`/{org}`, **desactivada por defecto** en todas. Con el interruptor apagado la
miga muestra el nombre como texto sin enlace y `/{org}` da 404; los eventos
siguen siendo públicos.

- `organizations.public_page_enabled` (`NOT NULL DEFAULT false`): el interruptor.
- `organizations.address`: dirección opcional que la organización decide hacer
  pública junto con el resto de su perfil.
- `app_resolve_public_organization(p_org_slug)`: `SECURITY DEFINER` de alcance
  mínimo (mismo patrón que `0032`/`0058`). Devuelve solo el `id`, y solo si la
  página está activada y la organización está activa: con el interruptor apagado,
  una organización inactiva o inexistente son indistinguibles.
- `website` pasa a exigir `http(s)://`; la migración antepone `https://` a los valores
  ya guardados sin esquema para que ninguna organización quede sin poder guardar
  su formulario. No es reversible (el `downgrade` no quita el esquema añadido).
- `app_list_registrations_by_email` devuelve además `organization_page_public`,
  para que «Mis eventos» sepa si puede enlazar a la organización.

Revision ID: 0059_pagina_publica_org
Revises: 0058_slug_evento_por_org
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0059_pagina_publica_org"
down_revision: str | None = "0058_slug_evento_por_org"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Valores heredados de antes de exigir `http(s)://`.
_NORMALIZAR_WEB = (
    "UPDATE organizations SET website = 'https://' || btrim(website) "
    "WHERE website IS NOT NULL AND btrim(website) <> '' "
    "AND btrim(website) !~* '^https?://'"
)
_QUITAR_WEB_VACIA = "UPDATE organizations SET website = NULL WHERE btrim(website) = ''"

_NOMBRE_RESOLVER = "app_resolve_public_organization(text)"
_RESOLVER = """
CREATE OR REPLACE FUNCTION app_resolve_public_organization(p_org_slug text)
RETURNS TABLE (id uuid)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT o.id
  FROM organizations o
  WHERE o.slug = p_org_slug
    AND o.public_page_enabled
    AND o.is_active
$$
"""

_NOMBRE_MIS_EVENTOS = "app_list_registrations_by_email(text)"
_MIS_EVENTOS = """
CREATE FUNCTION app_list_registrations_by_email(p_email text)
RETURNS TABLE (
  event_slug text,
  event_title text,
  starts_at timestamptz,
  organization_name text,
  status text,
  event_status text,
  organization_slug text{extra_columna}
)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT e.slug, e.title, e.starts_at, o.name, r.status, e.status, o.slug{extra_select}
  FROM event_registrations r
  JOIN events e ON e.id = r.event_id
  JOIN organizations o ON o.id = r.organization_id
  WHERE r.email = p_email AND o.is_active
  ORDER BY e.starts_at ASC
$$
"""


def _recrear_mis_eventos(*, con_pagina_publica: bool) -> None:
    op.execute(f"DROP FUNCTION IF EXISTS {_NOMBRE_MIS_EVENTOS}")
    op.execute(
        _MIS_EVENTOS.format(
            extra_columna=",\n  organization_page_public boolean" if con_pagina_publica else "",
            extra_select=", o.public_page_enabled" if con_pagina_publica else "",
        )
    )
    op.execute(f"REVOKE ALL ON FUNCTION {_NOMBRE_MIS_EVENTOS} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {_NOMBRE_MIS_EVENTOS} TO app_user")


def upgrade() -> None:
    op.add_column("organizations", sa.Column("address", sa.String(length=300), nullable=True))
    op.add_column(
        "organizations",
        sa.Column("public_page_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.execute(_NORMALIZAR_WEB)
    op.execute(_QUITAR_WEB_VACIA)
    op.execute(_RESOLVER)
    op.execute(f"REVOKE ALL ON FUNCTION {_NOMBRE_RESOLVER} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {_NOMBRE_RESOLVER} TO app_user")
    _recrear_mis_eventos(con_pagina_publica=True)


def downgrade() -> None:
    _recrear_mis_eventos(con_pagina_publica=False)
    op.execute(f"DROP FUNCTION IF EXISTS {_NOMBRE_RESOLVER}")
    op.drop_column("organizations", "public_page_enabled")
    op.drop_column("organizations", "address")
