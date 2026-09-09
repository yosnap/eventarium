"""Compra pública, guarda de pago de dos capas y webhooks de Stripe (fase 6
del PRD, fase 4 de trabajo).

Sin red real: `stripe.StripeClient` se sustituye por `FakeStripeClient`
(mismo patrón que `test_payments_stripe_client.py`). El foco es el hallazgo
#1 del red-team (los cuatro caminos de confirmación) y el diseño de dos
transacciones del checkout (hallazgo #12).
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import stripe
from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import Settings
from app.core.database import SessionApp, SessionMaintenance, set_organization_context
from app.modules.events import service as events_service
from app.modules.events.models import Event
from app.modules.payments import checkout_service, stripe_client
from app.modules.payments import repository as payments_repository
from app.modules.payments import webhooks as payments_webhooks
from app.modules.payments.models import EventPayment, EventTicketType, OrganizationStripeAccount
from app.modules.registrations import repository as registrations_repository
from app.modules.registrations import service as registrations_service
from app.modules.registrations.models import EventRegistration
from app.modules.tickets.models import EventTicket
from app.shared.errors import ValidationDomainError
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


class _FakeV1:
    def __init__(self) -> None:
        self.accounts = SimpleNamespace(create_async=AsyncMock(), retrieve_async=AsyncMock())
        self.account_links = SimpleNamespace(create_async=AsyncMock())
        self.checkout = SimpleNamespace(
            sessions=SimpleNamespace(create_async=AsyncMock(), retrieve_async=AsyncMock())
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


async def _crear_publicar_evento_de_pago(
    cliente: AsyncClient,
    cabeceras: dict[str, str],
    organizacion: OrganizacionDePrueba,
    slug: str,
    **overrides: object,
) -> dict:
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
    publicacion = await cliente.patch(
        f"{EVENTS}/{evento['id']}",
        headers=cabeceras,
        json={"status": "published", "visibility": "public"},
    )
    assert publicacion.status_code == 200, publicacion.text
    return publicacion.json()


def _settings_con_stripe_payments_enabled() -> Settings:
    return Settings(
        stripe_secret_key="sk_test_" + "a" * 40,
        stripe_webhook_secret=SECRETO_WEBHOOK,
    )


async def _crear_tipo(cliente: AsyncClient, cabeceras: dict[str, str], event_id: str, **datos):
    payload = {"name": "General", "price_cents": 1000}
    payload.update(datos)
    creado = await cliente.post(
        f"{EVENTS}/{event_id}/ticket-types", headers=cabeceras, json=payload
    )
    assert creado.status_code == 201, creado.text
    return creado.json()


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
    tipo = await _crear_tipo(cliente, cabeceras, evento["id"])
    return evento, tipo


async def _estado_inscripcion(event_id: str, email: str) -> str | None:
    async with SessionMaintenance() as session:
        fila = await session.scalar(
            select(EventRegistration).where(
                EventRegistration.event_id == uuid.UUID(event_id), EventRegistration.email == email
            )
        )
        return fila.status if fila is not None else None


# --- Los cuatro caminos de confirmación (hallazgo #1) -------------------------


async def test_camino_1_alta_directa_deja_pending_payment_sin_emitir_entrada(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    monkeypatch: pytest.MonkeyPatch,
    fake: FakeStripeClient,
) -> None:
    evento, tipo = await _preparar_evento_de_pago(cliente, organizacion, monkeypatch, "camino1")
    fake.v1.checkout.sessions.create_async.return_value = _sesion_creada()

    respuesta = await cliente.post(
        _url_checkout(evento["slug"]),
        headers={"Host": organizacion.host},
        json={
            "email": "camino1@example.com",
            "full_name": "Camino Uno",
            "data_processing_accepted": True,
            "ticket_type_id": tipo["id"],
            "turnstile_token": "token-de-prueba",
        },
    )
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["checkout_url"] is not None
    assert await _estado_inscripcion(evento["id"], "camino1@example.com") == "pending_payment"

    async with SessionMaintenance() as session:
        tickets = list(await session.scalars(select(EventTicket)))
        assert tickets == []


async def test_camino_2_verificacion_deja_pending_payment(
    organizacion: OrganizacionDePrueba,
) -> None:
    evento_id, ticket_type_id = await _fabricar_evento_de_pago_directo(organizacion, capacity=None)
    async with SessionMaintenance() as session:
        inscripcion = EventRegistration(
            event_id=evento_id,
            organization_id=organizacion.id,
            email="camino2@example.com",
            full_name="Camino Dos",
            status="pending_verification",
        )
        session.add(inscripcion)
        await session.commit()
        await session.refresh(inscripcion)
        token = await registrations_service.generate_token(
            registrations_service.PROPOSITO_VERIFICACION_INSCRIPCION, str(inscripcion.id)
        )

    async with SessionApp() as session:
        async with session.begin():
            await set_organization_context(session, organizacion.id)
            resultado = await registrations_service.verify_registration(session, token=token)
            assert resultado.status == "pending_payment"

    async with SessionMaintenance() as session:
        tickets = list(await session.scalars(select(EventTicket)))
        assert tickets == []


async def test_camino_3_aprobacion_tras_cambiar_a_paid_deja_pending_payment(
    organizacion: OrganizacionDePrueba,
) -> None:
    """El caso real del hallazgo: un evento `approval` cambia a `paid` con
    inscripciones ya en `pending_approval`."""
    async with SessionMaintenance() as session:
        evento = Event(
            organization_id=organizacion.id,
            slug="camino3",
            title="Camino 3",
            status="published",
            visibility="public",
            starts_at=AHORA,
            ends_at=AHORA + timedelta(days=1),
            location_mode="online",
            registration_mode="paid",
        )
        session.add(evento)
        await session.flush()
        inscripcion = EventRegistration(
            event_id=evento.id,
            organization_id=organizacion.id,
            email="camino3@example.com",
            full_name="Camino Tres",
            status="pending_approval",
        )
        session.add(inscripcion)
        await session.commit()
        evento_id, registration_id = evento.id, inscripcion.id

    async with SessionApp() as session:
        async with session.begin():
            await set_organization_context(session, organizacion.id)
            resultado = await registrations_service.approve_registration(
                session,
                organization_id=organizacion.id,
                event_id=evento_id,
                registration_id=registration_id,
            )
            assert resultado.status == "pending_payment"

    async with SessionMaintenance() as session:
        tickets = list(await session.scalars(select(EventTicket)))
        assert tickets == []


async def test_camino_4_promocion_de_lista_de_espera_deja_pending_payment(
    organizacion: OrganizacionDePrueba,
) -> None:
    async with SessionMaintenance() as session:
        evento = Event(
            organization_id=organizacion.id,
            slug="camino4",
            title="Camino 4",
            status="published",
            visibility="public",
            starts_at=AHORA,
            ends_at=AHORA + timedelta(days=1),
            location_mode="online",
            registration_mode="paid",
            capacity=1,
        )
        session.add(evento)
        await session.flush()
        inscripcion = EventRegistration(
            event_id=evento.id,
            organization_id=organizacion.id,
            email="camino4@example.com",
            full_name="Camino Cuatro",
            status="waitlisted",
            waitlist_promoted_at=AHORA,
            waitlist_promotion_expires_at=AHORA + timedelta(hours=1),
        )
        session.add(inscripcion)
        await session.commit()
        registration_id = inscripcion.id
        token = await registrations_service.generate_token(
            registrations_service.PROPOSITO_PROMOCION_LISTA_ESPERA, str(registration_id)
        )

    async with SessionApp() as session:
        async with session.begin():
            await set_organization_context(session, organizacion.id)
            resultado = await registrations_service.confirm_waitlist_promotion(session, token=token)
            assert resultado.status == "pending_payment"
            assert resultado.payment_expires_at is not None

    async with SessionMaintenance() as session:
        tickets = list(await session.scalars(select(EventTicket)))
        assert tickets == []


async def _fabricar_evento_de_pago_directo(
    organizacion: OrganizacionDePrueba, *, capacity: int | None
) -> tuple[uuid.UUID, uuid.UUID]:
    async with SessionMaintenance() as session:
        evento = Event(
            organization_id=organizacion.id,
            slug=f"evento-directo-{uuid.uuid4().hex[:8]}",
            title="Evento directo",
            status="published",
            visibility="public",
            starts_at=AHORA,
            ends_at=AHORA + timedelta(days=1),
            location_mode="online",
            registration_mode="paid",
            capacity=capacity,
        )
        session.add(evento)
        await session.flush()
        tipo = EventTicketType(
            organization_id=organizacion.id, event_id=evento.id, name="General", price_cents=1000
        )
        session.add(tipo)
        await session.commit()
        return evento.id, tipo.id


# --- Cinturón de seguridad ------------------------------------------------


async def test_cinturon_de_seguridad_rechaza_confirmed_sin_pago(
    organizacion: OrganizacionDePrueba,
) -> None:
    async with SessionMaintenance() as session:
        evento = Event(
            organization_id=organizacion.id,
            slug="cinturon",
            title="Cinturón",
            status="published",
            visibility="public",
            starts_at=AHORA,
            ends_at=AHORA + timedelta(days=1),
            location_mode="online",
            registration_mode="paid",
        )
        session.add(evento)
        await session.flush()
        inscripcion = EventRegistration(
            event_id=evento.id,
            organization_id=organizacion.id,
            email="cinturon@example.com",
            full_name="Cinturón De Seguridad",
            # Forzado directamente a `confirmed`, saltándose la capa 1.
            status="confirmed",
        )
        session.add(inscripcion)
        await session.commit()
        registration_id = inscripcion.id

    async with SessionApp() as session:
        async with session.begin():
            await set_organization_context(session, organizacion.id)
            inscripcion = await session.get(EventRegistration, registration_id)
            assert inscripcion is not None
            with pytest.raises(ValidationDomainError):
                await registrations_service._enviar_email_por_estado(session, inscripcion)  # noqa: SLF001

    async with SessionMaintenance() as session:
        tickets = list(await session.scalars(select(EventTicket)))
        assert tickets == []


# --- Checkout: T1/T2, idempotencia e importe -------------------------------


async def test_t1_hace_commit_antes_de_la_primera_llamada_a_stripe(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    monkeypatch: pytest.MonkeyPatch,
    fake: FakeStripeClient,
) -> None:
    evento, tipo = await _preparar_evento_de_pago(cliente, organizacion, monkeypatch, "t1-commit")

    llamado_stripe_tras_commit = False

    async def _create_async(*_args, **_kwargs):
        nonlocal llamado_stripe_tras_commit
        async with SessionMaintenance() as verificacion:
            pago = await verificacion.scalar(
                select(EventPayment).where(EventPayment.event_id == uuid.UUID(evento["id"]))
            )
            llamado_stripe_tras_commit = pago is not None and pago.status == "pending"
        return _sesion_creada()

    fake.v1.checkout.sessions.create_async.side_effect = _create_async

    respuesta = await cliente.post(
        _url_checkout(evento["slug"]),
        headers={"Host": organizacion.host},
        json={
            "email": "t1commit@example.com",
            "full_name": "T1 Commit",
            "data_processing_accepted": True,
            "ticket_type_id": tipo["id"],
            "turnstile_token": "token-de-prueba",
        },
    )
    assert respuesta.status_code == 200, respuesta.text
    assert llamado_stripe_tras_commit is True


async def test_idempotency_key_distinta_por_intento_de_checkout(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    monkeypatch: pytest.MonkeyPatch,
    fake: FakeStripeClient,
) -> None:
    evento, tipo = await _preparar_evento_de_pago(cliente, organizacion, monkeypatch, "idem-key")
    fake.v1.checkout.sessions.create_async.return_value = _sesion_creada()

    payload = {
        "email": "idem@example.com",
        "full_name": "Idem Potente",
        "data_processing_accepted": True,
        "ticket_type_id": tipo["id"],
        "turnstile_token": "token-de-prueba",
    }
    primera = await cliente.post(
        _url_checkout(evento["slug"]), headers={"Host": organizacion.host}, json=payload
    )
    assert primera.status_code == 200, primera.text
    _, primera_kwargs = fake.v1.checkout.sessions.create_async.call_args
    primera_clave = primera_kwargs["options"]["idempotency_key"]

    # Caduca y se reintenta con el mismo email: reactiva la misma fila de
    # `event_payments`, con `checkout_attempts` distinto (hallazgo #7 y #11).
    async with SessionMaintenance() as session:
        registro = await session.scalar(
            select(EventRegistration).where(EventRegistration.email == "idem@example.com")
        )
        pago = await session.scalar(
            select(EventPayment).where(EventPayment.registration_id == registro.id)
        )
        registro.status = "cancelled"
        pago.status = "pending"
        await session.commit()

    fake.v1.checkout.sessions.create_async.return_value = _sesion_creada("cs_test_2")
    segunda = await cliente.post(
        _url_checkout(evento["slug"]), headers={"Host": organizacion.host}, json=payload
    )
    assert segunda.status_code == 200, segunda.text
    _, segunda_kwargs = fake.v1.checkout.sessions.create_async.call_args
    segunda_clave = segunda_kwargs["options"]["idempotency_key"]

    assert primera_clave != segunda_clave

    async with SessionMaintenance() as session:
        pago = await session.scalar(
            select(EventPayment).where(EventPayment.registration_id == registro.id)
        )
        assert pago.checkout_attempts == 2


async def test_organizacion_sin_cuenta_operativa_da_409(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(events_service, "get_settings", _settings_con_stripe_payments_enabled)
    await _crear_organizacion_con_stripe(organizacion, charges_enabled=True)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_publicar_evento_de_pago(cliente, cabeceras, organizacion, "sin-cuenta")
    tipo = await _crear_tipo(cliente, cabeceras, evento["id"])

    # La cuenta se desactiva **después** de publicar: publicar ya exige
    # `charges_enabled = true` (`events/service.py::_asegurar_venta_posible`),
    # así que este es el único orden posible para llegar a un evento
    # publicado con la cuenta inoperativa.
    async with SessionMaintenance() as session:
        cuenta = await session.scalar(
            select(OrganizationStripeAccount).where(
                OrganizationStripeAccount.organization_id == organizacion.id
            )
        )
        cuenta.charges_enabled = False
        await session.commit()

    respuesta = await cliente.post(
        _url_checkout(evento["slug"]),
        headers={"Host": organizacion.host},
        json={
            "email": "sincuenta@example.com",
            "full_name": "Sin Cuenta",
            "data_processing_accepted": True,
            "ticket_type_id": tipo["id"],
            "turnstile_token": "token-de-prueba",
        },
    )
    assert respuesta.status_code == 409


# --- Webhooks ---------------------------------------------------------------


def _firmar(payload: bytes, timestamp: int, secreto: str = SECRETO_WEBHOOK) -> str:
    firma = stripe.WebhookSignature._compute_signature(f"{timestamp}.{payload.decode()}", secreto)
    return f"t={timestamp},v1={firma}"


async def _crear_pago_pending(
    organizacion: OrganizacionDePrueba, *, stripe_account_id: str, session_id: str = "cs_webhook_1"
) -> tuple[uuid.UUID, uuid.UUID]:
    async with SessionMaintenance() as session:
        evento = Event(
            organization_id=organizacion.id,
            slug=f"webhook-{uuid.uuid4().hex[:8]}",
            title="Evento webhook",
            status="published",
            visibility="public",
            starts_at=AHORA,
            ends_at=AHORA + timedelta(days=1),
            location_mode="online",
            registration_mode="paid",
        )
        session.add(evento)
        await session.flush()
        tipo = EventTicketType(
            organization_id=organizacion.id, event_id=evento.id, name="General", price_cents=1000
        )
        session.add(tipo)
        inscripcion = EventRegistration(
            event_id=evento.id,
            organization_id=organizacion.id,
            email="webhook@example.com",
            full_name="Webhook Tester",
            status="pending_payment",
            payment_expires_at=AHORA + timedelta(minutes=30),
        )
        session.add(inscripcion)
        await session.flush()
        pago = EventPayment(
            organization_id=organizacion.id,
            event_id=evento.id,
            registration_id=inscripcion.id,
            stripe_account_id=stripe_account_id,
            ticket_type_id=tipo.id,
            stripe_checkout_session_id=session_id,
            amount_cents=1000,
            currency="eur",
            status="pending",
        )
        session.add(pago)
        await session.commit()
        return inscripcion.id, pago.id


def _cuerpo_checkout_completed(
    *, event_id: str, session_id: str, payment_status: str = "paid", account: str | None
) -> bytes:
    import json

    cuerpo = {
        "id": event_id,
        "type": "checkout.session.completed",
        "account": account,
        "data": {
            "object": {
                "id": session_id,
                "payment_status": payment_status,
                "payment_intent": "pi_test_1",
            }
        },
    }
    return json.dumps(cuerpo).encode()


async def test_webhook_confirma_la_inscripcion_y_es_idempotente(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(stripe_client, "get_settings", _settings_con_stripe)
    stripe_account_id = await _crear_organizacion_con_stripe(organizacion)
    registration_id, _ = await _crear_pago_pending(
        organizacion, stripe_account_id=stripe_account_id
    )

    event_id = f"evt_{uuid.uuid4().hex}"
    cuerpo = _cuerpo_checkout_completed(
        event_id=event_id, session_id="cs_webhook_1", account=stripe_account_id
    )
    firma = _firmar(cuerpo, int(time.time()))

    async def _procesar_sincrono(kicked_event_id: str) -> None:
        await payments_webhooks.procesar_evento(kicked_event_id)

    monkeypatch.setattr(
        "app.core.tasks.process_stripe_webhook_task.kiq", AsyncMock(side_effect=_procesar_sincrono)
    )

    primera = await cliente.post(
        WEBHOOK_URL, content=cuerpo, headers={"stripe-signature": firma}
    )
    assert primera.status_code == 200, primera.text

    async with SessionMaintenance() as session:
        inscripcion = await session.get(EventRegistration, registration_id)
        assert inscripcion.status == "confirmed"
        tickets = list(await session.scalars(select(EventTicket)))
        assert len(tickets) == 1

    # Reenvío del mismo `evt_...`: una sola entrada, un solo pago `paid`.
    segunda = await cliente.post(
        WEBHOOK_URL, content=cuerpo, headers={"stripe-signature": firma}
    )
    assert segunda.status_code == 200, segunda.text
    async with SessionMaintenance() as session:
        tickets = list(await session.scalars(select(EventTicket)))
        assert len(tickets) == 1


async def test_webhook_payment_status_no_pagado_no_confirma(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(stripe_client, "get_settings", _settings_con_stripe)
    stripe_account_id = await _crear_organizacion_con_stripe(organizacion)
    registration_id, _ = await _crear_pago_pending(
        organizacion, stripe_account_id=stripe_account_id
    )

    event_id = f"evt_{uuid.uuid4().hex}"
    cuerpo = _cuerpo_checkout_completed(
        event_id=event_id,
        session_id="cs_webhook_1",
        payment_status="unpaid",
        account=stripe_account_id,
    )
    firma = _firmar(cuerpo, int(time.time()))
    monkeypatch.setattr(
        "app.core.tasks.process_stripe_webhook_task.kiq",
        AsyncMock(side_effect=payments_webhooks.procesar_evento),
    )

    respuesta = await cliente.post(WEBHOOK_URL, content=cuerpo, headers={"stripe-signature": firma})
    assert respuesta.status_code == 200

    async with SessionMaintenance() as session:
        inscripcion = await session.get(EventRegistration, registration_id)
        assert inscripcion.status == "pending_payment"
        tickets = list(await session.scalars(select(EventTicket)))
        assert tickets == []


async def test_webhook_organizacion_no_coincide_no_muta_nada(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    otra_organizacion: OrganizacionDePrueba,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(stripe_client, "get_settings", _settings_con_stripe)
    stripe_account_id_pago = f"acct_{organizacion.slug}"
    stripe_account_id_otra = f"acct_{otra_organizacion.slug}"
    registration_id, _ = await _crear_pago_pending(
        organizacion, stripe_account_id=stripe_account_id_pago
    )
    async with SessionMaintenance() as session:
        session.add(
            OrganizationStripeAccount(
                organization_id=otra_organizacion.id, stripe_account_id=stripe_account_id_otra
            )
        )
        await session.commit()

    event_id = f"evt_{uuid.uuid4().hex}"
    # El `event.account` resuelve a `otra_organizacion`, pero el pago
    # localizado por `stripe_checkout_session_id` es de `organizacion`.
    cuerpo = _cuerpo_checkout_completed(
        event_id=event_id, session_id="cs_webhook_1", account=stripe_account_id_otra
    )
    firma = _firmar(cuerpo, int(time.time()))
    monkeypatch.setattr(
        "app.core.tasks.process_stripe_webhook_task.kiq",
        AsyncMock(side_effect=payments_webhooks.procesar_evento),
    )

    respuesta = await cliente.post(WEBHOOK_URL, content=cuerpo, headers={"stripe-signature": firma})
    assert respuesta.status_code == 200

    async with SessionMaintenance() as session:
        inscripcion = await session.get(EventRegistration, registration_id)
        assert inscripcion.status == "pending_payment"
        fila = await payments_repository.get_webhook_event(session, event_id)
        assert fila.status == "failed"


async def test_webhook_sin_cabecera_firma_da_400(cliente: AsyncClient) -> None:
    respuesta = await cliente.post(WEBHOOK_URL, content=b'{"id": "evt_1"}')
    assert respuesta.status_code == 400


async def test_webhook_firma_invalida_da_400(
    cliente: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(stripe_client, "get_settings", _settings_con_stripe)
    respuesta = await cliente.post(
        WEBHOOK_URL, content=b'{"id": "evt_1"}', headers={"stripe-signature": "t=1,v1=falsa"}
    )
    assert respuesta.status_code == 400


async def test_webhook_cuerpo_no_json_con_firma_incorrecta_da_400_no_422(
    cliente: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(stripe_client, "get_settings", _settings_con_stripe)
    respuesta = await cliente.post(
        WEBHOOK_URL, content=b"no es json", headers={"stripe-signature": "t=1,v1=falsa"}
    )
    assert respuesta.status_code == 400


async def test_webhook_sin_account_se_marca_ignored(
    cliente: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(stripe_client, "get_settings", _settings_con_stripe)
    import json

    event_id = f"evt_{uuid.uuid4().hex}"
    cuerpo = json.dumps(
        {"id": event_id, "type": "account.updated", "data": {"object": {}}}
    ).encode()
    firma = _firmar(cuerpo, int(time.time()))

    respuesta = await cliente.post(WEBHOOK_URL, content=cuerpo, headers={"stripe-signature": firma})
    assert respuesta.status_code == 200

    async with SessionMaintenance() as session:
        fila = await payments_repository.get_webhook_event(session, event_id)
        assert fila.status == "ignored"
        assert fila.organization_id is None


async def test_webhook_evento_received_atascado_se_reencola_al_reenviar(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(stripe_client, "get_settings", _settings_con_stripe)
    stripe_account_id = await _crear_organizacion_con_stripe(organizacion)
    registration_id, _ = await _crear_pago_pending(
        organizacion, stripe_account_id=stripe_account_id
    )

    event_id = f"evt_{uuid.uuid4().hex}"
    cuerpo = _cuerpo_checkout_completed(
        event_id=event_id, session_id="cs_webhook_1", account=stripe_account_id
    )
    firma = _firmar(cuerpo, int(time.time()))

    # Primera entrega: se registra `received` pero la tarea nunca llega a
    # ejecutarse (simula la pérdida entre la cola y el worker).
    tarea_mock = AsyncMock()
    monkeypatch.setattr("app.core.tasks.process_stripe_webhook_task.kiq", tarea_mock)
    primera = await cliente.post(WEBHOOK_URL, content=cuerpo, headers={"stripe-signature": firma})
    assert primera.status_code == 200
    tarea_mock.assert_awaited_once()

    async with SessionMaintenance() as session:
        fila = await payments_repository.get_webhook_event(session, event_id)
        assert fila.status == "received"

    # Reentrega de Stripe: al seguir `received`, se reencola en vez de darse
    # por procesado.
    tarea_mock.reset_mock()
    tarea_mock.side_effect = payments_webhooks.procesar_evento
    segunda = await cliente.post(WEBHOOK_URL, content=cuerpo, headers={"stripe-signature": firma})
    assert segunda.status_code == 200
    tarea_mock.assert_awaited_once()

    async with SessionMaintenance() as session:
        inscripcion = await session.get(EventRegistration, registration_id)
        assert inscripcion.status == "confirmed"


async def test_barrido_reencola_eventos_received_atascados(
    organizacion: OrganizacionDePrueba,
) -> None:
    stripe_account_id = await _crear_organizacion_con_stripe(organizacion)
    registration_id, _ = await _crear_pago_pending(
        organizacion, stripe_account_id=stripe_account_id
    )
    event_id = f"evt_{uuid.uuid4().hex}"

    async with SessionMaintenance() as session:
        from app.modules.payments.models import StripeWebhookEvent

        session.add(
            StripeWebhookEvent(
                id=event_id,
                event_type="checkout.session.completed",
                stripe_account_id=stripe_account_id,
                payload={"id": "cs_webhook_1", "payment_status": "paid", "payment_intent": "pi_x"},
                status="received",
                received_at=AHORA - timedelta(minutes=15),
            )
        )
        await session.commit()

    async with SessionMaintenance() as session:
        atascados = await payments_repository.eventos_para_reencolar(session)
    assert event_id in atascados

    await payments_webhooks.procesar_evento(event_id)

    async with SessionMaintenance() as session:
        inscripcion = await session.get(EventRegistration, registration_id)
        assert inscripcion.status == "confirmed"


# --- Barrido de pagos caducados y reactivación tras caducar -----------------


async def test_barrido_expira_y_libera_la_plaza_y_promueve_lista_de_espera(
    fake: FakeStripeClient, organizacion: OrganizacionDePrueba
) -> None:
    stripe_account_id = f"acct_{organizacion.slug}"
    async with SessionMaintenance() as session:
        evento = Event(
            organization_id=organizacion.id,
            slug="barrido-expira",
            title="Barrido expira",
            status="published",
            visibility="public",
            starts_at=AHORA,
            ends_at=AHORA + timedelta(days=1),
            location_mode="online",
            registration_mode="paid",
            capacity=1,
        )
        session.add(evento)
        await session.flush()
        tipo = EventTicketType(
            organization_id=organizacion.id, event_id=evento.id, name="General", price_cents=1000
        )
        session.add(tipo)
        comprador = EventRegistration(
            event_id=evento.id,
            organization_id=organizacion.id,
            email="comprador@example.com",
            full_name="Comprador",
            status="pending_payment",
            payment_expires_at=AHORA - timedelta(minutes=1),
        )
        en_espera = EventRegistration(
            event_id=evento.id,
            organization_id=organizacion.id,
            email="espera@example.com",
            full_name="En Espera",
            status="waitlisted",
            waitlist_position=1,
        )
        session.add_all([comprador, en_espera])
        await session.flush()
        pago = EventPayment(
            organization_id=organizacion.id,
            event_id=evento.id,
            registration_id=comprador.id,
            stripe_account_id=stripe_account_id,
            ticket_type_id=tipo.id,
            stripe_checkout_session_id="cs_expira_1",
            amount_cents=1000,
            currency="eur",
            status="pending",
        )
        session.add(pago)
        await session.commit()
        comprador_id, espera_id = comprador.id, en_espera.id

    fake.v1.checkout.sessions.retrieve_async.return_value = SimpleNamespace(payment_status="unpaid")

    await checkout_service.expirar_pagos_pendientes()

    async with SessionMaintenance() as session:
        comprador_fila = await session.get(EventRegistration, comprador_id)
        assert comprador_fila.status == "cancelled"
        pago_fila = await session.scalar(
            select(EventPayment).where(EventPayment.registration_id == comprador_id)
        )
        assert pago_fila.status == "expired"
        espera_fila = await session.get(EventRegistration, espera_id)
        assert espera_fila.waitlist_promoted_at is not None


async def test_barrido_no_expira_si_stripe_reporta_pagado(
    fake: FakeStripeClient, organizacion: OrganizacionDePrueba
) -> None:
    stripe_account_id = f"acct_{organizacion.slug}"
    async with SessionMaintenance() as session:
        evento = Event(
            organization_id=organizacion.id,
            slug="barrido-pagado",
            title="Barrido pagado",
            status="published",
            visibility="public",
            starts_at=AHORA,
            ends_at=AHORA + timedelta(days=1),
            location_mode="online",
            registration_mode="paid",
        )
        session.add(evento)
        await session.flush()
        tipo = EventTicketType(
            organization_id=organizacion.id, event_id=evento.id, name="General", price_cents=1000
        )
        session.add(tipo)
        comprador = EventRegistration(
            event_id=evento.id,
            organization_id=organizacion.id,
            email="pagoreal@example.com",
            full_name="Pago Real",
            status="pending_payment",
            payment_expires_at=AHORA - timedelta(minutes=1),
        )
        session.add(comprador)
        await session.flush()
        pago = EventPayment(
            organization_id=organizacion.id,
            event_id=evento.id,
            registration_id=comprador.id,
            stripe_account_id=stripe_account_id,
            ticket_type_id=tipo.id,
            stripe_checkout_session_id="cs_pagado_1",
            amount_cents=1000,
            currency="eur",
            status="pending",
        )
        session.add(pago)
        await session.commit()
        comprador_id = comprador.id

    fake.v1.checkout.sessions.retrieve_async.return_value = SimpleNamespace(payment_status="paid")

    await checkout_service.expirar_pagos_pendientes()

    async with SessionMaintenance() as session:
        comprador_fila = await session.get(EventRegistration, comprador_id)
        assert comprador_fila.status == "confirmed"
        pago_fila = await session.scalar(
            select(EventPayment).where(EventPayment.registration_id == comprador_id)
        )
        assert pago_fila.status == "paid"
        tickets = list(
            await session.scalars(
                select(EventTicket).where(EventTicket.registration_id == comprador_id)
            )
        )
        assert len(tickets) == 1


async def test_regresion_evento_gratuito_con_lista_de_espera_no_se_ve_afectado(
    organizacion: OrganizacionDePrueba,
) -> None:
    """Hallazgo #5 y el riesgo de `count_reserved_registrations`: un evento
    gratuito con lista de espera sigue funcionando igual, porque la nueva
    condición de `pending_payment` nunca se cumple para él."""
    async with SessionMaintenance() as session:
        evento = Event(
            organization_id=organizacion.id,
            slug="gratuito-regresion",
            title="Gratuito",
            status="published",
            visibility="public",
            starts_at=AHORA,
            ends_at=AHORA + timedelta(days=1),
            location_mode="online",
            registration_mode="free",
            capacity=1,
        )
        session.add(evento)
        await session.flush()
        confirmado = EventRegistration(
            event_id=evento.id,
            organization_id=organizacion.id,
            email="confirmado@example.com",
            full_name="Confirmado",
            status="confirmed",
            confirmed_at=AHORA,
        )
        en_espera = EventRegistration(
            event_id=evento.id,
            organization_id=organizacion.id,
            email="espera-gratis@example.com",
            full_name="En Espera Gratis",
            status="waitlisted",
            waitlist_position=1,
        )
        session.add_all([confirmado, en_espera])
        await session.commit()
        organization_id, event_id, confirmado_id, en_espera_id = (
            evento.organization_id,
            evento.id,
            confirmado.id,
            en_espera.id,
        )

    async with SessionApp() as session:
        async with session.begin():
            await set_organization_context(session, organizacion.id)
            reservadas = await registrations_repository.count_reserved_registrations(
                session, organization_id, event_id
            )
            assert reservadas == 1

            await registrations_service.cancel_registration(
                session,
                organization_id=organization_id,
                event_id=event_id,
                registration_id=confirmado_id,
            )

    async with SessionMaintenance() as session:
        espera_fila = await session.get(EventRegistration, en_espera_id)
        assert espera_fila.waitlist_promoted_at is not None
