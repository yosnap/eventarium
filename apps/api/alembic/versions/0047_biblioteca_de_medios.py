"""biblioteca de medios

Fase 1 del plan `260918-1944-biblioteca-de-medios`. Cuatro tablas nuevas:

- `media`/`media_folders` (de organización, con RLS estándar —
  `organization_id` NOT NULL siempre, sin caso "de plataforma").
- `platform_media`/`platform_media_folders` (de instalación, sin RLS,
  protegidas con `REVOKE ALL ... FROM app_user` — mismo patrón que
  `platform_branding`/`cookie_consents`/`audit_log`: solo
  `app/modules/admin` las toca, con la sesión de mantenimiento).

El red-team de este plan encontró que la versión inicial asumía un GUC
`app.is_superadmin` inexistente para proteger medios de plataforma con RLS
en la misma tabla que los de organización — el contexto de sesión solo fija
`app.organization_id`/`app.user_id` (`app/core/database.py`), así que se
separó en dos pares de tablas en vez de inventar un patrón nuevo.

`media.id`+`media.organization_id` llevan `UniqueConstraint` para que las
columnas `*_media_id` añadidas a `organization_branding`/`events`/
`sponsors` puedan usar FK **compuesta** contra `(media.id,
media.organization_id)` — igual que las FK ya existentes de estas mismas
tablas hacia otros padres (`sponsors.event_id`, `apps/api/app/modules/
sponsors/models.py`): una FK simple no impediría que una fila de la
organización A apuntara a un `media` de la organización B, porque la
integridad referencial de Postgres no pasa por RLS.

Las 4 `ADD COLUMN *_media_id` son nullable, sin backfill: las imágenes ya
subidas antes de esta migración se quedan en `NULL` y siguen su
comportamiento actual (reemplazarlas borra el objeto anterior); solo las
imágenes asignadas DESPUÉS de esta migración (subida nueva o elegida de
biblioteca) rellenan la columna.

Revision ID: 0047_biblioteca_de_medios
Revises: 0046_indice_cookie_consents
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0047_biblioteca_de_medios"
down_revision: str | None = "0046_indice_cookie_consents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLAS_DE_ORGANIZACION = ("media_folders", "media")
_TABLAS_DE_PLATAFORMA = ("platform_media_folders", "platform_media")


def upgrade() -> None:
    _crear_tablas_de_organizacion()
    _verificar_privilegios_de_app_user()
    _activar_rls()
    _crear_tablas_de_plataforma()
    _restringir_tablas_de_plataforma()
    _anadir_columnas_de_asignacion()


def _crear_tablas_de_organizacion() -> None:
    op.create_table(
        "media_folders",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
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
            name="fk_media_folders_organization_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_media_folders")),
        sa.UniqueConstraint("organization_id", "slug", name="uq_media_folders_org_slug"),
        sa.UniqueConstraint("id", "organization_id", name="uq_media_folders_id_organization_id"),
    )
    op.create_index(
        op.f("ix_media_folders_organization_id"),
        "media_folders",
        ["organization_id"],
        unique=False,
    )

    op.create_table(
        "media",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("uploaded_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("folder_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("object_key", sa.String(length=500), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("alt", sa.String(length=300), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
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
            name="fk_media_organization_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by_user_id"],
            ["users.id"],
            name="fk_media_uploaded_by_user_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["folder_id", "organization_id"],
            ["media_folders.id", "media_folders.organization_id"],
            name="fk_media_folder_id_organization_id",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_media")),
        sa.UniqueConstraint("id", "organization_id", name="uq_media_id_organization_id"),
    )
    op.create_index(op.f("ix_media_organization_id"), "media", ["organization_id"], unique=False)
    op.create_index(op.f("ix_media_kind"), "media", ["kind"], unique=False)


def _verificar_privilegios_de_app_user() -> None:
    """Mismo patrón que `0012`/`0013`/`0020`/`0027`: falla aquí, no en runtime."""
    conexion = op.get_bind()
    for tabla in _TABLAS_DE_ORGANIZACION:
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
    for tabla in _TABLAS_DE_ORGANIZACION:
        op.execute(f"ALTER TABLE {tabla} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {tabla} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_{tabla} ON {tabla} "
            "USING (organization_id = app_current_organization()) "
            "WITH CHECK (organization_id = app_current_organization())"
        )


def _crear_tablas_de_plataforma() -> None:
    op.create_table(
        "platform_media_folders",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_platform_media_folders")),
        sa.UniqueConstraint("slug", name="uq_platform_media_folders_slug"),
    )

    op.create_table(
        "platform_media",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("uploaded_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("folder_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("object_key", sa.String(length=500), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("alt", sa.String(length=300), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
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
            ["uploaded_by_user_id"],
            ["users.id"],
            name="fk_platform_media_uploaded_by_user_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["folder_id"],
            ["platform_media_folders.id"],
            name="fk_platform_media_folder_id",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_platform_media")),
    )


def _restringir_tablas_de_plataforma() -> None:
    """Mismo patrón que `platform_branding` (`0022`), no el de
    `cookie_consents`/`audit_log` (`0012`): estas dos tablas alimentan el
    logo/favicon de plataforma que `GET /tenant/branding` sirve con una
    sesión de organización normal, así que se conserva `SELECT` — solo se
    retira el DML, para que solo `app/modules/admin` (sesión de
    mantenimiento) pueda escribirlas."""
    for tabla in _TABLAS_DE_PLATAFORMA:
        op.execute(f"REVOKE INSERT, UPDATE, DELETE ON {tabla} FROM app_user")


def _anadir_columnas_de_asignacion() -> None:
    op.add_column(
        "organization_branding",
        sa.Column("logo_media_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_organization_branding_logo_media_id_organization_id",
        "organization_branding",
        "media",
        ["logo_media_id", "organization_id"],
        ["id", "organization_id"],
    )

    op.add_column(
        "events", sa.Column("cover_media_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.create_foreign_key(
        "fk_events_cover_media_id_organization_id",
        "events",
        "media",
        ["cover_media_id", "organization_id"],
        ["id", "organization_id"],
    )

    op.add_column(
        "sponsors", sa.Column("logo_media_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.create_foreign_key(
        "fk_sponsors_logo_media_id_organization_id",
        "sponsors",
        "media",
        ["logo_media_id", "organization_id"],
        ["id", "organization_id"],
    )

    op.add_column(
        "platform_branding",
        sa.Column("logo_media_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "platform_branding",
        sa.Column("favicon_media_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_platform_branding_logo_media_id",
        "platform_branding",
        "platform_media",
        ["logo_media_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_platform_branding_favicon_media_id",
        "platform_branding",
        "platform_media",
        ["favicon_media_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_platform_branding_favicon_media_id", "platform_branding", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_platform_branding_logo_media_id", "platform_branding", type_="foreignkey"
    )
    op.drop_column("platform_branding", "favicon_media_id")
    op.drop_column("platform_branding", "logo_media_id")

    op.drop_constraint("fk_sponsors_logo_media_id_organization_id", "sponsors", type_="foreignkey")
    op.drop_column("sponsors", "logo_media_id")

    op.drop_constraint("fk_events_cover_media_id_organization_id", "events", type_="foreignkey")
    op.drop_column("events", "cover_media_id")

    op.drop_constraint(
        "fk_organization_branding_logo_media_id_organization_id",
        "organization_branding",
        type_="foreignkey",
    )
    op.drop_column("organization_branding", "logo_media_id")

    op.drop_table("platform_media")
    op.drop_table("platform_media_folders")

    for tabla in reversed(_TABLAS_DE_ORGANIZACION):
        op.execute(f"DROP POLICY IF EXISTS tenant_{tabla} ON {tabla}")
        op.execute(f"ALTER TABLE {tabla} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {tabla} DISABLE ROW LEVEL SECURITY")

    op.drop_index(op.f("ix_media_kind"), table_name="media")
    op.drop_index(op.f("ix_media_organization_id"), table_name="media")
    op.drop_table("media")

    op.drop_index(op.f("ix_media_folders_organization_id"), table_name="media_folders")
    op.drop_table("media_folders")
