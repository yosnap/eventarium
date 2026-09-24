"""OAuth del servidor MCP.

- `mcp_oauth_clients`: clientes dados de alta por registro dinámico
  (RFC 7591). Son de la instalación, no de una organización (un mismo Claude
  sirve a personas de organizaciones distintas), así que no llevan RLS: solo
  guardan metadatos públicos del cliente (nombre y direcciones de retorno),
  nunca datos de ninguna organización. Los clientes por CIMD (el `client_id`
  es una URL) no se guardan: se leen de su URL y se cachean.
- `mcp_connections.refresh_hash` y `refresh_hash_anterior`: huella del token
  de renovación vigente y del anterior. Cada renovación rota el token; si
  alguien presenta el anterior, es que se ha filtrado, y se revoca la conexión
  entera (detección de reutilización).
- `app_resolve_mcp_connection(p_id)` y `app_resolve_mcp_refresh(p_hash)`:
  mismo patrón que `app_resolve_mcp_key` (0055). Un token OAuth lleva el id de
  la conexión y la renovación llega con su huella; en ninguno de los dos
  casos se conoce aún la organización con la que fijar el RLS.

Revision ID: 0056_oauth_mcp
Revises: 0055_conexiones_mcp
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0056_oauth_mcp"
down_revision: str | None = "0055_conexiones_mcp"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_POR_ID = """
CREATE OR REPLACE FUNCTION app_resolve_mcp_connection(p_id uuid)
RETURNS TABLE (connection_id uuid, organization_id uuid, user_id uuid, user_active boolean)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT c.id, c.organization_id, c.user_id, u.is_active
  FROM mcp_connections c
  JOIN users u ON u.id = c.user_id
  WHERE c.id = p_id
    AND c.method = 'oauth'
    AND c.revoked_at IS NULL
    AND c.expires_at > now()
    AND EXISTS (SELECT 1 FROM organizations o WHERE o.id = c.organization_id AND o.is_active)
$$
"""

_POR_RENOVACION = """
CREATE OR REPLACE FUNCTION app_resolve_mcp_refresh(p_hash text)
RETURNS TABLE (connection_id uuid, organization_id uuid, user_id uuid, es_anterior boolean)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT c.id, c.organization_id, c.user_id, c.refresh_hash_anterior = p_hash
  FROM mcp_connections c
  WHERE c.method = 'oauth'
    AND c.revoked_at IS NULL
    AND c.expires_at > now()
    AND (c.refresh_hash = p_hash OR c.refresh_hash_anterior = p_hash)
$$
"""

_FUNCIONES = ("app_resolve_mcp_connection(uuid)", "app_resolve_mcp_refresh(text)")


def upgrade() -> None:
    op.create_table(
        "mcp_oauth_clients",
        sa.Column("client_id", sa.String(100), primary_key=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.add_column("mcp_connections", sa.Column("refresh_hash", sa.String(64), nullable=True))
    op.add_column(
        "mcp_connections", sa.Column("refresh_hash_anterior", sa.String(64), nullable=True)
    )
    op.create_index(
        "ix_mcp_connections_refresh_hash",
        "mcp_connections",
        ["refresh_hash"],
        postgresql_where=sa.text("refresh_hash IS NOT NULL"),
    )
    op.execute(_POR_ID)
    op.execute(_POR_RENOVACION)
    for nombre in _FUNCIONES:
        op.execute(f"REVOKE ALL ON FUNCTION {nombre} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {nombre} TO app_user")


def downgrade() -> None:
    for nombre in _FUNCIONES:
        op.execute(f"DROP FUNCTION IF EXISTS {nombre}")
    op.drop_index("ix_mcp_connections_refresh_hash", table_name="mcp_connections")
    op.drop_column("mcp_connections", "refresh_hash_anterior")
    op.drop_column("mcp_connections", "refresh_hash")
    op.drop_table("mcp_oauth_clients")
