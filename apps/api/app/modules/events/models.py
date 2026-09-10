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
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    Numeric,
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
        # Stripe admite un `expires_at` de Checkout Session entre 30 minutos y
        # 24h desde la creación de la sesión; la fase 4 de trabajo de pagos
        # añade siempre 60s de margen técnico, así que 1439 es el máximo que
        # no se pasa de las 24h.
        CheckConstraint(
            "payment_checkout_window_minutes BETWEEN 30 AND 1439",
            name="ck_events_payment_checkout_window_minutes_rango",
        ),
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
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    online_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # free | approval | paid
    registration_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="free")
    # Fecha a partir de la que se admiten inscripciones; `null` significa que ya
    # están abiertas (comportamiento previo a este campo, sigue siendo el
    # valor por defecto). Antes de esta fecha el listado y la ficha públicos
    # muestran el evento como «próximamente» en vez de «abierto», pero
    # `Event.status`/`visibility` siguen mandando sobre si se lista o no —
    # este campo no oculta el evento, solo cambia el rótulo de disponibilidad.
    registration_opens_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    email_verification_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Ventana que tiene un comprador para pagar antes de que su
    # `pending_payment` caduque y libere la plaza (fase 6 del PRD). Por
    # evento, no por instalación: el aforo (`capacity`) y la fila que retiene
    # la plaza (`event_registrations.payment_expires_at`) son ambos de nivel
    # evento — ver decisión de validación, sesión 1, del plan de la fase 6.
    payment_checkout_window_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=30
    )
    # Geocodificación de `location_address` con Nominatim (mismo mecanismo que
    # `EventVenue`, ver ahí la justificación completa). `null` mientras no haya
    # dirección, `location_mode` sea `online`, o la geocodificación haya
    # fallado — nunca bloquea guardar el evento.
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    geocoded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    sessions: Mapped[list[EventSession]] = relationship(
        back_populates="event", cascade="all, delete-orphan", lazy="selectin"
    )
    members: Mapped[list[EventMember]] = relationship(
        back_populates="event", cascade="all, delete-orphan", lazy="selectin"
    )
    venues: Mapped[list[EventVenue]] = relationship(
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
        # Sin `ondelete=CASCADE`: borrar una sede con sesiones que la referencian
        # se bloquea explícitamente en `service.delete_venue` con un 409 legible
        # (ver justificación ahí). `ondelete=SET NULL` es la red de seguridad de
        # base de datos para el único camino que se salta esa comprobación de
        # servicio: borrar la sede directamente en base de datos (rol de
        # mantenimiento, migraciones) — la sesión queda sin sede en vez de que la
        # fila entera desaparezca o la operación quede bloqueada a ese nivel.
        ForeignKeyConstraint(
            ["venue_id", "organization_id"],
            ["event_venues.id", "event_venues.organization_id"],
            name="fk_event_sessions_venue_id_organization_id",
            ondelete="SET NULL",
        ),
        UniqueConstraint("id", "organization_id", name="uq_event_sessions_id_organization_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_uuid7)
    event_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    # Sede (nivel superior) donde ocurre la sesión; `room` (más abajo) es la sala
    # o espacio concreto dentro de esa sede, texto libre sin relación con `venue`.
    # `null`: eventos de una sola sede no necesitan asignar una sede a cada sesión.
    venue_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
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


class EventVenue(Base, TimestampMixin):
    """Sede de un evento multisede: nombre, dirección real y aforo propios.

    Nivel superior a `EventSession.room` (texto libre, la sala dentro de la
    sede) — p. ej. la sede «Las Naves» puede tener las salas «Sala Principal»
    y «Sala 2», ambas como `room` de sesiones con el mismo `venue_id`. También
    se usa para geocodificar la ubicación simple de un evento de una sola sede
    (`Event.location_address`), mismo mecanismo, distinta fila destino.

    `latitude`/`longitude`/`geocoded_at` cachean el resultado de geocodificar
    `address` con Nominatim (`geocoding.geocode_address`): el servicio solo
    vuelve a llamar a Nominatim cuando `address` cambia respecto al valor
    guardado, nunca en cada lectura.
    """

    __tablename__ = "event_venues"
    __table_args__ = (
        ForeignKeyConstraint(
            ["event_id", "organization_id"],
            ["events.id", "events.organization_id"],
            name="fk_event_venues_event_id_organization_id",
            ondelete="CASCADE",
        ),
        # Objetivo de la FK compuesta de `event_sessions.venue_id`.
        UniqueConstraint("id", "organization_id", name="uq_event_venues_id_organization_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_uuid7)
    event_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    address: Mapped[str | None] = mapped_column(String(300), nullable=True)
    capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    geocoded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    event: Mapped[Event] = relationship(back_populates="venues")


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
        # Compuesta contra `(id, organization_id)` de `organization_members`, no
        # simple contra `id`: evita que una fila propia enlace con un miembro de
        # otra organización (la integridad referencial no pasa por RLS).
        ForeignKeyConstraint(
            ["organization_member_id", "organization_id"],
            ["organization_members.id", "organization_members.organization_id"],
            name="fk_event_members_organization_member_id_organization_id",
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
        PgUUID(as_uuid=True), nullable=False, index=True
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
        # Compuesta contra `(id, organization_id)` de `organization_members`: la
        # membresía de origen de la biografía debe pertenecer a esta misma
        # organización, no a una ajena (la integridad referencial no pasa por RLS).
        ForeignKeyConstraint(
            ["source_organization_member_id", "organization_id"],
            ["organization_members.id", "organization_members.organization_id"],
            name="fk_speaker_public_profiles_source_organization_member_id_org_id",
            ondelete="CASCADE",
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
        PgUUID(as_uuid=True), nullable=False
    )
