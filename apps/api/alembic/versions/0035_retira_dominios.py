"""retira organization_domains y platform_domains

Fase 6 (cierre) del plan «organización sin dominio»
(`plans/260914-0741-organizacion-sin-dominio/plan.md`). Decisión explícita
del usuario, siguiendo la recomendación de `reports/predict.md`: ninguna
organización tiene dominio propio desde este plan, y con `0034` los tres
endpoints que aún resolvían por host (`GET /tenant/branding`,
`GET /public/events`, `POST /public/cookie-consent`) han dejado de
necesitarlo — no queda ningún consumidor real de estas dos tablas ni de las
funciones `SECURITY DEFINER` que las leían.

Grep previo (fase 6) confirmando cero referencias activas antes de escribir
esta migración: `organization_domains`/`platform_domains` solo quedaban en
`resolve_organization`/`resolve_host` (retirados en el mismo cambio de
código que esta migración acompaña) y en la gestión de dominios del panel de
plataforma (endpoints `POST/GET /admin/organizations/{id}/domains`,
`GET/PUT /admin/platform-domains`, retirados igual — nunca tuvieron pantalla
en el frontend, solo cliente HTTP generado sin usar).

Se retira también `app_resolve_organization(text)` (resolución por host) y
`app_resolve_organization_by_slug(text)` (atajo de desarrollo por slug de
`resolve_organization`, sin sentido sin la función que lo llamaba).

Revision ID: 0035_retira_dominios
Revises: 0034_publico_sin_host
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0035_retira_dominios"
down_revision: str | None = "0034_publico_sin_host"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS app_resolve_organization(text)")
    op.execute("DROP FUNCTION IF EXISTS app_resolve_organization_by_slug(text)")

    op.drop_index(op.f("ix_organization_domains_organization_id"), table_name="organization_domains")
    op.drop_table("organization_domains")
    op.drop_table("platform_domains")


def downgrade() -> None:
    op.create_table(
        "organization_domains",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("host", sa.String(length=255), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_organization_domains_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organization_domains")),
        sa.UniqueConstraint("host", name=op.f("uq_organization_domains_host")),
    )
    op.create_index(
        op.f("ix_organization_domains_organization_id"),
        "organization_domains",
        ["organization_id"],
        unique=False,
    )
    op.execute("ALTER TABLE organization_domains ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE organization_domains FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_organization_domains ON organization_domains "
        "USING (organization_id = app_current_organization()) "
        "WITH CHECK (organization_id = app_current_organization())"
    )

    op.create_table(
        "platform_domains",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("host", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_platform_domains"),
        sa.UniqueConstraint("host", name="uq_platform_domains_host"),
    )
    op.execute("REVOKE INSERT, UPDATE, DELETE ON platform_domains FROM app_user")

    op.execute(
        """
CREATE OR REPLACE FUNCTION app_resolve_organization(p_host text)
RETURNS TABLE (id uuid, slug text, is_active boolean)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT o.id, o.slug::text, o.is_active
  FROM organization_domains d
  JOIN organizations o ON o.id = d.organization_id
  WHERE d.host = lower(p_host)
$$
        """
    )
    op.execute(
        """
CREATE OR REPLACE FUNCTION app_resolve_organization_by_slug(p_slug text)
RETURNS TABLE (id uuid, slug text, is_active boolean)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT o.id, o.slug::text, o.is_active
  FROM organizations o
  WHERE o.slug = lower(p_slug)
$$
        """
    )
    for nombre in ("app_resolve_organization(text)", "app_resolve_organization_by_slug(text)"):
        op.execute(f"REVOKE ALL ON FUNCTION {nombre} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {nombre} TO app_user")
