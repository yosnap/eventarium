"""patrocinadores, legal y auditoría

Fase 5 del PRD, fase 1 de trabajo. Cuatro tablas nuevas y columnas legales en
`organizations`.

`sponsor_tiers` (niveles, por organización) y `sponsors` (patrocinadores
concretos, por evento) siguen el mismo patrón de FK **compuestas** contra
`(id, organization_id)` del padre que `event_sessions`/`event_tickets`.
`sponsor_tiers` necesita además `UNIQUE(id, organization_id)` — sin esa
constraint la FK compuesta de `sponsors` no puede crearse, PostgreSQL exige un
índice único exacto sobre las columnas referenciadas.

`audit_log` y `cookie_consents` son tablas de instalación (no de dominio): sin
política RLS, pero **tampoco** con el acceso por defecto que `app_user`
recibiría de otro modo vía `ALTER DEFAULT PRIVILEGES`
(`infra/postgres/sql/roles.sql:45,50-51`). El `REVOKE ALL ... FROM app_user`
de abajo es la corrección de red-team más importante de esta fase (hallazgo
#1 del plan): sin él, cualquier sesión de organización podría leer y
**borrar** el registro de auditoría completo de la instalación. `INSERT` se
devuelve puntualmente sobre `cookie_consents` porque el endpoint público de
la fase 3 de trabajo escribe ahí sin autenticar.

`cookie_consents` no tiene `user_id` ni ningún campo de IP o su hash
(decisión #3 del plan): un hash de IP sin sal es reversible por fuerza bruta,
no es anonimización real, y `(organization_id, categorías, timestamp)` ya
basta para probar que se pidió consentimiento.

Backfill de `sponsors:read`/`sponsors:write` a roles existentes con
`organizations:write` (`WHERE NOT EXISTS`, idempotente) — cubre
organizaciones creadas **antes** de esta migración. Las creadas después se
cubren actualizando la plantilla `ORGANIZER` en
`app/modules/roles/system_roles.py` (`OWNER` ya los recibe vía
`tuple(Permission)`).

Revision ID: 0012_patrocinio_legal_auditoria
Revises: 0011_entradas_qr
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0012_patrocinio_legal_auditoria"
down_revision: str | None = "0011_entradas_qr"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Solo las de dominio (con RLS); `audit_log`/`cookie_consents` se comprueban
# aparte porque su comprobación de privilegios es negativa, no positiva.
TABLAS_DE_DOMINIO = (
    "sponsor_tiers",
    "sponsors",
)

TABLAS_DE_INSTALACION = (
    "audit_log",
    "cookie_consents",
)

ORGANIZATION_LEGAL_COLUMNS = (
    "legal_address",
    "tax_id",
    "legal_notice_content",
    "privacy_policy_content",
    "cookies_policy_content",
    "registration_terms_content",
)


def upgrade() -> None:
    _crear_tablas()
    _anadir_columnas_legales_de_organizacion()
    _verificar_privilegios_de_app_user()
    _activar_rls_de_dominio()
    _restringir_tablas_de_instalacion()
    _backfill_permisos_de_patrocinadores()


def _crear_tablas() -> None:
    op.create_table(
        "sponsor_tiers",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        # large | medium | small
        sa.Column("logo_size", sa.String(length=20), nullable=False, server_default="medium"),
        sa.Column("benefits", sa.Text(), nullable=True),
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
            name="fk_sponsor_tiers_organization_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sponsor_tiers")),
        sa.UniqueConstraint(
            "organization_id", "name", name="uq_sponsor_tiers_organization_id_name"
        ),
        # Obligatoria para que la FK compuesta de `sponsors` pueda crearse.
        sa.UniqueConstraint("id", "organization_id", name="uq_sponsor_tiers_id_organization_id"),
    )
    op.create_index(
        op.f("ix_sponsor_tiers_organization_id"), "sponsor_tiers", ["organization_id"], unique=False
    )

    op.create_table(
        "sponsors",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("event_id", sa.UUID(), nullable=False),
        sa.Column("tier_id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("logo_object_key", sa.String(length=500), nullable=True),
        sa.Column("website", sa.String(length=300), nullable=True),
        # monetaria | en_especie
        sa.Column("contribution_type", sa.String(length=20), nullable=False),
        sa.Column("contribution_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("contribution_description", sa.Text(), nullable=True),
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
            name="fk_sponsors_event_id_organization_id",
            ondelete="CASCADE",
        ),
        # `RESTRICT` (por defecto, sin `ondelete`): no se puede borrar un nivel
        # con patrocinadores activos, el organizador debe reasignarlos antes.
        sa.ForeignKeyConstraint(
            ["tier_id", "organization_id"],
            ["sponsor_tiers.id", "sponsor_tiers.organization_id"],
            name="fk_sponsors_tier_id_organization_id",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sponsors")),
        sa.UniqueConstraint("id", "organization_id", name="uq_sponsors_id_organization_id"),
    )
    op.create_index(op.f("ix_sponsors_event_id"), "sponsors", ["event_id"], unique=False)
    op.create_index(op.f("ix_sponsors_tier_id"), "sponsors", ["tier_id"], unique=False)
    op.create_index(
        op.f("ix_sponsors_organization_id"), "sponsors", ["organization_id"], unique=False
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.UUID(), nullable=False),
        # `SET NULL`, nunca `CASCADE`: conserva la fila de auditoría aunque el
        # usuario actor se borre después (p. ej. barrido de cuentas no
        # verificadas); borrar en cascada destruiría la propia prueba de
        # auditoría.
        sa.Column("actor_user_id", sa.UUID(), nullable=True),
        # Sin FK: `organization_id` es solo un filtro de consulta, nunca debe
        # arrastrar el borrado de una organización a su propio registro de
        # auditoría.
        sa.Column("organization_id", sa.UUID(), nullable=True),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("entity_type", sa.String(length=80), nullable=False),
        sa.Column("entity_id", sa.String(length=80), nullable=True),
        sa.Column("detail", JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name="fk_audit_log_actor_user_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_log")),
    )
    op.create_index(
        op.f("ix_audit_log_organization_id"), "audit_log", ["organization_id"], unique=False
    )
    op.create_index(op.f("ix_audit_log_action"), "audit_log", ["action"], unique=False)
    op.create_index(op.f("ix_audit_log_created_at"), "audit_log", ["created_at"], unique=False)

    op.create_table(
        "cookie_consents",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        # Lista de categorías aceptadas (`necessary` siempre incluida por el
        # propio banner, `analytics`/`marketing` opcionales). Sin `user_id`,
        # sin email, sin IP ni hash de IP en ninguna forma (decisión #3 del
        # plan) — no añadir ninguno de esos campos a futuro: un hash de IP sin
        # sal es reversible por fuerza bruta y reintroduce justo el problema
        # que este diseño evita a propósito.
        sa.Column("categories_accepted", JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_cookie_consents_organization_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cookie_consents")),
    )
    op.create_index(
        op.f("ix_cookie_consents_organization_id"),
        "cookie_consents",
        ["organization_id"],
        unique=False,
    )


def _anadir_columnas_legales_de_organizacion() -> None:
    op.add_column("organizations", sa.Column("legal_address", sa.Text(), nullable=True))
    op.add_column("organizations", sa.Column("tax_id", sa.String(length=40), nullable=True))
    # `NULL` significa "usar la plantilla por defecto" (decisión #2 del plan):
    # texto plano/Markdown restringido, nunca HTML crudo ni motor de
    # plantillas nuevo.
    op.add_column("organizations", sa.Column("legal_notice_content", sa.Text(), nullable=True))
    op.add_column("organizations", sa.Column("privacy_policy_content", sa.Text(), nullable=True))
    op.add_column("organizations", sa.Column("cookies_policy_content", sa.Text(), nullable=True))
    op.add_column(
        "organizations", sa.Column("registration_terms_content", sa.Text(), nullable=True)
    )


def _verificar_privilegios_de_app_user() -> None:
    """Mismo patrón que `0002_esquema_base`/`0011`: falla aquí, no en runtime."""
    conexion = op.get_bind()
    for tabla in TABLAS_DE_DOMINIO:
        concedido = conexion.execute(
            sa.text("SELECT has_table_privilege('app_user', :tabla, 'SELECT')"),
            {"tabla": tabla},
        ).scalar()
        if not concedido:
            raise RuntimeError(
                f"El rol «app_user» no tiene SELECT sobre «{tabla}». Ejecuta "
                "infra/scripts/ensure-roles.sh para aplicar ALTER DEFAULT PRIVILEGES."
            )


def _activar_rls_de_dominio() -> None:
    for tabla in TABLAS_DE_DOMINIO:
        op.execute(f"ALTER TABLE {tabla} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {tabla} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_{tabla} ON {tabla} "
            "USING (organization_id = app_current_organization()) "
            "WITH CHECK (organization_id = app_current_organization())"
        )


def _restringir_tablas_de_instalacion() -> None:
    """`audit_log`/`cookie_consents` no llevan RLS, pero eso no es "sin
    acceso": `ALTER DEFAULT PRIVILEGES` (`infra/postgres/sql/roles.sql`)
    concede SELECT/INSERT/UPDATE/DELETE a `app_user` sobre toda tabla nueva
    automáticamente. Sin este `REVOKE`, cualquier sesión de organización
    podría leer y borrar el registro de auditoría completo de la instalación
    (hallazgo #1 del red-team)."""
    for tabla in TABLAS_DE_INSTALACION:
        op.execute(f"REVOKE ALL ON {tabla} FROM app_user")
    # El endpoint público de consentimiento (fase 3 de trabajo) escribe desde
    # una sesión `app_user` sin autenticar.
    op.execute("GRANT INSERT ON cookie_consents TO app_user")


# Ancla al permiso, no al nombre del rol (mismo criterio que `0011`): un rol a
# medida con `organizations:write` también necesita `sponsors:*`, exista o no
# con la clave `owner`/`organizer`.
_BACKFILL_SPONSORS = (
    """
INSERT INTO role_permissions (role_id, permission, organization_id)
SELECT r.id, 'sponsors:read', r.organization_id
FROM roles r
WHERE EXISTS (
  SELECT 1 FROM role_permissions rp
  WHERE rp.role_id = r.id AND rp.permission = 'organizations:write'
)
AND NOT EXISTS (
  SELECT 1 FROM role_permissions rp2
  WHERE rp2.role_id = r.id AND rp2.permission = 'sponsors:read'
)
    """,
    """
INSERT INTO role_permissions (role_id, permission, organization_id)
SELECT r.id, 'sponsors:write', r.organization_id
FROM roles r
WHERE EXISTS (
  SELECT 1 FROM role_permissions rp
  WHERE rp.role_id = r.id AND rp.permission = 'organizations:write'
)
AND NOT EXISTS (
  SELECT 1 FROM role_permissions rp2
  WHERE rp2.role_id = r.id AND rp2.permission = 'sponsors:write'
)
    """,
)


def _backfill_permisos_de_patrocinadores() -> None:
    for sentencia in _BACKFILL_SPONSORS:
        op.execute(sentencia)


def downgrade() -> None:
    # `downgrade()` es destructivo a partir de aquí: borra las filas de
    # permisos que el propio `upgrade` insertó y, al final, las tablas
    # enteras con sus datos. Válido para revertir un despliegue fallido antes
    # de que existan datos reales — no para producción con datos.
    op.execute(
        "DELETE FROM role_permissions "
        "WHERE permission IN ('sponsors:read', 'sponsors:write') "
        "AND role_id IN ("
        "  SELECT r.id FROM roles r "
        "  WHERE EXISTS ("
        "    SELECT 1 FROM role_permissions rp "
        "    WHERE rp.role_id = r.id AND rp.permission = 'organizations:write'"
        "  )"
        ")"
    )

    for tabla in reversed(TABLAS_DE_DOMINIO):
        op.execute(f"DROP POLICY IF EXISTS tenant_{tabla} ON {tabla}")
        op.execute(f"ALTER TABLE {tabla} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {tabla} DISABLE ROW LEVEL SECURITY")

    for columna in reversed(ORGANIZATION_LEGAL_COLUMNS):
        op.drop_column("organizations", columna)

    op.drop_index(op.f("ix_cookie_consents_organization_id"), table_name="cookie_consents")
    op.drop_table("cookie_consents")

    op.drop_index(op.f("ix_audit_log_created_at"), table_name="audit_log")
    op.drop_index(op.f("ix_audit_log_action"), table_name="audit_log")
    op.drop_index(op.f("ix_audit_log_organization_id"), table_name="audit_log")
    op.drop_table("audit_log")

    op.drop_index(op.f("ix_sponsors_organization_id"), table_name="sponsors")
    op.drop_index(op.f("ix_sponsors_tier_id"), table_name="sponsors")
    op.drop_index(op.f("ix_sponsors_event_id"), table_name="sponsors")
    op.drop_table("sponsors")

    op.drop_index(op.f("ix_sponsor_tiers_organization_id"), table_name="sponsor_tiers")
    op.drop_table("sponsor_tiers")
