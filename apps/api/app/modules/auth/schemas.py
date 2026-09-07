"""Esquemas de entrada y salida de autenticación."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.security import password_meets_complexity


class LoginRequest(BaseModel):
    """Credenciales de acceso."""

    email: EmailStr = Field(description="Correo electrónico del usuario")
    password: str = Field(min_length=1, max_length=256, description="Contraseña")


class TokenResponse(BaseModel):
    """Access token. El refresh viaja en una cookie `HttpOnly` y no se expone aquí."""

    access_token: str
    token_type: str = "bearer"  # noqa: S105 - es el tipo del token, no un secreto
    expires_in: int = Field(description="Segundos de validez del access token")


class UserSummary(BaseModel):
    """Datos mínimos del usuario autenticado."""

    id: str
    email: EmailStr
    first_name: str | None
    last_name: str | None
    is_superadmin: bool


class LoginResponse(TokenResponse):
    """Respuesta del login."""

    user: UserSummary


class RegisterRequest(BaseModel):
    """Datos para crear una cuenta."""

    email: EmailStr = Field(description="Correo electrónico del usuario")
    password: str = Field(
        min_length=8,
        max_length=256,
        description=(
            "Contraseña: mínimo 8 caracteres, con mayúscula, minúscula, número y carácter especial"
        ),
    )
    turnstile_token: str = Field(description="Token del widget de Turnstile")

    @field_validator("password")
    @classmethod
    def _validar_complejidad(cls, valor: str) -> str:
        if not password_meets_complexity(valor):
            raise ValueError(
                "La contraseña debe tener mínimo 8 caracteres, una mayúscula, una "
                "minúscula, un número y un carácter especial."
            )
        return valor


class ResendVerificationRequest(BaseModel):
    """Datos para reenviar el correo de verificación."""

    email: EmailStr = Field(description="Correo electrónico de la cuenta")
    turnstile_token: str = Field(description="Token del widget de Turnstile")


class GenericMessageResponse(BaseModel):
    """Respuesta genérica, igual exista o no la cuenta (anti-enumeración)."""

    message: str


class ForgotPasswordRequest(BaseModel):
    """Datos para pedir la recuperación de una contraseña olvidada."""

    email: EmailStr = Field(description="Correo electrónico de la cuenta")
    turnstile_token: str = Field(description="Token del widget de Turnstile")


class ResetPasswordRequest(BaseModel):
    """Datos para completar la recuperación con el token recibido por correo."""

    token: str = Field(description="Token del enlace de recuperación")
    new_password: str = Field(
        min_length=8,
        max_length=256,
        description=(
            "Contraseña: mínimo 8 caracteres, con mayúscula, minúscula, número y carácter especial"
        ),
    )

    @field_validator("new_password")
    @classmethod
    def _validar_complejidad(cls, valor: str) -> str:
        if not password_meets_complexity(valor):
            raise ValueError(
                "La contraseña debe tener mínimo 8 caracteres, una mayúscula, una "
                "minúscula, un número y un carácter especial."
            )
        return valor


class VerifyEmailResponse(BaseModel):
    """Respuesta de la verificación de correo.

    Incluye un access token **sin organización** (`create_access_token` acepta
    `organization_id=None`): sirve solo de puente hasta crear la primera
    organización (fase 2), no para entrar en el panel de ninguna.
    """

    message: str
    access_token: str
    expires_in: int
