"""Modelos de inscripción de asistentes.

Fase 3 del PRD. Mismo patrón de la fase 2 (`app/modules/events/models.py`):
`organization_id` denormalizado en las cuatro tablas y FK **compuestas** contra
`(id, organization_id)` del padre, nunca FK simples — la integridad referencial
de PostgreSQL no pasa por RLS, así que una FK simple no impediría que una fila
hija con `organization_id` propio apuntara al recurso de otra organización.

Los tokens de verificación de email y de cancelación **no** viven aquí: son
opacos y de un solo uso, y ese mecanismo ya existe en
`app/modules/auth/verification.py` sobre Redis con TTL — una columna
`*_token_hash` sería una segunda implementación del mismo problema.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin
from app.shared.identifiers import new_uuid7


class EventRegistrationQuestion(Base, TimestampMixin):
    """Pregunta personalizada del formulario de inscripción de un evento."""

    __tablename__ = "event_registration_questions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["event_id", "organization_id"],
            ["events.id", "events.organization_id"],
            name="fk_event_registration_questions_event_id_organization_id",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "id", "organization_id", name="uq_event_registration_questions_id_organization_id"
        ),
        # `options` solo tiene sentido (y es obligatorio) para las preguntas de
        # opción; en `short_text` debe ser `NULL` para no sugerir opciones que
        # nunca se usan.
        # `options IS NOT NULL` explícito: sin él, con `options` en NULL de SQL
        # de verdad, `jsonb_typeof(options) = 'array'` se evalúa a desconocido
        # (NULL) en vez de falso, y un CHECK que da NULL se trata como
        # satisfecho — dejaría pasar una pregunta de opción sin opciones.
        CheckConstraint(
            "(type = 'short_text' AND options IS NULL) "
            "OR (type IN ('single_choice', 'multiple_choice') "
            "AND options IS NOT NULL "
            "AND jsonb_typeof(options) = 'array' AND jsonb_array_length(options) > 0)",
            name="ck_event_registration_questions_options_por_tipo",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_uuid7)
    event_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    # short_text | single_choice | multiple_choice
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    label: Mapped[str] = mapped_column(String(300), nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Lista de cadenas; obligatorio y no vacío en single_choice/multiple_choice,
    # NULL en short_text — ver CheckConstraint. `none_as_null=True`: por
    # defecto SQLAlchemy codifica un `None` de Python como el literal JSON
    # `null` (una fila, no ausencia de valor), que no cumple `options IS NULL`
    # a nivel de SQL — así, un `options=None` explícito guarda un NULL de SQL
    # de verdad.
    options: Mapped[list[str] | None] = mapped_column(JSONB(none_as_null=True), nullable=True)

    # `overlaps`: tanto esta relación como `EventRegistration.answers` escriben
    # `event_registration_answers.organization_id` (cada una desde su propia FK
    # compuesta) — la columna siempre se fija explícitamente en el código,
    # nunca por cascada del ORM, así que la ambigüedad que SQLAlchemy detecta
    # es inofensiva; mismo patrón que `EventMember.participations` en la fase 2
    # del PRD.
    answers: Mapped[list[EventRegistrationAnswer]] = relationship(
        back_populates="question", lazy="selectin", overlaps="answers,registration"
    )


class EventRegistration(Base, TimestampMixin):
    """Inscripción de un asistente a un evento.

    Una fila por `(event_id, email)` — nunca dos: reenviar el formulario con el
    mismo email no crea una segunda inscripción, reencola el email que
    corresponda a su estado actual (ver fase 2 de trabajo).
    """

    __tablename__ = "event_registrations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["event_id", "organization_id"],
            ["events.id", "events.organization_id"],
            name="fk_event_registrations_event_id_organization_id",
            ondelete="CASCADE",
        ),
        UniqueConstraint("event_id", "email", name="uq_event_registrations_event_id_email"),
        UniqueConstraint("id", "organization_id", name="uq_event_registrations_id_organization_id"),
        # Compuesto, no dos índices sueltos: es la consulta de aforo y
        # estadísticas de la fase 3 de trabajo (`COUNT(*) ... WHERE event_id = ?
        # AND status = ?`).
        Index("ix_event_registrations_event_id_status", "event_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_uuid7)
    event_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    organization_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Enlace opcional a una cuenta existente, resuelto por email con la función
    # `SECURITY DEFINER` `app_find_user_by_email` (`0004_correo_y_verificacion`):
    # el endpoint público no tiene organización en contexto y `users` está bajo
    # RLS, así que una consulta directa fallaría.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # pending_verification | pending_approval | confirmed | rejected | cancelled
    # | waitlisted
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending_verification")
    waitlist_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    waitlist_promoted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    waitlist_promotion_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    answers: Mapped[list[EventRegistrationAnswer]] = relationship(
        back_populates="registration",
        cascade="all, delete-orphan",
        lazy="selectin",
        overlaps="answers,question",
    )
    consent: Mapped[EventRegistrationConsent | None] = relationship(
        back_populates="registration", cascade="all, delete-orphan", lazy="selectin"
    )


class EventRegistrationAnswer(Base, TimestampMixin):
    """Respuesta de una inscripción a una pregunta personalizada."""

    __tablename__ = "event_registration_answers"
    __table_args__ = (
        ForeignKeyConstraint(
            ["registration_id", "organization_id"],
            ["event_registrations.id", "event_registrations.organization_id"],
            name="fk_event_registration_answers_registration_id_organization_id",
            ondelete="CASCADE",
        ),
        # Sin `ondelete`: RESTRICT por defecto, mismo patrón que
        # `event_session_participants.event_member_id`. Borrar una pregunta con
        # respuestas asociadas se rechaza a nivel de base de datos como último
        # cinturón de seguridad; el servicio ya lo comprueba antes y responde 409.
        ForeignKeyConstraint(
            ["question_id", "organization_id"],
            ["event_registration_questions.id", "event_registration_questions.organization_id"],
            name="fk_event_registration_answers_question_id_organization_id",
        ),
        UniqueConstraint(
            "registration_id",
            "question_id",
            name="uq_event_registration_answers_registration_id_question_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_uuid7)
    registration_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False, index=True
    )
    question_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    # Cadena para short_text/single_choice, lista de cadenas para multiple_choice.
    value: Mapped[Any] = mapped_column(JSONB, nullable=False)

    registration: Mapped[EventRegistration] = relationship(
        back_populates="answers", overlaps="answers,question"
    )
    question: Mapped[EventRegistrationQuestion] = relationship(
        back_populates="answers", overlaps="answers,registration"
    )


class EventRegistrationConsent(Base, TimestampMixin):
    """Consentimientos de una inscripción, cada uno auditable por separado.

    Nunca una sola casilla genérica: tratamiento de datos (obligatorio),
    marketing y grabación de imagen/voz (ambos opcionales, sin condicionar la
    inscripción) son consentimientos independientes.
    """

    __tablename__ = "event_registration_consents"
    __table_args__ = (
        ForeignKeyConstraint(
            ["registration_id", "organization_id"],
            ["event_registrations.id", "event_registrations.organization_id"],
            name="fk_event_registration_consents_registration_id_organization_id",
            ondelete="CASCADE",
        ),
        UniqueConstraint("registration_id", name="uq_event_registration_consents_registration_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_uuid7)
    registration_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False, index=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    data_processing_accepted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    marketing_accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    recording_accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    registration: Mapped[EventRegistration] = relationship(back_populates="consent")
