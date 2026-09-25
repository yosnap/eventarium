"""Proveedor de correo de la plataforma.

- `platform_email_settings`: fila única con la conexión SMTP que el
  superadmin guarda desde el panel; la contraseña (o API key) va cifrada con
  `AI_SETTINGS_ENCRYPTION_KEY`. Sin fila, el envío usa las variables `SMTP_*`.
- Mismo endurecimiento que `platform_ai_settings` (0048): `app_user` solo
  puede leerla; la escribe la sesión de mantenimiento del admin.

Revision ID: 0057_proveedor_correo
Revises: 0056_oauth_mcp
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0057_proveedor_correo"
down_revision: str | None = "0056_oauth_mcp"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLA = "platform_email_settings"


def upgrade() -> None:
    op.create_table(
        _TABLA,
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("host", sa.String(length=255), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("tls_mode", sa.String(length=10), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=False),
        sa.Column("password_encrypted", sa.Text(), nullable=False),
        sa.Column("password_hint", sa.String(length=8), nullable=False),
        sa.Column("from_address", sa.String(length=320), nullable=False),
        sa.Column("region", sa.String(length=30), nullable=True),
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
        sa.CheckConstraint("id = 1", name=op.f("ck_platform_email_settings_fila_unica")),
        sa.CheckConstraint(
            "provider IN ('resend', 'acumbamail', 'ses', 'custom')",
            name=op.f("ck_platform_email_settings_proveedor"),
        ),
        sa.CheckConstraint(
            "tls_mode IN ('implicit', 'starttls', 'none')",
            name=op.f("ck_platform_email_settings_tls"),
        ),
        sa.CheckConstraint(
            "port BETWEEN 1 AND 65535", name=op.f("ck_platform_email_settings_puerto")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_platform_email_settings")),
    )

    op.execute(f"REVOKE ALL ON {_TABLA} FROM app_user")
    op.execute(f"GRANT SELECT ON {_TABLA} TO app_user")
    conexion = op.get_bind()
    for privilegio, esperado in (
        ("SELECT", True),
        ("INSERT", False),
        ("UPDATE", False),
        ("DELETE", False),
    ):
        concedido = conexion.execute(
            sa.text("SELECT has_table_privilege('app_user', :tabla, :privilegio)"),
            {"tabla": _TABLA, "privilegio": privilegio},
        ).scalar()
        if bool(concedido) is not esperado:
            raise RuntimeError(
                f"Privilegios inesperados de «app_user» sobre «{_TABLA}»: "
                f"{privilegio}={concedido}, se esperaba {esperado}."
            )


def downgrade() -> None:
    op.drop_table(_TABLA)
