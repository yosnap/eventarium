"""Modelos de eventos, agenda y ponentes.

Toda tabla hija lleva `organization_id` denormalizado (no solo derivable vía la
FK a su padre), igual que `role_permissions` lo lleva pese a tener `role_id`: es
lo que permite a la política RLS filtrar en la propia tabla, sin subconsultas.

Las FK hacia el padre son **compuestas** contra `(id, organization_id)`, no
simples contra `id`: la integridad referencial de PostgreSQL no pasa por RLS, así
que una FK simple no impediría que una fila con `organization_id` propio
apuntara al recurso de otra organización. La FK compuesta hace que la propia
base de datos garantice que el padre referenciado pertenece a la misma
organización.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin
from app.shared.identifiers import new_uuid7


class Event(Base, TimestampMixin):
    """Evento de una organización, con su agenda."""

    __tablename__ = "events"
    __table_args__ = (
        UniqueConstraint("organization_id", "slug", name="uq_events_organization_id_slug"),
        # Objetivo de las FK compuestas de las tablas hijas (event_sessions, event_members).
        UniqueConstraint("id", "organization_id", name="uq_events_id_organization_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_uuid7)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    slug: Mapped[str] = mapped_column(String(160), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    cover_object_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # draft | published | archived
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    # public | hidden | private
    visibility: Mapped[str] = mapped_column(String(20), nullable=False, default="public")
    timezone: Mapped[str] = mapped_column(String(60), nullable=False, default="Europe/Madrid")
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # in_person | online | hybrid
    location_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    location_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    location_address: Mapped[str | None] = mapped_column(String(300), nullable=True)
    online_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # free | approval | paid
    registration_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="free")
    email_verification_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )

    sessions: Mapped[list[EventSession]] = relationship(
        back_populates="event", cascade="all, delete-orphan", lazy="selectin"
    )
    members: Mapped[list[EventMember]] = relationship(
        back_populates="event", cascade="all, delete-orphan", lazy="selectin"
    )


class EventSession(Base, TimestampMixin):
    """Sesión de la agenda de un evento: charla, descanso, servicio u otro."""

    __tablename__ = "event_sessions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["event_id", "organization_id"],
            ["events.id", "events.organization_id"],
            name="fk_event_sessions_event_id_organization_id",
            ondelete="CASCADE",
        ),
        UniqueConstraint("id", "organization_id", name="uq_event_sessions_id_organization_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_uuid7)
    event_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    # talk | break | service | other
    session_type: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    room: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # youtube | vimeo | twitch | other — nulo si la sesión no lleva vídeo.
    video_platform: Mapped[str | None] = mapped_column(String(20), nullable=True)
    video_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    materials: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    event: Mapped[Event] = relationship(back_populates="sessions")
    participants: Mapped[list[EventSessionParticipant]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        lazy="selectin",
        overlaps="participations,event_member",
    )


class EventMember(Base, TimestampMixin):
    """Persona de la organización que participa en un evento concreto."""

    __tablename__ = "event_members"
    __table_args__ = (
        ForeignKeyConstraint(
            ["event_id", "organization_id"],
            ["events.id", "events.organization_id"],
            name="fk_event_members_event_id_organization_id",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "event_id", "organization_member_id", name="uq_event_members_event_id_member_id"
        ),
        UniqueConstraint("id", "organization_id", name="uq_event_members_id_organization_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_uuid7)
    event_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    organization_member_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("organization_members.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    event: Mapped[Event] = relationship(back_populates="members")
    # `overlaps`: tanto esta relación como `EventSession.participants` escriben
    # `event_session_participants.organization_id` (cada una desde su propia FK
    # compuesta) — la columna siempre se fija explícitamente en el código, nunca
    # por cascada del ORM, así que la ambigüedad que SQLAlchemy detecta es
    # inofensiva; se silencia en vez de dejar el aviso en cada test.
    participations: Mapped[list[EventSessionParticipant]] = relationship(
        back_populates="event_member",
        cascade="all, delete-orphan",
        lazy="selectin",
        overlaps="participants,session",
    )


class EventSessionParticipant(Base, TimestampMixin):
    """Participación de un `EventMember` en una sesión, con un rol libre.

    La misma persona puede aparecer varias veces en la misma sesión con roles
    distintos (p. ej. ponente y moderador a la vez): cada combinación es una fila
    propia, no una lista dentro de una sola fila.
    """

    __tablename__ = "event_session_participants"
    __table_args__ = (
        ForeignKeyConstraint(
            ["session_id", "organization_id"],
            ["event_sessions.id", "event_sessions.organization_id"],
            name="fk_event_session_participants_session_id_organization_id",
            ondelete="CASCADE",
        ),
        # Sin `ondelete`: quitar a alguien del roster del evento mientras tiene
        # participaciones activas se rechaza a nivel de base de datos (RESTRICT,
        # el valor por defecto) como último cinturón de seguridad — el servicio ya
        # lo comprueba antes y devuelve 409, esto es la red por si algo se salta
        # esa capa.
        ForeignKeyConstraint(
            ["event_member_id", "organization_id"],
            ["event_members.id", "event_members.organization_id"],
            name="fk_event_session_participants_event_member_id_organization_id",
        ),
        UniqueConstraint(
            "session_id",
            "event_member_id",
            "role_key",
            name="uq_event_session_participants_session_member_role",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_uuid7)
    session_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    event_member_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False, index=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    # Etiqueta libre por asignación (p. ej. "speaker", "moderator", "presenter"):
    # independiente del rol de la persona en la organización, para que cada
    # organización pueda llamarlo como necesite sin esperar a un catálogo cerrado.
    role_key: Mapped[str] = mapped_column(String(60), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    session: Mapped[EventSession] = relationship(
        back_populates="participants", overlaps="participations,event_member"
    )
    event_member: Mapped[EventMember] = relationship(
        back_populates="participations", overlaps="participants,session"
    )


class SpeakerPublicProfile(Base, TimestampMixin):
    """Perfil público de una persona en una organización.

    Una fila por `(organization_id, user_id)` — la persona, no la membresía: la
    misma persona puede tener varias filas en `organization_members` (una por
    rol), y el perfil público no debe fragmentarse ni duplicarse entre ellas.
    `source_organization_member_id` indica de qué membresía en concreto se toma
    la biografía a publicar.
    """

    __tablename__ = "speaker_public_profiles"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "user_id", name="uq_speaker_public_profiles_organization_id_user_id"
        ),
        UniqueConstraint(
            "organization_id",
            "public_slug",
            name="uq_speaker_public_profiles_organization_id_public_slug",
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
    public_slug: Mapped[str] = mapped_column(String(80), nullable=False)
    source_organization_member_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("organization_members.id", ondelete="CASCADE"),
        nullable=False,
    )
