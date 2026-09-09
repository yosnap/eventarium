"""Modelos de organización, dominios, branding y membresías."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
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
    # Datos de la entidad responsable para las páginas legales (fase 5 del
    # PRD, decisión #2 del plan): un aviso legal real necesita dirección
    # postal y NIF/CIF, que la fase 1 no pidió porque entonces no había para
    # qué.
    legal_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    tax_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # `NULL` = usar la plantilla de texto plano/Markdown restringido por
    # defecto (nunca HTML crudo, nunca un motor de plantillas nuevo — Jinja2
    # no existe en el proyecto y añadirlo solo para esto abriría XSS/SSTI
    # sobre contenido editable por el tenant y servido en SSR público).
    legal_notice_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    privacy_policy_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    cookies_policy_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    registration_terms_content: Mapped[str | None] = mapped_column(Text, nullable=True)

    domains: Mapped[list[OrganizationDomain]] = relationship(
        back_populates="organization", cascade="all, delete-orphan", lazy="selectin"
    )
    branding: Mapped[OrganizationBranding | None] = relationship(
        back_populates="organization", cascade="all, delete-orphan", uselist=False, lazy="selectin"
    )


class OrganizationDomain(Base, TimestampMixin):
    """Host que resuelve a esta organización.

    `host` es único en toda la instalación: dos organizaciones no pueden reclamar el
    mismo dominio, que es la base de la resolución de tenant.
    """

    __tablename__ = "organization_domains"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_uuid7)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    host: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    organization: Mapped[Organization] = relationship(back_populates="domains")


class OrganizationBranding(Base, TimestampMixin):
    """Identidad visual de la organización."""

    __tablename__ = "organization_branding"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    template_key: Mapped[str] = mapped_column(String(40), nullable=False, default="classic")
    logo_object_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    favicon_object_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
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
