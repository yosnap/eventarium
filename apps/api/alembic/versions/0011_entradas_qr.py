"""entradas qr

Fase 4 del PRD, fase 1 de trabajo. Dos tablas nuevas (`event_tickets`,
`event_ticket_scans`), mismo patrón de FK **compuestas** contra
`(id, organization_id)` del padre y RLS que `0009_eventos_agenda_y_ponentes`/
`0010_inscripcion_de_asistentes`.

`event_ticket_scans.ticket_id` es **nulo**: un escaneo cuyo JWT no resuelve a
ninguna entrada real (`result = not_found` o firma inválida, fase 2 de
trabajo) no tiene una entrada a la que enlazar, pero el intento se registra
igual (auditoría).

Backfill de `tickets:read`+`tickets:write` a cualquier rol con
`organizations:write` (mismo criterio que usó `0010` para `registrations:*`),
más `tickets:write` (sin `tickets:read`) a los roles ya clonados de la
plantilla de sistema `volunteer` en organizaciones existentes: el
voluntariado solo escanea, no gestiona preguntas ni ve estadísticas
(decisión #8 del plan de la fase 4).

Revision ID: 0011_entradas_qr
Revises: 0010_inscripcion_de_asistentes
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011_entradas_qr"
down_revision: str | None = "0010_inscripcion_de_asistentes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLAS_NUEVAS = (
    "event_tickets",
    "event_ticket_scans",
)


def upgrade() -> None:
    _crear_tablas()
    _verificar_privilegios_de_app_user()
    _activar_rls()
    _backfill_permisos_de_entradas()


def _crear_tablas() -> None:
    op.create_table(
        "event_tickets",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("event_id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("registration_id", sa.UUID(), nullable=False),
        sa.Column(
            "issued_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("used_by_event_member_id", sa.UUID(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["event_id", "organization_id"],
            ["events.id", "events.organization_id"],
            name="fk_event_tickets_event_id_organization_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["registration_id", "organization_id"],
            ["event_registrations.id", "event_registrations.organization_id"],
            name="fk_event_tickets_registration_id_organization_id",
            ondelete="CASCADE",
        ),
        # `SET NULL` (no `RESTRICT`): es un dato de auditoría sobre quién marcó
        # el uso, no una referencia de la que dependa la validez de la entrada.
        sa.ForeignKeyConstraint(
            ["used_by_event_member_id", "organization_id"],
            ["event_members.id", "event_members.organization_id"],
            name="fk_event_tickets_used_by_event_member_id_organization_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_event_tickets")),
        sa.UniqueConstraint("registration_id", name="uq_event_tickets_registration_id"),
        sa.UniqueConstraint("id", "organization_id", name="uq_event_tickets_id_organization_id"),
    )
    op.create_index(
        op.f("ix_event_tickets_event_id"), "event_tickets", ["event_id"], unique=False
    )

    op.create_table(
        "event_ticket_scans",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("ticket_id", sa.UUID(), nullable=True),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("event_id", sa.UUID(), nullable=False),
        sa.Column("scanned_by_event_member_id", sa.UUID(), nullable=False),
        sa.Column("client_scan_id", sa.UUID(), nullable=False),
        sa.Column("client_scanned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "scanned_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("result", sa.String(length=30), nullable=False),
        sa.Column("device_label", sa.String(length=120), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id", "organization_id"],
            ["event_tickets.id", "event_tickets.organization_id"],
            name="fk_event_ticket_scans_ticket_id_organization_id",
            ondelete="CASCADE",
        ),
        # Sin `ondelete`: RESTRICT por defecto, mismo patrón que
        # `event_session_participants.event_member_id` — el registro de quién
        # escaneó es de auditoría, no debe desaparecer en cascada al quitar a
        # alguien del roster del evento.
        sa.ForeignKeyConstraint(
            ["scanned_by_event_member_id", "organization_id"],
            ["event_members.id", "event_members.organization_id"],
            name="fk_event_ticket_scans_scanned_by_event_member_id_org_id",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_event_ticket_scans")),
        sa.UniqueConstraint("client_scan_id", name="uq_event_ticket_scans_client_scan_id"),
    )
    op.create_index(
        op.f("ix_event_ticket_scans_event_id"), "event_ticket_scans", ["event_id"], unique=False
    )
    op.create_index(
        op.f("ix_event_ticket_scans_scanned_by_event_member_id"),
        "event_ticket_scans",
        ["scanned_by_event_member_id"],
        unique=False,
    )


def _verificar_privilegios_de_app_user() -> None:
    """Mismo patrón que `0002_esquema_base`/`0009`/`0010`: falla aquí, no en runtime."""
    conexion = op.get_bind()
    for tabla in TABLAS_NUEVAS:
        concedido = conexion.execute(
            sa.text("SELECT has_table_privilege('app_user', :tabla, 'SELECT')"),
            {"tabla": tabla},
        ).scalar()
        if not concedido:
            raise RuntimeError(
                f"El rol «app_user» no tiene SELECT sobre «{tabla}». Ejecuta "
                "infra/scripts/ensure-roles.sh para aplicar ALTER DEFAULT PRIVILEGES."
            )


def _activar_rls() -> None:
    for tabla in TABLAS_NUEVAS:
        op.execute(f"ALTER TABLE {tabla} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {tabla} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_{tabla} ON {tabla} "
            "USING (organization_id = app_current_organization()) "
            "WITH CHECK (organization_id = app_current_organization())"
        )


# Ancla al permiso, no al nombre del rol: un rol a medida con `organizations:write`
# también necesita `tickets:*`, exista o no con la clave `owner`/`organizer`.
_BACKFILL_TICKETS = (
    """
INSERT INTO role_permissions (role_id, permission, organization_id)
SELECT r.id, 'tickets:read', r.organization_id
FROM roles r
WHERE EXISTS (
  SELECT 1 FROM role_permissions rp
  WHERE rp.role_id = r.id AND rp.permission = 'organizations:write'
)
AND NOT EXISTS (
  SELECT 1 FROM role_permissions rp2
  WHERE rp2.role_id = r.id AND rp2.permission = 'tickets:read'
)
    """,
    """
INSERT INTO role_permissions (role_id, permission, organization_id)
SELECT r.id, 'tickets:write', r.organization_id
FROM roles r
WHERE EXISTS (
  SELECT 1 FROM role_permissions rp
  WHERE rp.role_id = r.id AND rp.permission = 'organizations:write'
)
AND NOT EXISTS (
  SELECT 1 FROM role_permissions rp2
  WHERE rp2.role_id = r.id AND rp2.permission = 'tickets:write'
)
    """,
    # El voluntariado solo escanea: `tickets:write` sin `tickets:read`, salvo
    # que el propio rol ya tuviera `organizations:write` (cubierto arriba).
    """
INSERT INTO role_permissions (role_id, permission, organization_id)
SELECT r.id, 'tickets:write', r.organization_id
FROM roles r
WHERE r.key = 'volunteer'
AND NOT EXISTS (
  SELECT 1 FROM role_permissions rp2
  WHERE rp2.role_id = r.id AND rp2.permission = 'tickets:write'
)
    """,
)


def _backfill_permisos_de_entradas() -> None:
    for sentencia in _BACKFILL_TICKETS:
        op.execute(sentencia)


def downgrade() -> None:
    # `downgrade()` es destructivo a partir de aquí: borra las filas de permisos
    # que el propio `upgrade` insertó y, al final, las tablas enteras con sus
    # datos. Válido para revertir un despliegue fallido antes de que existan
    # entradas reales — no para producción con datos.
    op.execute(
        "DELETE FROM role_permissions "
        "WHERE permission IN ('tickets:read', 'tickets:write') "
        "AND role_id IN ("
        "  SELECT r.id FROM roles r "
        "  WHERE r.key = 'volunteer' "
        "  OR EXISTS ("
        "    SELECT 1 FROM role_permissions rp "
        "    WHERE rp.role_id = r.id AND rp.permission = 'organizations:write'"
        "  )"
        ")"
    )

    for tabla in reversed(TABLAS_NUEVAS):
        op.execute(f"DROP POLICY IF EXISTS tenant_{tabla} ON {tabla}")
        op.execute(f"ALTER TABLE {tabla} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {tabla} DISABLE ROW LEVEL SECURITY")

    op.drop_index(
        op.f("ix_event_ticket_scans_scanned_by_event_member_id"),
        table_name="event_ticket_scans",
    )
    op.drop_index(op.f("ix_event_ticket_scans_event_id"), table_name="event_ticket_scans")
    op.drop_table("event_ticket_scans")

    op.drop_index(op.f("ix_event_tickets_event_id"), table_name="event_tickets")
    op.drop_table("event_tickets")
