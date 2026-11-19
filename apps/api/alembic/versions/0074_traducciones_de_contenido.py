"""Traducciones del contenido del organizador

- `content_translations`: una fila por campo traducido, con RLS por organización.
  El original sigue en su columna de siempre, así que no hay migración de datos.
  `event_id` agrupa lo que cuelga de un evento: la ficha carga sus traducciones en
  una sola consulta, y la traducción con IA trabaja evento a evento.
- `organizations.content_locales`: idiomas en que publica la organización.
- `organizations.source_locale`: idioma en que escribe la organización lo que no
  cuelga de un evento (etiquetas, tipos de sesión, niveles, políticas, perfiles).
- `events.source_locale`: idioma en que se escribe el evento.
- `event_categories.name_i18n`: nombre de cada categoría por idioma. Las categorías
  son de toda la instalación, no de una organización, y las edita el superadmin.

Revision ID: 0074_traducciones_de_contenido
Revises: 0073_idioma_de_inscripcion
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0074_traducciones_de_contenido"
down_revision: str | None = "0073_idioma_de_inscripcion"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLA = "content_translations"
_IDIOMAS = "('es-ES', 'en-US')"
_ARRAY_IDIOMAS = "ARRAY['es-ES','en-US']::varchar[]"
_TIPOS = (
    "'event', 'session', 'session_type', 'venue', 'ticket_type', 'question', "
    "'sponsor_tier', 'sponsor', 'member_profile', 'organization', 'policy_version', "
    "'nearby_place', 'tag'"
)
#: Tablas cuyas filas tienen traducciones propias (espejo de `campos.TABLAS`).
_TABLAS_TRADUCIBLES = {
    "session": "event_sessions",
    "session_type": "session_types",
    "venue": "event_venues",
    "ticket_type": "event_ticket_types",
    "question": "event_registration_questions",
    "sponsor_tier": "sponsor_tiers",
    "sponsor": "sponsors",
    "member_profile": "organization_members",
    "policy_version": "organization_policy_versions",
    "nearby_place": "event_nearby_places",
}


def upgrade() -> None:
    op.create_table(
        _TABLA,
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("event_id", sa.UUID(), nullable=True),
        sa.Column("entity_type", sa.String(30), nullable=False),
        sa.Column("entity_id", sa.UUID(), nullable=False),
        sa.Column("field", sa.String(200), nullable=False),
        sa.Column("locale", sa.String(10), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("origin", sa.String(10), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("retry_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
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
            name="fk_content_translations_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["event_id", "organization_id"],
            ["events.id", "events.organization_id"],
            name="fk_content_translations_event_id_organization_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["users.id"],
            name="fk_content_translations_updated_by_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_content_translations"),
        sa.UniqueConstraint(
            "organization_id",
            "entity_type",
            "entity_id",
            "field",
            "locale",
            name="uq_content_translations_campo",
        ),
        sa.CheckConstraint(f"entity_type IN ({_TIPOS})", name="entity_type"),
        sa.CheckConstraint(f"locale IN {_IDIOMAS}", name="locale"),
        sa.CheckConstraint("origin IN ('ia', 'manual', 'revisada')", name="origin"),
        sa.CheckConstraint(
            "status IN ('pendiente', 'en_curso', 'al_dia', 'error', 'desactualizada')",
            name="status",
        ),
        sa.CheckConstraint("error_count >= 0", name="error_count"),
    )
    op.create_index(
        "ix_content_translations_evento",
        _TABLA,
        ["organization_id", "event_id", "locale"],
    )

    concedido = (
        op.get_bind()
        .execute(
            sa.text("SELECT has_table_privilege('app_user', :tabla, 'SELECT')"), {"tabla": _TABLA}
        )
        .scalar()
    )
    if not concedido:
        raise RuntimeError(
            f"El rol «app_user» no tiene SELECT sobre «{_TABLA}». Ejecuta "
            "infra/scripts/ensure-roles.sh para aplicar ALTER DEFAULT PRIVILEGES."
        )

    op.execute(f"ALTER TABLE {_TABLA} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {_TABLA} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_{_TABLA} ON {_TABLA} "
        "USING (organization_id = app_current_organization()) "
        "WITH CHECK (organization_id = app_current_organization())"
    )

    # Al borrar una fila se borran sus traducciones en la misma transacción, sin
    # depender de que cada servicio de borrado se acuerde (también la biografía de
    # un miembro que se da de baja). Corre con los permisos de quien borra: bajo
    # RLS solo alcanza a las traducciones de su propia organización.
    op.execute(
        """
        CREATE FUNCTION app_borrar_traducciones() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            DELETE FROM content_translations
            WHERE organization_id = OLD.organization_id
              AND entity_type = TG_ARGV[0]
              AND entity_id = OLD.id;
            RETURN OLD;
        END
        $$
        """
    )
    for tipo, tabla in _TABLAS_TRADUCIBLES.items():
        op.execute(
            f"CREATE TRIGGER borrar_traducciones AFTER DELETE ON {tabla} "
            f"FOR EACH ROW EXECUTE FUNCTION app_borrar_traducciones('{tipo}')"
        )

    op.add_column(
        "organizations",
        sa.Column(
            "content_locales",
            postgresql.ARRAY(sa.String(10)),
            nullable=False,
            server_default=sa.text("ARRAY['es-ES']::varchar[]"),
        ),
    )
    op.create_check_constraint(
        "content_locales",
        "organizations",
        f"cardinality(content_locales) >= 1 AND content_locales <@ {_ARRAY_IDIOMAS}",
    )
    op.add_column(
        "organizations",
        sa.Column("source_locale", sa.String(10), nullable=False, server_default="es-ES"),
    )
    op.create_check_constraint("source_locale", "organizations", f"source_locale IN {_IDIOMAS}")
    op.add_column(
        "events",
        sa.Column("source_locale", sa.String(10), nullable=False, server_default="es-ES"),
    )
    op.create_check_constraint("source_locale", "events", f"source_locale IN {_IDIOMAS}")
    op.add_column(
        "event_categories",
        sa.Column(
            "name_i18n",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("event_categories", "name_i18n")
    op.execute("ALTER TABLE events DROP CONSTRAINT IF EXISTS ck_events_source_locale")
    op.drop_column("events", "source_locale")
    op.execute("ALTER TABLE organizations DROP CONSTRAINT IF EXISTS ck_organizations_source_locale")
    op.execute("ALTER TABLE organizations DROP COLUMN IF EXISTS source_locale")
    op.execute(
        "ALTER TABLE organizations DROP CONSTRAINT IF EXISTS ck_organizations_content_locales"
    )
    op.drop_column("organizations", "content_locales")
    for tabla in _TABLAS_TRADUCIBLES.values():
        op.execute(f"DROP TRIGGER IF EXISTS borrar_traducciones ON {tabla}")
    op.execute("DROP FUNCTION IF EXISTS app_borrar_traducciones()")
    op.execute(f"DROP POLICY IF EXISTS tenant_{_TABLA} ON {_TABLA}")
    op.drop_index("ix_content_translations_evento", table_name=_TABLA)
    op.drop_table(_TABLA)
