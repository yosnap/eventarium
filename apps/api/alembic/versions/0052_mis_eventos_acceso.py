"""mis eventos: resolución pública por email

Fase 1 del plan «mis-eventos-asistente». Magic-link por email que lista
todas las inscripciones de un asistente, cruzando organizaciones —
`event_registrations` lleva RLS por `organization_id` (migración `0010`), así
que no hay ningún contexto de organización que fijar antes de resolver "todas
las inscripciones de este email en cualquier organización": la propia
resolución necesita saltarse RLS con una función `SECURITY DEFINER` de
alcance mínimo, mismo patrón que `0032`.

Dos funciones, no una, por el mismo motivo que `0032` separa
`app_resolve_registration_organization` de una consulta genérica: cada
llamador solo necesita lo mínimo.

- `app_has_registration_by_email`: existencia únicamente (booleano), para el
  endpoint de solicitud — decide si se encola el correo, mismo patrón
  comprobar-antes-de-actuar que `forgot_password`/`app_find_user_by_email`,
  sin devolver ninguna fila real.
- `app_list_registrations_by_email`: las columnas mínimas para pintar el
  listado (slug/título del evento, fecha de inicio, nombre de la
  organización, estado de la inscripción) — nunca la fila entera de
  `event_registrations` (sin nombre completo, sin respuestas del
  formulario).

Ambas excluyen organizaciones desactivadas (`organizations.is_active`),
mismo criterio que las cuatro funciones de `0032`.

Índice nuevo sobre `event_registrations.email` en solitario (hallazgo de
red-team, Fase 3 de este plan: Medium): el único índice existente sobre la
tabla es compuesto `(event_id, status)` (`0010`), pensado para el aforo de
un evento concreto — ninguna consulta anterior filtraba por email sin
`event_id` delante. Sin este índice, ambas funciones fuerzan un seq scan
completo de la tabla en cada petición a los dos endpoints públicos nuevos.

Revision ID: 0052_mis_eventos_acceso
Revises: 0051_ocr_draft_en_extraccion
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0052_mis_eventos_acceso"
down_revision: str | None = "0051_ocr_draft_en_extraccion"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FUNCIONES = (
    """
CREATE OR REPLACE FUNCTION app_has_registration_by_email(p_email text)
RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT EXISTS (
    SELECT 1
    FROM event_registrations r
    JOIN organizations o ON o.id = r.organization_id
    WHERE r.email = p_email AND o.is_active
  )
$$
    """,
    """
CREATE OR REPLACE FUNCTION app_list_registrations_by_email(p_email text)
RETURNS TABLE (
  event_slug text,
  event_title text,
  starts_at timestamptz,
  organization_name text,
  status text
)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT e.slug, e.title, e.starts_at, o.name, r.status
  FROM event_registrations r
  JOIN events e ON e.id = r.event_id
  JOIN organizations o ON o.id = r.organization_id
  WHERE r.email = p_email AND o.is_active
  ORDER BY e.starts_at ASC
$$
    """,
)

_NOMBRES = (
    "app_has_registration_by_email(text)",
    "app_list_registrations_by_email(text)",
)


def upgrade() -> None:
    op.create_index(
        "ix_event_registrations_email", "event_registrations", ["email"], unique=False
    )
    for sentencia in _FUNCIONES:
        op.execute(sentencia)
    for nombre in _NOMBRES:
        op.execute(f"REVOKE ALL ON FUNCTION {nombre} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {nombre} TO app_user")


def downgrade() -> None:
    for nombre in _NOMBRES:
        op.execute(f"DROP FUNCTION IF EXISTS {nombre}")
    op.drop_index("ix_event_registrations_email", table_name="event_registrations")
