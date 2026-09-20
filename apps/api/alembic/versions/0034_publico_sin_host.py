"""corrección de comportamiento: los públicos que resolvían por host dejan de hacerlo

Fase 6 del plan «organización sin dominio»
(`plans/260914-0741-organizacion-sin-dominio/plan.md`). Dos endpoints
públicos seguían resolviendo la organización por `Host` (deliberadamente
diferido en las fases 2-3): en producción, sin dominio por organización, esto
son 404/pérdida de datos reales, no solo código viejo. Se corrige aquí:

- `POST /public/cookie-consent`: sin ningún host que la resuelva, la
  organización deja de tener sentido para un registro de consentimiento de
  toda la instalación (misma decisión ya tomada para las 4 páginas legales,
  que pasaron a ser de plataforma en una sesión anterior). `organization_id`
  pasa a admitir `NULL`: las filas nuevas se guardan sin organización, las
  antiguas conservan la suya (no se reescribe histórico).
- `GET /public/events` (el listado): pasa a listar los eventos publicados de
  **toda la instalación**, no de una organización resuelta por host — es lo
  que el frontend ya esperaba de él (misma llamada sin filtro en
  `upcoming-events.ts`/`events-list-page.ts`). RLS exige contexto de
  organización por fila; sin dominio no hay ningún host que lo fije de
  antemano, así que la función `SECURITY DEFINER` `app_list_public_event_organizations`
  (alcance mínimo, mismo patrón que `0032`) devuelve solo los `id` de
  organización con al menos un evento publicable — la resolución completa de
  cada organización se hace después, fijando su contexto RLS una por una.

Revision ID: 0034_publico_sin_host
Revises: 0033_verificado_activo
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0034_publico_sin_host"
down_revision: str | None = "0033_verificado_activo"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FUNCION = """
CREATE OR REPLACE FUNCTION app_list_public_event_organizations()
RETURNS TABLE (organization_id uuid)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT DISTINCT e.organization_id
  FROM events e
  JOIN organizations o ON o.id = e.organization_id
  WHERE e.status = 'published'
    AND e.visibility = 'public'
    AND o.is_active
$$
"""

_NOMBRE_FUNCION = "app_list_public_event_organizations()"


def upgrade() -> None:
    op.execute("ALTER TABLE cookie_consents ALTER COLUMN organization_id DROP NOT NULL")

    op.execute(_FUNCION)
    op.execute(f"REVOKE ALL ON FUNCTION {_NOMBRE_FUNCION} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {_NOMBRE_FUNCION} TO app_user")


def downgrade() -> None:
    op.execute(f"DROP FUNCTION IF EXISTS {_NOMBRE_FUNCION}")

    # Restaurar NOT NULL exige que no queden filas NULL: las que se hayan
    # guardado desde el upgrade no tienen organización real que asignarles,
    # así que se borran (son consentimientos anónimos de la instalación, sin
    # dato personal alguno que perder — ver el propio endpoint).
    op.execute("DELETE FROM cookie_consents WHERE organization_id IS NULL")
    op.execute("ALTER TABLE cookie_consents ALTER COLUMN organization_id SET NOT NULL")
