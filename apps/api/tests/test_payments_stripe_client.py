"""`payments/stripe_client.py` (fase 6 del PRD, fase 2 de trabajo): las seis
funciones del wrapper contra un cliente simulado, sin red real. Cada una
lleva su test aunque `crear_sesion_checkout`/`crear_reembolso`/
`verificar_firma_webhook` no se llamen todavía desde ningún router — riesgo
aceptado y documentado en la fase de trabajo (nadie las consume hasta las
fases 4 y 5).
"""

from __future__ import annotations

import time
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import stripe

from app.core.config import Settings
from app.modules.payments import stripe_client
from app.modules.payments.models import OrganizationStripeAccount
from app.shared.errors import ExternalServiceError, ServiceUnavailableError

SECRETO_WEBHOOK = "whsec_" + "b" * 40


def _settings_con_stripe() -> Settings:
    return Settings(
        stripe_secret_key="sk_test_" + "a" * 40,
        stripe_webhook_secret=SECRETO_WEBHOOK,
    )


def _cuenta(stripe_account_id: str = "acct_123") -> OrganizationStripeAccount:
    return OrganizationStripeAccount(
        organization_id=uuid.uuid4(), stripe_account_id=stripe_account_id
    )


class _FakeV1:
    def __init__(self) -> None:
        self.accounts = SimpleNamespace(create_async=AsyncMock(), retrieve_async=AsyncMock())
        self.account_links = SimpleNamespace(create_async=AsyncMock())
        self.checkout = SimpleNamespace(sessions=SimpleNamespace(create_async=AsyncMock()))
        self.refunds = SimpleNamespace(create_async=AsyncMock())


class FakeStripeClient:
    """Sustituye a `stripe.StripeClient`: nunca abre una conexión real."""

    def __init__(self) -> None:
        self.v1 = _FakeV1()


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeStripeClient:
    """Cliente simulado único: `_cliente()` construye siempre esta misma
    instancia mientras dura el test, así que cada test puede configurar sus
    mocks antes de llamar a la función bajo prueba."""
    instancia = FakeStripeClient()
    monkeypatch.setattr(stripe_client, "get_settings", _settings_con_stripe)
    monkeypatch.setattr(stripe_client.stripe, "StripeClient", lambda **_kwargs: instancia)
    return instancia


async def test_sin_configurar_lanza_service_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(stripe_client, "get_settings", Settings)
    with pytest.raises(ServiceUnavailableError):
        await stripe_client.crear_cuenta_conectada(idempotency_key="k1")


async def test_crear_cuenta_conectada_pasa_idempotency_key(fake: FakeStripeClient) -> None:
    fake.v1.accounts.create_async.return_value = SimpleNamespace(id="acct_nueva")

    creado = await stripe_client.crear_cuenta_conectada(idempotency_key="clave-1")

    assert creado.stripe_account_id == "acct_nueva"
    fake.v1.accounts.create_async.assert_awaited_once_with(
        params={"type": "standard"}, options={"idempotency_key": "clave-1"}
    )


async def test_crear_enlace_onboarding_genera_url(fake: FakeStripeClient) -> None:
    cuenta = _cuenta()
    fake.v1.account_links.create_async.return_value = SimpleNamespace(
        url="https://connect.stripe.com/setup/s/abc"
    )

    url = await stripe_client.crear_enlace_onboarding(
        cuenta,
        return_url="https://acme.example.com/admin/stripe?onboarding=retorno",
        refresh_url="https://acme.example.com/admin/stripe?onboarding=refresco",
    )

    assert url == "https://connect.stripe.com/setup/s/abc"
    fake.v1.account_links.create_async.assert_awaited_once_with(
        params={
            "account": cuenta.stripe_account_id,
            "type": "account_onboarding",
            "return_url": "https://acme.example.com/admin/stripe?onboarding=retorno",
            "refresh_url": "https://acme.example.com/admin/stripe?onboarding=refresco",
        }
    )


async def test_dos_onboardings_seguidos_generan_dos_urls_distintas(fake: FakeStripeClient) -> None:
    cuenta = _cuenta()
    fake.v1.account_links.create_async.side_effect = [
        SimpleNamespace(url="https://connect.stripe.com/setup/s/1"),
        SimpleNamespace(url="https://connect.stripe.com/setup/s/2"),
    ]

    primera = await stripe_client.crear_enlace_onboarding(
        cuenta, return_url="https://a.example.com/x", refresh_url="https://a.example.com/y"
    )
    segunda = await stripe_client.crear_enlace_onboarding(
        cuenta, return_url="https://a.example.com/x", refresh_url="https://a.example.com/y"
    )

    assert primera != segunda
    assert fake.v1.account_links.create_async.await_count == 2


async def test_error_del_sdk_se_traduce_a_external_service_error(fake: FakeStripeClient) -> None:
    cuenta = _cuenta()
    fake.v1.accounts.retrieve_async.side_effect = stripe.StripeError(
        "detalle interno de Stripe que no debe llegar al panel"
    )

    with pytest.raises(ExternalServiceError) as excinfo:
        await stripe_client.consultar_cuenta(cuenta)

    assert "detalle interno de Stripe" not in str(excinfo.value)


async def test_consultar_cuenta_devuelve_estado(fake: FakeStripeClient) -> None:
    cuenta = _cuenta()
    fake.v1.accounts.retrieve_async.return_value = SimpleNamespace(
        charges_enabled=True, payouts_enabled=False, details_submitted=True
    )

    estado = await stripe_client.consultar_cuenta(cuenta)

    assert estado.charges_enabled is True
    assert estado.payouts_enabled is False
    assert estado.details_submitted is True


async def test_crear_sesion_checkout_pasa_stripe_account_e_idempotency_key(
    fake: FakeStripeClient,
) -> None:
    cuenta = _cuenta("acct_checkout")
    fake.v1.checkout.sessions.create_async.return_value = SimpleNamespace(
        id="cs_test_1", url="https://checkout.stripe.com/c/1", expires_at=1
    )

    resultado = await stripe_client.crear_sesion_checkout(
        cuenta,
        linea=stripe_client.LineaDePrecioAdHoc(
            currency="eur", unit_amount_cents=1000, product_name="Entrada general"
        ),
        success_url="https://acme.example.com/ok",
        cancel_url="https://acme.example.com/cancel",
        expires_at_epoch=int(time.time()) + 3600,
        idempotency_key="checkout-clave-1",
    )

    assert resultado.stripe_checkout_session_id == "cs_test_1"
    _, kwargs = fake.v1.checkout.sessions.create_async.call_args
    assert kwargs["options"] == {
        "stripe_account": "acct_checkout",
        "idempotency_key": "checkout-clave-1",
    }


async def test_crear_reembolso_usa_la_cuenta_del_pago(fake: FakeStripeClient) -> None:
    fake.v1.refunds.create_async.return_value = SimpleNamespace(id="re_test_1")

    resultado = await stripe_client.crear_reembolso(
        stripe_account_id="acct_del_pago",
        stripe_payment_intent_id="pi_123",
        amount_cents=500,
        idempotency_key="refund_abc",
    )

    assert resultado.stripe_refund_id == "re_test_1"
    fake.v1.refunds.create_async.assert_awaited_once_with(
        params={"payment_intent": "pi_123", "amount": 500},
        options={"stripe_account": "acct_del_pago", "idempotency_key": "refund_abc"},
    )


def _firmar(payload: bytes, timestamp: int, secreto: str) -> str:
    firma = stripe.WebhookSignature._compute_signature(
        f"{timestamp}.{payload.decode()}", secreto
    )
    return f"t={timestamp},v1={firma}"


def test_verificar_firma_webhook_con_firma_valida(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(stripe_client, "get_settings", _settings_con_stripe)
    payload = b'{"id": "evt_test", "type": "account.updated"}'
    firma = _firmar(payload, int(time.time()), SECRETO_WEBHOOK)

    evento = stripe_client.verificar_firma_webhook(payload=payload, firma=firma)

    assert evento["id"] == "evt_test"


def test_verificar_firma_webhook_con_firma_invalida_lanza_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(stripe_client, "get_settings", _settings_con_stripe)
    with pytest.raises(ExternalServiceError):
        stripe_client.verificar_firma_webhook(payload=b"{}", firma="t=1,v1=firma-falsa")


def test_verificar_firma_webhook_sin_pagos_configurados_lanza_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(stripe_client, "get_settings", Settings)
    with pytest.raises(ServiceUnavailableError):
        stripe_client.verificar_firma_webhook(payload=b"{}", firma="t=1,v1=x")
