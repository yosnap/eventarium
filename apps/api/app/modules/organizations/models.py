"""Modelos de organización, branding y membresías."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin
from app.shared.identifiers import new_uuid7


class Organization(Base, TimestampMixin):
    """Organización que publica eventos (el tenant)."""

    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_uuid7)
    slug: Mapped[str] = mapped_column(String(60), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    legal_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    website: Mapped[str | None] = mapped_column(String(300), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    branding: Mapped[OrganizationBranding | None] = relationship(
        back_populates="organization", cascade="all, delete-orphan", uselist=False, lazy="selectin"
    )


class OrganizationBranding(Base, TimestampMixin):
    """Identidad visual de la organización."""

    __tablename__ = "organization_branding"
    __table_args__ = (
        # FK compuesta contra `(media.id, media.organization_id)` — nunca
        # simple: la integridad referencial de Postgres no pasa por RLS, así
        # que una FK simple permitiría apuntar a un `media` de otra
        # organización (biblioteca de medios, plan `260918-1944`).
        ForeignKeyConstraint(
            ["logo_media_id", "organization_id"],
            ["media.id", "media.organization_id"],
            name="fk_organization_branding_logo_media_id_organization_id",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    logo_object_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    favicon_object_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Nulo para logos subidos antes de la biblioteca de medios (sin
    # backfill, a propósito): esas imágenes siguen su ciclo de vida de
    # siempre (reemplazar borra el objeto anterior). No nulo = el logo está
    # gestionado por la biblioteca; reemplazarlo NO borra el objeto, porque
    # puede estar reutilizado en otro sitio.
    logo_media_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    # `NULL` = la plantilla marcada `is_default` en `theme_templates`. Sin
    # backfill (0014_plantillas_de_tema): las organizaciones existentes se
    # quedan en `NULL` y por tanto ven «Oscuro» sin tocar una fila.
    theme_template_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("theme_templates.id", ondelete="RESTRICT"),
        nullable=True,
    )
    social_links: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    organizer_blurb: Mapped[str | None] = mapped_column(Text, nullable=True)

    organization: Mapped[Organization] = relationship(back_populates="branding")


class OrganizationMember(Base, TimestampMixin):
    """Vínculo entre una persona y una organización con un rol concreto.

    `profile_data` guarda las respuestas a los campos definidos por el rol y se
    reutiliza entre ediciones del evento.
    """

    __tablename__ = "organization_members"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "user_id",
            "role_id",
            name="uq_organization_members_organization_id_user_id_role_id",
        ),
        # Objetivo de las FK compuestas de `event_members.organization_member_id` y
        # `speaker_public_profiles.source_organization_member_id`: sin esto, nada a
        # nivel de base de datos impediría que una fila propia referenciara a un
        # miembro de otra organización (la integridad referencial no pasa por RLS).
        UniqueConstraint(
            "id", "organization_id", name="uq_organization_members_id_organization_id"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_uuid7)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    profile_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    #: Último acceso **a esta organización**, escrito en el login. Va por
    #: membresía y no en `users`: una persona pertenece a varias organizaciones, y
    #: una columna global haría «saltar» la marca de todas las demás cuando entra
    #: en una. `None` es «no consta», no «hace mucho»: las filas anteriores a la
    #: migración no tienen el dato.
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# Import al final, no al principio: `OrganizationInvitation` vive en su propio
# fichero (fase 1 del plan de invitaciones) para no engordar este módulo, pero
# tiene que registrarse en `Base.metadata` en cuanto se importa
# `organizations.models` — que es lo que hace todo el resto del código para
# usar `OrganizationMember` — o sus FK compuestas contra `events`/`roles` no
# resuelven la tabla al `flush`.
from app.modules.organizations.invitations_models import OrganizationInvitation  # noqa: E402, F401
