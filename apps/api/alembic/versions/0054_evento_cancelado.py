"""Estado «cancelado» del evento.

- `events.status` gana `cancelled` y, por primera vez, un `CHECK`: hasta
  ahora solo lo validaba el `Literal` del schema.
- `events.cancelled_at` y `events.cancellation_reason` (texto opcional que ve
  el público).
- `event_registrations.cancelled_with_event` marca las inscripciones que
  canceló la cancelación del evento (no las que ya lo estaban), y
  `event_cancellation_notified_at` deja constancia del aviso: el barrido por
  lotes que avisa y reembolsa se puede reanudar sin repetir correos.
- `event_payment_refunds.reason` admite `event_cancelled`: el reembolso
  íntegro de una cancelación del evento no pasa por la política de plazo.
- `app_resolve_public_event_display`: como `app_resolve_public_event`, pero
  admite también eventos cancelados, para mostrar su ficha con el aviso. La
  inscripción y la compra siguen usando la función original, que solo
  resuelve eventos publicados.

Revision ID: 0054_evento_cancelado
Revises: 0053_politicas_organizador
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0054_evento_cancelado"
down_revision: str | None = "0053_politicas_organizador"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FUNCION_DISPLAY = """
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
"""
_NOMBRE_DISPLAY = "app_resolve_public_event_display(text)"

# «Mis eventos» necesita saber si el evento se canceló, para no confundirlo
# con una cancelación de la propia persona. Cambiar las columnas de retorno
# exige borrar y volver a crear la función (`0052_mis_eventos_acceso`).
_NOMBRE_MIS_EVENTOS = "app_list_registrations_by_email(text)"
_MIS_EVENTOS = """
CREATE FUNCTION app_list_registrations_by_email(p_email text)
RETURNS TABLE (
  event_slug text,
  event_title text,
  starts_at timestamptz,
  organization_name text,
  status text{extra_columna}
)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT e.slug, e.title, e.starts_at, o.name, r.status{extra_select}
  FROM event_registrations r
  JOIN events e ON e.id = r.event_id
  JOIN organizations o ON o.id = r.organization_id
  WHERE r.email = p_email AND o.is_active
  ORDER BY e.starts_at ASC
$$
"""


def _recrear_mis_eventos(*, con_estado_del_evento: bool) -> None:
    op.execute(f"DROP FUNCTION IF EXISTS {_NOMBRE_MIS_EVENTOS}")
    op.execute(
        _MIS_EVENTOS.format(
            extra_columna=",\n  event_status text" if con_estado_del_evento else "",
            extra_select=", e.status" if con_estado_del_evento else "",
        )
    )
    op.execute(f"REVOKE ALL ON FUNCTION {_NOMBRE_MIS_EVENTOS} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {_NOMBRE_MIS_EVENTOS} TO app_user")


def upgrade() -> None:
    op.create_check_constraint(
        "ck_events_status",
        "events",
        "status IN ('draft', 'published', 'archived', 'cancelled')",
    )
    op.add_column("events", sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("events", sa.Column("cancellation_reason", sa.Text(), nullable=True))

    op.add_column(
        "event_registrations",
        sa.Column("cancelled_with_event", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "event_registrations",
        sa.Column("event_cancellation_notified_at", sa.DateTime(timezone=True), nullable=True),
    )
    # El barrido busca las pendientes de aviso de un evento: índice parcial
    # pequeño, solo con las filas que aún le quedan por procesar.
    op.create_index(
        "ix_event_registrations_aviso_cancelacion",
        "event_registrations",
        ["organization_id", "event_id"],
        postgresql_where=sa.text("cancelled_with_event AND event_cancellation_notified_at IS NULL"),
    )

    op.drop_constraint("ck_event_payment_refunds_reason", "event_payment_refunds", type_="check")
    op.create_check_constraint(
        "ck_event_payment_refunds_reason",
        "event_payment_refunds",
        "reason IN ('cancellation', 'manual', 'event_cancelled')",
    )

    op.execute(_FUNCION_DISPLAY)
    op.execute(f"REVOKE ALL ON FUNCTION {_NOMBRE_DISPLAY} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {_NOMBRE_DISPLAY} TO app_user")
    _recrear_mis_eventos(con_estado_del_evento=True)


def downgrade() -> None:
    # Solo reversible mientras no haya eventos cancelados: el despliegue lee
    # `cancelled` antes de permitir escribirlo, así que volver atrás con
    # cancelados ya guardados rompería el CHECK de la versión anterior.
    _recrear_mis_eventos(con_estado_del_evento=False)
    op.execute(f"DROP FUNCTION IF EXISTS {_NOMBRE_DISPLAY}")
    op.drop_constraint("ck_event_payment_refunds_reason", "event_payment_refunds", type_="check")
    op.create_check_constraint(
        "ck_event_payment_refunds_reason",
        "event_payment_refunds",
        "reason IN ('cancellation', 'manual')",
    )
    op.drop_index("ix_event_registrations_aviso_cancelacion", table_name="event_registrations")
    op.drop_column("event_registrations", "event_cancellation_notified_at")
    op.drop_column("event_registrations", "cancelled_with_event")
    op.drop_column("events", "cancellation_reason")
    op.drop_column("events", "cancelled_at")
    op.drop_constraint("ck_events_status", "events", type_="check")
