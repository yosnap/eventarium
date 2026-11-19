"""Esquemas del módulo de eventos y agenda."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    AfterValidator,
    BaseModel,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)

from app.core.mensajes import marcar
from app.modules.events.categories import normalizar_etiquetas
from app.modules.nearby.schemas import PublicNearbyPlace
from app.modules.organizations.schemas import SLUG_PATTERN, PublicOrganizationRef
from app.modules.sponsors.schemas import PublicSponsorTier
from app.modules.theme_templates.schemas import PublicTheme, validar_theme_overrides
from app.modules.translations.schemas import ContentLocaleInfo

EventStatus = Literal["draft", "published", "archived", "cancelled"]
# Lo que se acepta al crear o editar: `cancelled` no está porque solo se llega
# con `cancelar_evento`, que además cancela inscripciones, reembolsa y avisa.
# Con un PATCH se cancelaría el evento sin nada de eso.
EventStatusInput = Literal["draft", "published", "archived"]
EventVisibility = Literal["public", "hidden", "private"]
LocationMode = Literal["in_person", "online", "hybrid"]
RegistrationMode = Literal["free", "approval", "paid"]
TicketSalesState = Literal["open", "upcoming", "closed"]
# Horas antes del inicio a las que sale el recordatorio a los inscritos. Mismo
# conjunto que el `CHECK` de base de datos, el MCP y el desplegable del panel.
ReminderHours = Literal[2, 6, 12, 24, 48, 72]

# Markdown del editor del panel (o de la API/MCP). El tope protege la ficha
# pública, que lo convierte y sanea en el navegador de cada visitante, y el
# propio editor, que lo carga entero.
LONGITUD_MAXIMA_DESCRIPCION = 20000
DescripcionDeEvento = Annotated[str, Field(max_length=LONGITUD_MAXIMA_DESCRIPCION)]
SessionType = Literal["talk", "workshop", "break", "service", "other"]
VideoPlatform = Literal["youtube", "vimeo", "twitch", "other"]

# Dominios admitidos por plataforma declarada. Para «other» basta con `https`: no
# hay una plataforma conocida que restringir, pero el enlace igualmente no puede
# sustituirse por un `iframe`/enlace desde un dominio arbitrario sin cifrar.
_DOMINIOS_POR_PLATAFORMA: dict[str, tuple[str, ...]] = {
    "youtube": ("youtube.com", "youtu.be"),
    "vimeo": ("vimeo.com",),
    "twitch": ("twitch.tv",),
}
# Un mensaje por plataforma, para que cada uno sea un literal traducible.
_ENLACE_FUERA_DE_LA_PLATAFORMA: dict[str, str] = {
    "youtube": marcar(
        "El enlace del vídeo debe pertenecer a youtube.com o youtu.be para la plataforma «youtube»."
    ),
    "vimeo": marcar("El enlace del vídeo debe pertenecer a vimeo.com para la plataforma «vimeo»."),
    "twitch": marcar(
        "El enlace del vídeo debe pertenecer a twitch.tv para la plataforma «twitch»."
    ),
}
# `null` explícito en campos de `EventUpdate` que no lo admiten.
_NO_ADMITE_NULL: dict[str, str] = {
    "contingency_fund_percent": marcar("`contingency_fund_percent` no admite `null`."),
    "reminder_enabled": marcar("`reminder_enabled` no admite `null`."),
    "reminder_hours_before": marcar("`reminder_hours_before` no admite `null`."),
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
        raise ValueError(marcar("El enlace del vídeo debe usar https."))
    dominios = _DOMINIOS_POR_PLATAFORMA.get(platform or "")
    if dominios is None:
        return
    host = (urlparse(url).hostname or "").lower()
    if not any(host == dominio or host.endswith(f".{dominio}") for dominio in dominios):
        raise ValueError(_ENLACE_FUERA_DE_LA_PLATAFORMA[platform or ""])  # mensaje marcado


def validate_materials(materials: list[dict[str, Any]]) -> None:
    """Cada material con `url` exige `https`, mismo motivo que `video_url`."""
    for material in materials:
        url = material.get("url")
        if url is not None and not str(url).startswith("https://"):
            raise ValueError(marcar("El enlace de cada material debe usar https."))


class EventCategoryOut(BaseModel):
    """Categoría del catálogo de instalación, tal y como la ve el panel."""

    id: str
    slug: str
    name: str
    display_order: int
    is_active: bool


class PublicCategoryRef(BaseModel):
    """La categoría de un evento en los contratos públicos."""

    slug: str
    name: str


class EventCategoryCreate(BaseModel):
    slug: Annotated[str, Field(min_length=2, max_length=40, pattern=SLUG_PATTERN)]
    name: Annotated[str, Field(min_length=1, max_length=80)]
    display_order: Annotated[int, Field(ge=0, le=10000)] = 0
    is_active: bool = True


class EventCategoryUpdate(BaseModel):
    """El identificador (`slug`) no se cambia: forma parte de las URLs de filtro."""

    name: Annotated[str, Field(min_length=1, max_length=80)] | None = None
    display_order: Annotated[int, Field(ge=0, le=10000)] | None = None
    is_active: bool | None = None


def _etiquetas_normalizadas(valor: list[str]) -> list[str]:
    return normalizar_etiquetas(valor)


def _zona_horaria_valida(valor: str | None) -> str | None:
    """Una zona IANA que `zoneinfo` conozca: con otra, las horas de los correos
    del evento no se podrían calcular."""
    if valor is None:
        return None
    try:
        ZoneInfo(valor)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("La zona horaria no es válida: usa una del tipo «Europe/Madrid».") from exc
    return valor


class EventCreate(BaseModel):
    """Alta de un evento."""

    slug: Annotated[str, Field(min_length=2, max_length=160, pattern=SLUG_PATTERN)]
    title: Annotated[str, Field(min_length=1, max_length=200)]
    summary: str | None = None
    description: DescripcionDeEvento | None = None
    # Id de una categoría **activa** del catálogo, o `None` (sin categoría).
    category_id: str | None = None
    # Minúsculas, máx. 10, 2–30 caracteres; ver `categories.normalizar_etiquetas`.
    tags: list[str] = Field(default_factory=list)
    status: EventStatusInput = "draft"
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
    reminder_enabled: bool = True
    # Sin valor, el servicio pone 24 h (48 h en eventos de pago).
    reminder_hours_before: ReminderHours | None = None

    @field_validator("timezone")
    @classmethod
    def _validar_zona(cls, valor: str | None) -> str | None:
        return _zona_horaria_valida(valor)

    @model_validator(mode="after")
    def _validar_fechas(self) -> EventCreate:
        _validar_rango_de_fechas(self.starts_at, self.ends_at)
        return self

    @field_validator("tags")
    @classmethod
    def _normalizar_tags(cls, valor: list[str]) -> list[str]:
        return _etiquetas_normalizadas(valor)


class EventUpdate(BaseModel):
    """Campos editables de un evento. `status` incluido: así se publica o archiva."""

    # Al cambiar las fechas: mover también las sesiones de la agenda el mismo
    # intervalo que el inicio. Sin él, si alguna quedara fuera, la API responde
    # 409 (`sesiones_fuera_de_rango`) para que el panel pregunte.
    mover_sesiones: bool = False

    title: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    summary: str | None = None
    description: DescripcionDeEvento | None = None
    # `null` explícito **quita** la categoría; si el campo no viene, no cambia.
    category_id: str | None = None
    # Si no viene, no cambia; `[]` quita todas. `null` no es válido.
    tags: list[str] | None = None
    status: EventStatusInput | None = None
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
    reminder_enabled: bool | None = None
    reminder_hours_before: ReminderHours | None = None

    @field_validator("timezone")
    @classmethod
    def _validar_zona(cls, valor: str | None) -> str | None:
        return _zona_horaria_valida(valor)

    # Único campo de contabilidad editable desde este esquema (plan.md
    # Decisión #6): `budget_approved_at`/`contingency_fund_cents` nunca
    # viajan por aquí, solo por el servicio de `accounting`. El servicio de
    # eventos rechaza este campo si el presupuesto ya está aprobado.
    contingency_fund_percent: Annotated[Decimal, Field(ge=0, le=100)] | None = None
    # Plantilla visual del evento, del catálogo de la plataforma. `None` no
    # cambia nada (PATCH parcial); para volver a heredar la de la organización
    # se envía cadena vacía, que el servicio traduce a `NULL`.
    theme_template_id: str | None = None
    # Ajustes de color/fuente sobre la plantilla resuelta. Semántica DISTINTA
    # de `theme_template_id` (a propósito, no un descuido): campo AUSENTE del
    # body = sin cambios (PATCH parcial, `exclude_unset`); un `null` EXPLÍCITO
    # = borra los overrides existentes; un objeto = lo reemplaza entero, no
    # se fusiona con el anterior.
    theme_overrides: dict[str, Any] | None = None

    @field_validator("theme_overrides")
    @classmethod
    def _validar_theme_overrides(cls, valor: dict[str, Any] | None) -> dict[str, Any] | None:
        return validar_theme_overrides(valor)

    @model_validator(mode="after")
    def _validar_fechas(self) -> EventUpdate:
        if self.starts_at is not None and self.ends_at is not None:
            _validar_rango_de_fechas(self.starts_at, self.ends_at)
        return self

    @field_validator("tags")
    @classmethod
    def _normalizar_tags(cls, valor: list[str] | None) -> list[str] | None:
        if valor is None:
            raise ValueError("`tags` no admite `null`: usa una lista vacía para quitarlas.")
        return _etiquetas_normalizadas(valor)

    @model_validator(mode="after")
    def _rechazar_null_explicito_en_contingency_fund_percent(self) -> EventUpdate:
        # `NUMERIC(5,2) NOT NULL` en `events`: a diferencia del resto de
        # campos de este schema, un `null` explícito aquí no significa "sin
        # cambios" (eso ya lo cubre `exclude_unset`), significa un valor
        # inválido que llegaría al `setattr` genérico de `update_event` y
        # rompería la constraint `NOT NULL` — y ese `IntegrityError` lo
        # capturaba la rama de conflicto de `slug`, devolviendo un 409 con el
        # mensaje falso "ya existe un evento con el identificador «None»".
        for campo, mensaje in _NO_ADMITE_NULL.items():
            if campo in self.model_fields_set and getattr(self, campo) is None:
                raise ValueError(mensaje)  # mensaje marcado
        return self


class EventResponse(BaseModel):
    """Evento tal y como lo ve el panel de administración."""

    id: str
    slug: str
    # La categoría se devuelve entera, aunque esté desactivada: el selector del
    # panel la muestra igualmente para no borrarla al guardar.
    category: EventCategoryOut | None = None
    tags: list[str] = Field(default_factory=list)
    title: str
    summary: str | None
    description: str | None
    cover_url: str | None
    status: EventStatus
    cancelled_at: datetime | None = None
    cancellation_reason: str | None = None
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
    reminder_enabled: bool
    reminder_hours_before: int
    attendance_closed_at: datetime | None = None
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
    # `None` significa sin personalización propia (usa la plantilla resuelta tal cual).
    theme_overrides: dict[str, Any] | None


class EventListItem(EventResponse):
    """Evento en el listado del panel: lo de `EventResponse` más su precio, que
    el organizador quiere ver en la tabla sin abrir cada evento."""

    # Entrada más barata entre los tipos activos, estén o no a la venta ahora
    # (al organizador le importa el precio aunque la venta no haya abierto).
    # `None` en un evento que no es de pago o que aún no tiene entradas.
    price_from_cents: int | None = None
    price_currency: str | None = None
    price_multiple: bool = False


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


ColorDeTipo = Literal["azul", "violeta", "verde", "ambar", "rosa", "cian", "rojo", "gris"]


class SessionTypeRef(BaseModel):
    """El tipo de una sesión, tal y como se pinta (panel y páginas públicas)."""

    id: str
    name: str
    color: str
    is_break: bool


class SessionTypeOut(SessionTypeRef):
    """Un tipo de sesión del catálogo de la organización."""

    description: str | None
    base_key: str | None
    display_order: int
    is_active: bool
    # Sesiones que lo usan: con alguna no se puede borrar, solo desactivar.
    sesiones: int


def _nombre_con_texto(valor: str) -> str:
    """Sin espacios en los extremos ni dobles; solo espacios no es un nombre."""
    limpio = " ".join(valor.split())
    if not limpio:
        raise ValueError("El tipo de sesión necesita un nombre.")
    return limpio


NombreDeTipo = Annotated[str, Field(min_length=1, max_length=60), AfterValidator(_nombre_con_texto)]
DescripcionDeTipo = Annotated[str, Field(max_length=200)]


class SessionTypeCreate(BaseModel):
    name: NombreDeTipo
    description: DescripcionDeTipo | None = None
    color: ColorDeTipo = "azul"
    is_break: bool = False


class SessionTypeUpdate(BaseModel):
    name: NombreDeTipo | None = None
    description: DescripcionDeTipo | None = None
    color: ColorDeTipo | None = None
    is_break: bool | None = None
    is_active: bool | None = None


class SessionTypeOrder(BaseModel):
    """Todos los tipos de la organización, en el orden nuevo."""

    ids: list[str] = Field(min_length=1, max_length=200)


class EventSessionCreate(BaseModel):
    """Alta de una sesión de agenda.

    El tipo va por `session_type_id` (el catálogo de la organización). El texto
    `session_type` se sigue aceptando durante la transición: se traduce al tipo
    con esa clave base (`talk`, `workshop`…). Sin ninguno, el primer tipo activo
    que no es una pausa.
    """

    session_type: SessionType | None = None
    session_type_id: str | None = None
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
    session_type_id: str | None = None
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
    # Texto heredado (clave base del tipo, u `other` en los propios), mientras
    # haya clientes que lo lean. El tipo de verdad es `type`.
    session_type: str
    type: SessionTypeRef
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


class SessionParticipationOut(BaseModel):
    """Una persona del roster en una sesión, con su horario: lo justo para que
    el panel avise de solapes sin pedir los participantes sesión a sesión."""

    event_member_id: str
    session_id: str
    session_title: str
    starts_at: datetime
    ends_at: datetime
    role_key: str


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
    # Identificador opaco y estable de la persona en esta organización (nunca su
    # UUID): deja a la página juntar ponentes de la agenda y del roster sin duplicar.
    ref: str


class PublicEventSummary(ContentLocaleInfo):
    """Evento tal y como aparece en el listado público.

    `reserved_count` es el número de plazas realmente reservadas: `confirmed` +
    `pending_payment` dentro de su ventana de pago + promociones de lista de
    espera dentro de su ventana de confirmación — misma regla que
    `registrations.repository.count_reserved_registrations`. Nunca se expone el
    detalle de qué estado concreto ocupa cada plaza, solo el agregado.
    """

    slug: str
    organization: PublicOrganizationRef
    category: PublicCategoryRef | None = None
    tags: list[str] = Field(default_factory=list)
    # Texto que se muestra de cada etiqueta en el idioma servido, solo de las que
    # cambian; `tags` sigue llevando el original, que es el que filtra.
    tag_labels: dict[str, str] = Field(default_factory=dict)
    # El evento está cancelado: en la página de su organización sigue apareciendo,
    # marcado. El directorio general no lista los cancelados.
    cancelled: bool = False
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
    # Venta de entradas de un evento de pago (`payments.VentaPublica`): `open`
    # (se puede comprar), `upcoming` (abre en `ticket_sales_opens_at`) o
    # `closed` (terminada o sin tipos activos). `None` si el evento no es de
    # pago. Con él la web no confunde nunca un evento de pago con uno gratuito.
    ticket_sales: TicketSalesState | None = None
    ticket_sales_opens_at: datetime | None = None


class PublicEventSession(BaseModel):
    """Sesión de la agenda tal y como se muestra en la página pública del evento."""

    id: str
    # Texto heredado (clave base); el nombre, color y pausa vienen en `type`.
    session_type: str
    type: SessionTypeRef
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


class PublicSessionDetail(PublicEventSession, ContentLocaleInfo):
    """La misma sesión, con el enlace a su evento padre para la página propia."""

    event_slug: str
    event_title: str
    # `hidden` = «solo con enlace»: la web lo marca `noindex` en todas sus páginas.
    visibility: EventVisibility = "public"
    organization: PublicOrganizationRef
    # Plantilla del evento padre, ya resuelta: la página la aplica igual que la
    # ficha del evento para no cambiar de aspecto al navegar dentro de él.
    theme: PublicTheme | None = None


class PublicVenue(BaseModel):
    """Sede tal y como se muestra en la página pública del evento, sin campos
    de auditoría (`display_order`/`geocoded_at` son detalle interno)."""

    id: str
    name: str
    address: str | None
    capacity: int | None
    latitude: float | None
    longitude: float | None


class PublicEventDetail(ContentLocaleInfo):
    """Evento publicado con su agenda completa, para la página pública de detalle.

    También sirve a un evento cancelado, que sigue visible con su aviso:
    `cancelled` lo indica y `cancellation_reason` lleva el motivo público.
    """

    slug: str
    organization: PublicOrganizationRef
    category: PublicCategoryRef | None = None
    tags: list[str] = Field(default_factory=list)
    # Texto que se muestra de cada etiqueta en el idioma servido, solo de las que
    # cambian; `tags` sigue llevando el original, que es el que filtra.
    tag_labels: dict[str, str] = Field(default_factory=dict)
    cancelled: bool = False
    cancellation_reason: str | None = None
    # `hidden` = «solo con enlace»: la web lo marca `noindex` en todas sus páginas.
    visibility: EventVisibility = "public"
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
    # Mismo criterio que `PublicEventSummary.ticket_sales`.
    ticket_sales: TicketSalesState | None = None
    ticket_sales_opens_at: datetime | None = None
    # Geocodificación de `location_address`, para el mapa del evento de una
    # sola sede. `None` si no hay dirección, el evento es `online` o falló.
    latitude: float | None
    longitude: float | None
    # Plantilla visual del evento, con la herencia ya resuelta. `None` solo si
    # el catálogo estuviera vacío, que no es un estado posible hoy.
    theme: PublicTheme | None = None
    sessions: list[PublicEventSession]
    # Ponentes enlazados al evento, tengan o no sesión en la agenda.
    speakers: list[PublicParticipant] = Field(default_factory=list)
    # Ordenadas por `display_order`. El frontend decide, a partir de su
    # longitud, si activa la vista de "programa por sede" (2 sedes o más) —
    # decisión de tanda 3, aquí solo se exponen los datos.
    venues: list[PublicVenue] = Field(default_factory=list)
    # Alojamiento, restaurantes, parking… que el organizador señala cerca del evento.
    nearby_places: list[PublicNearbyPlace] = Field(default_factory=list)
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
    # Su entrada en el roster de este evento: la que se asigna a una sesión.
    event_member_id: str
    user_id: str
    email: str
    first_name: str | None
    last_name: str | None
    # Titular profesional de su ficha (`profile_data.titular`), para pintar
    # bajo el nombre; `None` si no lo rellenó.
    titular: str | None
    # Biografía de su ficha, para que el equipo la lea sin salir del panel
    # (quien ve esta vista ya puede leer los perfiles de los miembros).
    bio: str | None = None
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
