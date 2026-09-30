"""slug de evento único por organización

Decisión del dueño, 2026-09-29: la organización pasa a formar parte de la URL
pública (`/{org}/{evento}`), así que el slug de un evento solo tiene que ser
único dentro de su organización. Esto revierte la unicidad global de la
migración `0030`, cuyo motivo (no había dominio que distinguiera organizaciones)
desaparece al poner la organización en la ruta.

Lo que evita que el cambio abra un hueco:

- **Resolución determinista.** Las funciones `SECURITY DEFINER` pasan a
  recibir `(p_org_slug, p_slug)`; la organización activa, el estado y la
  visibilidad se comprueban **dentro**, igual que en `0032`. Las versiones de
  un solo argumento se eliminan: con slugs repetibles devolverían varias filas
  y elegir «la más antigua» permitiría secuestrar un enlace antiguo creando un
  evento con el mismo slug en otra organización.
- **Enlaces antiguos congelados.** `legacy_event_slugs` se rellena una sola vez
  con los eventos existentes; `/public/events/{slug}` (ruta plana anterior)
  resuelve solo por esa tabla y devuelve 404 si el evento ya no es publicable,
  nunca «el siguiente» con el mismo slug.
- **Sin marcha atrás rota.** `downgrade()` aborta y lista los slugs repetidos
  entre organizaciones antes de recrear `uq_events_slug`.

`app_list_registrations_by_email` devuelve además el slug de la organización,
que «Mis eventos» necesita para construir el enlace.

Revision ID: 0058_slug_evento_por_org
Revises: 0057_proveedor_correo
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0058_slug_evento_por_org"
down_revision: str | None = "0057_proveedor_correo"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FUNCIONES_NUEVAS = (
    (
        "app_resolve_public_event(text, text)",
        """
CREATE OR REPLACE FUNCTION app_resolve_public_event(p_org_slug text, p_slug text)
RETURNS TABLE (id uuid, organization_id uuid)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT e.id, e.organization_id
  FROM events e
  JOIN organizations o ON o.id = e.organization_id
  WHERE o.slug = p_org_slug
    AND e.slug = p_slug
    AND e.status = 'published'
    AND e.visibility = 'public'
    AND o.is_active
$$
        """,
    ),
    (
        "app_resolve_public_event_display(text, text)",
        """
CREATE OR REPLACE FUNCTION app_resolve_public_event_display(p_org_slug text, p_slug text)
RETURNS TABLE (id uuid, organization_id uuid)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT e.id, e.organization_id
  FROM events e
  JOIN organizations o ON o.id = e.organization_id
  WHERE o.slug = p_org_slug
    AND e.slug = p_slug
    AND e.status IN ('published', 'cancelled')
    AND e.visibility = 'public'
    AND o.is_active
$$
        """,
    ),
    (
        "app_resolve_legacy_event(text, boolean)",
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
    AND o.is_active
$$
        """,
    ),
)

# Firmas anteriores (0032 y 0054), que `downgrade()` restablece.
_FUNCIONES_ANTERIORES = (
    (
        "app_resolve_public_event(text)",
        """
CREATE OR REPLACE FUNCTION app_resolve_public_event(p_slug text)
RETURNS TABLE (id uuid, organization_id uuid)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT e.id, e.organization_id
  FROM events e
  WHERE e.slug = p_slug
    AND e.status = 'published'
    AND e.visibility = 'public'
    AND EXISTS (SELECT 1 FROM organizations o WHERE o.id = e.organization_id AND o.is_active)
$$
        """,
    ),
    (
        "app_resolve_public_event_display(text)",
        """
CREATE OR REPLACE FUNCTION app_resolve_public_event_display(p_slug text)
RETURNS TABLE (id uuid, organization_id uuid)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT e.id, e.organization_id
  FROM events e
  WHERE e.slug = p_slug
    AND e.status IN ('published', 'cancelled')
    AND e.visibility = 'public'
    AND EXISTS (SELECT 1 FROM organizations o WHERE o.id = e.organization_id AND o.is_active)
$$
        """,
    ),
)

_NOMBRE_MIS_EVENTOS = "app_list_registrations_by_email(text)"
_MIS_EVENTOS = """
CREATE FUNCTION app_list_registrations_by_email(p_email text)
RETURNS TABLE (
  event_slug text,
  event_title text,
  starts_at timestamptz,
  organization_name text,
  status text,
  event_status text{extra_columna}
)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT e.slug, e.title, e.starts_at, o.name, r.status, e.status{extra_select}
  FROM event_registrations r
  JOIN events e ON e.id = r.event_id
  JOIN organizations o ON o.id = r.organization_id
  WHERE r.email = p_email AND o.is_active
  ORDER BY e.starts_at ASC
$$
"""

_COMPROBACION_DUPLICADOS = """
DO $$
DECLARE
    conflictos text;
BEGIN
    SELECT string_agg(DISTINCT slug, ', ') INTO conflictos
    FROM (
        SELECT slug FROM events GROUP BY slug HAVING count(*) > 1
    ) duplicados;
    IF conflictos IS NOT NULL THEN
        RAISE EXCEPTION
            'No se puede bajar la migración 0058: hay slugs de evento repetidos entre organizaciones: %. Renómbralos a mano (con copia de seguridad previa) y vuelve a bajar.',
            conflictos;
    END IF;
END $$;
"""


def _recrear_mis_eventos(*, con_organizacion: bool) -> None:
    op.execute(f"DROP FUNCTION IF EXISTS {_NOMBRE_MIS_EVENTOS}")
    op.execute(
        _MIS_EVENTOS.format(
            extra_columna=",\n  organization_slug text" if con_organizacion else "",
            extra_select=", o.slug" if con_organizacion else "",
        )
    )
    op.execute(f"REVOKE ALL ON FUNCTION {_NOMBRE_MIS_EVENTOS} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {_NOMBRE_MIS_EVENTOS} TO app_user")


def _crear_funciones(funciones: tuple[tuple[str, str], ...]) -> None:
    for nombre, sentencia in funciones:
        op.execute(sentencia)
        op.execute(f"REVOKE ALL ON FUNCTION {nombre} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {nombre} TO app_user")


def upgrade() -> None:
    # Enlaces antiguos: se congelan ahora, antes de que ningún slug pueda repetirse.
    op.execute(
        """
CREATE TABLE legacy_event_slugs (
    slug text PRIMARY KEY,
    event_id uuid NOT NULL REFERENCES events (id) ON DELETE CASCADE,
    organization_id uuid NOT NULL REFERENCES organizations (id) ON DELETE CASCADE
)
        """
    )
    op.execute(
        "INSERT INTO legacy_event_slugs (slug, event_id, organization_id) "
        "SELECT slug, id, organization_id FROM events"
    )
    op.execute("CREATE INDEX ix_legacy_event_slugs_event_id ON legacy_event_slugs (event_id)")
    # Solo las funciones `SECURITY DEFINER` (que corren como `app_maintainer`, con
    # `BYPASSRLS`) la leen. RLS sin ninguna política es la defensa real: el
    # `REVOKE` lo deshace `infra/postgres/sql/roles.sql` al reaplicarse sobre una
    # base viva, y con RLS forzada y sin política `app_user` no ve ni escribe nada.
    op.execute("ALTER TABLE legacy_event_slugs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE legacy_event_slugs FORCE ROW LEVEL SECURITY")
    op.execute("REVOKE ALL ON legacy_event_slugs FROM app_user")

    op.drop_constraint("uq_events_slug", "events", type_="unique")
    op.create_unique_constraint(
        "uq_events_organization_id_slug", "events", ["organization_id", "slug"]
    )

    for nombre, _ in _FUNCIONES_ANTERIORES:
        op.execute(f"DROP FUNCTION IF EXISTS {nombre}")
    _crear_funciones(_FUNCIONES_NUEVAS)
    _recrear_mis_eventos(con_organizacion=True)


def downgrade() -> None:
    op.execute(_COMPROBACION_DUPLICADOS)

    _recrear_mis_eventos(con_organizacion=False)
    for nombre, _ in _FUNCIONES_NUEVAS:
        op.execute(f"DROP FUNCTION IF EXISTS {nombre}")
    _crear_funciones(_FUNCIONES_ANTERIORES)

    op.drop_constraint("uq_events_organization_id_slug", "events", type_="unique")
    op.create_unique_constraint("uq_events_slug", "events", ["slug"])
    op.execute("DROP TABLE legacy_event_slugs")
