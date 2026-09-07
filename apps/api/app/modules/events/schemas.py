"""Esquemas del módulo de eventos y agenda."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.modules.organizations.schemas import SLUG_PATTERN

EventStatus = Literal["draft", "published", "archived"]
EventVisibility = Literal["public", "hidden", "private"]
LocationMode = Literal["in_person", "online", "hybrid"]
RegistrationMode = Literal["free", "approval", "paid"]
SessionType = Literal["talk", "break", "service", "other"]
VideoPlatform = Literal["youtube", "vimeo", "twitch", "other"]


def _validar_rango_de_fechas(starts_at: datetime, ends_at: datetime) -> None:
    if ends_at <= starts_at:
        raise ValueError("La fecha de fin debe ser posterior a la de inicio.")


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
