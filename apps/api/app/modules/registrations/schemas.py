"""Esquemas de inscripción de asistentes: formulario público y panel de organizador."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, EmailStr, Field

RegistrationStatus = Literal[
    "pending_verification",
    "pending_approval",
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
    turnstile_token: str = Field(description="Token del widget de Turnstile")


class RegistrationMessageResponse(BaseModel):
    """Respuesta genérica del alta: siempre el mismo mensaje, exista o no ya el email."""

    message: str


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
    """Estadísticas de conversión del embudo de inscripción de un evento."""

    initiated: int
    verified: int
    pending_approval: int
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
