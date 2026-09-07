"""Esquemas de entrada y salida de autenticación."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


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
    full_name: str
    is_superadmin: bool


class LoginResponse(TokenResponse):
    """Respuesta del login."""

    user: UserSummary


class RegisterRequest(BaseModel):
    """Datos para crear una cuenta."""

    email: EmailStr = Field(description="Correo electrónico del usuario")
    password: str = Field(
        min_length=8, max_length=256, description="Contraseña, mínimo 8 caracteres"
    )
    full_name: str = Field(min_length=1, max_length=200, description="Nombre completo")
    turnstile_token: str = Field(description="Token del widget de Turnstile")


class ResendVerificationRequest(BaseModel):
    """Datos para reenviar el correo de verificación."""

    email: EmailStr = Field(description="Correo electrónico de la cuenta")
    turnstile_token: str = Field(description="Token del widget de Turnstile")


class GenericMessageResponse(BaseModel):
    """Respuesta genérica, igual exista o no la cuenta (anti-enumeración)."""

    message: str


class VerifyEmailResponse(BaseModel):
    """Respuesta de la verificación de correo."""

    message: str
