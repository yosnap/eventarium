"""Versiones de las políticas y condiciones propias de cada organizador.

Una fila por guardado; nunca se reescribe una anterior (la migración `0053`
revoca `UPDATE` y `DELETE` a `app_user`). Ver el encabezado de esa migración
para el significado de `event_id` y `content` nulos.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.identifiers import new_uuid7

#: Los cuatro documentos que puede escribir un organizador, en el orden en que
#: se muestran. Espejo del `CHECK` de la migración `0053`.
TIPOS_DE_POLITICA: tuple[str, ...] = ("condiciones", "reembolsos", "privacidad", "otras")


class OrganizationPolicyVersion(Base):
    __tablename__ = "organization_policy_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["event_id", "organization_id"],
            ["events.id", "events.organization_id"],
            name="fk_organization_policy_versions_event_id_organization_id",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "kind IN ('condiciones', 'otras', 'privacidad', 'reembolsos')",
            name="ck_organization_policy_versions_kind",
        ),
        CheckConstraint(
            "event_id IS NOT NULL OR content IS NOT NULL",
            name="ck_organization_policy_versions_contenido_de_organizacion",
        ),
        CheckConstraint(
            "event_id IS NULL OR content IS NULL OR content <> ''",
            name="ck_organization_policy_versions_texto_de_evento",
        ),
        CheckConstraint("version >= 1", name="ck_organization_policy_versions_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_uuid7)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    #: `None` = texto por defecto de la organización.
    event_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    #: `None` solo en filas de evento: «vuelve a heredar el de la organización».
    #: `''` en una fila de organización: «retirado».
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
