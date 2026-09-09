"""Endpoint público de presupuesto de compra (fase 6 del PRD, fase 3 de trabajo).

Mismo patrón que `registrations/public_router.py`: sin autenticación, contexto
RLS fijado por el `Host` vía `OrganizationDep`/`DbDep`. Un presupuesto es
puramente informativo — **nunca** reserva cupo ni consume un uso de código, ver
`service.calcular_presupuesto` — así que este router no crea nada, solo lee.

Lleva `limit_per_ip` propio (`CHECKOUT_QUOTE_POR_IP`) y Turnstile obligatorio:
sin ambos, sería un oráculo para enumerar códigos de descuento por fuerza
bruta contra un código inexistente, caducado, agotado o de otro tipo de
entrada — los cuatro casos responden siempre el mismo mensaje genérico
(`service.MENSAJE_CODIGO_NO_VALIDO`), el motivo exacto solo queda en el log
del servidor.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.core.deps import DbDep, OrganizationDep
from app.core.ratelimit import CHECKOUT_QUOTE_POR_IP, INSCRIPCION_POR_IP, limit_per_ip
from app.core.turnstile import require_turnstile
from app.modules.events import repository as events_repository
from app.modules.events.models import Event
from app.modules.payments import checkout_service, repository, service
from app.modules.payments.schemas import (
    CheckoutQuoteRequest,
    CheckoutQuoteResponse,
    CheckoutStartRequest,
    CheckoutStartResponse,
    PaymentStatusResponse,
)
from app.modules.registrations import repository as registrations_repository
from app.modules.registrations.schemas import RegistrationAnswerInput
from app.shared.errors import NotFoundError, ValidationDomainError

router = APIRouter(prefix="/public", tags=["público"])


async def _obtener_evento_o_404(organizacion: OrganizationDep, session: DbDep, slug: str) -> Event:
    evento = await events_repository.get_public_event_by_slug(session, organizacion.id, slug)
    if evento is None:
        raise NotFoundError("El evento no existe.")
    return evento


@router.post(
    "/events/{slug}/checkout/quote",
    summary="Presupuesto de compra de una entrada",
    description=(
        "Calcula el precio final de un tipo de entrada, con o sin código de "
        "descuento. Nunca reserva cupo ni consume el uso de un código: es "
        "puramente informativo."
    ),
    response_model=CheckoutQuoteResponse,
    dependencies=[limit_per_ip("checkout-quote", CHECKOUT_QUOTE_POR_IP)],
)
async def quote_checkout(
    evento: Annotated[Event, Depends(_obtener_evento_o_404)],
    datos: CheckoutQuoteRequest,
    request: Request,
    session: DbDep,
) -> CheckoutQuoteResponse:
    await require_turnstile(request, datos.turnstile_token)

    try:
        ticket_type_id = uuid.UUID(datos.ticket_type_id)
    except ValueError as exc:
        raise ValidationDomainError("Este tipo de entrada no está disponible.") from exc

    presupuesto = await service.calcular_presupuesto(
        session,
        organization_id=evento.organization_id,
        event_id=evento.id,
        ticket_type_id=ticket_type_id,
        code=datos.code,
    )
    return CheckoutQuoteResponse(
        price_cents=presupuesto.price_cents,
        discount_cents=presupuesto.discount_cents,
        total_cents=presupuesto.total_cents,
        currency=presupuesto.currency,
    )


@router.post(
    "/events/{slug}/checkout",
    summary="Comprar una entrada de un evento de pago",
    description=(
        "Inscripción + selección de tipo de entrada y código de descuento en una "
        "sola petición. Dos transacciones internas (T1 con bloqueos, sin red; T2 "
        "con red, sin bloqueos): nunca una llamada a Stripe con filas bloqueadas. "
        "Respuesta siempre con la misma forma, para no revelar si el email ya "
        "estaba inscrito."
    ),
    response_model=CheckoutStartResponse,
    dependencies=[limit_per_ip("checkout-compra", INSCRIPCION_POR_IP)],
)
async def start_checkout(
    evento: Annotated[Event, Depends(_obtener_evento_o_404)],
    datos: CheckoutStartRequest,
    request: Request,
) -> CheckoutStartResponse:
    """`checkout_service.iniciar_compra` abre su propia sesión (T1 + T2, ver
    su docstring): no recibe la del `DbDep` de la petición, que envuelve toda
    la petición en una única transacción y no admite un `commit` a mitad de
    camino."""
    await require_turnstile(request, datos.turnstile_token)

    try:
        ticket_type_id = uuid.UUID(datos.ticket_type_id)
    except ValueError as exc:
        raise ValidationDomainError("Este tipo de entrada no está disponible.") from exc

    resultado = await checkout_service.iniciar_compra(
        event=evento,
        email=str(datos.email),
        full_name=datos.full_name,
        answers=[
            RegistrationAnswerInput(question_id=respuesta.question_id, value=respuesta.value)
            for respuesta in datos.answers
        ],
        data_processing_accepted=datos.data_processing_accepted,
        marketing_accepted=datos.marketing_accepted,
        recording_accepted=datos.recording_accepted,
        ticket_type_id=ticket_type_id,
        code=datos.code,
    )
    return CheckoutStartResponse(message=resultado.message, checkout_url=resultado.checkout_url)


@router.get(
    "/events/{slug}/checkout/{registration_id}/status",
    summary="Estado real de un pago, para la pantalla de retorno",
    description=(
        "Consulta lo persistido, nunca da el pago por confirmado por el mero "
        "retorno desde Stripe: el webhook es la única fuente de verdad."
    ),
    response_model=PaymentStatusResponse,
    dependencies=[limit_per_ip("checkout-estado", CHECKOUT_QUOTE_POR_IP)],
)
async def get_checkout_status(
    evento: Annotated[Event, Depends(_obtener_evento_o_404)],
    registration_id: str,
    session: DbDep,
) -> PaymentStatusResponse:
    try:
        registro_id = uuid.UUID(registration_id)
    except ValueError as exc:
        raise NotFoundError("La inscripción no existe.") from exc

    inscripcion = await registrations_repository.get_registration(
        session, evento.organization_id, evento.id, registro_id
    )
    if inscripcion is None:
        raise NotFoundError("La inscripción no existe.")

    pago = await repository.get_payment_by_registration(
        session, evento.organization_id, registro_id
    )
    return PaymentStatusResponse(
        registration_status=inscripcion.status,
        payment_status=pago.status if pago is not None else None,
    )
