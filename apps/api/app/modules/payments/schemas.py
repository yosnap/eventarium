"""Schemas Pydantic de pagos (fase 6 del PRD, fase 2 de trabajo).

Fase 3 de trabajo: tipos de entrada, códigos de descuento y presupuesto
público. Las fases 4-5 amplían este fichero con pagos y reembolsos, cada una
añadida por su propia fase de trabajo.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, EmailStr, Field, model_validator

DiscountType = Literal["percentage", "fixed_amount"]


def _prohibir_null_explicito(instancia: BaseModel, campos: tuple[str, ...]) -> None:
    """Mismo motivo que `sponsors/schemas.py`: en un `PATCH` parcial, un `null`
    explícito sobre una columna `NOT NULL` debe ser un 422 claro, no un
    `IntegrityError` sin traducir."""
    enviados_a_null = [
        campo
        for campo in campos
        if campo in instancia.model_fields_set and getattr(instancia, campo) is None
    ]
    if enviados_a_null:
        raise ValueError(f"Los campos {', '.join(enviados_a_null)} no admiten «null» explícito.")


def _validar_rango_de_descuento(discount_type: str, discount_value: int) -> None:
    """Espejo del `CHECK` condicionado de la fase 1
    (`ck_event_discount_codes_discount_value_por_tipo`): 1-100 si es
    porcentaje, cualquier importe positivo si es fijo."""
    if discount_type == "percentage" and not (1 <= discount_value <= 100):
        raise ValueError("Un descuento de porcentaje debe estar entre 1 y 100.")
    if discount_type == "fixed_amount" and discount_value <= 0:
        raise ValueError("Un descuento de importe fijo debe ser mayor que 0.")


class StripeOnboardingResponse(BaseModel):
    """URL de un solo uso del `AccountLink`. Nunca se persiste ni se cachea."""

    onboarding_url: str


class StripeAccountResponse(BaseModel):
    """Estado persistido de la cuenta Stripe de la organización.

    `connected` distingue «hay una fila activa» (aunque `charges_enabled`
    todavía sea `False`, p. ej. durante el KYC) de «no hay ninguna cuenta o
    la única que hubo está desautorizada» — en ese segundo caso el resto de
    campos no tiene sentido y el frontend ofrece directamente el botón de
    conectar.
    """

    connected: bool
    charges_enabled: bool
    payouts_enabled: bool
    details_submitted: bool
    connected_at: datetime | None
    deauthorized_at: datetime | None
    last_synced_at: datetime | None


def estado_no_conectado() -> StripeAccountResponse:
    return StripeAccountResponse(
        connected=False,
        charges_enabled=False,
        payouts_enabled=False,
        details_submitted=False,
        connected_at=None,
        deauthorized_at=None,
        last_synced_at=None,
    )


# --- Tipos de entrada ---------------------------------------------------------


class TicketTypeCreate(BaseModel):
    """Alta de un tipo de entrada desde el panel de organizador."""

    name: Annotated[str, Field(min_length=1, max_length=160)]
    description: Annotated[str, Field(max_length=4000)] | None = None
    price_cents: Annotated[int, Field(ge=0)]
    currency: Annotated[str, Field(min_length=3, max_length=3)] = "eur"
    max_quantity: Annotated[int, Field(gt=0)] | None = None
    sales_start_at: datetime | None = None
    sales_end_at: datetime | None = None
    sort_order: int = 0
    is_active: bool = True

    @model_validator(mode="after")
    def _validar_ventana(self) -> TicketTypeCreate:
        if (
            self.sales_start_at is not None
            and self.sales_end_at is not None
            and self.sales_end_at <= self.sales_start_at
        ):
            raise ValueError("El fin de la ventana de venta debe ser posterior al inicio.")
        return self


class TicketTypeUpdate(BaseModel):
    """Edición parcial de un tipo de entrada."""

    name: Annotated[str, Field(min_length=1, max_length=160)] | None = None
    description: Annotated[str, Field(max_length=4000)] | None = None
    price_cents: Annotated[int, Field(ge=0)] | None = None
    currency: Annotated[str, Field(min_length=3, max_length=3)] | None = None
    max_quantity: Annotated[int, Field(gt=0)] | None = None
    sales_start_at: datetime | None = None
    sales_end_at: datetime | None = None
    sort_order: int | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def _validar_null_explicito(self) -> TicketTypeUpdate:
        _prohibir_null_explicito(
            self, ("name", "price_cents", "currency", "sort_order", "is_active")
        )
        return self


class TicketTypeResponse(BaseModel):
    """Tipo de entrada tal como lo ve el panel de organizador."""

    id: str
    name: str
    description: str | None
    price_cents: int
    currency: str
    max_quantity: int | None
    sales_start_at: datetime | None
    sales_end_at: datetime | None
    sort_order: int
    is_active: bool


# --- Códigos de descuento ------------------------------------------------------


class DiscountCodeCreate(BaseModel):
    """Alta de un código de descuento desde el panel de organizador.

    `code` se normaliza a mayúsculas en el servicio, no aquí: la normalización
    debe aplicarse igual en el alta y en la edición parcial, y `model_validator`
    de un `Create` no puede compartirse con la clase `Update` sin duplicarlo.
    """

    code: Annotated[str, Field(min_length=1, max_length=60)]
    discount_type: DiscountType
    discount_value: int
    max_uses: Annotated[int, Field(gt=0)] | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    ticket_type_id: str | None = None

    @model_validator(mode="after")
    def _validar(self) -> DiscountCodeCreate:
        _validar_rango_de_descuento(self.discount_type, self.discount_value)
        if (
            self.valid_from is not None
            and self.valid_until is not None
            and self.valid_until <= self.valid_from
        ):
            raise ValueError("El fin de la vigencia debe ser posterior al inicio.")
        return self


class DiscountCodeUpdate(BaseModel):
    """Edición parcial de un código de descuento.

    `discount_type`/`discount_value` se validan juntos en el servicio si se
    edita solo uno de los dos: el esquema no conoce el valor ya guardado del
    otro campo.
    """

    code: Annotated[str, Field(min_length=1, max_length=60)] | None = None
    discount_type: DiscountType | None = None
    discount_value: int | None = None
    max_uses: Annotated[int, Field(gt=0)] | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    ticket_type_id: str | None = None

    @model_validator(mode="after")
    def _validar(self) -> DiscountCodeUpdate:
        _prohibir_null_explicito(self, ("code", "discount_type", "discount_value"))
        if self.discount_type is not None and self.discount_value is not None:
            _validar_rango_de_descuento(self.discount_type, self.discount_value)
        if (
            self.valid_from is not None
            and self.valid_until is not None
            and self.valid_until <= self.valid_from
        ):
            raise ValueError("El fin de la vigencia debe ser posterior al inicio.")
        return self


class DiscountCodeResponse(BaseModel):
    """Código de descuento tal como lo ve el panel, con su uso derivado."""

    id: str
    code: str
    discount_type: DiscountType
    discount_value: int
    max_uses: int | None
    valid_from: datetime | None
    valid_until: datetime | None
    ticket_type_id: str | None
    used_count: int


# --- Presupuesto público -------------------------------------------------------


class PublicTicketTypeResponse(BaseModel):
    """Tipo de entrada tal como lo ve el formulario público de compra.

    Solo se listan los vigentes en el instante de la consulta (`is_active` y
    dentro de la ventana de venta, `service.validar_tipo_vigente`): un tipo
    fuera de ventana no debe ofrecerse para elegir, aunque su `checkout/quote`
    ya lo rechace igualmente si se fuerza el `ticket_type_id` a mano."""

    id: str
    name: str
    description: str | None
    price_cents: int
    currency: str


class CheckoutQuoteRequest(BaseModel):
    """Petición de presupuesto público: nunca reserva cupo ni consume un uso."""

    ticket_type_id: str
    code: Annotated[str, Field(max_length=60)] | None = None
    turnstile_token: str = Field(description="Token del widget de Turnstile")


class CheckoutQuoteResponse(BaseModel):
    """Presupuesto de compra: precio de lista, descuento aplicado y total."""

    price_cents: int
    discount_cents: int
    total_cents: int
    currency: str


# --- Compra pública (fase 6 del PRD, fase 4 de trabajo) -----------------------


class RegistrationAnswerInputPublic(BaseModel):
    """Copia de `registrations.schemas.RegistrationAnswerInput`: los módulos
    de dominio no se importan schemas entre sí (mismo criterio que
    `payments/service.py` no importa `registrations`), solo el tipo de datos
    que necesita `checkout_service` para reenviarlo tal cual."""

    question_id: str
    value: str | list[str] | None = None


class CheckoutStartRequest(BaseModel):
    """Formulario público de compra: inscripción + selección de tipo de
    entrada y código de descuento opcional, en una sola petición (paso único
    del embudo, decisión de producto de la fase 6)."""

    email: EmailStr
    full_name: Annotated[str, Field(min_length=1, max_length=200)]
    answers: list[RegistrationAnswerInputPublic] = Field(default_factory=list)
    data_processing_accepted: bool = Field(
        description="Consentimiento de tratamiento de datos, obligatorio para inscribirse."
    )
    marketing_accepted: bool = False
    recording_accepted: bool = False
    ticket_type_id: str
    code: Annotated[str, Field(max_length=60)] | None = None
    turnstile_token: str = Field(description="Token del widget de Turnstile")


class CheckoutStartResponse(BaseModel):
    """Respuesta siempre con la misma forma (hallazgo de no filtrar si el
    email ya estaba inscrito): `checkout_url` es `null` cuando la
    inscripción existente no es pagable ahora mismo."""

    message: str
    checkout_url: str | None


class PaymentStatusResponse(BaseModel):
    """Estado real de un pago, para la pantalla de retorno — nunca se da el
    pago por confirmado por el mero retorno desde Stripe."""

    registration_status: str
    payment_status: str | None
