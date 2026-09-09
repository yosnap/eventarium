"""Router y handlers de webhooks de Stripe (fase 6 del PRD, fase 4 de trabajo).

Único endpoint de la instalación sin tenant por `Host` (decisión #9 del
plan): Stripe llama a una URL fija, sin el `Host` de la organización. La
ruta real lleva el prefijo `/api/v1` como todas las demás — el router se
incluye en el mismo `APIRouter(prefix=API_PREFIX)` de `app/main.py`.

Reglas no negociables, todas verificadas por su propio test:
- La firma se verifica sobre el **raw body**, antes de parsear nada: sin
  modelo Pydantic en la firma del handler, sin `await request.json()`.
- Idempotencia medida sobre el *proceso*, no sobre la recepción: el handler
  HTTP solo inserta la fila `received` y encola la tarea; el
  procesamiento real (`procesar_evento`) vive fuera de la petición.
- Un solo endpoint, un solo secreto, ámbito «cuentas conectadas»: un evento
  sin `account` de nivel superior se marca `ignored` sin encolar nada.
- `checkout.session.completed` localiza el pago **exclusivamente** por
  `stripe_checkout_session_id`, nunca por `metadata` ni
  `client_reference_id`, y verifica que la organización del
  pago coincide con la resuelta desde `event.account`.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import maintenance_session
from app.modules.payments import checkout_service, repository
from app.modules.payments import stripe_client as stripe_gateway
from app.modules.payments.models import OrganizationStripeAccount, StripeWebhookEvent
from app.modules.registrations.models import EventRegistration
from app.modules.tickets.service import revocar_entrada
from app.shared.errors import DomainError, ExternalServiceError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["webhooks"])

# Lista blanca de campos que sí se persisten en `stripe_webhook_events.payload`:
# nunca datos personales del comprador. `id` siempre se
# guarda: es el identificador con el que se localiza el pago.
_CAMPOS_POR_TIPO: dict[str, tuple[str, ...]] = {
    "checkout.session.completed": ("payment_status", "payment_intent"),
    "account.updated": ("charges_enabled", "payouts_enabled", "details_submitted"),
    "charge.refunded": ("payment_intent", "amount_refunded"),
}


def _proyectar_payload(evento_dict: dict[str, object]) -> dict[str, object]:
    datos = evento_dict["data"]["object"]  # type: ignore[index]
    tipo = str(evento_dict["type"])
    proyeccion: dict[str, object] = {"id": datos.get("id")}
    for campo in _CAMPOS_POR_TIPO.get(tipo, ()):
        proyeccion[campo] = datos.get(campo)
    return proyeccion


@router.post(
    "/webhooks/stripe",
    summary="Webhook de Stripe (cuentas conectadas)",
    description=(
        "Único endpoint de webhooks de la instalación, registrado en Stripe con "
        "`connect: true`. Verifica la firma sobre el cuerpo crudo antes de parsear "
        "nada. Sin esquema de cuerpo: no genera ningún modelo tipado en el cliente."
    ),
)
async def stripe_webhook(request: Request) -> Response:
    cuerpo = await request.body()
    firma = request.headers.get("stripe-signature")
    if not firma:
        raise DomainError("Falta la cabecera Stripe-Signature.")

    try:
        evento = stripe_gateway.verificar_firma_webhook(payload=cuerpo, firma=firma)
    except ExternalServiceError as exc:
        raise DomainError(exc.detail) from exc

    # `stripe.Event` es un `StripeObject`, no un `dict`: `.get()` choca con su
    # propio bloqueo de métodos de `dict` (ver `stripe._stripe_object`).
    # `.to_dict()` evita ese caso especial para el resto del handler.
    evento_dict: dict[str, object] = evento.to_dict()
    event_id = str(evento_dict["id"])
    event_type = str(evento_dict["type"])
    stripe_account_id = evento_dict.get("account")

    async with maintenance_session() as session:
        if not stripe_account_id:
            # Ámbito plataforma, al que esta instalación no está suscrita
            # (decisión #9): se registra `ignored`, sin encolar nada.
            await repository.registrar_evento_ignorado_sin_cuenta(
                session,
                event_id=event_id,
                event_type=event_type,
                payload=_proyectar_payload(evento_dict),
            )
            return Response(status_code=200)

        insertado = await repository.registrar_evento_recibido(
            session,
            event_id=event_id,
            event_type=event_type,
            stripe_account_id=str(stripe_account_id),
            payload=_proyectar_payload(evento_dict),
        )
        if not insertado:
            fila = await repository.get_webhook_event(session, event_id)
            if fila is not None and fila.status in ("processed", "ignored"):
                return Response(status_code=200)
            # `received`/`failed`: Stripe reintrega porque no llegamos a
            # terminar la vez anterior — se reencola, no se da por procesado.

    from app.core.tasks import process_stripe_webhook_task

    await process_stripe_webhook_task.kiq(event_id)
    return Response(status_code=200)


async def procesar_evento(event_id: str) -> None:
    """Efecto de dominio de un evento ya insertado como `received`
    (`process_stripe_webhook_task`). Relee el payload de la base de datos,
    nunca del argumento serializado en la cola (decisión #9).

    `status = 'processed'`/`'failed'` se escribe **en la misma transacción**
    que aplica (o falla al aplicar) el efecto de dominio: «procesado» solo es
    cierto si el efecto se confirmó. Si falla, se relanza para que
    `retry_on_error=True` de la tarea reintente.
    """
    error: Exception | None = None
    async with maintenance_session() as session:
        fila = await session.get(StripeWebhookEvent, event_id, with_for_update=True)
        if fila is None or fila.status in ("processed", "ignored"):
            return

        fila.attempts += 1
        fila.last_attempt_at = datetime.now(UTC)

        organizacion = (
            await repository.get_cuenta_por_stripe_account_id(session, fila.stripe_account_id)
            if fila.stripe_account_id
            else None
        )
        if organizacion is None:
            # `event.account` no resuelve a ninguna organización conocida:
            # un 4xx/5xx haría a Stripe reintentar indefinidamente un evento
            # que nunca podrá procesarse.
            fila.status = "ignored"
            fila.processed_at = datetime.now(UTC)
            return

        fila.organization_id = organizacion.organization_id
        try:
            fila.status = await _despachar(session, fila, organizacion)
            fila.processed_at = datetime.now(UTC)
        except Exception as exc:  # noqa: BLE001 - se traduce a `failed` y se relanza
            error = exc
            fila.status = "failed"
            fila.error = str(exc)[:2000]

    if error is not None:
        raise error


async def _despachar(
    session: AsyncSession, fila: StripeWebhookEvent, organizacion: OrganizationStripeAccount
) -> str:
    if fila.event_type == "checkout.session.completed":
        return await _handle_checkout_completed(session, fila, organizacion)
    if fila.event_type == "account.updated":
        return await _handle_account_updated(session, fila, organizacion)
    if fila.event_type == "account.application.deauthorized":
        return await _handle_account_deauthorized(session, organizacion)
    if fila.event_type == "charge.refunded":
        return await _handle_charge_refunded(session, fila, organizacion)
    return "ignored"


async def _handle_checkout_completed(
    session: AsyncSession, fila: StripeWebhookEvent, organizacion: OrganizationStripeAccount
) -> str:
    payload = fila.payload
    stripe_checkout_session_id = payload.get("id")
    if not isinstance(stripe_checkout_session_id, str):
        return "ignored"

    pago = await repository.get_payment_by_checkout_session_id(session, stripe_checkout_session_id)
    if pago is None:
        return "ignored"

    if pago.organization_id != organizacion.organization_id:
        # Con Connect Standard el organizador controla su propio Dashboard y
        # puede firmar eventos legítimos con la `metadata` que quiera:
        # resolver el tenant por `event.account` no autoriza
        # la mutación por sí solo.
        logger.error(
            "Webhook checkout.session.completed: organization_id del pago %s (%s) no "
            "coincide con la organización resuelta desde event.account (%s).",
            pago.id,
            pago.organization_id,
            organizacion.organization_id,
        )
        return "failed"

    if payload.get("payment_status") != "paid":
        # `unpaid`/`no_payment_required`: con `payment_method_types=["card"]`
        # no debería llegar, pero el organizador puede habilitar métodos
        # diferidos en su Dashboard. No confirma nada.
        return "ignored"

    if pago.registration_id is None:
        return "ignored"

    inscripcion = await session.get(EventRegistration, pago.registration_id)
    if inscripcion is None:
        return "ignored"

    payment_intent = payload.get("payment_intent")
    return await checkout_service.confirmar_pago_y_registro(
        session,
        pago,
        inscripcion,
        stripe_payment_intent_id=payment_intent if isinstance(payment_intent, str) else None,
    )


async def _handle_account_updated(
    session: AsyncSession, fila: StripeWebhookEvent, organizacion: OrganizationStripeAccount
) -> str:
    if organizacion.deauthorized_at is not None:
        return "ignored"
    payload = fila.payload
    await repository.actualizar_estado(
        session,
        organizacion,
        charges_enabled=bool(payload.get("charges_enabled")),
        payouts_enabled=bool(payload.get("payouts_enabled")),
        details_submitted=bool(payload.get("details_submitted")),
        last_synced_at=datetime.now(UTC),
    )
    return "processed"


async def _handle_account_deauthorized(
    session: AsyncSession, organizacion: OrganizationStripeAccount
) -> str:
    await repository.marcar_desautorizada(session, organizacion, momento=datetime.now(UTC))
    return "processed"


async def _handle_charge_refunded(
    session: AsyncSession, fila: StripeWebhookEvent, organizacion: OrganizationStripeAccount
) -> str:
    """Fuente de verdad de `refunded_cents` (fase 5 de trabajo de la fase 6
    del PRD): incluye los reembolsos hechos por el organizador desde su
    propio Dashboard de Stripe, que con Connect Standard puede hacer sin
    pasar por la plataforma.

    Localiza el pago **exclusivamente** por `stripe_payment_intent_id`
    (`UNIQUE`), nunca por `metadata` (ampliado en la fase 5), y
    verifica que su organización coincide con la resuelta desde
    `event.account` antes de mutar nada. `refunded_cents` se **fija** al
    acumulado que reporta Stripe (`amount_refunded`), nunca se suma un delta:
    es la única forma de que converjan los reembolsos del panel y los del
    Dashboard del organizador, y de que reenviar el mismo evento no duplique
    el importe.
    """
    payload = fila.payload
    stripe_payment_intent_id = payload.get("payment_intent")
    if not isinstance(stripe_payment_intent_id, str):
        return "ignored"

    pago = await repository.get_payment_by_payment_intent_id(session, stripe_payment_intent_id)
    if pago is None:
        return "ignored"

    if pago.organization_id != organizacion.organization_id:
        logger.error(
            "Webhook charge.refunded: organization_id del pago %s (%s) no coincide con la "
            "organización resuelta desde event.account (%s).",
            pago.id,
            pago.organization_id,
            organizacion.organization_id,
        )
        return "failed"

    amount_refunded = payload.get("amount_refunded")
    if not isinstance(amount_refunded, int):
        return "ignored"

    pago.refunded_cents = amount_refunded
    es_total = amount_refunded >= pago.amount_cents
    if es_total:
        pago.status = "refunded"
        pago.refunded_at = datetime.now(UTC)
    elif amount_refunded > 0:
        pago.status = "partially_refunded"

    deberia_revocar = es_total or await repository.tiene_reembolso_con_revocacion(session, pago.id)
    if deberia_revocar and pago.registration_id is not None:
        await revocar_entrada(
            session, organization_id=pago.organization_id, registration_id=pago.registration_id
        )
    return "processed"
