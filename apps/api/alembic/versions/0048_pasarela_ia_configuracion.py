"""pasarela de ia: configuracion de dos niveles y servicios

Fase 1 del plan `260911-0325-prd-pasarela-ia-multiproveedor`. Cuatro tablas:

- `platform_ai_settings` (fila única, `CHECK id = 1`) y `platform_services`:
  **de instalación**, sin `organization_id`, así que no llevan RLS de
  organización. Eso no es «sin restricción»: `ALTER DEFAULT PRIVILEGES`
  (`infra/postgres/sql/roles.sql`) concede SELECT/INSERT/UPDATE/DELETE a
  `app_user` sobre toda tabla nueva, así que sin `REVOKE` cualquier sesión de
  organización podría **borrar o sobrescribir** la clave de plataforma, el
  techo de gasto y los interruptores globales (hallazgo V-2 del red-team).
  Se aplica el mismo patrón que `0013_pagos_stripe_connect` /
  `0014_plantillas_de_tema`: `REVOKE ALL` y, encima, `GRANT SELECT`.

  El `GRANT SELECT` incluye `api_key_encrypted` a propósito: la organización
  que **hereda** la configuración y el worker de taskiq tienen que leer la
  fila de plataforma en su **misma** sesión (`SessionApp`, misma
  transacción), sin abrir una sesión de mantenimiento (V-3/V-4). Lo que se
  lee es texto cifrado; el secreto real (`AI_SETTINGS_ENCRYPTION_KEY`) vive
  fuera de la base de datos. Lo que sí queda revocado es la **escritura**.

- `organization_ai_settings` (1:1 con la organización, `CASCADE`) y
  `organization_services`: de organización, con `FORCE ROW LEVEL SECURITY` y
  `CREATE POLICY tenant_<tabla>` como el resto del esquema (`0012`, `0013`,
  `0020`).

`organization_services` solo puede **desactivar** (`CHECK enabled = false`):
volver a heredar es borrar la fila, y no existe «forzar on» — un servicio
apagado globalmente no se reactiva por organización (V-7).

Revision ID: 0048_pasarela_ia_configuracion
Revises: 0047_biblioteca_de_medios
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0048_pasarela_ia_configuracion"
down_revision: str | None = "0047_biblioteca_de_medios"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLAS_DE_ORGANIZACION = ("organization_ai_settings", "organization_services")
_TABLAS_DE_PLATAFORMA = ("platform_ai_settings", "platform_services")

#: Catálogo cerrado de servicios conmutables, igual que
#: `app/modules/ai_gateway/servicios.py`. Se siembran activos.
_SERVICIOS = ("ai",)


def upgrade() -> None:
    _crear_tablas_de_plataforma()
    _restringir_tablas_de_plataforma()
    _sembrar_servicios()
    _crear_tablas_de_organizacion()
    _verificar_privilegios_de_app_user()
    _activar_rls_de_dominio()


def _crear_tablas_de_plataforma() -> None:
    op.create_table(
        "platform_ai_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=True),
        sa.Column("default_model", sa.String(length=120), nullable=True),
        sa.Column("api_base", sa.String(length=300), nullable=True),
        sa.Column("api_key_encrypted", sa.Text(), nullable=True),
        sa.Column("api_key_hint", sa.String(length=8), nullable=True),
        sa.Column("monthly_ceiling_usd", sa.Numeric(precision=14, scale=6), nullable=True),
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
        sa.CheckConstraint("id = 1", name="ck_platform_ai_settings_fila_unica"),
        sa.CheckConstraint(
            "(provider IS NULL AND default_model IS NULL AND api_key_encrypted IS NULL) "
            "OR (provider IS NOT NULL AND default_model IS NOT NULL "
            "AND api_key_encrypted IS NOT NULL)",
            name="ck_platform_ai_settings_credencial_completa",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_platform_ai_settings")),
    )

    op.create_table(
        "platform_services",
        sa.Column("service_key", sa.String(length=40), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
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
        sa.PrimaryKeyConstraint("service_key", name=op.f("pk_platform_services")),
    )


def _restringir_tablas_de_plataforma() -> None:
    """`REVOKE ALL` + `GRANT SELECT`, con verificación (V-2).

    El `REVOKE` retira lo que `ALTER DEFAULT PRIVILEGES` concede solo; el
    `GRANT SELECT` devuelve **únicamente** la lectura, que es la que
    necesitan la organización heredera y el worker en su propia sesión.
    """
    conexion = op.get_bind()
    for tabla in _TABLAS_DE_PLATAFORMA:
        op.execute(f"REVOKE ALL ON {tabla} FROM app_user")
        op.execute(f"GRANT SELECT ON {tabla} TO app_user")

    for tabla in _TABLAS_DE_PLATAFORMA:
        for privilegio, esperado in (
            ("SELECT", True),
            ("INSERT", False),
            ("UPDATE", False),
            ("DELETE", False),
        ):
            concedido = conexion.execute(
                sa.text("SELECT has_table_privilege('app_user', :tabla, :privilegio)"),
                {"tabla": tabla, "privilegio": privilegio},
            ).scalar()
            if bool(concedido) is not esperado:
                raise RuntimeError(
                    f"Privilegios inesperados de «app_user» sobre «{tabla}»: "
                    f"{privilegio}={concedido}, se esperaba {esperado}. Revisa "
                    "infra/postgres/sql/roles.sql y los GRANT/REVOKE de esta migración."
                )


def _sembrar_servicios() -> None:
    """El catálogo de servicios nace activo.

    Sin fila, el código ya trata un servicio como activo (el catálogo manda),
    pero sembrarla deja el estado explícito y permite la FK de
    `organization_services.service_key`.
    """
    for clave in _SERVICIOS:
        op.execute(
            sa.text(
                "INSERT INTO platform_services (service_key, enabled) "
                "VALUES (:clave, true) ON CONFLICT (service_key) DO NOTHING"
            ).bindparams(clave=clave)
        )


def _crear_tablas_de_organizacion() -> None:
    op.create_table(
        "organization_ai_settings",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        # NOT NULL: una fila de override sin credencial completa no existe
        # (V-5, resolución todo-o-nada por fila).
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("default_model", sa.String(length=120), nullable=False),
        sa.Column("api_base", sa.String(length=300), nullable=True),
        sa.Column("api_key_encrypted", sa.Text(), nullable=False),
        sa.Column("api_key_hint", sa.String(length=8), nullable=False),
        sa.Column("monthly_limit_usd", sa.Numeric(precision=14, scale=6), nullable=True),
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
            name="fk_organization_ai_settings_organization_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("organization_id", name=op.f("pk_organization_ai_settings")),
    )

    op.create_table(
        "organization_services",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("service_key", sa.String(length=40), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
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
            name="fk_organization_services_organization_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["service_key"],
            ["platform_services.service_key"],
            name="fk_organization_services_service_key",
            ondelete="CASCADE",
        ),
        # El override solo desactiva (V-7): «forzar on» no existe, así que un
        # `true` aquí sería una configuración que el código no sabe leer.
        sa.CheckConstraint("enabled = false", name="ck_organization_services_solo_desactiva"),
        sa.PrimaryKeyConstraint("organization_id", "service_key", name="pk_organization_services"),
    )


def _verificar_privilegios_de_app_user() -> None:
    """Mismo patrón que `0013`/`0020`: falla aquí, no en runtime."""
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


def _activar_rls_de_dominio() -> None:
    for tabla in _TABLAS_DE_ORGANIZACION:
        op.execute(f"ALTER TABLE {tabla} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {tabla} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_{tabla} ON {tabla} "
            "USING (organization_id = app_current_organization()) "
            "WITH CHECK (organization_id = app_current_organization())"
        )


def downgrade() -> None:
    for tabla in reversed(_TABLAS_DE_ORGANIZACION):
        op.execute(f"DROP POLICY IF EXISTS tenant_{tabla} ON {tabla}")
        op.execute(f"ALTER TABLE {tabla} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {tabla} DISABLE ROW LEVEL SECURITY")

    op.drop_table("organization_services")
    op.drop_table("organization_ai_settings")
    op.drop_table("platform_services")
    op.drop_table("platform_ai_settings")
