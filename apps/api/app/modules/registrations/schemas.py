"""Esquemas públicos de inscripción de asistentes."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, EmailStr, Field


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
