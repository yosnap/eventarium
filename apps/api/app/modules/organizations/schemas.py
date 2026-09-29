"""Esquemas del módulo de organizaciones."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.security import password_meets_complexity

SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"


class PublicOrganizationRef(BaseModel):
    """Organización tal y como aparece en un contrato público (URL y miga).

    `page_public` indica si la organización tiene página pública propia; la
    miga enlaza a `/{slug}` solo cuando es `true`.
    """

    slug: str
    name: str
    # `true` si la organización activó su página pública (`/{slug}`): la miga
    # solo enlaza a ella en ese caso.
    page_public: bool = False


_RUTAS_DE_LA_APLICACION = frozenset(
    {
        "acceder", "account", "admin", "agenda", "analitica-externa", "branding",
        "cancelar-inscripcion", "check-in", "confirmar-promocion", "contabilidad",
        "correo", "crear-organizacion", "cuenta", "dashboard", "descuentos", "diseno",
        "editar", "entradas", "espacio-de-trabajo", "estilo", "eventos", "events", "ia",
        "identidad", "inscripciones", "invitacion", "legal", "legales", "mcp", "members",
        "mi-entrada", "mis-eventos", "oauth", "organization", "pago", "patrocinadores",
        "payments", "plantillas", "politicas", "ponentes", "recuperar-contrasena",
        "registrations", "registro", "roles", "servicios", "sponsor-tiers", "stripe",
        "suplantar", "usuarios", "verificar-correo", "verificar-inscripcion",
    }
)  # fmt: skip
_RUTAS_DEL_PROXY = frozenset({"healthz", ".well-known", "media"})
_TERMINOS_DE_CONFIANZA = frozenset(
    {
        "organizaciones", "organizations", "organizador", "organizadores", "plataforma",
        "platform", "eventarium", "oficial", "official", "soporte", "ayuda", "seguridad",
        "security", "privacidad", "privacy", "terminos", "terms", "cookies", "pagos",
        "facturacion", "billing", "login", "logout", "signup", "staff", "equipo", "team",
        "root", "administrador", "administrator", "moderador", "moderator", "noreply",
        "postmaster", "abuse", "contacto", "contact", "about", "acerca", "tickets",
        "categorias", "categorias-de-eventos", "etiquetas", "tags", "search", "buscar",
    }
)  # fmt: skip

# Identificadores que no puede reclamar una organización: colisionarían con una
# ruta de la aplicación (la organización pasa a ser el primer segmento de la URL
# pública, `/{org}/{evento}`), con el proxy inverso, con la propia instalación o
# con nombres que alguien podría dar por hecho que son de la plataforma. Se
# aplica igual en `check-slug`, en la creación por autoservicio y en el alta por
# superadmin o CLI: la comprobación previa no puede prometer disponibilidad que
# la creación real luego rechace.
RESERVED_SLUGS = (
    frozenset(
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
    )  # fmt: skip
    | _RUTAS_DE_LA_APLICACION
    | _RUTAS_DEL_PROXY
    | _TERMINOS_DE_CONFIANZA
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
    # str, no EmailStr: misma razón que MemberResponse.email.
    contact_email: str | None = None
    address: str | None = None
    # Sin valor por defecto: un constructor que se olvide de pasarlo falla en
    # tipos en vez de devolver un `false` falso.
    public_page_enabled: bool
    is_active: bool


class OrganizationUpdate(BaseModel):
    """Campos editables de la organización."""

    name: Annotated[str, Field(min_length=1, max_length=160)] | None = None
    legal_name: Annotated[str, Field(max_length=200)] | None = None
    description: str | None = None
    website: Annotated[str, Field(max_length=300, pattern=r"^https?://\S+$")] | None = None
    contact_email: EmailStr | None = None
    address: Annotated[str, Field(max_length=300)] | None = None
    public_page_enabled: bool | None = None

    @field_validator("address")
    @classmethod
    def _direccion_sin_blancos(cls, valor: str | None) -> str | None:
        # Una dirección de solo espacios se guarda como «sin dirección».
        return (valor.strip() or None) if valor is not None else None

    @field_validator("public_page_enabled")
    @classmethod
    def _sin_null_en_el_interruptor(cls, valor: bool | None) -> bool | None:
        # Columna `NOT NULL`: un `null` explícito no significa «sin cambios»
        # (eso ya lo cubre `exclude_unset`), significa un valor inválido.
        if valor is None:
            raise ValueError("`public_page_enabled` no admite `null`.")
        return valor


class SocialLinkInput(BaseModel):
    """Enlace social del organizador."""

    kind: Annotated[str, Field(min_length=1, max_length=40)]
    url: Annotated[str, Field(min_length=1, max_length=500, pattern=r"^https?://")]


class BrandingUpdate(BaseModel):
    """Identidad visual editable desde el panel."""

    # `None` = la plantilla de tema por defecto de la plataforma. Un id que
    # no exista en el catálogo es un 422 (comprobado en el router: aquí solo
    # se valida la forma del dato, no su existencia).
    theme_template_id: str | None = None
    social_links: list[SocialLinkInput] = Field(default_factory=list)
    organizer_blurb: str | None = None


class BrandingAdminResponse(BaseModel):
    """Branding tal y como lo ve el panel de administración."""

    theme_template_id: str | None = None
    social_links: list[dict[str, Any]]
    organizer_blurb: str | None = None
    logo_url: str | None = None
    favicon_url: str | None = None


class MemberRoleOut(BaseModel):
    """Un rol concreto de una persona, con la fila de membresía que lo sostiene.

    `id` es el `organization_member_id` de **esa** fila — hace falta tal cual
    para quitar justo ese rol (`DELETE /me/members/{id}`) o para referenciarlo
    desde otro sitio que necesite una membresía concreta, no la persona
    (el roster de un evento, `event_members.organization_member_id`)."""

    id: str
    role_id: str
    role_key: str
    role_name: str


class MemberResponse(BaseModel):
    """Una persona de la organización, con **todos** sus roles.

    Fase 4 del plan de invitaciones: antes esto era una fila por rol
    (`role_id`/`role_key` sueltos), así que la misma persona con dos roles
    aparecía dos veces sin nada que dijera que eran la misma. `profile_data`
    es el de la membresía con más campos rellenos (empate → la más antigua):
    es el que más sirve para mostrar de un vistazo, y evita fragmentar sus
    datos como advierte `SpeakerPublicProfile` (`events/models.py`)."""

    user_id: str
    # str, no EmailStr: un email de dominio reservado (p. ej. example.test)
    # ya guardado reventaría la lectura completa de miembros al validar de
    # nuevo al serializar. El formato se valida en la entrada, no aquí.
    email: str
    first_name: str | None
    last_name: str | None
    roles: list[MemberRoleOut]
    profile_data: dict[str, Any]


class MemberCreate(BaseModel):
    """Alta de un miembro por correo electrónico."""

    email: EmailStr
    first_name: Annotated[str, Field(min_length=1, max_length=100)]
    last_name: Annotated[str, Field(min_length=1, max_length=100)]
    role_id: str
    profile_data: dict[str, Any] = Field(default_factory=dict)


class InvitationCreate(BaseModel):
    """Alta de una invitación de equipo: solo email y rol.

    Sin `first_name`/`last_name` — quien invita por correo no sabe cómo se
    llama la persona; lo completa ella al aceptar (fase 2)."""

    email: EmailStr
    role_id: str


class InvitationResponse(BaseModel):
    """Invitación tal y como la ve el organizador, con el estado calculado."""

    id: str
    # str, no EmailStr: misma razón que MemberResponse.email — lo validado
    # en la entrada no se revalida al leer.
    email: str
    role_id: str
    role_key: str
    event_id: str | None
    # pendiente | aceptada | revocada | caducada (calculado, ver
    # `invitations_service.estado_efectivo`).
    estado: str
    expires_at: datetime
    created_at: datetime


class InvitationCreateResponse(BaseModel):
    """Resultado de `POST /organizations/me/invitations`.

    `status="added"` cuando el correo ya tenía cuenta (regla A.2: se añade
    directamente, sin token); `status="invited"` cuando se ha creado la
    invitación. Nunca lleva el token: eso solo viaja al correo (fase 2)."""

    status: Literal["added", "invited"]
    member: MemberResponse | None = None
    invitation: InvitationResponse | None = None


class InvitationPublicResponse(BaseModel):
    """`GET /public/invitations/{token}`: lo mínimo para pintar la pantalla.

    Nunca la lista de miembros ni ningún otro dato de negocio (requisito de
    seguridad del PRD) — solo lo que hace falta para decir «te han invitado a
    X con el rol Y»."""

    organization_name: str
    role_name: str
    # `True` en el caso anómalo: la fase 1 no emite token si el correo ya
    # tenía cuenta al invitar, pero pudo ganar una contraseña después por
    # otra vía (p. ej. una recuperación). La pantalla lo dice y ofrece entrar
    # en vez de mostrar el formulario de nombre y contraseña.
    account_has_password: bool


class InvitationTokenErrorResponse(BaseModel):
    """Token inválido, caducado, revocado o ya aceptado: un mensaje por caso."""

    state: Literal["invalida", "caducada", "revocada", "aceptada"]
    message: str


class InvitationAcceptRequest(BaseModel):
    """Datos que completa la persona invitada al aceptar."""

    first_name: Annotated[str, Field(min_length=1, max_length=100)]
    last_name: Annotated[str, Field(min_length=1, max_length=100)]
    password: str = Field(
        min_length=8,
        max_length=256,
        description=(
            "Contraseña: mínimo 8 caracteres, con mayúscula, minúscula, número y carácter especial"
        ),
    )

    @field_validator("password")
    @classmethod
    def _validar_complejidad(cls, valor: str) -> str:
        if not password_meets_complexity(valor):
            raise ValueError(
                "La contraseña debe tener mínimo 8 caracteres, una mayúscula, una "
                "minúscula, un número y un carácter especial."
            )
        return valor


class InvitationAcceptResponse(BaseModel):
    """Confirmación de alta. Sin `host`: la petición ya llegó al dominio
    correcto (el enlace del correo apunta al propio de la organización), así
    que no hace falta redirigir a ningún otro sitio."""

    organization_slug: str


class OrganizationCreate(BaseModel):
    """Alta de organización (solo superadmin)."""

    slug: Annotated[str, Field(min_length=2, max_length=60, pattern=SLUG_PATTERN)]
    name: Annotated[str, Field(min_length=1, max_length=160)]
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
    """Organización recién creada, con una sesión completa ya activa en ella.

    Sin dominio por organización (fase 4 del plan de organización sin
    dominio), no hay ningún host al que redirigir: quien crea la
    organización puede venir de verificar su correo, sin ninguna sesión
    normal todavía (sin cookie de refresco), así que este endpoint emite la
    suya propia — mismo mecanismo que `/auth/login`, con la organización
    recién creada ya activa. El cliente no necesita llamar aparte a
    `switch-organization`.
    """

    id: str
    slug: str
    access_token: str
    expires_in: int


class CheckSlugResponse(BaseModel):
    """Disponibilidad de un identificador de organización."""

    available: bool


class PublicSocialLink(BaseModel):
    kind: str
    url: str


class PublicOrganizationProfile(BaseModel):
    """Lo único que una organización hace público con su página `/{slug}`.

    Esquema explícito, sin `from_attributes` y sin reutilizar
    `OrganizationResponse`: un campo nuevo en el modelo no llega aquí por
    accidente. Nunca `legal_name` ni `contact_email`.
    """

    slug: str
    name: str
    description: str | None
    website: str | None
    address: str | None
    logo_url: str | None
    social_links: list[PublicSocialLink]
