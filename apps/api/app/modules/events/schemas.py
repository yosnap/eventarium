"""Esquemas del módulo de eventos y agenda."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, model_validator

from app.modules.organizations.schemas import SLUG_PATTERN

EventStatus = Literal["draft", "published", "archived"]
EventVisibility = Literal["public", "hidden", "private"]
LocationMode = Literal["in_person", "online", "hybrid"]
RegistrationMode = Literal["free", "approval", "paid"]
SessionType = Literal["talk", "break", "service", "other"]
VideoPlatform = Literal["youtube", "vimeo", "twitch", "other"]

# Dominios admitidos por plataforma declarada. Para «other» basta con `https`: no
# hay una plataforma conocida que restringir, pero el enlace igualmente no puede
# sustituirse por un `iframe`/enlace desde un dominio arbitrario sin cifrar.
_DOMINIOS_POR_PLATAFORMA: dict[str, tuple[str, ...]] = {
    "youtube": ("youtube.com", "youtu.be"),
    "vimeo": ("vimeo.com",),
    "twitch": ("twitch.tv",),
}


def _validar_rango_de_fechas(starts_at: datetime, ends_at: datetime) -> None:
    if ends_at <= starts_at:
        raise ValueError("La fecha de fin debe ser posterior a la de inicio.")


def validate_video_url(platform: str | None, url: str | None) -> None:
    """`video_url` exige `https` y, si la plataforma es conocida, un dominio de su
    lista — para no acabar sirviendo un `iframe`/enlace controlado por terceros
    desde el propio dominio de la organización."""
    if url is None:
        return
    if not url.startswith("https://"):
        raise ValueError("El enlace del vídeo debe usar https.")
    dominios = _DOMINIOS_POR_PLATAFORMA.get(platform or "")
    if dominios is None:
        return
    host = (urlparse(url).hostname or "").lower()
    if not any(host == dominio or host.endswith(f".{dominio}") for dominio in dominios):
        raise ValueError(
            f"El enlace del vídeo debe pertenecer a {' o '.join(dominios)} "
            f"para la plataforma «{platform}»."
        )


def validate_materials(materials: list[dict[str, Any]]) -> None:
    """Cada material con `url` exige `https`, mismo motivo que `video_url`."""
    for material in materials:
        url = material.get("url")
        if url is not None and not str(url).startswith("https://"):
            raise ValueError("El enlace de cada material debe usar https.")


class EventCreate(BaseModel):
    """Alta de un evento."""

    slug: Annotated[str, Field(min_length=2, max_length=160, pattern=SLUG_PATTERN)]
    title: Annotated[str, Field(min_length=1, max_length=200)]
    summary: str | None = None
    description: str | None = None
    status: EventStatus = "draft"
    visibility: EventVisibility = "public"
    timezone: Annotated[str, Field(min_length=1, max_length=60)] = "Europe/Madrid"
    starts_at: datetime
    ends_at: datetime
    location_mode: LocationMode
    location_name: Annotated[str, Field(max_length=200)] | None = None
    location_address: Annotated[str, Field(max_length=300)] | None = None
    online_url: Annotated[str, Field(max_length=500)] | None = None
    capacity: Annotated[int, Field(ge=1)] | None = None
    registration_mode: RegistrationMode = "free"
    email_verification_required: bool = True

    @model_validator(mode="after")
    def _validar_fechas(self) -> EventCreate:
        _validar_rango_de_fechas(self.starts_at, self.ends_at)
        return self


class EventUpdate(BaseModel):
    """Campos editables de un evento. `status` incluido: así se publica o archiva."""

    title: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    summary: str | None = None
    description: str | None = None
    status: EventStatus | None = None
    visibility: EventVisibility | None = None
    timezone: Annotated[str, Field(min_length=1, max_length=60)] | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    location_mode: LocationMode | None = None
    location_name: Annotated[str, Field(max_length=200)] | None = None
    location_address: Annotated[str, Field(max_length=300)] | None = None
    online_url: Annotated[str, Field(max_length=500)] | None = None
    capacity: Annotated[int, Field(ge=1)] | None = None
    registration_mode: RegistrationMode | None = None
    email_verification_required: bool | None = None

    @model_validator(mode="after")
    def _validar_fechas(self) -> EventUpdate:
        if self.starts_at is not None and self.ends_at is not None:
            _validar_rango_de_fechas(self.starts_at, self.ends_at)
        return self


class EventResponse(BaseModel):
    """Evento tal y como lo ve el panel de administración."""

    id: str
    slug: str
    title: str
    summary: str | None
    description: str | None
    cover_url: str | None
    status: EventStatus
    visibility: EventVisibility
    timezone: str
    starts_at: datetime
    ends_at: datetime
    location_mode: LocationMode
    location_name: str | None
    location_address: str | None
    online_url: str | None
    capacity: int | None
    registration_mode: RegistrationMode
    email_verification_required: bool


class EventSessionCreate(BaseModel):
    """Alta de una sesión de agenda."""

    session_type: SessionType
    title: Annotated[str, Field(min_length=1, max_length=200)]
    description: str | None = None
    starts_at: datetime
    ends_at: datetime
    room: Annotated[str, Field(max_length=120)] | None = None
    video_platform: VideoPlatform | None = None
    video_url: Annotated[str, Field(max_length=500)] | None = None
    materials: list[dict[str, Any]] = Field(default_factory=list)
    sort_order: int = 0

    @model_validator(mode="after")
    def _validar_fechas(self) -> EventSessionCreate:
        _validar_rango_de_fechas(self.starts_at, self.ends_at)
        validate_video_url(self.video_platform, self.video_url)
        validate_materials(self.materials)
        return self


class EventSessionUpdate(BaseModel):
    """Campos editables de una sesión."""

    session_type: SessionType | None = None
    title: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    description: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    room: Annotated[str, Field(max_length=120)] | None = None
    video_platform: VideoPlatform | None = None
    video_url: Annotated[str, Field(max_length=500)] | None = None
    materials: list[dict[str, Any]] | None = None
    sort_order: int | None = None

    @model_validator(mode="after")
    def _validar_fechas(self) -> EventSessionUpdate:
        if self.starts_at is not None and self.ends_at is not None:
            _validar_rango_de_fechas(self.starts_at, self.ends_at)
        return self


class EventSessionResponse(BaseModel):
    """Sesión de agenda tal y como la ve el panel de administración."""

    id: str
    session_type: SessionType
    title: str
    description: str | None
    starts_at: datetime
    ends_at: datetime
    room: str | None
    video_platform: VideoPlatform | None
    video_url: str | None
    materials: list[dict[str, Any]]
    sort_order: int
    # Necesario para el control de concurrencia optimista del `PUT` de
    # participantes: el cliente lo envía de vuelta como `expected_updated_at`.
    updated_at: datetime


class EventMemberCreate(BaseModel):
    """Alta de una persona en el roster de un evento.

    Se elige entre los miembros ya existentes de la organización (cualquier rol) —
    el alta de la propia membresía sigue siendo cosa de `admin/members`.
    """

    organization_member_id: str


class EventMemberResponse(BaseModel):
    """Persona del roster de un evento, con los datos que hacen falta para
    mostrarla en el selector de participantes de una sesión."""

    id: str
    organization_member_id: str
    user_id: str
    email: str
    first_name: str | None
    last_name: str | None
    role_key: str


class SessionParticipantEntry(BaseModel):
    """Una asignación dentro del reemplazo completo de participantes de una sesión."""

    event_member_id: str
    role_key: Annotated[str, Field(min_length=1, max_length=60)]


class SessionParticipantsUpdate(BaseModel):
    """Reemplazo completo de la lista de participantes de una sesión.

    `expected_updated_at` es el `updated_at` de la sesión que el cliente tenía
    cargado: si no coincide con el actual, la petición falla con 409 en vez de
    sobrescribir en silencio el trabajo de otra persona.
    """

    expected_updated_at: datetime
    participants: list[SessionParticipantEntry]


class SessionParticipantResponse(BaseModel):
    """Participación de una persona en una sesión, con su rol libre."""

    id: str
    event_member_id: str
    user_id: str
    email: str
    first_name: str | None
    last_name: str | None
    role_key: str
    sort_order: int


class PublicParticipant(BaseModel):
    """Participante tal y como se muestra en las páginas públicas.

    Nunca lleva el correo — a diferencia de `SessionParticipantResponse`, que es
    para el panel de administración. `public_slug` solo está presente si esa
    persona activó su perfil público; si no, es `None` y la página no enlaza a
    ningún sitio.
    """

    display_name: str
    role_key: str
    public_slug: str | None


class PublicEventSummary(BaseModel):
    """Evento tal y como aparece en el listado público."""

    slug: str
    title: str
    summary: str | None
    cover_url: str | None
    timezone: str
    starts_at: datetime
    ends_at: datetime
    location_mode: LocationMode
    location_name: str | None


class PublicEventSession(BaseModel):
    """Sesión de la agenda tal y como se muestra en la página pública del evento."""

    id: str
    session_type: SessionType
    title: str
    description: str | None
    starts_at: datetime
    ends_at: datetime
    room: str | None
    video_platform: VideoPlatform | None
    video_url: str | None
    materials: list[dict[str, Any]]
    participants: list[PublicParticipant]


class PublicSessionDetail(PublicEventSession):
    """La misma sesión, con el enlace a su evento padre para la página propia."""

    event_slug: str
    event_title: str


class PublicEventDetail(BaseModel):
    """Evento publicado con su agenda completa, para la página pública de detalle."""

    slug: str
    title: str
    summary: str | None
    description: str | None
    cover_url: str | None
    timezone: str
    starts_at: datetime
    ends_at: datetime
    location_mode: LocationMode
    location_name: str | None
    location_address: str | None
    online_url: str | None
    capacity: int | None
    registration_mode: RegistrationMode
    sessions: list[PublicEventSession]
