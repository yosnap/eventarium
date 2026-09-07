"""Esquemas del módulo de usuarios."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.permissions import Permission
from app.core.security import password_meets_complexity


class CurrentUserResponse(BaseModel):
    """Usuario autenticado en el contexto de la organización actual."""

    id: str
    email: EmailStr
    first_name: str | None
    last_name: str | None
    is_superadmin: bool
    organization_id: str
    roles: list[str]
    permissions: list[Permission]


class UserMeUpdate(BaseModel):
    """Campos editables directamente, sin flujo propio (nombre, locale).

    El correo no está aquí: tiene su propio flujo con confirmación
    (`POST /users/me/change-email`).
    """

    first_name: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    last_name: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    locale: Annotated[str, Field(min_length=2, max_length=10)] | None = None


class ChangeEmailRequest(BaseModel):
    """Solicitud de cambio de correo: exige la contraseña actual."""

    new_email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class ChangeEmailConfirmRequest(BaseModel):
    """Confirmación del cambio de correo con el token recibido en el correo nuevo."""

    token: str


class ChangePasswordRequest(BaseModel):
    """Cambio de contraseña: exige la actual."""

    current_password: str = Field(min_length=1, max_length=256)
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


class SocialLinkUpdate(BaseModel):
    """Enlace social del perfil de una persona."""

    url: Annotated[str, Field(min_length=1, max_length=500, pattern=r"^https?://")]


class SocialLinkResponse(BaseModel):
    """Enlace social tal y como lo ve el panel."""

    model_config = ConfigDict(from_attributes=True)

    kind: str
    url: str


class OrganizationMembershipResponse(BaseModel):
    """Una organización a la que pertenece la persona, para el selector del panel."""

    organization_id: str
    slug: str
    name: str
    host: str | None
