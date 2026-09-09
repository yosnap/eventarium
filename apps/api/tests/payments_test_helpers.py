"""Fijaciones y ayudantes compartidos por `test_payments_checkout.py` y
`test_payments_webhooks.py` (fase 6 del PRD, fase 4 de trabajo).

Sin red real: `stripe.StripeClient` se sustituye por `FakeStripeClient`
(mismo patrón que `test_payments_stripe_client.py`).
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from app.core.config import Settings
from app.core.database import SessionMaintenance
from app.modules.events import service as events_service
from app.modules.payments import stripe_client
from app.modules.payments.models import OrganizationStripeAccount
from tests.conftest import OrganizacionDePrueba, iniciar_sesion

EVENTS = "/api/v1/events"
WEBHOOK_URL = "/api/v1/webhooks/stripe"
SECRETO_WEBHOOK = "whsec_" + "c" * 40
AHORA = datetime.now(UTC).replace(microsecond=0)


def _settings_con_stripe() -> Settings:
    return Settings(
        stripe_secret_key="sk_test_" + "a" * 40,
        stripe_webhook_secret=SECRETO_WEBHOOK,
    )


# Alias histórico: el ajuste de settings es el mismo tanto si lo consume
# `events_service` (guarda de venta) como `stripe_client` (llamadas reales).
_settings_con_stripe_payments_enabled = _settings_con_stripe


class _FakeV1:
    def __init__(self) -> None:
        self.accounts = SimpleNamespace(create_async=AsyncMock(), retrieve_async=AsyncMock())
        self.account_links = SimpleNamespace(create_async=AsyncMock())
        self.checkout = SimpleNamespace(
            sessions=SimpleNamespace(
                create_async=AsyncMock(),
                retrieve_async=AsyncMock(),
                expire_async=AsyncMock(),
            )
        )
        self.refunds = SimpleNamespace(create_async=AsyncMock())


class FakeStripeClient:
    def __init__(self) -> None:
        self.v1 = _FakeV1()


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeStripeClient:
    instancia = FakeStripeClient()
    monkeypatch.setattr(stripe_client, "get_settings", _settings_con_stripe)
    monkeypatch.setattr(stripe_client.stripe, "StripeClient", lambda **_kwargs: instancia)
    return instancia


def _sesion_creada(session_id: str = "cs_test_1") -> SimpleNamespace:
    return SimpleNamespace(
        id=session_id,
        url=f"https://checkout.stripe.com/c/{session_id}",
        expires_at=int(time.time()) + 3600,
    )


async def _crear_organizacion_con_stripe(
    organizacion: OrganizacionDePrueba, *, charges_enabled: bool = True
) -> str:
    stripe_account_id = f"acct_{organizacion.slug}"
    async with SessionMaintenance() as session:
        session.add(
            OrganizationStripeAccount(
                organization_id=organizacion.id,
                stripe_account_id=stripe_account_id,
                charges_enabled=charges_enabled,
            )
        )
        await session.commit()
    return stripe_account_id


def _payload_evento_pago(slug: str, **overrides: object) -> dict:
    payload = {
        "slug": slug,
        "title": f"Evento {slug}",
        "starts_at": AHORA.isoformat(),
        "ends_at": (AHORA + timedelta(days=2)).isoformat(),
        "location_mode": "in_person",
        "registration_mode": "paid",
        "email_verification_required": False,
        "payment_checkout_window_minutes": 30,
    }
    payload.update(overrides)
    return payload


async def _crear_tipo(cliente: AsyncClient, cabeceras: dict[str, str], event_id: str, **datos):
    payload = {"name": "General", "price_cents": 1000}
    payload.update(datos)
    creado = await cliente.post(
        f"{EVENTS}/{event_id}/ticket-types", headers=cabeceras, json=payload
    )
    assert creado.status_code == 201, creado.text
    return creado.json()


async def _crear_publicar_evento_de_pago(
    cliente: AsyncClient,
    cabeceras: dict[str, str],
    organizacion: OrganizacionDePrueba,
    slug: str,
    **overrides: object,
) -> dict:
    """Crea el evento en borrador, le añade un tipo de entrada («General») y
    solo entonces lo publica: `_asegurar_venta_posible` exige al menos un
    tipo de entrada vigente para publicar un evento `paid` (hallazgo C1b del
    code review de la fase 6), así que publicar antes de tener uno daría 409.
    """
    monkeypatch_activo = overrides.pop("_monkeypatch", None)
    if monkeypatch_activo is not None:
        monkeypatch_activo.setattr(
            events_service, "get_settings", _settings_con_stripe_payments_enabled
        )
    creacion = await cliente.post(
        EVENTS, headers=cabeceras, json=_payload_evento_pago(slug, **overrides)
    )
    assert creacion.status_code == 201, creacion.text
    evento = creacion.json()
    await _crear_tipo(cliente, cabeceras, evento["id"])
    publicacion = await cliente.patch(
        f"{EVENTS}/{evento['id']}",
        headers=cabeceras,
        json={"status": "published", "visibility": "public"},
    )
    assert publicacion.status_code == 200, publicacion.text
    return publicacion.json()


def _url_checkout(slug: str) -> str:
    return f"/api/v1/public/events/{slug}/checkout"


async def _preparar_evento_de_pago(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    monkeypatch: pytest.MonkeyPatch,
    slug: str,
    **overrides: object,
) -> tuple[dict, dict]:
    monkeypatch.setattr(events_service, "get_settings", _settings_con_stripe_payments_enabled)
    await _crear_organizacion_con_stripe(organizacion)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_publicar_evento_de_pago(
        cliente, cabeceras, organizacion, slug, **overrides
    )
    # `_crear_publicar_evento_de_pago` ya crea el tipo «General» (lo necesita
    # para poder publicar): se recupera aquí en vez de crear un segundo, que
    # chocaría con `UniqueConstraint(event_id, name)`.
    listado = await cliente.get(f"{EVENTS}/{evento['id']}/ticket-types", headers=cabeceras)
    assert listado.status_code == 200, listado.text
    tipo = listado.json()[0]
    return evento, tipo


async def _estado_inscripcion(event_id: str, email: str) -> str | None:
    from sqlalchemy import select

    from app.modules.registrations.models import EventRegistration

    async with SessionMaintenance() as session:
        fila = await session.scalar(
            select(EventRegistration).where(
                EventRegistration.event_id == uuid.UUID(event_id), EventRegistration.email == email
            )
        )
        return fila.status if fila is not None else None
