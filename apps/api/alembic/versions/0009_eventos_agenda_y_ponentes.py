"""eventos, agenda y ponentes

Fase 2 del PRD. Cinco tablas nuevas (`events`, `event_sessions`, `event_members`,
`event_session_participants`, `speaker_public_profiles`), con FK **compuestas**
contra `(id, organization_id)` del padre en vez de FK simples: la integridad
referencial de PostgreSQL no pasa por RLS, así que una FK simple no impediría que
una fila hija con `organization_id` propio apuntara al recurso de otra
organización. RLS con el mismo patrón que `0003_politicas_rls`. Backfill de
`events:read`/`events:write` para todo rol que ya tenga `organizations:write`
(no solo `owner`/`organizer` por nombre: un rol a medida con esa misma capacidad
también lo necesita).

Revision ID: 0009_eventos_agenda_y_ponentes
Revises: 0008_cuenta_y_recuperacion
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0009_eventos_agenda_y_ponentes"
down_revision: str | None = "0008_cuenta_y_recuperacion"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLAS_NUEVAS = (
    "events",
    "event_sessions",
    "event_members",
    "event_session_participants",
    "speaker_public_profiles",
)


def upgrade() -> None:
    _crear_tablas()
    _verificar_privilegios_de_app_user()
    _activar_rls()
    _backfill_permisos_de_eventos()


def _crear_tablas() -> None:
    op.create_table(
        "events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("slug", sa.String(length=160), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("cover_object_key", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("visibility", sa.String(length=20), nullable=False),
        sa.Column("timezone", sa.String(length=60), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("location_mode", sa.String(length=20), nullable=False),
        sa.Column("location_name", sa.String(length=200), nullable=True),
        sa.Column("location_address", sa.String(length=300), nullable=True),
        sa.Column("online_url", sa.String(length=500), nullable=True),
        sa.Column("capacity", sa.Integer(), nullable=True),
        sa.Column("registration_mode", sa.String(length=20), nullable=False),
        sa.Column("email_verification_required", sa.Boolean(), nullable=False),
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
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_events_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_events")),
        sa.UniqueConstraint("organization_id", "slug", name="uq_events_organization_id_slug"),
        sa.UniqueConstraint("id", "organization_id", name="uq_events_id_organization_id"),
    )
    op.create_index(op.f("ix_events_organization_id"), "events", ["organization_id"], unique=False)

    op.create_table(
        "event_sessions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("event_id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("session_type", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("room", sa.String(length=120), nullable=True),
        sa.Column("video_platform", sa.String(length=20), nullable=True),
        sa.Column("video_url", sa.String(length=500), nullable=True),
        sa.Column("materials", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
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
            name="fk_event_sessions_event_id_organization_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_event_sessions")),
        sa.UniqueConstraint("id", "organization_id", name="uq_event_sessions_id_organization_id"),
    )
    op.create_index(
        op.f("ix_event_sessions_event_id"), "event_sessions", ["event_id"], unique=False
    )

    op.create_table(
        "event_members",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("event_id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("organization_member_id", sa.UUID(), nullable=False),
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
            name="fk_event_members_event_id_organization_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_member_id"],
            ["organization_members.id"],
            name=op.f("fk_event_members_organization_member_id_organization_members"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_event_members")),
        sa.UniqueConstraint(
            "event_id", "organization_member_id", name="uq_event_members_event_id_member_id"
        ),
        sa.UniqueConstraint("id", "organization_id", name="uq_event_members_id_organization_id"),
    )
    op.create_index(op.f("ix_event_members_event_id"), "event_members", ["event_id"], unique=False)
    op.create_index(
        op.f("ix_event_members_organization_member_id"),
        "event_members",
        ["organization_member_id"],
        unique=False,
    )

    op.create_table(
        "event_session_participants",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("event_member_id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("role_key", sa.String(length=60), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
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
            ["session_id", "organization_id"],
            ["event_sessions.id", "event_sessions.organization_id"],
            name="fk_event_session_participants_session_id_organization_id",
            ondelete="CASCADE",
        ),
        # Sin `ondelete`: RESTRICT por defecto. Quitar a alguien del roster con
        # participaciones activas se rechaza a nivel de base de datos como último
        # cinturón de seguridad; el servicio ya lo comprueba antes y responde 409.
        sa.ForeignKeyConstraint(
            ["event_member_id", "organization_id"],
            ["event_members.id", "event_members.organization_id"],
            name="fk_event_session_participants_event_member_id_organization_id",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_event_session_participants")),
        sa.UniqueConstraint(
            "session_id",
            "event_member_id",
            "role_key",
            name="uq_event_session_participants_session_member_role",
        ),
    )
    op.create_index(
        op.f("ix_event_session_participants_session_id"),
        "event_session_participants",
        ["session_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_event_session_participants_event_member_id"),
        "event_session_participants",
        ["event_member_id"],
        unique=False,
    )

    op.create_table(
        "speaker_public_profiles",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("public_slug", sa.String(length=80), nullable=False),
        sa.Column("source_organization_member_id", sa.UUID(), nullable=False),
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
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_speaker_public_profiles_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_speaker_public_profiles_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_organization_member_id"],
            ["organization_members.id"],
            name=op.f(
                "fk_speaker_public_profiles_source_organization_member_id_organization_members"
            ),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_speaker_public_profiles")),
        sa.UniqueConstraint(
            "organization_id",
            "user_id",
            name="uq_speaker_public_profiles_organization_id_user_id",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "public_slug",
            name="uq_speaker_public_profiles_organization_id_public_slug",
        ),
    )
    op.create_index(
        op.f("ix_speaker_public_profiles_organization_id"),
        "speaker_public_profiles",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_speaker_public_profiles_user_id"),
        "speaker_public_profiles",
        ["user_id"],
        unique=False,
    )


def _verificar_privilegios_de_app_user() -> None:
    """Mismo patrón que `0002_esquema_base`: falla aquí, no en runtime."""
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
# también necesita `events:*`, exista o no con la clave `owner`/`organizer`.
_BACKFILL_EVENTS = (
    """
INSERT INTO role_permissions (role_id, permission, organization_id)
SELECT r.id, 'events:read', r.organization_id
FROM roles r
WHERE EXISTS (
  SELECT 1 FROM role_permissions rp
  WHERE rp.role_id = r.id AND rp.permission = 'organizations:write'
)
AND NOT EXISTS (
  SELECT 1 FROM role_permissions rp2
  WHERE rp2.role_id = r.id AND rp2.permission = 'events:read'
)
    """,
    """
INSERT INTO role_permissions (role_id, permission, organization_id)
SELECT r.id, 'events:write', r.organization_id
FROM roles r
WHERE EXISTS (
  SELECT 1 FROM role_permissions rp
  WHERE rp.role_id = r.id AND rp.permission = 'organizations:write'
)
AND NOT EXISTS (
  SELECT 1 FROM role_permissions rp2
  WHERE rp2.role_id = r.id AND rp2.permission = 'events:write'
)
    """,
)


def _backfill_permisos_de_eventos() -> None:
    for sentencia in _BACKFILL_EVENTS:
        op.execute(sentencia)


def downgrade() -> None:
    # `downgrade()` es destructivo a partir de aquí: borra las filas de permisos
    # que el propio `upgrade` insertó y, al final, las tablas enteras con sus
    # datos. Válido para revertir un despliegue fallido antes de que existan
    # eventos reales — no para producción con datos.
    op.execute(
        "DELETE FROM role_permissions WHERE permission IN ('events:read', 'events:write') "
        "AND role_id IN ("
        "  SELECT r.id FROM roles r "
        "  JOIN role_permissions rp ON rp.role_id = r.id AND rp.permission = 'organizations:write'"
        ")"
    )

    for tabla in reversed(TABLAS_NUEVAS):
        op.execute(f"DROP POLICY IF EXISTS tenant_{tabla} ON {tabla}")
        op.execute(f"ALTER TABLE {tabla} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {tabla} DISABLE ROW LEVEL SECURITY")

    op.drop_index(op.f("ix_speaker_public_profiles_user_id"), table_name="speaker_public_profiles")
    op.drop_index(
        op.f("ix_speaker_public_profiles_organization_id"), table_name="speaker_public_profiles"
    )
    op.drop_table("speaker_public_profiles")

    op.drop_index(
        op.f("ix_event_session_participants_event_member_id"),
        table_name="event_session_participants",
    )
    op.drop_index(
        op.f("ix_event_session_participants_session_id"), table_name="event_session_participants"
    )
    op.drop_table("event_session_participants")

    op.drop_index(op.f("ix_event_members_organization_member_id"), table_name="event_members")
    op.drop_index(op.f("ix_event_members_event_id"), table_name="event_members")
    op.drop_table("event_members")

    op.drop_index(op.f("ix_event_sessions_event_id"), table_name="event_sessions")
    op.drop_table("event_sessions")

    op.drop_index(op.f("ix_events_organization_id"), table_name="events")
    op.drop_table("events")
