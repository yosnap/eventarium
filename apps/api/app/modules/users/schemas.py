"""Esquemas del módulo de usuarios."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.core.permissions import Permission
from app.core.security import password_meets_complexity
from app.modules.organizations.schemas import SLUG_PATTERN

# Lista blanca fija de `profile_data` que se sirve en el perfil público de un
# ponente. Nunca se vuelca `profile_data` completo: un campo a medida que una
# organización haya añadido a un rol (teléfono, DNI, disponibilidad…) no está
# pensado para publicarse y se descarta explícitamente aunque exista.
PUBLIC_PROFILE_FIELDS: tuple[str, ...] = (
    "bio",
    "titular",
    "empresa",
    "curriculum",
    "web",
    "contacto",
)


def filter_public_profile_fields(profile_data: dict[str, Any]) -> dict[str, Any]:
    """Aplica la lista blanca fija sobre `profile_data`."""
    return {clave: valor for clave, valor in profile_data.items() if clave in PUBLIC_PROFILE_FIELDS}


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


class PublicProfileUpdate(BaseModel):
    """Activa, cambia o desactiva el perfil público de ponente (autoservicio).

    `public_slug: null` desactiva el perfil (borra la fila de
    `speaker_public_profiles`); un valor no nulo lo activa o lo actualiza, y en
    ese caso `source_organization_member_id` es obligatorio.
    """

    public_slug: Annotated[str, Field(min_length=2, max_length=80, pattern=SLUG_PATTERN)] | None
    source_organization_member_id: str | None = None

    @model_validator(mode="after")
    def _validar_consistencia(self) -> PublicProfileUpdate:
        if self.public_slug is not None and self.source_organization_member_id is None:
            raise ValueError(
                "Falta indicar de qué membresía tomar la biografía (source_organization_member_id)."
            )
        return self


class PublicProfileResponse(BaseModel):
    """Estado actual del perfil público propio."""

    active: bool
    public_slug: str | None
    source_organization_member_id: str | None


class EligibleMembershipResponse(BaseModel):
    """Membresía propia cuyo rol declara al menos un campo publicable."""

    organization_member_id: str
    role_key: str
    role_name: str


class PublicProfileStateResponse(BaseModel):
    """Estado del perfil público más las membresías desde las que se puede activar."""

    profile: PublicProfileResponse
    eligible_memberships: list[EligibleMembershipResponse]


class CheckPublicSlugResponse(BaseModel):
    """Disponibilidad de un identificador de ponente."""

    available: bool


class PublicSpeakerHistoryItem(BaseModel):
    """Una participación del historial público de un ponente."""

    event_slug: str
    event_title: str
    session_id: str
    session_title: str
    starts_at: datetime
    role_key: str


class PublicSpeakerProfile(BaseModel):
    """Perfil público de un ponente tal y como lo ve cualquier visitante."""

    display_name: str
    public_slug: str
    fields: dict[str, Any]
    social_links: list[SocialLinkResponse]
    history: list[PublicSpeakerHistoryItem]
