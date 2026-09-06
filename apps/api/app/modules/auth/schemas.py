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
