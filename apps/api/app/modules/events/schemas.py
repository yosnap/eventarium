"""Esquemas del módulo de eventos y agenda."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.modules.organizations.schemas import SLUG_PATTERN
from app.modules.sponsors.schemas import PublicSponsorTier

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
    city: Annotated[str, Field(max_length=120)] | None = None
    online_url: Annotated[str, Field(max_length=500)] | None = None
    capacity: Annotated[int, Field(ge=1)] | None = None
    registration_mode: RegistrationMode = "free"
    # `None` (por defecto): la inscripción ya está abierta. Con fecha, el
    # listado y la ficha públicos muestran el evento como «próximamente»
    # mientras no se alcance.
    registration_opens_at: datetime | None = None
    email_verification_required: bool = True
    # Ventana de pago (fase 6 del PRD): minutos que tiene un comprador para
    # pagar antes de que su plaza reservada caduque. Rango igual al `CHECK` de
    # base de datos, para rechazar el valor en el schema y no solo allí.
    payment_checkout_window_minutes: Annotated[int, Field(ge=30, le=1439)] = 30

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
    city: Annotated[str, Field(max_length=120)] | None = None
    online_url: Annotated[str, Field(max_length=500)] | None = None
    capacity: Annotated[int, Field(ge=1)] | None = None
    registration_mode: RegistrationMode | None = None
    registration_opens_at: datetime | None = None
    email_verification_required: bool | None = None
    payment_checkout_window_minutes: Annotated[int, Field(ge=30, le=1439)] | None = None
    # Único campo de contabilidad editable desde este esquema (plan.md
    # Decisión #6): `budget_approved_at`/`contingency_fund_cents` nunca
    # viajan por aquí, solo por el servicio de `accounting`. El servicio de
    # eventos rechaza este campo si el presupuesto ya está aprobado.
    contingency_fund_percent: Annotated[Decimal, Field(ge=0, le=100)] | None = None
    # Plantilla visual del evento, del catálogo de la plataforma. `None` no
    # cambia nada (PATCH parcial); para volver a heredar la de la organización
    # se envía cadena vacía, que el servicio traduce a `NULL`.
    theme_template_id: str | None = None

    @model_validator(mode="after")
    def _validar_fechas(self) -> EventUpdate:
        if self.starts_at is not None and self.ends_at is not None:
            _validar_rango_de_fechas(self.starts_at, self.ends_at)
        return self

    @model_validator(mode="after")
    def _rechazar_null_explicito_en_contingency_fund_percent(self) -> EventUpdate:
        # `NUMERIC(5,2) NOT NULL` en `events`: a diferencia del resto de
        # campos de este schema, un `null` explícito aquí no significa "sin
        # cambios" (eso ya lo cubre `exclude_unset`), significa un valor
        # inválido que llegaría al `setattr` genérico de `update_event` y
        # rompería la constraint `NOT NULL` — y ese `IntegrityError` lo
        # capturaba la rama de conflicto de `slug`, devolviendo un 409 con el
        # mensaje falso "ya existe un evento con el identificador «None»".
        if (
            "contingency_fund_percent" in self.model_fields_set
            and self.contingency_fund_percent is None
        ):
            raise ValueError("`contingency_fund_percent` no admite `null`.")
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
    city: str | None
    online_url: str | None
    capacity: int | None
    registration_mode: RegistrationMode
    registration_opens_at: datetime | None
    email_verification_required: bool
    payment_checkout_window_minutes: int
    # Resultado de geocodificar `location_address` (Nominatim); nunca los rellena
    # el organizador directamente, ver `EventCreate`/`EventUpdate`.
    latitude: float | None
    longitude: float | None
    # Contabilidad por evento (PRD fase 7, plan.md Decisión #6): de solo
    # lectura aquí — `EventUpdate` no las incluye. `contingency_fund_percent`
    # es la única de las cuatro editable, y solo por el servicio de eventos,
    # no por `EventUpdate` genérico (fase 3 de trabajo de la contabilidad).
    contingency_fund_percent: Decimal
    budget_approved_at: datetime | None
    contingency_fund_cents: int | None
    accounting_currency: str
    # `None` significa que hereda la plantilla de la organización.
    theme_template_id: str | None


class EventVenueCreate(BaseModel):
    """Alta de una sede de un evento multisede."""

    name: Annotated[str, Field(min_length=1, max_length=160)]
    address: Annotated[str, Field(max_length=300)] | None = None
    capacity: Annotated[int, Field(ge=1)] | None = None
    display_order: int = 0


class EventVenueUpdate(BaseModel):
    """Campos editables de una sede."""

    name: Annotated[str, Field(min_length=1, max_length=160)] | None = None
    address: Annotated[str, Field(max_length=300)] | None = None
    capacity: Annotated[int, Field(ge=1)] | None = None
    display_order: int | None = None


class EventVenueResponse(BaseModel):
    """Sede tal y como la ve el panel de administración."""

    id: str
    name: str
    address: str | None
    capacity: int | None
    display_order: int
    latitude: float | None
    longitude: float | None
    geocoded_at: datetime | None


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
    venue_id: str | None = None

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
    venue_id: str | None = None

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
    venue_id: str | None
    # Necesario para el control de concurrencia optimista del `PUT` de
    # participantes: el cliente lo envía de vuelta como `expected_updated_at`.
    updated_at: datetime


class EventMemberCreate(BaseModel):
    """Alta de una persona en el roster de un evento.

    Se elige entre los miembros ya existentes de la organización (cualquier rol) —
    el alta de la propia membresía sigue siendo cosa de `admin/members`.
    """

    organization_member_id: str


class EventInvitationCreate(BaseModel):
    """Invitación de ponente desde el evento (fase 3 del plan de invitaciones).

    Sin `role_id`, el rol es `speaker` — el flujo por defecto. Se puede
    indicar otro (p. ej. un moderador) si el organizador lo necesita."""

    email: EmailStr
    role_id: str | None = None


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
    """Evento tal y como aparece en el listado público.

    `reserved_count` es el número de plazas realmente reservadas: `confirmed` +
    `pending_payment` dentro de su ventana de pago + promociones de lista de
    espera dentro de su ventana de confirmación — misma regla que
    `registrations.repository.count_reserved_registrations`. Nunca se expone el
    detalle de qué estado concreto ocupa cada plaza, solo el agregado.
    """

    slug: str
    title: str
    summary: str | None
    cover_url: str | None
    timezone: str
    starts_at: datetime
    ends_at: datetime
    location_mode: LocationMode
    location_name: str | None
    city: str | None
    registration_mode: RegistrationMode
    # `None`: la inscripción ya está abierta. Con fecha futura, el listado
    # muestra «próximamente» en vez de «abierto» (ver `Event.registration_opens_at`).
    registration_opens_at: datetime | None
    capacity: int | None
    reserved_count: int
    # Precio «desde» del tipo de entrada vigente más barato (`EventTicketType`,
    # módulo `payments`), solo con `registration_mode == "paid"`. `None` si el
    # evento es gratis o, siendo de pago, no tiene ningún tipo vigente ahora
    # mismo — nunca un precio inventado.
    price_from_cents: int | None
    price_currency: str | None
    # `True` solo si entre los tipos vigentes hay más de un precio *distinto*
    # (el front antepone «Desde»); con un único precio —un solo tipo o varios
    # al mismo importe— este campo va en `False` y se muestra el importe solo.
    price_multiple: bool


class PublicEventSession(BaseModel):
    """Sesión de la agenda tal y como se muestra en la página pública del evento."""

    id: str
    session_type: SessionType
    title: str
    description: str | None
    starts_at: datetime
    ends_at: datetime
    room: str | None
    # Sede (nivel superior a `room`) de la sesión; `None` si el evento no usa
    # sedes múltiples o la sesión no tiene ninguna asignada. Permite al
    # frontend agrupar la agenda por sede cuando el evento tiene 2 o más.
    venue_id: str | None
    video_platform: VideoPlatform | None
    video_url: str | None
    materials: list[dict[str, Any]]
    participants: list[PublicParticipant]


class PublicSessionDetail(PublicEventSession):
    """La misma sesión, con el enlace a su evento padre para la página propia."""

    event_slug: str
    event_title: str


class PublicVenue(BaseModel):
    """Sede tal y como se muestra en la página pública del evento, sin campos
    de auditoría (`display_order`/`geocoded_at` son detalle interno)."""

    id: str
    name: str
    address: str | None
    capacity: int | None
    latitude: float | None
    longitude: float | None


class PublicTheme(BaseModel):
    """Plantilla visual resuelta para una página pública.

    Se sirve **ya resuelta**, con la herencia aplicada en el servidor (evento →
    organización → por defecto del catálogo): el cliente no tiene que encadenar
    tres niveles ni conocer el catálogo para pintar la página.
    """

    id: str
    key: str
    name: str
    tokens: dict[str, Any]


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
    registration_opens_at: datetime | None
    # Plazas realmente reservadas, misma regla que `PublicEventSummary.reserved_count`
    # (`registrations.repository.count_reserved_registrations`): permite a la ficha
    # pintar la ocupación, no solo el aforo total.
    reserved_count: int
    # Mismo criterio que `PublicEventSummary.price_from_cents`/`price_multiple`.
    price_from_cents: int | None
    price_currency: str | None
    price_multiple: bool
    # Geocodificación de `location_address`, para el mapa del evento de una
    # sola sede. `None` si no hay dirección, el evento es `online` o falló.
    latitude: float | None
    longitude: float | None
    # Plantilla visual del evento, con la herencia ya resuelta. `None` solo si
    # el catálogo estuviera vacío, que no es un estado posible hoy.
    theme: PublicTheme | None = None
    sessions: list[PublicEventSession]
    # Ordenadas por `display_order`. El frontend decide, a partir de su
    # longitud, si activa la vista de "programa por sede" (2 sedes o más) —
    # decisión de tanda 3, aquí solo se exponen los datos.
    venues: list[PublicVenue] = Field(default_factory=list)
    sponsor_tiers: list[PublicSponsorTier] = Field(default_factory=list)


# --- Ponentes del evento (panel de organizador) ------------------------------


class SpeakerSessionOut(BaseModel):
    """Una sesión de la agenda donde el ponente está asignado."""

    id: str
    titulo: str
    starts_at: datetime | None


class SpeakerCompletitudOut(BaseModel):
    """Estado de la ficha del ponente, sobre las claves del perfil de ponente.

    `faltantes` nombra las claves sin rellenar para que el panel pueda decir
    «falta bio y foto» sin adivinarlo del porcentaje.
    """

    porcentaje: int
    rellenas: int
    total: int
    faltantes: list[str]


class SpeakerRowOut(BaseModel):
    """Fila de la vista agregada de ponentes de un evento."""

    organization_member_id: str
    user_id: str
    email: str
    first_name: str | None
    last_name: str | None
    # Titular profesional de su ficha (`profile_data.titular`), para pintar
    # bajo el nombre; `None` si no lo rellenó.
    titular: str | None
    sesiones: list[SpeakerSessionOut]
    completitud: SpeakerCompletitudOut
    # Eventos de esta organización donde la persona está en el roster,
    # incluido el actual: primera participación = 1, repetir = más de 1.
    ediciones: int
    # Slug del perfil público si la persona lo activó; `None` si no.
    public_slug: str | None


class EventSpeakersViewOut(BaseModel):
    """Vista agregada de ponentes, con el total de sesiones del evento."""

    items: list[SpeakerRowOut]
    total_sesiones: int


class SpeakerHistoryItemOut(BaseModel):
    """Una línea del historial de participación de una persona."""

    evento_titulo: str
    # Rol con el que participó en esa sesión; `None` si la asignación no lo
    # fija.
    rol: str | None
    fecha: datetime | None
