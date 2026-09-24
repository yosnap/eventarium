"""Conexión de un asistente MCP (ver migración `0055_conexiones_mcp`)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.identifiers import new_uuid7


class McpConnection(Base):
    """Una conexión por asistente: la persona, la organización en la que
    actúa, qué puede hacer (`scopes`) y sobre qué eventos (`event_ids`, NULL =
    todos). De una clave de API solo se guarda su huella."""

    __tablename__ = "mcp_connections"
    __table_args__ = (
        CheckConstraint("method IN ('api_key', 'oauth')", name="ck_mcp_connections_method"),
        CheckConstraint(
            "(method = 'api_key') = (key_hash IS NOT NULL)",
            name="ck_mcp_connections_clave_solo_api_key",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_uuid7)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    method: Mapped[str] = mapped_column(String(20), nullable=False)
    oauth_client_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    scopes: Mapped[list[str]] = mapped_column(ARRAY(String(60)), nullable=False)
    event_ids: Mapped[list[uuid.UUID] | None] = mapped_column(
        ARRAY(PgUUID(as_uuid=True)), nullable=True
    )
    key_prefix: Mapped[str | None] = mapped_column(String(20), nullable=True)
    key_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
