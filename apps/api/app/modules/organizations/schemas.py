"""Esquemas del módulo de organizaciones."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field

SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"

# Subdominios que no puede reclamar el autoservicio: colisionarían con la propia
# instalación o con nombres que alguien podría dar por hecho que están reservados al
# operador. Se aplica igual en `check-slug` que en la creación: la comprobación previa
# no puede prometer disponibilidad que la creación real luego rechace.
RESERVED_SLUGS = frozenset(
    {
        "www",
        "api",
        "admin",
        "mail",
        "app",
        "media",
        "static",
        "assets",
        "docs",
        "status",
        "support",
        "help",
        "blog",
        "cdn",
    }
)


class OrganizationResponse(BaseModel):
    """Datos de la organización actual."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    slug: str
    name: str
    legal_name: str | None = None
    description: str | None = None
    website: str | None = None
    contact_email: EmailStr | None = None
    is_active: bool


class OrganizationUpdate(BaseModel):
    """Campos editables de la organización."""

    name: Annotated[str, Field(min_length=1, max_length=160)] | None = None
    legal_name: Annotated[str, Field(max_length=200)] | None = None
    description: str | None = None
    website: Annotated[str, Field(max_length=300)] | None = None
    contact_email: EmailStr | None = None


class SocialLinkInput(BaseModel):
    """Enlace social del organizador."""

    kind: Annotated[str, Field(min_length=1, max_length=40)]
    url: Annotated[str, Field(min_length=1, max_length=500, pattern=r"^https?://")]


class BrandingUpdate(BaseModel):
    """Identidad visual editable desde el panel."""

    template_key: Annotated[str, Field(min_length=1, max_length=40)] = "classic"
    colors: dict[str, str] = Field(default_factory=dict)
    fonts: dict[str, str] = Field(default_factory=dict)
    social_links: list[SocialLinkInput] = Field(default_factory=list)
    organizer_blurb: str | None = None


class BrandingAdminResponse(BaseModel):
    """Branding tal y como lo ve el panel de administración."""

    template_key: str
    colors: dict[str, Any]
    fonts: dict[str, Any]
    social_links: list[dict[str, Any]]
    organizer_blurb: str | None = None
    logo_url: str | None = None
    favicon_url: str | None = None


class MemberResponse(BaseModel):
    """Miembro de la organización."""

    id: str
    user_id: str
    email: EmailStr
    first_name: str | None
    last_name: str | None
    role_id: str
    role_key: str
    profile_data: dict[str, Any]


class MemberCreate(BaseModel):
    """Alta de un miembro por correo electrónico."""

    email: EmailStr
    first_name: Annotated[str, Field(min_length=1, max_length=100)]
    last_name: Annotated[str, Field(min_length=1, max_length=100)]
    role_id: str
    profile_data: dict[str, Any] = Field(default_factory=dict)


class OrganizationCreate(BaseModel):
    """Alta de organización (solo superadmin)."""

    slug: Annotated[str, Field(min_length=2, max_length=60, pattern=SLUG_PATTERN)]
    name: Annotated[str, Field(min_length=1, max_length=160)]
    host: Annotated[str, Field(min_length=3, max_length=255)]
    legal_name: Annotated[str, Field(max_length=200)] | None = None
    contact_email: EmailStr | None = None


class SelfServiceOrganizationCreate(BaseModel):
    """Alta de organización por autoservicio (persona ya verificada)."""

    name: Annotated[str, Field(min_length=1, max_length=160)]
    slug: Annotated[str, Field(min_length=2, max_length=60, pattern=SLUG_PATTERN)]
    first_name: Annotated[str, Field(min_length=1, max_length=100)]
    last_name: Annotated[str, Field(min_length=1, max_length=100)]
    turnstile_token: str = Field(description="Token del widget de Turnstile")


class SelfServiceOrganizationResponse(BaseModel):
    """Organización recién creada.

    Sin token de sesión: el subdominio nuevo es un origen distinto de donde se ha
    llamado a este endpoint (normalmente el dominio principal de la instalación), así
    que ninguna cookie ni token en memoria viajaría con la persona hasta allí. El
    cliente redirige a `host` y la persona entra con su correo y contraseña, esta vez
    con éxito porque ya pertenece a una organización.
    """

    id: str
    slug: str
    host: str


class CheckSlugResponse(BaseModel):
    """Disponibilidad de un identificador de organización."""

    available: bool


class DomainCreate(BaseModel):
    """Alta de dominio (solo superadmin)."""

    host: Annotated[str, Field(min_length=3, max_length=255)]
    is_primary: bool = False


class DomainResponse(BaseModel):
    """Dominio asociado a una organización."""

    id: str
    host: str
    is_primary: bool
