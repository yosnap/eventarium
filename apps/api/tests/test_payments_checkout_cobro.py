"""Compra pública de pago: liberar el cupo y el código cuando el pago nunca se
cobra, el cinturón de seguridad de `confirmed` y las dos transacciones del
checkout (commit antes de Stripe, idempotencia e importe). Los cuatro caminos de
confirmación están en `test_payments_checkout.py`.
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
from app.modules.payments import checkout_service
from app.modules.payments import repository as payments_repository
from app.modules.payments.models import EventPayment, EventTicketType, OrganizationStripeAccount
from app.modules.registrations import service as registrations_service
from app.modules.registrations.models import EventRegistration
from app.modules.tickets.models import EventTicket
from app.shared.errors import ValidationDomainError
from tests.conftest import OrganizacionDePrueba, iniciar_sesion
from tests.payments_test_helpers import (
    AHORA,
    EVENTS,
    FakeStripeClient,
    _crear_organizacion_con_stripe,
    _crear_publicar_evento_de_pago,
    _fabricar_evento_de_pago_directo,
    _preparar_evento_de_pago,
    _sesion_creada,
    _settings_con_stripe_payments_enabled,
    _url_checkout,
)

# --- Liberar cupo/uso de código cuando el pago nunca llega a cobrarse -------


async def test_rechazar_inscripcion_libera_el_pago_pendiente_y_el_cupo(
    organizacion: OrganizacionDePrueba,
) -> None:
    """Antes de este
    fix, `reject_registration` dejaba el `event_payments` en `pending` para
    siempre — `ESTADOS_CONSUMIBLES` lo sigue contando como cupo ocupado, y
    ningún barrido lo expira nunca (exige `EventRegistration.status ==
    "pending_payment"`, que una inscripción rechazada nunca vuelve a tener).
    """
    async with SessionMaintenance() as session:
        evento = Event(
            organization_id=organizacion.id,
            slug="rechazo-libera-cupo",
            title="Rechazo libera cupo",
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
            organization_id=organizacion.id,
            event_id=evento.id,
            name="General",
            price_cents=1000,
            max_quantity=1,
        )
        session.add(tipo)
        await session.flush()
        inscripcion = EventRegistration(
            event_id=evento.id,
            organization_id=organizacion.id,
            email="rechazado@example.com",
            full_name="Rechazado",
            status="pending_approval",
            ticket_type_id=tipo.id,
        )
        session.add(inscripcion)
        await session.flush()
        pago = EventPayment(
            organization_id=organizacion.id,
            event_id=evento.id,
            registration_id=inscripcion.id,
            stripe_account_id="acct_rechazo",
            ticket_type_id=tipo.id,
            amount_cents=1000,
            currency="eur",
            status="pending",
        )
        session.add(pago)
        await session.commit()
        evento_id, tipo_id, registration_id = evento.id, tipo.id, inscripcion.id

    async with SessionMaintenance() as session:
        # Antes de rechazar: el cupo (`max_quantity=1`) ya está agotado por
        # el pago `pending` de la solicitud sin resolver.
        vendidas = await payments_repository.count_used_ticket_type(
            session, organizacion.id, tipo_id
        )
        assert vendidas == 1

    async with SessionApp() as session:
        async with session.begin():
            await set_organization_context(session, organizacion.id)
            resultado = await registrations_service.reject_registration(
                session,
                organization_id=organizacion.id,
                event_id=evento_id,
                registration_id=registration_id,
            )
            assert resultado.status == "rejected"

    async with SessionMaintenance() as session:
        pago = await session.scalar(
            select(EventPayment).where(EventPayment.registration_id == registration_id)
        )
        assert pago is not None
        assert pago.status == "expired"
        vendidas = await payments_repository.count_used_ticket_type(
            session, organizacion.id, tipo_id
        )
        assert vendidas == 0


async def test_cancelar_inscripcion_pending_payment_libera_el_pago_sin_cobrar(
    organizacion: OrganizacionDePrueba,
) -> None:
    """Mismo camino, aplicado a la cancelación: cancelar una inscripción
    `pending_payment` que nunca llegó a pagarse tampoco pasaba por
    `preparar_reembolso_por_cancelacion` (solo actúa sobre pagos ya cobrados,
    `ESTADOS_REEMBOLSABLES`), así que el pago `pending` también quedaba
    huérfano."""
    async with SessionMaintenance() as session:
        evento = Event(
            organization_id=organizacion.id,
            slug="cancelacion-libera-cupo",
            title="Cancelación libera cupo",
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
            organization_id=organizacion.id,
            event_id=evento.id,
            name="General",
            price_cents=1000,
            max_quantity=1,
        )
        session.add(tipo)
        await session.flush()
        inscripcion = EventRegistration(
            event_id=evento.id,
            organization_id=organizacion.id,
            email="cancelado-sin-pagar@example.com",
            full_name="Cancelado Sin Pagar",
            status="pending_payment",
            ticket_type_id=tipo.id,
            payment_expires_at=AHORA + timedelta(minutes=30),
        )
        session.add(inscripcion)
        await session.flush()
        pago = EventPayment(
            organization_id=organizacion.id,
            event_id=evento.id,
            registration_id=inscripcion.id,
            stripe_account_id="acct_cancelacion",
            ticket_type_id=tipo.id,
            amount_cents=1000,
            currency="eur",
            status="pending",
        )
        session.add(pago)
        await session.commit()
        evento_id, tipo_id, registration_id = evento.id, tipo.id, inscripcion.id

    async with SessionApp() as session:
        async with session.begin():
            await set_organization_context(session, organizacion.id)
            await registrations_service.cancel_registration(
                session,
                organization_id=organizacion.id,
                event_id=evento_id,
                registration_id=registration_id,
            )

    async with SessionMaintenance() as session:
        pago = await session.scalar(
            select(EventPayment).where(EventPayment.registration_id == registration_id)
        )
        assert pago is not None
        assert pago.status == "expired"
        vendidas = await payments_repository.count_used_ticket_type(
            session, organizacion.id, tipo_id
        )
        assert vendidas == 0


async def test_reutilizar_pago_expira_la_sesion_de_stripe_anterior(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    monkeypatch: pytest.MonkeyPatch,
    fake: FakeStripeClient,
) -> None:
    """El test de
    idempotencia ya cubría que las claves difieren entre intentos, pero nunca
    comprobó que la sesión de Checkout anterior se expira de verdad en
    Stripe — solo que el método del doble existía. Aquí se asserta la
    llamada real a `expire_async`, con la sesión y la cuenta correctas."""
    evento, tipo = await _preparar_evento_de_pago(
        cliente, organizacion, monkeypatch, "expira-sesion"
    )
    fake.v1.checkout.sessions.create_async.return_value = _sesion_creada("cs_primera_sesion")

    payload = {
        "email": "expira-sesion@example.com",
        "full_name": "Expira Sesion",
        "data_processing_accepted": True,
        "ticket_type_id": tipo["id"],
        "turnstile_token": "token-de-prueba",
    }
    primera = await cliente.post(_url_checkout(evento["slug"]), json=payload)
    assert primera.status_code == 200, primera.text

    async with SessionMaintenance() as session:
        registro = await session.scalar(
            select(EventRegistration).where(EventRegistration.email == "expira-sesion@example.com")
        )
        pago = await session.scalar(
            select(EventPayment).where(EventPayment.registration_id == registro.id)
        )
        cuenta = await session.scalar(
            select(OrganizationStripeAccount).where(
                OrganizationStripeAccount.organization_id == organizacion.id
            )
        )
        registro.status = "cancelled"
        pago.status = "pending"
        stripe_account_id_esperado = cuenta.stripe_account_id
        await session.commit()

    fake.v1.checkout.sessions.create_async.return_value = _sesion_creada("cs_segunda_sesion")
    segunda = await cliente.post(_url_checkout(evento["slug"]), json=payload)
    assert segunda.status_code == 200, segunda.text

    fake.v1.checkout.sessions.expire_async.assert_awaited_once_with(
        "cs_primera_sesion",
        options={"stripe_account": stripe_account_id_esperado},
    )


async def test_idempotency_key_mismo_expires_at_en_dos_intentos_de_la_misma_inscripcion(
    organizacion: OrganizacionDePrueba, fake: FakeStripeClient
) -> None:
    """El test
    `test_idempotency_key_distinta_por_intento_de_checkout` solo prueba que
    la clave cambia entre intentos; no prueba la causa raíz de un
    `expires_at` recalculado con `datetime.now(UTC)` en cada llamada a
    `crear_sesion_de_pago`, en vez de derivarse siempre del mismo
    `payment_expires_at` ya persistido — lo que rompería la reutilización de
    la `idempotency_key` en Stripe si esta función se reintentara). Llama dos
    veces a `crear_sesion_de_pago` sobre la misma fila de pago, con el reloj
    avanzado entre medias, y comprueba que Stripe recibe el mismo
    `expires_at` las dos veces."""
    stripe_account_id = await _crear_organizacion_con_stripe(organizacion)
    evento_id, ticket_type_id = await _fabricar_evento_de_pago_directo(organizacion, capacity=None)
    payment_expires_at = AHORA + timedelta(minutes=30)
    async with SessionMaintenance() as session:
        inscripcion = EventRegistration(
            event_id=evento_id,
            organization_id=organizacion.id,
            email="mismo-expires@example.com",
            full_name="Mismo Expires",
            status="pending_payment",
            ticket_type_id=ticket_type_id,
            payment_expires_at=payment_expires_at,
        )
        session.add(inscripcion)
        await session.flush()
        pago = EventPayment(
            organization_id=organizacion.id,
            event_id=evento_id,
            registration_id=inscripcion.id,
            stripe_account_id=stripe_account_id,
            ticket_type_id=ticket_type_id,
            amount_cents=1000,
            currency="eur",
            status="pending",
            checkout_attempts=1,
        )
        session.add(pago)
        await session.commit()
        payment_id = pago.id

    fake.v1.checkout.sessions.create_async.return_value = _sesion_creada("cs_primer_intento")
    async with SessionApp() as session:
        async with session.begin():
            await set_organization_context(session, organizacion.id)
            await checkout_service.crear_sesion_de_pago(
                session, payment_id=payment_id, locale="es-ES"
            )
    _, primeros_kwargs = fake.v1.checkout.sessions.create_async.call_args
    primer_expires_at = primeros_kwargs["params"]["expires_at"]
    primera_clave = primeros_kwargs["options"]["idempotency_key"]

    # Simula un reintento real: Stripe llegó a crear la
    # sesión, pero el proceso murió antes de persistir
    # `checkout_link_delivered_at` (si hubiera llegado a persistir, la
    # siguiente llamada devolvería `pago.checkout_url` sin volver a llamar a
    # Stripe — el `if pago.checkout_link_delivered_at is not None: return
    # ...` de `crear_sesion_de_pago`). El mismo `checkout_attempts` (sin
    # pasar por `crear_o_reutilizar_pago`, que sí lo incrementaría) y el
    # mismo `payment_expires_at` de la inscripción: nada se llegó a
    # persistir del primer intento, así que el segundo parte del mismo
    # estado exacto.
    async with SessionMaintenance() as session:
        pago = await session.get(EventPayment, payment_id)
        pago.checkout_link_delivered_at = None
        pago.checkout_url = None
        pago.stripe_checkout_session_id = None
        pago.expires_at = None
        inscripcion = await session.get(EventRegistration, pago.registration_id)
        inscripcion.payment_expires_at = payment_expires_at
        await session.commit()

    fake.v1.checkout.sessions.create_async.reset_mock()
    fake.v1.checkout.sessions.create_async.return_value = _sesion_creada("cs_segundo_intento")
    async with SessionApp() as session:
        async with session.begin():
            await set_organization_context(session, organizacion.id)
            await checkout_service.crear_sesion_de_pago(
                session, payment_id=payment_id, locale="es-ES"
            )
    _, segundos_kwargs = fake.v1.checkout.sessions.create_async.call_args
    segundo_expires_at = segundos_kwargs["params"]["expires_at"]
    segunda_clave = segundos_kwargs["options"]["idempotency_key"]

    # Mismo `checkout_attempts` (retry del mismo intento, no uno nuevo): la
    # `idempotency_key` es la misma las dos veces, y ahora también lo es
    # `expires_at` — antes de este fix, un `expires_at` recalculado con
    # `datetime.now(UTC)` habría roto esta invariante y Stripe habría
    # rechazado la reutilización de la clave con parámetros distintos.
    assert primera_clave == segunda_clave
    assert primer_expires_at == segundo_expires_at


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
    primera = await cliente.post(_url_checkout(evento["slug"]), json=payload)
    assert primera.status_code == 200, primera.text
    _, primera_kwargs = fake.v1.checkout.sessions.create_async.call_args
    primera_clave = primera_kwargs["options"]["idempotency_key"]

    # Caduca y se reintenta con el mismo email: reactiva la misma fila de
    # `event_payments`, con `checkout_attempts` distinto.
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
    segunda = await cliente.post(_url_checkout(evento["slug"]), json=payload)
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
        json={
            "email": "sincuenta@example.com",
            "full_name": "Sin Cuenta",
            "data_processing_accepted": True,
            "ticket_type_id": tipo["id"],
            "turnstile_token": "token-de-prueba",
        },
    )
    assert respuesta.status_code == 409
