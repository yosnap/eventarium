"""Esquemas de inscripción de asistentes: formulario público y panel de organizador."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.modules.policies.schemas import AcceptedPolicyOut

RegistrationStatus = Literal[
    "pending_verification",
    "pending_approval",
    "pending_payment",
    "confirmed",
    "rejected",
    "cancelled",
    "waitlisted",
]
RegistrationQuestionType = Literal["short_text", "single_choice", "multiple_choice"]


class RegistrationQuestionPublic(BaseModel):
    """Pregunta personalizada tal como la ve el formulario público."""

    id: str
    # short_text | single_choice | multiple_choice
    type: str
    label: str
    required: bool
    options: list[str] | None = None
    sort_order: int


class RegistrationAnswerInput(BaseModel):
    """Respuesta a una pregunta personalizada del formulario de inscripción."""

    question_id: str
    # Cadena para `short_text`/`single_choice`, lista de cadenas para
    # `multiple_choice`. `None` equivale a "sin respuesta" (válido si la
    # pregunta no es obligatoria).
    value: str | list[str] | None = None


class SubmitRegistrationRequest(BaseModel):
    """Datos del formulario público de inscripción a un evento."""

    email: EmailStr
    full_name: Annotated[str, Field(min_length=1, max_length=200)]
    answers: list[RegistrationAnswerInput] = Field(default_factory=list)
    data_processing_accepted: bool = Field(
        description="Consentimiento de tratamiento de datos, obligatorio para inscribirse."
    )
    marketing_accepted: bool = False
    recording_accepted: bool = False
    accepted_policy_version_ids: list[UUID] = Field(
        default_factory=list,
        # Como mucho una por tipo (hay cuatro): el tope corta cuerpos abusivos
        # antes de validar nada más.
        max_length=10,
        description=(
            "Versiones de las políticas del organizador que se muestran y se "
            "aceptan (las de `GET /public/events/{slug}/policies`)."
        ),
    )
    turnstile_token: str = Field(description="Token del widget de Turnstile")


class RegistrationMessageResponse(BaseModel):
    """Respuesta genérica del alta: siempre el mismo mensaje, exista o no ya el email."""

    message: str


class RegistrationRejectRequest(BaseModel):
    """Motivo opcional del rechazo, dirigido a la persona rechazada.

    No se guarda en ninguna tabla: viaja solo en el correo de aviso, igual
    que cualquier otro campo de texto libre en un cuerpo de correo. Nota de
    alcance: esto acota la retención en Postgres, no en la cola de tareas —
    ver el comentario de `send_registration_rejected_email`
    (`app/core/tasks.py`) sobre Redis Streams.
    """

    reason: Annotated[str, Field(max_length=500)] | None = None


class VerifyRegistrationRequest(BaseModel):
    """Token del enlace de verificación recibido por correo."""

    token: str


class VerifyRegistrationResponse(BaseModel):
    """Resultado de verificar una inscripción."""

    message: str
    # confirmed | pending_approval | waitlisted
    status: str


class ConfirmWaitlistPromotionRequest(BaseModel):
    """Token del enlace de confirmación de una promoción de lista de espera."""

    token: str


class ConfirmWaitlistPromotionResponse(BaseModel):
    """Resultado de confirmar una promoción de lista de espera."""

    message: str


class CancelRegistrationRequest(BaseModel):
    """Token del enlace de autocancelación recibido por correo."""

    token: str


class CancelRegistrationResponse(BaseModel):
    """Resultado de cancelar una inscripción por autocancelación."""

    message: str


# --- Mis eventos (magic-link, sin cuenta) -------------------------------


class MisEventosSolicitarRequest(BaseModel):
    """Email del formulario de «Mis eventos»."""

    email: EmailStr
    turnstile_token: str = Field(description="Token del widget de Turnstile")


class MisEventosVerRequest(BaseModel):
    """Token del magic-link de «Mis eventos».

    `POST`, no `GET`: el endpoint consume el token (efecto secundario), y un
    `GET` con efectos secundarios lo puede disparar sin querer un escáner de
    enlaces de correo corporativo (hallazgo de code-review, alcance mínimo
    revisado en la Fase 3) — mismo motivo por el que `verify`/`cancel`/
    `confirm-waitlist-promotion` ya son `POST` en este mismo router.
    """

    token: str


class MyRegistrationItem(BaseModel):
    """Una inscripción tal como la ve el listado de «Mis eventos»."""

    event_slug: str
    event_title: str
    starts_at: datetime
    organization_name: str
    status: RegistrationStatus
    # La organización canceló el evento (no confundir con una cancelación de
    # la propia persona).
    event_cancelled: bool = False


class MyRegistrationsResponse(BaseModel):
    """Listado de inscripciones de un email, cruzando organizaciones."""

    registrations: list[MyRegistrationItem]


# --- Panel de organizador (fase 3 de trabajo) --------------------------------


class RegistrationAnswerOut(BaseModel):
    """Respuesta de una inscripción, tal como la ve el panel de organizador."""

    question_id: str
    label: str
    value: Any


class RegistrationConsentOut(BaseModel):
    data_processing_accepted_at: datetime
    marketing_accepted_at: datetime | None
    recording_accepted_at: datetime | None
    #: Aceptación de las políticas propias del organizador (`None` si el
    #: evento no tenía textos vigentes al inscribirse).
    organizer_policies_accepted_at: datetime | None = None
    accepted_policies: list[AcceptedPolicyOut] = Field(default_factory=list)


class RegistrationListItem(BaseModel):
    """Fila del listado de inscripciones del panel de organizador."""

    id: str
    email: str
    full_name: str
    status: RegistrationStatus
    created_at: datetime
    verified_at: datetime | None
    confirmed_at: datetime | None
    waitlist_promoted_at: datetime | None
    waitlist_promotion_expires_at: datetime | None


class RegistrationDetail(RegistrationListItem):
    """Detalle de una inscripción, con respuestas y consentimientos."""

    approved_at: datetime | None
    rejected_at: datetime | None
    cancelled_at: datetime | None
    answers: list[RegistrationAnswerOut]
    consent: RegistrationConsentOut | None


class RegistrationStats(BaseModel):
    """Estadísticas del embudo de inscripción de un evento.

    Los cuatro escalones del embudo son `initiated → verified → approved →
    issued`. Los dos últimos no salen de los conteos por estado: `approved` es
    un hito (`approved_at`), y aprobar deja la fila en `confirmed` o
    `waitlisted`; `issued` vive en `event_tickets`.
    """

    initiated: int
    verified: int
    #: Inscripciones que pasaron por aprobación (`approved_at`), sea cual sea su
    #: estado actual. No es un estado: una vez aprobada, la fila pasa a
    #: `confirmed` o `waitlisted`.
    approved: int
    #: Entradas emitidas (`event_tickets.issued_at`), sin contar las revocadas.
    issued: int
    pending_approval: int
    pending_payment: int
    confirmed: int
    rejected: int
    cancelled: int
    waitlisted: int
    verified_conversion_rate: float | None
    confirmed_conversion_rate: float | None


class RegistrationQuestionCreate(BaseModel):
    """Alta de una pregunta personalizada desde el panel de organizador."""

    type: RegistrationQuestionType
    label: Annotated[str, Field(min_length=1, max_length=300)]
    required: bool = False
    sort_order: int = 0
    options: list[str] | None = None


class RegistrationQuestionUpdate(BaseModel):
    """Edición parcial de una pregunta personalizada.

    `type`/`options` solo se aplican si la pregunta no tiene respuestas
    asociadas todavía — el servicio responde 409 si las hay (decisión #6 del
    PRD, fase 3).
    """

    type: RegistrationQuestionType | None = None
    label: Annotated[str, Field(min_length=1, max_length=300)] | None = None
    required: bool | None = None
    sort_order: int | None = None
    options: list[str] | None = None


class RegistrationQuestionResponse(BaseModel):
    """Pregunta personalizada tal como la ve el panel de organizador."""

    id: str
    type: RegistrationQuestionType
    label: str
    required: bool
    sort_order: int
    options: list[str] | None
