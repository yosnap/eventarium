"""inscripción de asistentes

Fase 3 del PRD. Cuatro tablas nuevas (`event_registration_questions`,
`event_registrations`, `event_registration_answers`,
`event_registration_consents`), con el mismo patrón de FK **compuestas** contra
`(id, organization_id)` del padre y RLS que `0009_eventos_agenda_y_ponentes`.
Backfill de `registrations:read`/`registrations:write` para todo rol que ya
tenga `organizations:write` — mismo criterio que usó `0009` para `events:*`.

Los tokens de verificación de email y de cancelación no viven en estas tablas:
son opacos y de un solo uso, y ese mecanismo ya existe en Redis
(`app/modules/auth/verification.py`). `event_registrations` no lleva ninguna
columna de token.

Revision ID: 0010_inscripcion_de_asistentes
Revises: 0009_eventos_agenda_y_ponentes
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0010_inscripcion_de_asistentes"
down_revision: str | None = "0009_eventos_agenda_y_ponentes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLAS_NUEVAS = (
    "event_registration_questions",
    "event_registrations",
    "event_registration_answers",
    "event_registration_consents",
)


def upgrade() -> None:
    _crear_tablas()
    _verificar_privilegios_de_app_user()
    _activar_rls()
    _backfill_permisos_de_inscripciones()


def _crear_tablas() -> None:
    op.create_table(
        "event_registration_questions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("event_id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("label", sa.String(length=300), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("options", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
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
            name="fk_event_registration_questions_event_id_organization_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_event_registration_questions")),
        sa.UniqueConstraint(
            "id", "organization_id", name="uq_event_registration_questions_id_organization_id"
        ),
        # `options IS NOT NULL` explícito: sin él, con `options` en NULL de SQL
        # de verdad, `jsonb_typeof(options) = 'array'` se evalúa a
        # desconocido (NULL) en vez de falso, y un CHECK que da NULL se trata
        # como satisfecho — dejaría pasar una pregunta de opción sin opciones.
        sa.CheckConstraint(
            "(type = 'short_text' AND options IS NULL) "
            "OR (type IN ('single_choice', 'multiple_choice') "
            "AND options IS NOT NULL "
            "AND jsonb_typeof(options) = 'array' AND jsonb_array_length(options) > 0)",
            name="ck_event_registration_questions_options_por_tipo",
        ),
    )
    op.create_index(
        op.f("ix_event_registration_questions_event_id"),
        "event_registration_questions",
        ["event_id"],
        unique=False,
    )

    op.create_table(
        "event_registrations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("event_id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("waitlist_position", sa.Integer(), nullable=True),
        sa.Column("waitlist_promoted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("waitlist_promotion_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
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
            name="fk_event_registrations_event_id_organization_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_event_registrations_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_event_registrations")),
        sa.UniqueConstraint("event_id", "email", name="uq_event_registrations_event_id_email"),
        sa.UniqueConstraint(
            "id", "organization_id", name="uq_event_registrations_id_organization_id"
        ),
    )
    op.create_index(
        "ix_event_registrations_event_id_status",
        "event_registrations",
        ["event_id", "status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_event_registrations_user_id"), "event_registrations", ["user_id"], unique=False
    )

    op.create_table(
        "event_registration_answers",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("registration_id", sa.UUID(), nullable=False),
        sa.Column("question_id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
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
            ["registration_id", "organization_id"],
            ["event_registrations.id", "event_registrations.organization_id"],
            name="fk_event_registration_answers_registration_id_organization_id",
            ondelete="CASCADE",
        ),
        # Sin `ondelete`: RESTRICT por defecto, mismo patrón que
        # `event_session_participants.event_member_id` en la fase 2 del PRD.
        # Borrar una pregunta con respuestas asociadas se rechaza a nivel de base
        # de datos como último cinturón de seguridad; el servicio ya lo comprueba
        # antes y responde 409.
        sa.ForeignKeyConstraint(
            ["question_id", "organization_id"],
            ["event_registration_questions.id", "event_registration_questions.organization_id"],
            name="fk_event_registration_answers_question_id_organization_id",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_event_registration_answers")),
        sa.UniqueConstraint(
            "registration_id",
            "question_id",
            name="uq_event_registration_answers_registration_id_question_id",
        ),
    )
    op.create_index(
        op.f("ix_event_registration_answers_registration_id"),
        "event_registration_answers",
        ["registration_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_event_registration_answers_question_id"),
        "event_registration_answers",
        ["question_id"],
        unique=False,
    )

    op.create_table(
        "event_registration_consents",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("registration_id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("data_processing_accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("marketing_accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recording_accepted_at", sa.DateTime(timezone=True), nullable=True),
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
            ["registration_id", "organization_id"],
            ["event_registrations.id", "event_registrations.organization_id"],
            name="fk_event_registration_consents_registration_id_organization_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_event_registration_consents")),
        sa.UniqueConstraint(
            "registration_id", name="uq_event_registration_consents_registration_id"
        ),
    )
    op.create_index(
        op.f("ix_event_registration_consents_registration_id"),
        "event_registration_consents",
        ["registration_id"],
        unique=False,
    )


def _verificar_privilegios_de_app_user() -> None:
    """Mismo patrón que `0002_esquema_base`/`0009`: falla aquí, no en runtime."""
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
# también necesita `registrations:*`, exista o no con la clave `owner`/`organizer`.
_BACKFILL_REGISTRATIONS = (
    """
INSERT INTO role_permissions (role_id, permission, organization_id)
SELECT r.id, 'registrations:read', r.organization_id
FROM roles r
WHERE EXISTS (
  SELECT 1 FROM role_permissions rp
  WHERE rp.role_id = r.id AND rp.permission = 'organizations:write'
)
AND NOT EXISTS (
  SELECT 1 FROM role_permissions rp2
  WHERE rp2.role_id = r.id AND rp2.permission = 'registrations:read'
)
    """,
    """
INSERT INTO role_permissions (role_id, permission, organization_id)
SELECT r.id, 'registrations:write', r.organization_id
FROM roles r
WHERE EXISTS (
  SELECT 1 FROM role_permissions rp
  WHERE rp.role_id = r.id AND rp.permission = 'organizations:write'
)
AND NOT EXISTS (
  SELECT 1 FROM role_permissions rp2
  WHERE rp2.role_id = r.id AND rp2.permission = 'registrations:write'
)
    """,
)


def _backfill_permisos_de_inscripciones() -> None:
    for sentencia in _BACKFILL_REGISTRATIONS:
        op.execute(sentencia)


def downgrade() -> None:
    # `downgrade()` es destructivo a partir de aquí: borra las filas de permisos
    # que el propio `upgrade` insertó y, al final, las tablas enteras con sus
    # datos. Válido para revertir un despliegue fallido antes de que existan
    # inscripciones reales — no para producción con datos.
    op.execute(
        "DELETE FROM role_permissions "
        "WHERE permission IN ('registrations:read', 'registrations:write') "
        "AND role_id IN ("
        "  SELECT r.id FROM roles r "
        "  JOIN role_permissions rp ON rp.role_id = r.id AND rp.permission = 'organizations:write'"
        ")"
    )

    for tabla in reversed(TABLAS_NUEVAS):
        op.execute(f"DROP POLICY IF EXISTS tenant_{tabla} ON {tabla}")
        op.execute(f"ALTER TABLE {tabla} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {tabla} DISABLE ROW LEVEL SECURITY")

    op.drop_index(
        op.f("ix_event_registration_consents_registration_id"),
        table_name="event_registration_consents",
    )
    op.drop_table("event_registration_consents")

    op.drop_index(
        op.f("ix_event_registration_answers_question_id"), table_name="event_registration_answers"
    )
    op.drop_index(
        op.f("ix_event_registration_answers_registration_id"),
        table_name="event_registration_answers",
    )
    op.drop_table("event_registration_answers")

    op.drop_index(op.f("ix_event_registrations_user_id"), table_name="event_registrations")
    op.drop_index("ix_event_registrations_event_id_status", table_name="event_registrations")
    op.drop_table("event_registrations")

    op.drop_index(
        op.f("ix_event_registration_questions_event_id"),
        table_name="event_registration_questions",
    )
    op.drop_table("event_registration_questions")
