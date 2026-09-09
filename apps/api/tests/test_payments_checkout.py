"""Compra pública y guarda de pago de dos capas (fase 6 del PRD, fase 4 de
trabajo).

El foco es el hallazgo #1 del red-team (los cuatro caminos de confirmación)
y el diseño de dos transacciones del checkout (hallazgo #12). Los webhooks
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
from app.modules.payments.models import EventPayment, EventTicketType, OrganizationStripeAccount
from app.modules.registrations import service as registrations_service
from app.modules.registrations.models import EventRegistration
from app.modules.tickets.models import EventTicket
from app.shared.errors import ConflictError, ValidationDomainError
from tests.conftest import OrganizacionDePrueba, iniciar_sesion
from tests.payments_test_helpers import (
    AHORA,
    EVENTS,
    FakeStripeClient,
    _crear_organizacion_con_stripe,
    _crear_publicar_evento_de_pago,
    _estado_inscripcion,
    _preparar_evento_de_pago,
    _sesion_creada,
    _settings_con_stripe_payments_enabled,
    _url_checkout,
)

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
            ticket_type_id=ticket_type_id,
        )
        session.add(inscripcion)
        await session.flush()
        # El pago ya existe en `pending`, tal como lo deja
        # `checkout_service.iniciar_compra` en el alta (fase 6 del PRD,
        # hallazgo C1 del code review): `verify_registration` lo reutiliza,
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
        # `checkout_service.iniciar_compra` en el alta (fase 6 del PRD,
        # hallazgo C1 del code review): `approve_registration` lo reutiliza,
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
    """Sin un `event_payments` ya creado (nunca debería ocurrir tras el
    hallazgo C1b, que obliga a pasar por el embudo de compra) la aprobación no
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
        # `checkout_service.iniciar_compra` en el alta (fase 6 del PRD,
        # hallazgo C1 del code review): `confirm_waitlist_promotion` lo
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
    # `_crear_publicar_evento_de_pago` ya crea el tipo «General» (lo necesita
    # para poder publicar, ver `_asegurar_venta_posible`): se recupera en vez
    # de crear un segundo, que chocaría con `UniqueConstraint(event_id, name)`.
    listado = await cliente.get(f"{EVENTS}/{evento['id']}/ticket-types", headers=cabeceras)
    assert listado.status_code == 200, listado.text
    tipo = listado.json()[0]

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
