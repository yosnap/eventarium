"""sedes múltiples de evento

Fase de sedes múltiples por evento (varios días, varias salas/sedes, cada una
con su propio aforo). Tabla nueva `event_venues`, misma FK compuesta contra
`(id, organization_id)` del padre que ya usa `event_sessions` y RLS con el
mismo patrón que `0009_eventos_agenda_y_ponentes`.

`event_sessions.venue_id` es el nivel superior a `room` (que sigue siendo
texto libre, la sala dentro de la sede): nullable, para que un evento de una
sola sede no necesite asignar sede a cada sesión.

`events.latitude`/`longitude`/`geocoded_at`: mismo mecanismo de
dirección+geocodificación (Nominatim) que `event_venues`, aplicado a la
ubicación simple de un evento de una sola sede (`events.location_address`).

Revision ID: 0017_sedes_multiples_de_evento
Revises: 0016_ciudad_de_evento
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0017_sedes_multiples_de_evento"
down_revision: str | None = "0016_ciudad_de_evento"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    _crear_tabla_event_venues()
    _anadir_columnas_de_geocodificacion_a_events()
    _anadir_venue_id_a_event_sessions()
    _verificar_privilegios_de_app_user()
    _activar_rls()


def _crear_tabla_event_venues() -> None:
    op.create_table(
        "event_venues",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("event_id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("address", sa.String(length=300), nullable=True),
        sa.Column("capacity", sa.Integer(), nullable=True),
        sa.Column("latitude", sa.Numeric(9, 6), nullable=True),
        sa.Column("longitude", sa.Numeric(9, 6), nullable=True),
        sa.Column("geocoded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False),
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
            name="fk_event_venues_event_id_organization_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_event_venues")),
        sa.UniqueConstraint("id", "organization_id", name="uq_event_venues_id_organization_id"),
    )
    op.create_index(op.f("ix_event_venues_event_id"), "event_venues", ["event_id"], unique=False)


def _anadir_columnas_de_geocodificacion_a_events() -> None:
    op.add_column("events", sa.Column("latitude", sa.Numeric(9, 6), nullable=True))
    op.add_column("events", sa.Column("longitude", sa.Numeric(9, 6), nullable=True))
    op.add_column(
        "events", sa.Column("geocoded_at", sa.DateTime(timezone=True), nullable=True)
    )


def _anadir_venue_id_a_event_sessions() -> None:
    op.add_column("event_sessions", sa.Column("venue_id", sa.UUID(), nullable=True))
    op.create_index(
        op.f("ix_event_sessions_venue_id"), "event_sessions", ["venue_id"], unique=False
    )
    # Sin `ondelete=CASCADE`: borrar una sede con sesiones asociadas se
    # bloquea explícitamente en `service.delete_venue` con un 409 legible.
    # `SET NULL` es la red de seguridad de base de datos para el único camino
    # que se salta esa comprobación (borrado directo con rol de mantenimiento).
    op.create_foreign_key(
        "fk_event_sessions_venue_id_organization_id",
        "event_sessions",
        "event_venues",
        ["venue_id", "organization_id"],
        ["id", "organization_id"],
        ondelete="SET NULL",
    )


def _verificar_privilegios_de_app_user() -> None:
    """Mismo patrón que `0002_esquema_base`: falla aquí, no en runtime."""
    conexion = op.get_bind()
    concedido = conexion.execute(
        sa.text("SELECT has_table_privilege('app_user', :tabla, 'SELECT')"),
        {"tabla": "event_venues"},
    ).scalar()
    if not concedido:
        raise RuntimeError(
            "El rol «app_user» no tiene SELECT sobre «event_venues». Ejecuta "
            "infra/scripts/ensure-roles.sh para aplicar ALTER DEFAULT PRIVILEGES."
        )


def _activar_rls() -> None:
    op.execute("ALTER TABLE event_venues ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE event_venues FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_event_venues ON event_venues "
        "USING (organization_id = app_current_organization()) "
        "WITH CHECK (organization_id = app_current_organization())"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_event_venues ON event_venues")
    op.execute("ALTER TABLE event_venues NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE event_venues DISABLE ROW LEVEL SECURITY")

    op.drop_constraint(
        "fk_event_sessions_venue_id_organization_id", "event_sessions", type_="foreignkey"
    )
    op.drop_index(op.f("ix_event_sessions_venue_id"), table_name="event_sessions")
    op.drop_column("event_sessions", "venue_id")

    op.drop_column("events", "geocoded_at")
    op.drop_column("events", "longitude")
    op.drop_column("events", "latitude")

    op.drop_index(op.f("ix_event_venues_event_id"), table_name="event_venues")
    op.drop_table("event_venues")
