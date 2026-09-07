"""Modelos de usuario.

`users` es global a la instalación (una persona puede pertenecer a varias
organizaciones) pero **también** está protegida por RLS: solo es visible el propio
usuario o quien comparta organización con él.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin
from app.shared.identifiers import new_uuid7


class User(Base, TimestampMixin):
    """Persona con acceso a la plataforma."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_uuid7)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    # Nulo cuando la cuenta se creó por invitación y aún no tiene contraseña.
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Nulos hasta que hacen falta: el registro no los pide (un nombre completo en un
    # único campo es ambiguo para repartir en nombre/apellidos después). Se exigen más
    # tarde, en el punto donde de verdad hacen falta — crear una organización, fase 2;
    # inscribirse a un evento, fase 3 — no en el alta de la cuenta.
    first_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    avatar_object_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    locale: Mapped[str] = mapped_column(String(10), nullable=False, default="es-ES")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_superadmin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Nulo hasta que la persona verifica su correo. No se reutiliza `is_active`: esa
    # columna ya gatea el login y los miembros invitados se crean activos sin verificar.
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    social_links: Mapped[list[UserSocialLink]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )


class UserSocialLink(Base, TimestampMixin):
    """Enlace social del perfil de una persona."""

    __tablename__ = "user_social_links"
    __table_args__ = (
        UniqueConstraint("user_id", "kind", name="uq_user_social_links_user_id_kind"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_uuid7)
    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)

    user: Mapped[User] = relationship(back_populates="social_links")
