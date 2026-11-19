"""Una traducción por campo, con RLS por organización."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin
from app.shared.identifiers import new_uuid7


class ContentTranslation(Base, TimestampMixin):
    """El valor de `field` de una entidad en `locale`.

    El original sigue en la columna de la entidad. `source_hash` es la huella del
    original con el que se hizo la traducción: si el original cambia, la huella
    deja de coincidir y la traducción no se sirve aunque su `status` no se haya
    actualizado todavía.
    """

    __tablename__ = "content_translations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["event_id", "organization_id"],
            ["events.id", "events.organization_id"],
            name="fk_content_translations_event_id_organization_id",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "organization_id",
            "entity_type",
            "entity_id",
            "field",
            "locale",
            name="uq_content_translations_campo",
        ),
        CheckConstraint("origin IN ('ia', 'manual', 'revisada')", name="origin"),
        CheckConstraint(
            "status IN ('pendiente', 'en_curso', 'al_dia', 'error', 'desactualizada')",
            name="status",
        ),
        Index("ix_content_translations_evento", "organization_id", "event_id", "locale"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_uuid7)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey(
            "organizations.id",
            ondelete="CASCADE",
            name="fk_content_translations_organization_id_organizations",
        ),
        nullable=False,
    )
    #: Evento del que cuelga la entidad; `None` para lo que es de la organización.
    event_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    field: Mapped[str] = mapped_column(String(200), nullable=False)
    locale: Mapped[str] = mapped_column(String(10), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    origin: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retry_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey(
            "users.id", ondelete="SET NULL", name="fk_content_translations_updated_by_users"
        ),
        nullable=True,
    )
