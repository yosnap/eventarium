"""Biblioteca de medios reutilizable.

`media`/`media_folders` son tablas de dominio (RLS estándar, `organization_id`
NOT NULL siempre — no hay caso "medio de plataforma" aquí, ver `PlatformMedia`
más abajo). `UniqueConstraint("id", "organization_id")` en `Media` existe para
que las tablas consumidoras (`OrganizationBranding.logo_media_id`,
`Event.cover_media_id`, `Sponsor.logo_media_id`) puedan usar una FK
**compuesta** contra `(media.id, media.organization_id)`, igual que
`sponsors.event_id`/`sponsors.tier_id` en `app/modules/sponsors/models.py`:
la integridad referencial de Postgres no pasa por RLS, así que una FK simple
permitiría a un domain row de la organización A apuntar a un `media` de la
organización B sin que nada a nivel de base de datos lo impida.

`PlatformMedia`/`PlatformMediaFolder` son tablas de instalación (sin RLS,
igual que `platform_branding`): se protegen con `REVOKE ALL ... FROM
app_user` y solo se tocan desde `app/modules/admin/` con la sesión de
mantenimiento (rol con `BYPASSRLS`) — nunca se mezclan con
`media` en la misma tabla porque no existe ningún GUC de sesión equivalente
a `app.organization_id` para "esto es de plataforma" (`app/core/database.py`
solo fija `app.organization_id` y `app.user_id`).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin
from app.shared.identifiers import new_uuid7


class MediaFolder(Base, TimestampMixin):
    """Carpeta de biblioteca, de un `kind` implícito (el del primer medio que
    se le asigna) — sin carpetas transversales a varios `kind` en esta
    entrega."""

    __tablename__ = "media_folders"
    __table_args__ = (
        UniqueConstraint("organization_id", "slug", name="uq_media_folders_org_slug"),
        # Objetivo de la FK compuesta de `Media.folder_id` (ver docstring).
        UniqueConstraint("id", "organization_id", name="uq_media_folders_id_organization_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_uuid7)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False)


class Media(Base, TimestampMixin):
    """Una imagen ya subida a la biblioteca de una organización, reutilizable
    sin volver a subirla."""

    __tablename__ = "media"
    __table_args__ = (
        ForeignKeyConstraint(
            ["folder_id", "organization_id"],
            ["media_folders.id", "media_folders.organization_id"],
            name="fk_media_folder_id_organization_id",
        ),
        UniqueConstraint("id", "organization_id", name="uq_media_id_organization_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_uuid7)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Catálogo cerrado validado en código (`branding`/`events`/`sponsors`),
    # no en BD — gobierna qué permiso hace falta para subir/listar/borrar
    # este medio (hallazgo de red-team: sin esta columna, cualquier
    # `*:write` de la organización veía y podía borrar toda la biblioteca).
    kind: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    uploaded_by_user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    folder_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    object_key: Mapped[str] = mapped_column(String(500), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size: Mapped[int] = mapped_column(nullable=False)
    width: Mapped[int | None] = mapped_column(nullable=True)
    height: Mapped[int | None] = mapped_column(nullable=True)
    alt: Mapped[str | None] = mapped_column(String(300), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PlatformMediaFolder(Base, TimestampMixin):
    """Carpeta de la biblioteca de plataforma — sin RLS, protegida como
    `platform_branding` (ver docstring del módulo)."""

    __tablename__ = "platform_media_folders"
    __table_args__ = (UniqueConstraint("slug", name="uq_platform_media_folders_slug"),)

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_uuid7)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False)


class PlatformMedia(Base, TimestampMixin):
    """Imagen de la biblioteca de plataforma — sin RLS, sin `organization_id`
    ni `kind` (un único contexto: identidad de la instalación)."""

    __tablename__ = "platform_media"
    __table_args__ = (
        ForeignKeyConstraint(
            ["folder_id"],
            ["platform_media_folders.id"],
            name="fk_platform_media_folder_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_uuid7)
    uploaded_by_user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    folder_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    object_key: Mapped[str] = mapped_column(String(500), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size: Mapped[int] = mapped_column(nullable=False)
    width: Mapped[int | None] = mapped_column(nullable=True)
    height: Mapped[int | None] = mapped_column(nullable=True)
    alt: Mapped[str | None] = mapped_column(String(300), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
