"""Unico fichero del proyecto que importa el SDK de Stripe.

Decision 7 del plan (fase 6 del PRD): ninguna funcion de servicio llama a
Stripe directamente. Toda funcion de este modulo recibe un
OrganizationStripeAccount ya resuelto (o el stripe_account_id leido de una
fila de event_payments), nunca un acct_id de tipo str que venga del
body/query de una peticion. El unico resolutor es
repository.get_cuenta_activa.

Reglas no negociables:
- Solo variantes *_async del SDK.
- Toda llamada mutante exige idempotency_key.
- Se captura stripe.StripeError (modulo raiz) y se traduce a
  ExternalServiceError, nunca se deja escapar el mensaje crudo del SDK.
- Timeout explicito en el cliente HTTP.
"""

from __future__ import annotations

from dataclasses import dataclass

import stripe  # noqa: TID251 - unico fichero autorizado, ver pyproject.toml
from stripe._http_client import HTTPXClient

from app.core.config import get_settings
from app.modules.payments.models import OrganizationStripeAccount
from app.shared.errors import ExternalServiceError, ServiceUnavailableError

_TIMEOUT_SEGUNDOS = 15


def _cliente() -> stripe.StripeClient:
    settings = get_settings()
    if not settings.payments_enabled:
        raise ServiceUnavailableError("Los pagos no estan configurados en esta instalacion.")
    return stripe.StripeClient(
        api_key=settings.stripe_secret_key,
        http_client=HTTPXClient(timeout=_TIMEOUT_SEGUNDOS, allow_sync_methods=False),
    )


def _traducir_error(exc: stripe.StripeError) -> ExternalServiceError:
    return ExternalServiceError(
        "La pasarela de pago no ha podido completar la operacion. Intentalo de nuevo "
        "en unos minutos."
    )


@dataclass(frozen=True, slots=True)
class CuentaConectadaCreada:
    stripe_account_id: str


async def crear_cuenta_conectada(*, idempotency_key: str) -> CuentaConectadaCreada:
    cliente = _cliente()
    try:
        cuenta = await cliente.v1.accounts.create_async(
            params={"type": "standard"},
            options={"idempotency_key": idempotency_key},
        )
    except stripe.StripeError as exc:
        raise _traducir_error(exc) from exc
    return CuentaConectadaCreada(stripe_account_id=cuenta.id)


async def crear_enlace_onboarding(
    cuenta: OrganizationStripeAccount, *, return_url: str, refresh_url: str
) -> str:
    cliente = _cliente()
    try:
        enlace = await cliente.v1.account_links.create_async(
            params={
                "account": cuenta.stripe_account_id,
                "type": "account_onboarding",
                "return_url": return_url,
                "refresh_url": refresh_url,
            }
        )
    except stripe.StripeError as exc:
        raise _traducir_error(exc) from exc
    return enlace.url


@dataclass(frozen=True, slots=True)
class EstadoDeCuenta:
    charges_enabled: bool
    payouts_enabled: bool
    details_submitted: bool


async def consultar_cuenta(cuenta: OrganizationStripeAccount) -> EstadoDeCuenta:
    cliente = _cliente()
    try:
        cuenta_stripe = await cliente.v1.accounts.retrieve_async(cuenta.stripe_account_id)
    except stripe.StripeError as exc:
        raise _traducir_error(exc) from exc
    return EstadoDeCuenta(
        charges_enabled=bool(cuenta_stripe.charges_enabled),
        payouts_enabled=bool(cuenta_stripe.payouts_enabled),
        details_submitted=bool(cuenta_stripe.details_submitted),
    )


@dataclass(frozen=True, slots=True)
class LineaDePrecioAdHoc:
    currency: str
    unit_amount_cents: int
    product_name: str


@dataclass(frozen=True, slots=True)
class SesionDeCheckoutCreada:
    stripe_checkout_session_id: str
    checkout_url: str
    expires_at_epoch: int


async def crear_sesion_checkout(
    cuenta: OrganizationStripeAccount,
    *,
    linea: LineaDePrecioAdHoc,
    success_url: str,
    cancel_url: str,
    expires_at_epoch: int,
    idempotency_key: str,
) -> SesionDeCheckoutCreada:
    cliente = _cliente()
    try:
        sesion = await cliente.v1.checkout.sessions.create_async(
            params={
                "mode": "payment",
                "line_items": [
                    {
                        "price_data": {
                            "currency": linea.currency,
                            "unit_amount": linea.unit_amount_cents,
                            "product_data": {"name": linea.product_name},
                        },
                        "quantity": 1,
                    }
                ],
                "success_url": success_url,
                "cancel_url": cancel_url,
                "expires_at": expires_at_epoch,
            },
            options={
                "stripe_account": cuenta.stripe_account_id,
                "idempotency_key": idempotency_key,
            },
        )
    except stripe.StripeError as exc:
        raise _traducir_error(exc) from exc
    if sesion.url is None or sesion.expires_at is None:
        raise ExternalServiceError(
            "La pasarela de pago no ha devuelto una sesion de compra valida."
        )
    return SesionDeCheckoutCreada(
        stripe_checkout_session_id=sesion.id,
        checkout_url=sesion.url,
        expires_at_epoch=sesion.expires_at,
    )


@dataclass(frozen=True, slots=True)
class ReembolsoCreado:
    stripe_refund_id: str


async def crear_reembolso(
    *,
    stripe_account_id: str,
    stripe_payment_intent_id: str,
    amount_cents: int,
    idempotency_key: str,
) -> ReembolsoCreado:
    cliente = _cliente()
    try:
        reembolso = await cliente.v1.refunds.create_async(
            params={
                "payment_intent": stripe_payment_intent_id,
                "amount": amount_cents,
            },
            options={
                "stripe_account": stripe_account_id,
                "idempotency_key": idempotency_key,
            },
        )
    except stripe.StripeError as exc:
        raise _traducir_error(exc) from exc
    return ReembolsoCreado(stripe_refund_id=reembolso.id)


def verificar_firma_webhook(*, payload: bytes, firma: str) -> stripe.Event:
    settings = get_settings()
    if not settings.payments_enabled:
        raise ServiceUnavailableError("Los pagos no estan configurados en esta instalacion.")
    try:
        evento: stripe.Event = stripe.Webhook.construct_event(
            payload, firma, settings.stripe_webhook_secret
        )
    except (stripe.SignatureVerificationError, ValueError) as exc:
        raise ExternalServiceError("Firma de webhook no valida.") from exc
    return evento
