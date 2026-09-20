"""Webhooks de Stripe, barridos y concurrencia de cupos/códigos (fase 6 del
PRD, fase 4 de trabajo).

Sin red real: `stripe.StripeClient` se sustituye por `FakeStripeClient`. El
alta de la compra (los cuatro caminos de confirmación, T1/T2, idempotencia
del checkout) está en `test_payments_checkout.py`; aquí vive todo lo que
ocurre **después**: confirmación por webhook, recuperación de eventos
perdidos, barrido de pagos caducados y concurrencia real sobre cupos y
códigos de descuento.
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import stripe
from httpx import AsyncClient
from sqlalchemy import select

from app.core.database import SessionApp, SessionMaintenance, set_organization_context
from app.modules.events.models import Event
from app.modules.payments import checkout_service, stripe_client
from app.modules.payments import repository as payments_repository
from app.modules.payments import webhooks as payments_webhooks
from app.modules.payments.models import (
    EventDiscountCode,
    EventPayment,
    EventTicketType,
    OrganizationStripeAccount,
    StripeWebhookEvent,
)
from app.modules.registrations import repository as registrations_repository
from app.modules.registrations import service as registrations_service
from app.modules.registrations.models import EventRegistration
from app.modules.tickets.models import EventTicket
from app.shared.errors import ValidationDomainError
from tests.conftest import OrganizacionDePrueba
from tests.payments_test_helpers import (
    AHORA,
    SECRETO_WEBHOOK,
    WEBHOOK_URL,
    FakeStripeClient,
    _crear_organizacion_con_stripe,
    _sesion_creada,
    _settings_con_stripe,
)

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

    primera = await cliente.post(WEBHOOK_URL, content=cuerpo, headers={"stripe-signature": firma})
    assert primera.status_code == 200, primera.text

    async with SessionMaintenance() as session:
        inscripcion = await session.get(EventRegistration, registration_id)
        assert inscripcion.status == "confirmed"
        tickets = list(await session.scalars(select(EventTicket)))
        assert len(tickets) == 1

    # Reenvío del mismo `evt_...`: una sola entrada, un solo pago `paid`.
    segunda = await cliente.post(WEBHOOK_URL, content=cuerpo, headers={"stripe-signature": firma})
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


async def test_confirmar_pago_ya_reembolsado_no_vuelve_a_paid(
    organizacion: OrganizacionDePrueba,
) -> None:
    """La prueba
    existente de `confirmar_pago_y_registro` solo cubre el camino feliz. Un
    pago ya `refunded` (o `expired`) que reciba una segunda confirmación —
    reenvío de Stripe, o una carrera con el barrido de caducados — no debe
    volver a `paid`, y la función debe devolver `"ignored"` en vez de aplicar
    el cambio."""
    stripe_account_id = f"acct_{organizacion.slug}"
    async with SessionMaintenance() as session:
        evento = Event(
            organization_id=organizacion.id,
            slug="reembolsado-no-revive",
            title="Reembolsado no revive",
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
            email="reembolsado@example.com",
            full_name="Reembolsado",
            status="cancelled",
            cancelled_at=AHORA,
        )
        session.add(inscripcion)
        await session.flush()
        pago = EventPayment(
            organization_id=organizacion.id,
            event_id=evento.id,
            registration_id=inscripcion.id,
            stripe_account_id=stripe_account_id,
            ticket_type_id=tipo.id,
            stripe_checkout_session_id="cs_reembolsado_1",
            amount_cents=1000,
            currency="eur",
            status="refunded",
            refunded_cents=1000,
            refunded_at=AHORA,
        )
        session.add(pago)
        await session.commit()
        payment_id, registration_id = pago.id, inscripcion.id

    async with SessionApp() as session:
        async with session.begin():
            await set_organization_context(session, organizacion.id)
            pago = await session.get(EventPayment, payment_id)
            inscripcion = await session.get(EventRegistration, registration_id)
            resultado = await checkout_service.confirmar_pago_y_registro(
                session, pago, inscripcion, stripe_payment_intent_id="pi_reintentado"
            )
            assert resultado == "ignored"

    async with SessionMaintenance() as session:
        pago_fila = await session.get(EventPayment, payment_id)
        assert pago_fila.status == "refunded"
        assert pago_fila.stripe_payment_intent_id is None
        inscripcion_fila = await session.get(EventRegistration, registration_id)
        assert inscripcion_fila.status == "cancelled"


async def test_webhook_checkout_completed_sobre_pago_ya_expirado_no_lo_revive(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mismo escenario que el estado exacto exigido antes de confirmar, pero
    por el camino completo del webhook real
    (`_handle_checkout_completed`): un `checkout.session.completed` reenviado
    contra un pago ya `expired` (p. ej. el barrido de caducados ganó la
    carrera) debe quedar `"ignored"` en `stripe_webhook_events`, sin volver a
    confirmar la inscripción."""
    monkeypatch.setattr(stripe_client, "get_settings", _settings_con_stripe)
    stripe_account_id = await _crear_organizacion_con_stripe(organizacion)
    registration_id, payment_id = await _crear_pago_pending(
        organizacion, stripe_account_id=stripe_account_id, session_id="cs_expirado_ya_1"
    )
    async with SessionMaintenance() as session:
        pago = await session.get(EventPayment, payment_id)
        inscripcion = await session.get(EventRegistration, registration_id)
        pago.status = "expired"
        inscripcion.status = "cancelled"
        inscripcion.cancelled_at = AHORA
        await session.commit()

    event_id = f"evt_{uuid.uuid4().hex}"
    cuerpo = _cuerpo_checkout_completed(
        event_id=event_id, session_id="cs_expirado_ya_1", account=stripe_account_id
    )
    firma = _firmar(cuerpo, int(time.time()))
    monkeypatch.setattr(
        "app.core.tasks.process_stripe_webhook_task.kiq",
        AsyncMock(side_effect=payments_webhooks.procesar_evento),
    )

    respuesta = await cliente.post(WEBHOOK_URL, content=cuerpo, headers={"stripe-signature": firma})
    assert respuesta.status_code == 200, respuesta.text

    async with SessionMaintenance() as session:
        pago_fila = await session.get(EventPayment, payment_id)
        assert pago_fila.status == "expired"
        inscripcion_fila = await session.get(EventRegistration, registration_id)
        assert inscripcion_fila.status == "cancelled"
        fila = await payments_repository.get_webhook_event(session, event_id)
        assert fila.status == "ignored"


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


async def test_barrido_red_de_seguridad_expira_pago_huerfano_de_inscripcion_rechazada(
    fake: FakeStripeClient, organizacion: OrganizacionDePrueba
) -> None:
    """Red de seguridad
    además del cambio explícito en `reject_registration`. Simula una fila que
    se hubiera quedado huérfana por cualquier otro camino no cubierto
    explícitamente (aquí, forzando el estado `rejected` sin pasar por
    `reject_registration`): el barrido debe expirar igualmente el pago
    `pending`, sin consultar Stripe (nunca hubo Checkout Session real que
    consultar para esta inscripción)."""
    stripe_account_id = f"acct_{organizacion.slug}"
    async with SessionMaintenance() as session:
        evento = Event(
            organization_id=organizacion.id,
            slug="barrido-red-seguridad",
            title="Barrido red de seguridad",
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
        await session.flush()
        inscripcion = EventRegistration(
            event_id=evento.id,
            organization_id=organizacion.id,
            email="huerfano@example.com",
            full_name="Huérfano",
            status="rejected",
            rejected_at=AHORA,
            ticket_type_id=tipo.id,
        )
        session.add(inscripcion)
        await session.flush()
        pago = EventPayment(
            organization_id=organizacion.id,
            event_id=evento.id,
            registration_id=inscripcion.id,
            stripe_account_id=stripe_account_id,
            ticket_type_id=tipo.id,
            amount_cents=1000,
            currency="eur",
            status="pending",
        )
        session.add(pago)
        await session.commit()
        registration_id, payment_id = inscripcion.id, pago.id

    await checkout_service.expirar_pagos_pendientes()

    fake.v1.checkout.sessions.retrieve_async.assert_not_awaited()
    async with SessionMaintenance() as session:
        pago_fila = await session.get(EventPayment, payment_id)
        assert pago_fila.status == "expired"
        inscripcion_fila = await session.get(EventRegistration, registration_id)
        assert inscripcion_fila.status == "rejected"


async def test_regresion_evento_gratuito_con_lista_de_espera_no_se_ve_afectado(
    organizacion: OrganizacionDePrueba,
) -> None:
    """El riesgo de `count_reserved_registrations`: un evento
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


# --- Enlace de pago de los caminos 2, 3 y 4: idempotencia -------------------


async def test_dispatch_enlaces_es_idempotente(
    fake: FakeStripeClient, organizacion: OrganizacionDePrueba, monkeypatch: pytest.MonkeyPatch
) -> None:
    stripe_account_id = await _crear_organizacion_con_stripe(organizacion)
    async with SessionMaintenance() as session:
        evento = Event(
            organization_id=organizacion.id,
            slug="dispatch-idem",
            title="Dispatch idem",
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
            email="dispatch@example.com",
            full_name="Dispatch Test",
            status="pending_payment",
        )
        session.add(inscripcion)
        await session.flush()
        pago = EventPayment(
            organization_id=organizacion.id,
            event_id=evento.id,
            registration_id=inscripcion.id,
            stripe_account_id=stripe_account_id,
            ticket_type_id=tipo.id,
            amount_cents=1000,
            currency="eur",
            status="pending",
        )
        session.add(pago)
        await session.commit()
        payment_id = pago.id

    correo_mock = AsyncMock()
    monkeypatch.setattr("app.core.tasks.send_registration_payment_link_email.kiq", correo_mock)
    fake.v1.checkout.sessions.create_async.return_value = _sesion_creada("cs_dispatch_1")

    await checkout_service.dispatch_pending_payment_links()
    await checkout_service.dispatch_pending_payment_links()

    assert fake.v1.checkout.sessions.create_async.await_count == 1
    correo_mock.assert_awaited_once()

    async with SessionMaintenance() as session:
        pago_fila = await session.get(EventPayment, payment_id)
        assert pago_fila.stripe_checkout_session_id == "cs_dispatch_1"
        assert pago_fila.checkout_link_delivered_at is not None


# --- Concurrencia: cupo de tipo de entrada y usos de código ------------------


async def test_tres_compras_concurrentes_sobre_cupo_de_dos_solo_dos_prosperan(
    organizacion: OrganizacionDePrueba, monkeypatch: pytest.MonkeyPatch
) -> None:
    import asyncio

    monkeypatch.setattr(stripe_client, "get_settings", _settings_con_stripe)
    await _crear_organizacion_con_stripe(organizacion)

    async with SessionMaintenance() as session:
        evento = Event(
            organization_id=organizacion.id,
            slug="concurrencia-cupo",
            title="Concurrencia cupo",
            status="published",
            visibility="public",
            starts_at=AHORA,
            ends_at=AHORA + timedelta(days=1),
            location_mode="online",
            registration_mode="paid",
            email_verification_required=False,
        )
        session.add(evento)
        await session.flush()
        tipo = EventTicketType(
            organization_id=organizacion.id,
            event_id=evento.id,
            name="Limitado",
            price_cents=1000,
            max_quantity=2,
        )
        session.add(tipo)
        await session.commit()
        evento_id, tipo_id = evento.id, tipo.id

    evento_fresco = None
    async with SessionMaintenance() as session:
        evento_fresco = await session.get(Event, evento_id)
        assert evento_fresco is not None
        session.expunge(evento_fresco)

    async def _crear_sesion_id(*_args, **_kwargs):
        return _sesion_creada(f"cs_{uuid.uuid4().hex[:8]}")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(stripe_client, "get_settings", _settings_con_stripe)
        instancia = FakeStripeClient()
        instancia.v1.checkout.sessions.create_async.side_effect = _crear_sesion_id
        mp.setattr(stripe_client.stripe, "StripeClient", lambda **_kwargs: instancia)

        resultados = await asyncio.gather(
            *[
                checkout_service.iniciar_compra(
                    event=evento_fresco,
                    email=f"concurrente{i}@example.com",
                    full_name=f"Concurrente {i}",
                    answers=[],
                    data_processing_accepted=True,
                    marketing_accepted=False,
                    recording_accepted=False,
                    ticket_type_id=tipo_id,
                    code=None,
                )
                for i in range(3)
            ],
            return_exceptions=True,
        )

    exitos = [r for r in resultados if not isinstance(r, Exception) and r.checkout_url is not None]
    fallos = [r for r in resultados if isinstance(r, ValidationDomainError)]
    assert len(exitos) == 2, resultados
    assert len(fallos) == 1

    async with SessionMaintenance() as session:
        vendidas = await payments_repository.count_used_ticket_type(
            session, organizacion.id, tipo_id
        )
        assert vendidas == 2


async def test_cuatro_usos_concurrentes_de_codigo_con_max_uses_tres(
    organizacion: OrganizacionDePrueba, monkeypatch: pytest.MonkeyPatch
) -> None:
    import asyncio

    monkeypatch.setattr(stripe_client, "get_settings", _settings_con_stripe)
    await _crear_organizacion_con_stripe(organizacion)

    async with SessionMaintenance() as session:
        evento = Event(
            organization_id=organizacion.id,
            slug="concurrencia-codigo",
            title="Concurrencia código",
            status="published",
            visibility="public",
            starts_at=AHORA,
            ends_at=AHORA + timedelta(days=1),
            location_mode="online",
            registration_mode="paid",
            email_verification_required=False,
        )
        session.add(evento)
        await session.flush()
        tipo = EventTicketType(
            organization_id=organizacion.id, event_id=evento.id, name="General", price_cents=1000
        )
        session.add(tipo)
        await session.flush()
        codigo = EventDiscountCode(
            organization_id=organizacion.id,
            event_id=evento.id,
            code="LIMITADO3",
            discount_type="percentage",
            discount_value=10,
            max_uses=3,
        )
        session.add(codigo)
        await session.commit()
        evento_id, tipo_id = evento.id, tipo.id

    async with SessionMaintenance() as session:
        evento_fresco = await session.get(Event, evento_id)
        assert evento_fresco is not None
        session.expunge(evento_fresco)

    async def _crear_sesion_id(*_args, **_kwargs):
        return _sesion_creada(f"cs_{uuid.uuid4().hex[:8]}")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(stripe_client, "get_settings", _settings_con_stripe)
        instancia = FakeStripeClient()
        instancia.v1.checkout.sessions.create_async.side_effect = _crear_sesion_id
        mp.setattr(stripe_client.stripe, "StripeClient", lambda **_kwargs: instancia)

        resultados = await asyncio.gather(
            *[
                checkout_service.iniciar_compra(
                    event=evento_fresco,
                    email=f"codigo{i}@example.com",
                    full_name=f"Codigo {i}",
                    answers=[],
                    data_processing_accepted=True,
                    marketing_accepted=False,
                    recording_accepted=False,
                    ticket_type_id=tipo_id,
                    code="LIMITADO3",
                )
                for i in range(4)
            ],
            return_exceptions=True,
        )

    exitos = [r for r in resultados if not isinstance(r, Exception) and r.checkout_url is not None]
    assert len(exitos) == 3, resultados

    async with SessionMaintenance() as session:
        codigo_fila = await session.scalar(
            select(EventDiscountCode).where(EventDiscountCode.event_id == evento_id)
        )
        usos = await payments_repository.count_used_discount_code(
            session, organizacion.id, codigo_fila.id
        )
        assert usos == 3


async def test_webhook_sesion_desconocida_se_marca_ignored(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(stripe_client, "get_settings", _settings_con_stripe)
    stripe_account_id = await _crear_organizacion_con_stripe(organizacion)

    event_id = f"evt_{uuid.uuid4().hex}"
    cuerpo = _cuerpo_checkout_completed(
        event_id=event_id, session_id="cs_no_existe", account=stripe_account_id
    )
    firma = _firmar(cuerpo, int(time.time()))
    monkeypatch.setattr(
        "app.core.tasks.process_stripe_webhook_task.kiq",
        AsyncMock(side_effect=payments_webhooks.procesar_evento),
    )

    respuesta = await cliente.post(WEBHOOK_URL, content=cuerpo, headers={"stripe-signature": firma})
    assert respuesta.status_code == 200

    async with SessionMaintenance() as session:
        fila = await payments_repository.get_webhook_event(session, event_id)
        assert fila.status == "ignored"
