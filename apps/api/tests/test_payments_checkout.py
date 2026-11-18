"""Compra pública y guarda de pago de dos capas (fase 6 del PRD, fase 4 de
trabajo).

El foco son los cuatro caminos de confirmación
y el diseño de dos transacciones del checkout. Los webhooks
que confirman estas compras están en `test_payments_webhooks.py`.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.database import SessionApp, SessionMaintenance, set_organization_context
from app.modules.events import service as events_service
from app.modules.events.models import Event
from app.modules.payments.models import EventPayment, EventTicketType
from app.modules.registrations import service as registrations_service
from app.modules.registrations.models import EventRegistration
from app.modules.tickets.models import EventTicket
from app.shared.errors import ConflictError
from tests.conftest import OrganizacionDePrueba, iniciar_sesion
from tests.payments_test_helpers import (
    AHORA,
    EVENTS,
    FakeStripeClient,
    _crear_organizacion_con_stripe,
    _crear_tipo,
    _estado_inscripcion,
    _fabricar_evento_de_pago_directo,
    _payload_evento_pago,
    _preparar_evento_de_pago,
    _sesion_creada,
    _settings_con_stripe_payments_enabled,
    _url_checkout,
)

# --- Los cuatro caminos de confirmación ---------------------------------------


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


@pytest.mark.parametrize(("accept_language", "prefijo"), [("es-ES", ""), ("en-US,en;q=0.9", "/en")])
async def test_stripe_vuelve_a_la_web_en_el_idioma_de_la_compra(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    monkeypatch: pytest.MonkeyPatch,
    fake: FakeStripeClient,
    accept_language: str,
    prefijo: str,
) -> None:
    sufijo = "idioma" + prefijo.strip("/")
    evento, tipo = await _preparar_evento_de_pago(cliente, organizacion, monkeypatch, sufijo)
    fake.v1.checkout.sessions.create_async.return_value = _sesion_creada()

    respuesta = await cliente.post(
        _url_checkout(evento["slug"]),
        headers={"Accept-Language": accept_language},
        json={
            "email": f"{sufijo}@example.com",
            "full_name": "Compra Con Idioma",
            "data_processing_accepted": True,
            "ticket_type_id": tipo["id"],
            "turnstile_token": "token-de-prueba",
        },
    )
    assert respuesta.status_code == 200, respuesta.text
    parametros = fake.v1.checkout.sessions.create_async.await_args.kwargs["params"]
    retorno, cancelado = (
        ("/en/payment/return?", "/en/payment/cancelled?")
        if prefijo
        else ("/pago/retorno?", "/pago/cancelado?")
    )
    assert retorno in parametros["success_url"]
    assert cancelado in parametros["cancel_url"]
    if not prefijo:
        assert "/en/" not in parametros["success_url"]


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
            ticket_type_id=ticket_type_id,
        )
        session.add(inscripcion)
        await session.flush()
        # El pago ya existe en `pending`, tal como lo deja
        # `checkout_service.iniciar_compra` en el alta (fase 6 del PRD):
        # `verify_registration` lo reutiliza,
        # nunca lo crea desde cero.
        pago = EventPayment(
            organization_id=organizacion.id,
            event_id=evento_id,
            registration_id=inscripcion.id,
            stripe_account_id="acct_camino2",
            ticket_type_id=ticket_type_id,
            amount_cents=1000,
            currency="eur",
            status="pending",
        )
        session.add(pago)
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
            assert resultado.payment_expires_at is not None

    async with SessionMaintenance() as session:
        tickets = list(await session.scalars(select(EventTicket)))
        assert tickets == []
        pago = await session.scalar(
            select(EventPayment).where(EventPayment.registration_id == inscripcion.id)
        )
        assert pago is not None
        assert pago.status == "pending"


async def test_camino_3_aprobacion_tras_cambiar_a_paid_deja_pending_payment(
    organizacion: OrganizacionDePrueba,
) -> None:
    """Un evento `approval` cambia a `paid` con
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
        tipo = EventTicketType(
            organization_id=organizacion.id, event_id=evento.id, name="General", price_cents=1000
        )
        session.add(tipo)
        await session.flush()
        inscripcion = EventRegistration(
            event_id=evento.id,
            organization_id=organizacion.id,
            email="camino3@example.com",
            full_name="Camino Tres",
            status="pending_approval",
            ticket_type_id=tipo.id,
        )
        session.add(inscripcion)
        await session.flush()
        # El pago ya existe en `pending`, tal como lo deja
        # `checkout_service.iniciar_compra` en el alta (fase 6 del PRD):
        # `approve_registration` lo reutiliza,
        # nunca lo crea desde cero.
        pago = EventPayment(
            organization_id=organizacion.id,
            event_id=evento.id,
            registration_id=inscripcion.id,
            stripe_account_id="acct_camino3",
            ticket_type_id=tipo.id,
            amount_cents=1000,
            currency="eur",
            status="pending",
        )
        session.add(pago)
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
            assert resultado.payment_expires_at is not None

    async with SessionMaintenance() as session:
        tickets = list(await session.scalars(select(EventTicket)))
        assert tickets == []
        pago = await session.scalar(
            select(EventPayment).where(EventPayment.registration_id == registration_id)
        )
        assert pago is not None
        assert pago.status == "pending"


async def test_camino_3_aprobacion_sin_compra_iniciada_falla(
    organizacion: OrganizacionDePrueba,
) -> None:
    """Sin un `event_payments` ya creado (nunca debería ocurrir, ya que el
    embudo de compra obliga a pasar por ahí) la aprobación no
    puede dejar la inscripción colgada en `pending_payment` sin ningún pago
    posible: falla en vez de aplicar el cambio."""
    async with SessionMaintenance() as session:
        evento = Event(
            organization_id=organizacion.id,
            slug="camino3-sin-pago",
            title="Camino 3 sin pago",
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
            email="camino3-sin-pago@example.com",
            full_name="Camino Tres Sin Pago",
            status="pending_approval",
        )
        session.add(inscripcion)
        await session.commit()
        evento_id, registration_id = evento.id, inscripcion.id

    async with SessionApp() as session:
        async with session.begin():
            await set_organization_context(session, organizacion.id)
            with pytest.raises(ConflictError):
                await registrations_service.approve_registration(
                    session,
                    organization_id=organizacion.id,
                    event_id=evento_id,
                    registration_id=registration_id,
                )


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
        tipo = EventTicketType(
            organization_id=organizacion.id, event_id=evento.id, name="General", price_cents=1000
        )
        session.add(tipo)
        await session.flush()
        inscripcion = EventRegistration(
            event_id=evento.id,
            organization_id=organizacion.id,
            email="camino4@example.com",
            full_name="Camino Cuatro",
            status="waitlisted",
            waitlist_promoted_at=AHORA,
            waitlist_promotion_expires_at=AHORA + timedelta(hours=1),
            ticket_type_id=tipo.id,
        )
        session.add(inscripcion)
        await session.flush()
        # El pago ya existe en `pending`, tal como lo deja
        # `checkout_service.iniciar_compra` en el alta (fase 6 del PRD):
        # `confirm_waitlist_promotion` lo
        # reutiliza, nunca lo crea desde cero.
        pago = EventPayment(
            organization_id=organizacion.id,
            event_id=evento.id,
            registration_id=inscripcion.id,
            stripe_account_id="acct_camino4",
            ticket_type_id=tipo.id,
            amount_cents=1000,
            currency="eur",
            status="pending",
        )
        session.add(pago)
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
        pago = await session.scalar(
            select(EventPayment).where(EventPayment.registration_id == registration_id)
        )
        assert pago is not None
        assert pago.status == "pending"


async def test_camino_4_promocion_sin_compra_iniciada_falla(
    organizacion: OrganizacionDePrueba,
) -> None:
    """Simétrico de `test_camino_3_aprobacion_sin_compra_iniciada_falla`: sin
    un pago ya creado, la promoción no puede dejar la inscripción colgada en
    `pending_payment`."""
    async with SessionMaintenance() as session:
        evento = Event(
            organization_id=organizacion.id,
            slug="camino4-sin-pago",
            title="Camino 4 sin pago",
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
            email="camino4-sin-pago@example.com",
            full_name="Camino Cuatro Sin Pago",
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
            with pytest.raises(ConflictError):
                await registrations_service.confirm_waitlist_promotion(session, token=token)


async def test_camino_3_endpoint_real_en_evento_de_aprobacion_crea_el_pago(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    monkeypatch: pytest.MonkeyPatch,
    fake: FakeStripeClient,
) -> None:
    """Los
    `test_camino_3_*`/`test_camino_4_*` anteriores insertaban el pago a mano
    y solo comprobaban que sobrevivía a `approve_registration`/
    `confirm_waitlist_promotion`. Este ejercita el camino real de producción
    (`POST /public/events/{slug}/checkout`) sobre un evento en modo
    aprobación con un tipo de entrada configurado — sin insertar nada a mano,
    la propia petición debe dejar la fila de `event_payments`."""
    monkeypatch.setattr(events_service, "get_settings", _settings_con_stripe_payments_enabled)
    await _crear_organizacion_con_stripe(organizacion)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    creacion = await cliente.post(
        EVENTS,
        headers=cabeceras,
        json=_payload_evento_pago("aprobacion-real", registration_mode="approval"),
    )
    assert creacion.status_code == 201, creacion.text
    evento = creacion.json()
    tipo = await _crear_tipo(cliente, cabeceras, evento["id"])
    publicacion = await cliente.patch(
        f"{EVENTS}/{evento['id']}",
        headers=cabeceras,
        json={"status": "published", "visibility": "public"},
    )
    assert publicacion.status_code == 200, publicacion.text

    respuesta = await cliente.post(
        _url_checkout(evento["slug"]),
        json={
            "email": "aprobacion-real@example.com",
            "full_name": "Aprobación Real",
            "data_processing_accepted": True,
            "ticket_type_id": tipo["id"],
            "turnstile_token": "token-de-prueba",
        },
    )
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["checkout_url"] is None
    assert (
        await _estado_inscripcion(evento["id"], "aprobacion-real@example.com") == "pending_approval"
    )

    async with SessionMaintenance() as session:
        pago = await session.scalar(
            select(EventPayment).where(EventPayment.event_id == uuid.UUID(evento["id"]))
        )
        assert pago is not None
        assert pago.status == "pending"
    fake.v1.checkout.sessions.create_async.assert_not_awaited()


async def test_camino_4_endpoint_real_con_aforo_lleno_crea_el_pago(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    monkeypatch: pytest.MonkeyPatch,
    fake: FakeStripeClient,
) -> None:
    """Simétrico del test anterior para el camino de lista de espera: dos
    compras reales contra un evento con `capacity=1`, la segunda debe quedar
    `waitlisted` con su propio pago `pending`, creado por la petición misma."""
    evento, tipo = await _preparar_evento_de_pago(
        cliente, organizacion, monkeypatch, "aforo-lleno-real", capacity=1
    )
    fake.v1.checkout.sessions.create_async.return_value = _sesion_creada()

    primera = await cliente.post(
        _url_checkout(evento["slug"]),
        json={
            "email": "primero-aforo@example.com",
            "full_name": "Primero Aforo",
            "data_processing_accepted": True,
            "ticket_type_id": tipo["id"],
            "turnstile_token": "token-de-prueba",
        },
    )
    assert primera.status_code == 200, primera.text
    assert await _estado_inscripcion(evento["id"], "primero-aforo@example.com") == "pending_payment"

    fake.v1.checkout.sessions.create_async.reset_mock()
    segunda = await cliente.post(
        _url_checkout(evento["slug"]),
        json={
            "email": "segundo-aforo@example.com",
            "full_name": "Segundo Aforo",
            "data_processing_accepted": True,
            "ticket_type_id": tipo["id"],
            "turnstile_token": "token-de-prueba",
        },
    )
    assert segunda.status_code == 200, segunda.text
    assert segunda.json()["checkout_url"] is None
    assert await _estado_inscripcion(evento["id"], "segundo-aforo@example.com") == "waitlisted"

    async with SessionMaintenance() as session:
        registro = await session.scalar(
            select(EventRegistration).where(EventRegistration.email == "segundo-aforo@example.com")
        )
        pago = await session.scalar(
            select(EventPayment).where(EventPayment.registration_id == registro.id)
        )
        assert pago is not None
        assert pago.status == "pending"
    fake.v1.checkout.sessions.create_async.assert_not_awaited()
