"""invitaciones de equipo

Fase 1 del plan de invitaciones (plan.md). Tabla `organization_invitations`:
guarda **estado**, nunca el token — el token de un solo uso va a Redis
(`auth/verification.py`, `PROPOSITO_INVITACION`), con el `id` de esta fila
como payload.

`role_id` con `ON DELETE CASCADE`: borrar un rol cancela (borra) las
invitaciones pendientes que apuntaban a él, coherente con que un rol borrado
no debería poder concederse.

`event_id` con FK **compuesta** contra `(id, organization_id)` de `events`,
mismo patrón que `event_members` (`0009`): nulo para una invitación de
equipo, relleno cuando nace desde un evento (fase 3).

`accepted_by_user_id`/`invited_by_user_id` con `ON DELETE SET NULL`, mismo
patrón que `audit_log.actor_user_id`/`subject_user_id` (`0012`, `0023`): la
fila se conserva por trazabilidad aunque la persona se borre.

`token_hash` guarda la huella (SHA-256) del token vigente en Redis, no el
token — igual que `users.password_hash` no es la contraseña. Sirve para que
reenviar una invitación pueda revocar el enlace anterior por su huella sin
haber guardado nunca el token en claro.

`estado` solo admite lo que no se deduce (`pendiente`, `aceptada`,
`revocada`): «caducada» se calcula al leer comparando `expires_at`
(`invitations_service.estado_efectivo`), no se escribe.

Revision ID: 0027_invitaciones_de_equipo
Revises: 0026_permiso_de_invitaciones
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0027_invitaciones_de_equipo"
down_revision: str | None = "0026_permiso_de_invitaciones"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLA = "organization_invitations"


def upgrade() -> None:
    _crear_tabla()
    _verificar_privilegios_de_app_user()
    _activar_rls()


def _crear_tabla() -> None:
    op.create_table(
        _TABLA,
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("role_id", sa.UUID(), nullable=False),
        sa.Column("event_id", sa.UUID(), nullable=True),
        sa.Column("estado", sa.String(length=20), nullable=False, server_default="pendiente"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_by_user_id", sa.UUID(), nullable=True),
        sa.Column("invited_by_user_id", sa.UUID(), nullable=True),
        sa.Column("token_hash", sa.String(length=64), nullable=True),
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
            name="fk_organization_invitations_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["roles.id"],
            name="fk_organization_invitations_role_id_roles",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["event_id", "organization_id"],
            ["events.id", "events.organization_id"],
            name="fk_organization_invitations_event_id_organization_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["accepted_by_user_id"],
            ["users.id"],
            name="fk_organization_invitations_accepted_by_user_id_users",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["invited_by_user_id"],
            ["users.id"],
            name="fk_organization_invitations_invited_by_user_id_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organization_invitations")),
        sa.CheckConstraint(
            "estado IN ('pendiente', 'aceptada', 'revocada')",
            name="ck_organization_invitations_estado",
        ),
    )
    op.create_index(
        op.f("ix_organization_invitations_organization_id"),
        _TABLA,
        ["organization_id"],
        unique=False,
    )
    op.create_index(op.f("ix_organization_invitations_role_id"), _TABLA, ["role_id"], unique=False)
    op.create_index(
        op.f("ix_organization_invitations_event_id"), _TABLA, ["event_id"], unique=False
    )


def _verificar_privilegios_de_app_user() -> None:
    """Mismo patrón que `0012`/`0013`/`0020`: falla aquí, no en runtime."""
    conexion = op.get_bind()
    concedido = conexion.execute(
        sa.text("SELECT has_table_privilege('app_user', :tabla, 'SELECT')"),
        {"tabla": _TABLA},
    ).scalar()
    if not concedido:
        raise RuntimeError(
            f"El rol «app_user» no tiene SELECT sobre «{_TABLA}». Ejecuta "
            "infra/scripts/ensure-roles.sh para aplicar ALTER DEFAULT PRIVILEGES."
        )


def _activar_rls() -> None:
    op.execute(f"ALTER TABLE {_TABLA} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {_TABLA} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_{_TABLA} ON {_TABLA} "
        "USING (organization_id = app_current_organization()) "
        "WITH CHECK (organization_id = app_current_organization())"
    )


def downgrade() -> None:
    op.execute(f"DROP POLICY IF EXISTS tenant_{_TABLA} ON {_TABLA}")
    op.execute(f"ALTER TABLE {_TABLA} NO FORCE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {_TABLA} DISABLE ROW LEVEL SECURITY")

    op.drop_index(op.f("ix_organization_invitations_event_id"), table_name=_TABLA)
    op.drop_index(op.f("ix_organization_invitations_role_id"), table_name=_TABLA)
    op.drop_index(op.f("ix_organization_invitations_organization_id"), table_name=_TABLA)
    op.drop_table(_TABLA)
