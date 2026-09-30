"""eliminar un evento cancelado

Decisión del dueño, 2026-09-30: una organización puede **eliminar** un evento,
pero solo cuando ya está cancelado. Cancelar y eliminar son dos acciones y dos
estados distintos: un evento activo no se elimina; primero se cancela.

La eliminación es **lógica**: `events.deleted_at`. El evento desaparece del
panel, de las listas y del público, pero no se borra ninguna fila, así que las
inscripciones, los cobros, los reembolsos y la contabilidad asociados se
conservan para auditoría y para cuadrar las cuentas. El identificador
(`slug`) sigue reservado dentro de la organización.

Las funciones `SECURITY DEFINER` que resuelven o listan eventos públicos
excluyen los eliminados. Se recrean con `CREATE OR REPLACE` (misma firma y
mismas columnas); el `downgrade` restablece las definiciones anteriores
(`0034`, `0058` y `0059`). Volver atrás hace visibles otra vez los eventos que
estuvieran eliminados, porque la columna deja de existir.

Revision ID: 0060_evento_eliminado
Revises: 0059_pagina_publica_org
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0060_evento_eliminado"
down_revision: str | None = "0059_pagina_publica_org"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SIN_ELIMINADOS = "AND e.deleted_at IS NULL"


def _funciones(filtro: str) -> tuple[str, ...]:
    """Las funciones de resolución y listado, con o sin el filtro de eliminados."""
    return (
        f"""
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
    {filtro}
$$
        """,
        f"""
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
    {filtro}
$$
        """,
        f"""
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
    {filtro}
$$
        """,
        f"""
CREATE OR REPLACE FUNCTION app_list_public_event_organizations()
RETURNS TABLE (organization_id uuid)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT DISTINCT e.organization_id
  FROM events e
  JOIN organizations o ON o.id = e.organization_id
  WHERE e.status = 'published'
    AND e.visibility = 'public'
    AND o.is_active
    {filtro}
$$
        """,
        f"""
CREATE OR REPLACE FUNCTION app_list_registrations_by_email(p_email text)
RETURNS TABLE (
  event_slug text,
  event_title text,
  starts_at timestamptz,
  organization_name text,
  status text,
  event_status text,
  organization_slug text,
  organization_page_public boolean
)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT e.slug, e.title, e.starts_at, o.name, r.status, e.status, o.slug, o.public_page_enabled
  FROM event_registrations r
  JOIN events e ON e.id = r.event_id
  JOIN organizations o ON o.id = r.organization_id
  WHERE r.email = p_email AND o.is_active
    {filtro}
  ORDER BY e.starts_at ASC
$$
        """,
    )


def upgrade() -> None:
    op.add_column("events", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    for sentencia in _funciones(_SIN_ELIMINADOS):
        op.execute(sentencia)


def downgrade() -> None:
    for sentencia in _funciones(""):
        op.execute(sentencia)
    op.drop_column("events", "deleted_at")
