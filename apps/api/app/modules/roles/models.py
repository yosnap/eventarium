"""Modelos de roles, permisos y campos de perfil.

Decisión clave: los roles del sistema **se clonan** en cada organización en lugar de
compartirse. Así `organization_id` es `NOT NULL` en todas las filas, RLS es uniforme
y una organización puede ampliar sus roles sin afectar a las demás.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin
from app.shared.identifiers import new_uuid7

# Tipos admitidos por los campos de perfil personalizados.
FIELD_TYPES = ("text", "textarea", "url", "email", "phone", "date", "select", "boolean")


class Role(Base, TimestampMixin):
    """Rol dentro de una organización."""

    __tablename__ = "roles"
    __table_args__ = (
        UniqueConstraint("organization_id", "key", name="uq_roles_organization_id_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_uuid7)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    key: Mapped[str] = mapped_column(String(60), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Un rol de sistema no se puede borrar y conserva sus campos bloqueados.
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    system_template_key: Mapped[str | None] = mapped_column(String(60), nullable=True)

    permissions: Mapped[list[RolePermission]] = relationship(
        back_populates="role", cascade="all, delete-orphan", lazy="selectin"
    )
    profile_fields: Mapped[list[RoleProfileField]] = relationship(
        back_populates="role",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="RoleProfileField.sort_order",
    )


class RolePermission(Base):
    """Permiso concedido a un rol. El valor pertenece al enum `Permission`."""

    __tablename__ = "role_permissions"

    role_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    permission: Mapped[str] = mapped_column(String(60), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    role: Mapped[Role] = relationship(back_populates="permissions")


class RoleProfileField(Base, TimestampMixin):
    """Campo del perfil que se pide a quien tiene ese rol."""

    __tablename__ = "role_profile_fields"
    __table_args__ = (
        UniqueConstraint("role_id", "key", name="uq_role_profile_fields_role_id_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_uuid7)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key: Mapped[str] = mapped_column(String(60), nullable=False)
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    field_type: Mapped[str] = mapped_column(String(20), nullable=False, default="text")
    options: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Los campos que vienen de la plantilla del sistema no se pueden borrar.
    is_locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    role: Mapped[Role] = relationship(back_populates="profile_fields")
