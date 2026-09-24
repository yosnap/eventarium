"""Conexiones del servidor MCP.

- `mcp_connections`: una conexión por asistente (clave de API u OAuth), de una
  persona en una organización, con sus ámbitos y, opcionalmente, la lista de
  eventos a los que se limita. RLS por organización como el resto de tablas.
- `app_resolve_mcp_key(p_hash)`: con una clave no se conoce la organización
  hasta encontrar su fila, y bajo RLS la búsqueda no vería nada. Función
  `SECURITY DEFINER` de alcance mínimo (patrón de `0003` y `0032`): devuelve
  solo la conexión, su organización, su persona y si la cuenta sigue activa;
  con eso se fija el contexto RLS y el resto de la petición va por el camino
  normal.
- `app_revoke_mcp_connections_of_user(p_user_id)`: cambiar o restablecer la
  contraseña, o desactivar la cuenta, revoca todas sus conexiones en todas
  sus organizaciones — desde una sesión que no tiene organización activa.
- Backfill de `mcp:connect` para los roles `owner` ya creados: la plantilla
  `OWNER` hereda el catálogo entero, pero solo al crear organizaciones nuevas
  (el mismo hueco que `0026_permiso_de_invitaciones`).

Revision ID: 0055_conexiones_mcp
Revises: 0054_evento_cancelado
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0055_conexiones_mcp"
down_revision: str | None = "0054_evento_cancelado"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLA = "mcp_connections"

_RESOLVER = """
CREATE OR REPLACE FUNCTION app_resolve_mcp_key(p_hash text)
RETURNS TABLE (connection_id uuid, organization_id uuid, user_id uuid, user_active boolean)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT c.id, c.organization_id, c.user_id, u.is_active
  FROM mcp_connections c
  JOIN users u ON u.id = c.user_id
  WHERE c.key_hash = p_hash
    AND c.revoked_at IS NULL
    AND c.expires_at > now()
    AND EXISTS (SELECT 1 FROM organizations o WHERE o.id = c.organization_id AND o.is_active)
$$
"""

_REVOCAR = """
CREATE OR REPLACE FUNCTION app_revoke_mcp_connections_of_user(p_user_id uuid)
RETURNS integer
LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path = public AS $$
  WITH revocadas AS (
    UPDATE mcp_connections
    SET revoked_at = now(), revoked_by = p_user_id
    WHERE user_id = p_user_id AND revoked_at IS NULL
    RETURNING 1
  )
  SELECT count(*)::integer FROM revocadas
$$
"""

_FUNCIONES = (
    "app_resolve_mcp_key(text)",
    "app_revoke_mcp_connections_of_user(uuid)",
)

_BACKFILL_OWNER = """
INSERT INTO role_permissions (role_id, permission, organization_id)
SELECT r.id, 'mcp:connect', r.organization_id
FROM roles r
WHERE r.is_system AND r.key = 'owner'
AND NOT EXISTS (
  SELECT 1 FROM role_permissions rp
  WHERE rp.role_id = r.id AND rp.permission = 'mcp:connect'
)
"""


def upgrade() -> None:
    op.create_table(
        _TABLA,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("method", sa.String(20), nullable=False),
        sa.Column("oauth_client_id", sa.String(500), nullable=True),
        sa.Column("scopes", postgresql.ARRAY(sa.String(60)), nullable=False),
        # NULL = todos los eventos de la organización.
        sa.Column("event_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=True),
        sa.Column("key_prefix", sa.String(20), nullable=True),
        sa.Column("key_hash", sa.String(64), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.CheckConstraint("method IN ('api_key', 'oauth')", name="ck_mcp_connections_method"),
        sa.CheckConstraint(
            "(method = 'api_key') = (key_hash IS NOT NULL)",
            name="ck_mcp_connections_clave_solo_api_key",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["revoked_by"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "uq_mcp_connections_key_hash", _TABLA, ["key_hash"], unique=True,
        postgresql_where=sa.text("key_hash IS NOT NULL"),
    )
    op.create_index("ix_mcp_connections_org_user", _TABLA, ["organization_id", "user_id"])

    op.execute(f"ALTER TABLE {_TABLA} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {_TABLA} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_{_TABLA} ON {_TABLA} "
        "USING (organization_id = app_current_organization()) "
        "WITH CHECK (organization_id = app_current_organization())"
    )

    op.execute(_RESOLVER)
    op.execute(_REVOCAR)
    for nombre in _FUNCIONES:
        op.execute(f"REVOKE ALL ON FUNCTION {nombre} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {nombre} TO app_user")

    op.execute(_BACKFILL_OWNER)


def downgrade() -> None:
    op.execute("DELETE FROM role_permissions WHERE permission = 'mcp:connect'")
    for nombre in _FUNCIONES:
        op.execute(f"DROP FUNCTION IF EXISTS {nombre}")
    op.drop_table(_TABLA)
