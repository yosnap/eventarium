"""políticas y condiciones propias de cada organizador

Una tabla de versiones inmutables y dos columnas nuevas en el consentimiento
de inscripción.

- `organization_policy_versions`: cada guardado de un texto (condiciones,
  reembolsos, privacidad u otras) es una fila nueva; nunca se reescribe una
  anterior, porque hay inscripciones que aceptaron versiones concretas y el
  organizador tiene que poder probar qué decía cada una. `event_id` nulo es
  el texto por defecto de la organización; con evento, es su sustitución.
  `content` nulo solo se admite en filas de evento y significa «vuelve a
  heredar el de la organización»; `''` en una fila de organización significa
  «retirado».

  Inmutable de verdad, no por convención: `ALTER DEFAULT PRIVILEGES` concede
  a `app_user` `INSERT`, `UPDATE` y `DELETE` sobre toda tabla nueva (ver
  `0022_identidad_plataforma`), así que aquí se revocan `UPDATE` y `DELETE`
  explícitamente y se comprueba que la revocación ha surtido efecto. Las
  filas solo desaparecen en cascada con su evento o su organización.

- `event_registration_consents` gana la fecha en que se aceptaron las
  políticas del organizador y la lista exacta de versiones aceptadas. La
  lista no lleva clave foránea (un array no puede tenerla): basta con que las
  versiones nunca se borren, y las que se borran en cascada arrastran también
  las inscripciones de ese evento u organización.

`downgrade` borra la tabla y las columnas: solo es seguro mientras no haya
inscripciones con políticas aceptadas; después destruye la prueba de
aceptación y requiere backup y una decisión explícita.

Revision ID: 0053_politicas_organizador
Revises: 0052_mis_eventos_acceso
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0053_politicas_organizador"
down_revision: str | None = "0052_mis_eventos_acceso"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLA = "organization_policy_versions"

#: Espejo de `policies.models.TIPOS_DE_POLITICA`.
_TIPOS = ("condiciones", "otras", "privacidad", "reembolsos")


def upgrade() -> None:
    tipos = ", ".join(f"'{tipo}'" for tipo in _TIPOS)
    op.create_table(
        _TABLA,
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_organization_policy_versions_organization_id",
            ondelete="CASCADE",
        ),
        # Compuesta: sin ella, una fila podría apuntar a un evento de otra
        # organización (la FK no pasa por RLS).
        sa.ForeignKeyConstraint(
            ["event_id", "organization_id"],
            ["events.id", "events.organization_id"],
            name="fk_organization_policy_versions_event_id_organization_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_organization_policy_versions_created_by",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(f"kind IN ({tipos})", name="ck_organization_policy_versions_kind"),
        sa.CheckConstraint(
            "event_id IS NOT NULL OR content IS NOT NULL",
            name="ck_organization_policy_versions_contenido_de_organizacion",
        ),
        # Un texto propio de evento nunca es `''`: solo hay «texto propio» o
        # «heredar» (`NULL`). Sin esto, una tercera semántica quedaría grabada
        # para siempre en una tabla que no admite UPDATE.
        sa.CheckConstraint(
            "event_id IS NULL OR content IS NULL OR content <> ''",
            name="ck_organization_policy_versions_texto_de_evento",
        ),
        sa.CheckConstraint("version >= 1", name="ck_organization_policy_versions_version"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organization_policy_versions")),
    )
    # `NULLS NOT DISTINCT` (Postgres 15+; local y producción usan 16): sin él,
    # dos filas de organización (`event_id` nulo) con la misma versión no
    # chocarían y el número de versión dejaría de ser único. Sirve también de
    # índice de lectura: la última versión por `(organización, evento, tipo)`
    # se recorre en sentido inverso sobre él.
    op.execute(
        f"CREATE UNIQUE INDEX uq_organization_policy_versions_version ON {_TABLA} "
        "(organization_id, event_id, kind, version) NULLS NOT DISTINCT"
    )

    op.add_column(
        "event_registration_consents",
        sa.Column("organizer_policies_accepted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "event_registration_consents",
        sa.Column(
            "accepted_policy_version_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
    )

    op.execute(f"REVOKE UPDATE, DELETE ON {_TABLA} FROM app_user")
    _verificar_privilegios_de_app_user()

    op.execute(f"ALTER TABLE {_TABLA} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {_TABLA} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_{_TABLA} ON {_TABLA} "
        "USING (organization_id = app_current_organization()) "
        "WITH CHECK (organization_id = app_current_organization())"
    )


def _verificar_privilegios_de_app_user() -> None:
    """Falla aquí, no en runtime: `SELECT` e `INSERT` sí; `UPDATE` y `DELETE` no."""
    conexion = op.get_bind()
    esperados = {"SELECT": True, "INSERT": True, "UPDATE": False, "DELETE": False}
    for privilegio, debe_tenerlo in esperados.items():
        concedido = conexion.execute(
            sa.text("SELECT has_table_privilege('app_user', :tabla, :privilegio)"),
            {"tabla": _TABLA, "privilegio": privilegio},
        ).scalar()
        if bool(concedido) != debe_tenerlo:
            estado = "no tiene" if debe_tenerlo else "conserva"
            raise RuntimeError(
                f"El rol «app_user» {estado} {privilegio} sobre «{_TABLA}». "
                "Revisa infra/scripts/ensure-roles.sh y los privilegios por defecto."
            )


def downgrade() -> None:
    op.execute(f"DROP POLICY IF EXISTS tenant_{_TABLA} ON {_TABLA}")
    op.drop_column("event_registration_consents", "accepted_policy_version_ids")
    op.drop_column("event_registration_consents", "organizer_policies_accepted_at")
    op.execute("DROP INDEX IF EXISTS uq_organization_policy_versions_version")
    op.drop_table(_TABLA)
