"""Reembolsos con outbox, política de plazo y revocación de entradas (fase 6
del PRD, fase 5 de trabajo).

Sin red real: `stripe.StripeClient` se sustituye por un doble, mismo patrón
que `test_payments_checkout_and_webhooks.py`. El foco es el outbox (hallazgos
#11 y #12), la política de reembolso automático (hallazgo #13) y que
`refunded_cents` se fija desde `charge.refunded`, nunca se suma.
"""

from __future__ import annotations

import asyncio
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
from app.modules.events.models import Event
from app.modules.payments import refunds_service, stripe_client
from app.modules.payments import repository as payments_repository
from app.modules.payments import webhooks as payments_webhooks
from app.modules.payments.models import (
    EventPayment,
    EventPaymentRefund,
    EventTicketType,
    OrganizationStripeAccount,
)
from app.modules.registrations import service as registrations_service
from app.modules.registrations.models import EventRegistration
from app.modules.tickets.models import EventTicket
from app.modules.tickets.service import emitir_entrada
from app.shared.errors import ConflictError
from tests.conftest import OrganizacionDePrueba, iniciar_sesion

EVENTS = "/api/v1/events"
WEBHOOK_URL = "/api/v1/webhooks/stripe"
SECRETO_WEBHOOK = "whsec_" + "d" * 40
AHORA = datetime.now(UTC).replace(microsecond=0)


def _settings_con_stripe() -> Settings:
    return Settings(stripe_secret_key="sk_test_" + "a" * 40, stripe_webhook_secret=SECRETO_WEBHOOK)


class _FakeV1:
    def __init__(self) -> None:
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


def _reembolso_creado(refund_id: str = "re_1") -> SimpleNamespace:
    return SimpleNamespace(id=refund_id)


async def _crear_organizacion_con_stripe(organizacion: OrganizacionDePrueba) -> str:
    stripe_account_id = f"acct_{organizacion.slug}"
    async with SessionMaintenance() as session:
        session.add(
            OrganizationStripeAccount(
                organization_id=organizacion.id,
                stripe_account_id=stripe_account_id,
                charges_enabled=True,
            )
        )
        await session.commit()
    return stripe_account_id


async def _crear_evento_pagado(
    organizacion: OrganizacionDePrueba,
    *,
    stripe_account_id: str,
    starts_at: datetime = AHORA + timedelta(days=10),
    payment_intent_id: str = "pi_test_1",
    used_at: datetime | None = None,
    capacity: int | None = None,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Evento publicado con una inscripción `confirmed`, su entrada emitida y
    un pago `paid`. Devuelve `(event_id, registration_id, payment_id)`."""
    async with SessionMaintenance() as session:
        evento = Event(
            organization_id=organizacion.id,
            slug=f"reembolso-{uuid.uuid4().hex[:8]}",
            title="Evento de reembolso",
            status="published",
            visibility="public",
            starts_at=starts_at,
            ends_at=starts_at + timedelta(hours=2),
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
        await session.flush()
        inscripcion = EventRegistration(
            event_id=evento.id,
            organization_id=organizacion.id,
            email=f"comprador-{uuid.uuid4().hex[:6]}@example.com",
            full_name="Comprador de prueba",
            status="confirmed",
            confirmed_at=AHORA,
        )
        session.add(inscripcion)
        await session.flush()
        ticket = await emitir_entrada(session, inscripcion)
        if used_at is not None:
            ticket.used_at = used_at
        pago = EventPayment(
            organization_id=organizacion.id,
            event_id=evento.id,
            registration_id=inscripcion.id,
            stripe_account_id=stripe_account_id,
            ticket_type_id=tipo.id,
            stripe_checkout_session_id=f"cs_{uuid.uuid4().hex[:8]}",
            stripe_payment_intent_id=payment_intent_id,
            amount_cents=1000,
            currency="eur",
            status="paid",
            paid_at=AHORA,
        )
        session.add(pago)
        await session.commit()
        return evento.id, inscripcion.id, pago.id


async def _cancelar(
    organization_id: uuid.UUID, event_id: uuid.UUID, registration_id: uuid.UUID
) -> None:
    async with SessionApp() as session:
        async with session.begin():
            await set_organization_context(session, organization_id)
            await registrations_service.cancel_registration(
                session,
                organization_id=organization_id,
                event_id=event_id,
                registration_id=registration_id,
            )


# --- Outbox: cancelación crea la intención, nunca llama a Stripe -------------


async def test_cancelacion_dentro_de_plazo_crea_intencion_y_revoca(
    organizacion: OrganizacionDePrueba, fake: FakeStripeClient
) -> None:
    stripe_account_id = await _crear_organizacion_con_stripe(organizacion)
    event_id, registration_id, payment_id = await _crear_evento_pagado(
        organizacion, stripe_account_id=stripe_account_id
    )

    await _cancelar(organizacion.id, event_id, registration_id)

    async with SessionMaintenance() as session:
        inscripcion = await session.get(EventRegistration, registration_id)
        assert inscripcion.status == "cancelled"
        ticket = await session.scalar(
            select(EventTicket).where(EventTicket.registration_id == registration_id)
        )
        assert ticket.revoked_at is not None

        reembolso = await session.scalar(
            select(EventPaymentRefund).where(EventPaymentRefund.payment_id == payment_id)
        )
        assert reembolso is not None
        assert reembolso.status == "pending"
        assert reembolso.reason == "cancellation"
        assert reembolso.revoke_ticket is True
        assert reembolso.amount_cents == 1000

    fake.v1.refunds.create_async.assert_not_awaited()


async def test_autocancelacion_publica_hereda_el_mismo_outbox(
    organizacion: OrganizacionDePrueba, fake: FakeStripeClient
) -> None:
    """Mismo camino que el panel, sin ningún código propio (Success Criteria)."""
    stripe_account_id = await _crear_organizacion_con_stripe(organizacion)
    event_id, registration_id, payment_id = await _crear_evento_pagado(
        organizacion, stripe_account_id=stripe_account_id
    )

    token = await registrations_service._generar_token_cancelacion(registration_id)  # noqa: SLF001
    async with SessionApp() as session:
        async with session.begin():
            await set_organization_context(session, organizacion.id)
            await registrations_service.cancel_registration_by_token(session, token=token)

    async with SessionMaintenance() as session:
        reembolso = await session.scalar(
            select(EventPaymentRefund).where(EventPaymentRefund.payment_id == payment_id)
        )
        assert reembolso is not None
        assert reembolso.status == "pending"
    fake.v1.refunds.create_async.assert_not_awaited()


async def test_ninguna_llamada_a_stripe_dentro_de_cancelar_inscripcion(
    organizacion: OrganizacionDePrueba, fake: FakeStripeClient
) -> None:
    """Hallazgo #12, verificado contando llamadas al cliente simulado durante
    la propia transacción de cancelación (antes de que la tarea programada
    pueda ejecutarse)."""
    stripe_account_id = await _crear_organizacion_con_stripe(organizacion)
    event_id, registration_id, _ = await _crear_evento_pagado(
        organizacion, stripe_account_id=stripe_account_id
    )

    async with SessionApp() as session:
        async with session.begin():
            await set_organization_context(session, organizacion.id)
            inscripcion = await registrations_service.repository.get_registration_for_update(
                session, organizacion.id, event_id, registration_id
            )
            await registrations_service._cancelar_inscripcion(  # noqa: SLF001
                session, organization_id=organizacion.id, event_id=event_id, inscripcion=inscripcion
            )
            assert fake.v1.refunds.create_async.await_count == 0


# --- Política de plazo (hallazgo #13) ----------------------------------------


async def test_evento_ya_empezado_cancela_sin_reembolso_automatico(
    organizacion: OrganizacionDePrueba,
) -> None:
    stripe_account_id = await _crear_organizacion_con_stripe(organizacion)
    event_id, registration_id, payment_id = await _crear_evento_pagado(
        organizacion, stripe_account_id=stripe_account_id, starts_at=AHORA - timedelta(hours=1)
    )

    await _cancelar(organizacion.id, event_id, registration_id)

    async with SessionMaintenance() as session:
        reembolso = await session.scalar(
            select(EventPaymentRefund).where(EventPaymentRefund.payment_id == payment_id)
        )
        assert reembolso is None
        inscripcion = await session.get(EventRegistration, registration_id)
        assert inscripcion.status == "cancelled"


async def test_entrada_ya_usada_cancela_sin_reembolso_automatico(
    organizacion: OrganizacionDePrueba,
) -> None:
    stripe_account_id = await _crear_organizacion_con_stripe(organizacion)
    event_id, registration_id, payment_id = await _crear_evento_pagado(
        organizacion, stripe_account_id=stripe_account_id, used_at=AHORA
    )

    await _cancelar(organizacion.id, event_id, registration_id)

    async with SessionMaintenance() as session:
        reembolso = await session.scalar(
            select(EventPaymentRefund).where(EventPaymentRefund.payment_id == payment_id)
        )
        assert reembolso is None


async def test_fuera_de_plazo_de_corte_cancela_sin_reembolso_automatico(
    organizacion: OrganizacionDePrueba,
) -> None:
    stripe_account_id = await _crear_organizacion_con_stripe(organizacion)
    # `payment_refund_cutoff_hours` por defecto es 24: un evento que empieza
    # dentro de 1 hora está dentro del plazo de corte.
    event_id, registration_id, payment_id = await _crear_evento_pagado(
        organizacion, stripe_account_id=stripe_account_id, starts_at=AHORA + timedelta(hours=1)
    )

    await _cancelar(organizacion.id, event_id, registration_id)

    async with SessionMaintenance() as session:
        reembolso = await session.scalar(
            select(EventPaymentRefund).where(EventPaymentRefund.payment_id == payment_id)
        )
        assert reembolso is None


# --- Tarea de reembolsos: ejecución, idempotencia y concurrencia ------------


async def test_tarea_ejecuta_el_reembolso_pendiente(
    organizacion: OrganizacionDePrueba, fake: FakeStripeClient
) -> None:
    stripe_account_id = await _crear_organizacion_con_stripe(organizacion)
    event_id, registration_id, payment_id = await _crear_evento_pagado(
        organizacion, stripe_account_id=stripe_account_id
    )
    await _cancelar(organizacion.id, event_id, registration_id)
    fake.v1.refunds.create_async.return_value = _reembolso_creado("re_ejecutado")

    await refunds_service.procesar_reembolsos_pendientes()

    _, kwargs = fake.v1.refunds.create_async.call_args
    assert kwargs["options"]["idempotency_key"].startswith("refund_")
    assert kwargs["options"]["stripe_account"] == stripe_account_id

    async with SessionMaintenance() as session:
        reembolso = await session.scalar(
            select(EventPaymentRefund).where(EventPaymentRefund.payment_id == payment_id)
        )
        assert reembolso.status == "succeeded"
        assert reembolso.stripe_refund_id == "re_ejecutado"
        # El importe del pago lo fija el webhook, no la respuesta de la tarea.
        pago = await session.get(EventPayment, payment_id)
        assert pago.status == "paid"
        assert pago.refunded_cents == 0


async def test_idempotency_key_deriva_de_la_pk_del_outbox(
    organizacion: OrganizacionDePrueba, fake: FakeStripeClient
) -> None:
    stripe_account_id = await _crear_organizacion_con_stripe(organizacion)
    event_id, registration_id, payment_id = await _crear_evento_pagado(
        organizacion, stripe_account_id=stripe_account_id
    )
    await _cancelar(organizacion.id, event_id, registration_id)
    fake.v1.refunds.create_async.return_value = _reembolso_creado()

    async with SessionMaintenance() as session:
        reembolso = await session.scalar(
            select(EventPaymentRefund).where(EventPaymentRefund.payment_id == payment_id)
        )
        refund_id = reembolso.id

    await refunds_service.procesar_reembolsos_pendientes()

    _, kwargs = fake.v1.refunds.create_async.call_args
    assert kwargs["options"]["idempotency_key"] == f"refund_{refund_id}"


async def test_fallo_de_escritura_tras_exito_en_stripe_deja_rastro_y_reintenta_misma_clave(
    organizacion: OrganizacionDePrueba, fake: FakeStripeClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hallazgo #11: simula que Stripe confirma el reembolso pero la
    transacción que marca `succeeded` nunca llega a completarse (la fila se
    queda `submitted`). El barrido de atascados la retoma con la **misma**
    `idempotency_key`, sin duplicar el reembolso."""
    stripe_account_id = await _crear_organizacion_con_stripe(organizacion)
    event_id, registration_id, payment_id = await _crear_evento_pagado(
        organizacion, stripe_account_id=stripe_account_id
    )
    await _cancelar(organizacion.id, event_id, registration_id)
    fake.v1.refunds.create_async.return_value = _reembolso_creado("re_atascado")

    llamada_original = refunds_service.maintenance_session
    llamadas = {"n": 0}

    def _maintenance_session_que_falla_la_escritura_final():
        llamadas["n"] += 1
        # 1ª apertura: lista las filas `pending`. 2ª: marca `submitted`. 3ª:
        # escribiría `succeeded` — se simula que esa tercera transacción
        # nunca llega a persistir, dejando la fila en `submitted` (como si el
        # proceso hubiera muerto justo después de la llamada a Stripe).
        if llamadas["n"] == 3:

            class _SesionRota:
                async def __aenter__(self):
                    raise RuntimeError("fallo simulado tras la llamada a Stripe")

                async def __aexit__(self, *_args):
                    return False

            return _SesionRota()
        return llamada_original()

    monkeypatch.setattr(
        refunds_service, "maintenance_session", _maintenance_session_que_falla_la_escritura_final
    )

    with pytest.raises(RuntimeError):
        await refunds_service.procesar_reembolsos_pendientes()

    async with SessionMaintenance() as session:
        reembolso = await session.scalar(
            select(EventPaymentRefund).where(EventPaymentRefund.payment_id == payment_id)
        )
        assert reembolso.status == "submitted"
        refund_id = reembolso.id
        # Atascada hace más de 10 minutos, para que el barrido la recoja.
        reembolso.submitted_at = AHORA - timedelta(minutes=15)
        await session.commit()

    monkeypatch.setattr(refunds_service, "maintenance_session", llamada_original)
    fake.v1.refunds.create_async.reset_mock()
    fake.v1.refunds.create_async.return_value = _reembolso_creado("re_atascado")

    await refunds_service.reencolar_reembolsos_atascados()

    _, kwargs = fake.v1.refunds.create_async.call_args
    assert kwargs["options"]["idempotency_key"] == f"refund_{refund_id}"
    async with SessionMaintenance() as session:
        reembolso = await session.get(EventPaymentRefund, refund_id)
        assert reembolso.status == "succeeded"


async def test_dos_ejecuciones_concurrentes_producen_un_solo_reembolso(
    organizacion: OrganizacionDePrueba, fake: FakeStripeClient
) -> None:
    stripe_account_id = await _crear_organizacion_con_stripe(organizacion)
    event_id, registration_id, payment_id = await _crear_evento_pagado(
        organizacion, stripe_account_id=stripe_account_id
    )
    await _cancelar(organizacion.id, event_id, registration_id)

    async def _crear_con_retardo(*_args, **_kwargs):
        await asyncio.sleep(0.05)
        return _reembolso_creado("re_concurrente")

    fake.v1.refunds.create_async.side_effect = _crear_con_retardo

    await asyncio.gather(
        refunds_service.procesar_reembolsos_pendientes(),
        refunds_service.procesar_reembolsos_pendientes(),
    )

    assert fake.v1.refunds.create_async.await_count == 1
    async with SessionMaintenance() as session:
        reembolso = await session.scalar(
            select(EventPaymentRefund).where(EventPaymentRefund.payment_id == payment_id)
        )
        assert reembolso.status == "succeeded"


# --- C2: `attempts` sube en toda salida no exitosa, con tope de reintentos --


async def test_error_directo_de_stripe_incrementa_attempts_y_deja_failed(
    organizacion: OrganizacionDePrueba, fake: FakeStripeClient
) -> None:
    """Hallazgo IMP-2 (C2) del code review de la fase 6, ronda 3: antes de
    `_marcar_intento_fallido`, la rama de error directo de
    `_ejecutar_reembolso` (la llamada a Stripe lanza `ExternalServiceError`)
    no incrementaba `attempts` — un reembolso que siempre fallara nunca
    llegaba a `_INTENTOS_MAXIMOS` y se reencolaba para siempre sin ninguna
    alarma."""
    stripe_account_id = await _crear_organizacion_con_stripe(organizacion)
    event_id, registration_id, payment_id = await _crear_evento_pagado(
        organizacion, stripe_account_id=stripe_account_id
    )
    await _cancelar(organizacion.id, event_id, registration_id)
    fake.v1.refunds.create_async.side_effect = stripe.StripeError(
        "detalle interno de Stripe que no debe llegar al panel"
    )

    await refunds_service.procesar_reembolsos_pendientes()

    async with SessionMaintenance() as session:
        reembolso = await session.scalar(
            select(EventPaymentRefund).where(EventPaymentRefund.payment_id == payment_id)
        )
        assert reembolso.status == "failed"
        assert reembolso.attempts == 1
        assert reembolso.error is not None


async def test_reintento_atascado_partiendo_de_failed_incrementa_attempts_y_se_detiene_en_el_tope(
    organizacion: OrganizacionDePrueba,
    fake: FakeStripeClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Complementa el test anterior con el otro camino del hallazgo C2: un
    reintento vía `reencolar_reembolsos_atascados` que arranca ya en `failed`
    también debe incrementar `attempts`, hasta dejar de reencolarse al llegar
    a `_INTENTOS_MAXIMOS` (5) y registrar el error en el log."""
    stripe_account_id = await _crear_organizacion_con_stripe(organizacion)
    event_id, registration_id, payment_id = await _crear_evento_pagado(
        organizacion, stripe_account_id=stripe_account_id
    )
    await _cancelar(organizacion.id, event_id, registration_id)
    fake.v1.refunds.create_async.side_effect = stripe.StripeError("fallo persistente simulado")

    async with SessionMaintenance() as session:
        reembolso = await session.scalar(
            select(EventPaymentRefund).where(EventPaymentRefund.payment_id == payment_id)
        )
        reembolso.status = "failed"
        reembolso.attempts = 4
        refund_id = reembolso.id
        await session.commit()

    caplog.set_level("ERROR", logger="app.modules.payments.refunds_service")
    await refunds_service.reencolar_reembolsos_atascados()

    async with SessionMaintenance() as session:
        reembolso = await session.get(EventPaymentRefund, refund_id)
        assert reembolso.status == "failed"
        assert reembolso.attempts == 5
    assert any("agotado sus reintentos" in mensaje for mensaje in caplog.messages)

    # Al haber agotado el tope, un nuevo barrido no debe volver a reencolarlo
    # ni a llamar otra vez a Stripe (`refunds_atascados` excluye `attempts >=
    # _INTENTOS_MAXIMOS`).
    fake.v1.refunds.create_async.reset_mock()
    await refunds_service.reencolar_reembolsos_atascados()
    fake.v1.refunds.create_async.assert_not_awaited()
    async with SessionMaintenance() as session:
        reembolso = await session.get(EventPaymentRefund, refund_id)
        assert reembolso.attempts == 5


# --- C3: dos reembolsos parciales solapados ----------------------------------


async def test_dos_reembolsos_parciales_solapados_no_superan_el_importe_pendiente(
    organizacion: OrganizacionDePrueba, fake: FakeStripeClient
) -> None:
    """Hallazgo IMP-2 (C3) del code review de la fase 6, ronda 3: un segundo
    reembolso parcial manual, pedido mientras el primero sigue `pending`/
    `submitted` (su `charge.refunded` todavía no ha llegado), no debe poder
    pedir más de lo que de verdad queda pendiente — `suma_reembolsos_en_curso`
    debe restar el primero, todavía en curso, del importe disponible."""
    stripe_account_id = await _crear_organizacion_con_stripe(organizacion)
    _, _, payment_id = await _crear_evento_pagado(organizacion, stripe_account_id=stripe_account_id)

    async with SessionApp() as session:
        async with session.begin():
            await set_organization_context(session, organizacion.id)
            # Primer reembolso parcial: importe 700 de un pago de 1000,
            # dejado `pending` (su webhook `charge.refunded` no ha llegado
            # todavía, así que `refunded_cents` sigue en 0).
            await refunds_service.solicitar_reembolso_manual(
                session,
                organization_id=organizacion.id,
                payment_id=payment_id,
                amount_cents=700,
                revoke_ticket=False,
            )

    # Sin el fix de C3, el importe pendiente se seguiría calculando como
    # `amount_cents - refunded_cents` (1000 - 0 = 1000), permitiendo pedir un
    # segundo reembolso de hasta 1000 sobre un pago que ya solo tiene 300
    # realmente disponibles.
    async with SessionApp() as session:
        async with session.begin():
            await set_organization_context(session, organizacion.id)
            with pytest.raises(ConflictError):
                await refunds_service.solicitar_reembolso_manual(
                    session,
                    organization_id=organizacion.id,
                    payment_id=payment_id,
                    amount_cents=400,
                    revoke_ticket=False,
                )

    # El importe justo que queda (300) sigue admitiéndose.
    async with SessionApp() as session:
        async with session.begin():
            await set_organization_context(session, organizacion.id)
            segundo = await refunds_service.solicitar_reembolso_manual(
                session,
                organization_id=organizacion.id,
                payment_id=payment_id,
                amount_cents=300,
                revoke_ticket=False,
            )
            assert segundo.amount_cents == 300


# --- Reembolso manual: importe, estado y aislamiento cross-tenant -----------


async def test_reembolsar_mas_del_pendiente_da_409_sin_llamar_a_stripe(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, fake: FakeStripeClient
) -> None:
    stripe_account_id = await _crear_organizacion_con_stripe(organizacion)
    event_id, _, payment_id = await _crear_evento_pagado(
        organizacion, stripe_account_id=stripe_account_id
    )
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    respuesta = await cliente.post(
        f"{EVENTS}/{event_id}/payments/{payment_id}/refund",
        headers=cabeceras,
        json={"amount_cents": 5000},
    )
    assert respuesta.status_code == 409, respuesta.text
    fake.v1.refunds.create_async.assert_not_awaited()


async def test_pago_no_reembolsable_da_409(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    stripe_account_id = await _crear_organizacion_con_stripe(organizacion)
    event_id, _, payment_id = await _crear_evento_pagado(
        organizacion, stripe_account_id=stripe_account_id
    )
    async with SessionMaintenance() as session:
        pago = await session.get(EventPayment, payment_id)
        pago.status = "refunded"
        pago.refunded_cents = pago.amount_cents
        await session.commit()

    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    respuesta = await cliente.post(
        f"{EVENTS}/{event_id}/payments/{payment_id}/refund", headers=cabeceras, json={}
    )
    assert respuesta.status_code == 409, respuesta.text


async def test_reembolso_total_revoca_ignorando_revoke_ticket(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, monkeypatch: pytest.MonkeyPatch
) -> None:
    stripe_account_id = await _crear_organizacion_con_stripe(organizacion)
    event_id, registration_id, payment_id = await _crear_evento_pagado(
        organizacion, stripe_account_id=stripe_account_id
    )
    monkeypatch.setattr("app.core.tasks.process_refunds_task.kiq", AsyncMock())
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    respuesta = await cliente.post(
        f"{EVENTS}/{event_id}/payments/{payment_id}/refund",
        headers=cabeceras,
        json={"revoke_ticket": False},
    )
    assert respuesta.status_code == 202, respuesta.text

    async with SessionMaintenance() as session:
        reembolso = await session.scalar(
            select(EventPaymentRefund).where(EventPaymentRefund.payment_id == payment_id)
        )
        assert reembolso.amount_cents == 1000
        assert reembolso.revoke_ticket is True
        assert reembolso.reason == "manual"


async def test_reembolso_parcial_no_revoca_salvo_casilla(
    organizacion: OrganizacionDePrueba,
) -> None:
    stripe_account_id = await _crear_organizacion_con_stripe(organizacion)
    _, _, payment_id = await _crear_evento_pagado(organizacion, stripe_account_id=stripe_account_id)

    async with SessionApp() as session:
        async with session.begin():
            await set_organization_context(session, organizacion.id)
            reembolso = await refunds_service.solicitar_reembolso_manual(
                session,
                organization_id=organizacion.id,
                payment_id=payment_id,
                amount_cents=400,
                revoke_ticket=False,
            )
            assert reembolso.revoke_ticket is False

    async with SessionApp() as session:
        async with session.begin():
            await set_organization_context(session, organizacion.id)
            reembolso = await refunds_service.solicitar_reembolso_manual(
                session,
                organization_id=organizacion.id,
                payment_id=payment_id,
                amount_cents=400,
                revoke_ticket=True,
            )
            assert reembolso.revoke_ticket is True


async def test_aislamiento_cross_tenant_del_reembolso(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    otra_organizacion: OrganizacionDePrueba,
) -> None:
    stripe_account_id_b = await _crear_organizacion_con_stripe(otra_organizacion)
    event_id_b, _, payment_id_b = await _crear_evento_pagado(
        otra_organizacion, stripe_account_id=stripe_account_id_b
    )

    _, cabeceras_a = await iniciar_sesion(cliente, organizacion)
    respuesta = await cliente.post(
        f"{EVENTS}/{event_id_b}/payments/{payment_id_b}/refund", headers=cabeceras_a, json={}
    )
    assert respuesta.status_code == 404


async def test_acct_id_del_reembolso_sale_de_la_fila_del_pago_no_de_la_cuenta_actual(
    organizacion: OrganizacionDePrueba, fake: FakeStripeClient
) -> None:
    """Hallazgo #17: un pago cobrado en una cuenta luego desconectada y
    sustituida por una nueva solo se reembolsa contra la cuenta original."""
    stripe_account_id_antigua = await _crear_organizacion_con_stripe(organizacion)
    event_id, registration_id, payment_id = await _crear_evento_pagado(
        organizacion, stripe_account_id=stripe_account_id_antigua
    )

    async with SessionMaintenance() as session:
        cuenta = await session.scalar(
            select(OrganizationStripeAccount).where(
                OrganizationStripeAccount.organization_id == organizacion.id
            )
        )
        cuenta.deauthorized_at = AHORA
        session.add(
            OrganizationStripeAccount(
                organization_id=organizacion.id,
                stripe_account_id=f"acct_{organizacion.slug}_nueva",
                charges_enabled=True,
            )
        )
        await session.commit()

    await _cancelar(organizacion.id, event_id, registration_id)
    fake.v1.refunds.create_async.return_value = _reembolso_creado()
    await refunds_service.procesar_reembolsos_pendientes()

    _, kwargs = fake.v1.refunds.create_async.call_args
    assert kwargs["options"]["stripe_account"] == stripe_account_id_antigua


# --- Webhook charge.refunded --------------------------------------------------


def _firmar(payload: bytes, timestamp: int) -> str:
    firma = stripe.WebhookSignature._compute_signature(
        f"{timestamp}.{payload.decode()}", SECRETO_WEBHOOK
    )
    return f"t={timestamp},v1={firma}"


def _cuerpo_charge_refunded(
    *, event_id: str, payment_intent: str, amount_refunded: int, account: str | None
) -> bytes:
    import json

    cuerpo = {
        "id": event_id,
        "type": "charge.refunded",
        "account": account,
        "data": {
            "object": {
                "id": "ch_1",
                "payment_intent": payment_intent,
                "amount_refunded": amount_refunded,
            }
        },
    }
    return json.dumps(cuerpo).encode()


async def test_webhook_charge_refunded_total_fija_importe_y_revoca(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(stripe_client, "get_settings", _settings_con_stripe)
    stripe_account_id = await _crear_organizacion_con_stripe(organizacion)
    event_id, registration_id, payment_id = await _crear_evento_pagado(
        organizacion, stripe_account_id=stripe_account_id, payment_intent_id="pi_total_1"
    )
    monkeypatch.setattr(
        "app.core.tasks.process_stripe_webhook_task.kiq",
        AsyncMock(side_effect=payments_webhooks.procesar_evento),
    )

    evt_id = f"evt_{uuid.uuid4().hex}"
    cuerpo = _cuerpo_charge_refunded(
        event_id=evt_id,
        payment_intent="pi_total_1",
        amount_refunded=1000,
        account=stripe_account_id,
    )
    firma = _firmar(cuerpo, int(time.time()))
    respuesta = await cliente.post(WEBHOOK_URL, content=cuerpo, headers={"stripe-signature": firma})
    assert respuesta.status_code == 200, respuesta.text

    async with SessionMaintenance() as session:
        pago = await session.get(EventPayment, payment_id)
        assert pago.refunded_cents == 1000
        assert pago.status == "refunded"
        ticket = await session.scalar(
            select(EventTicket).where(EventTicket.registration_id == registration_id)
        )
        assert ticket.revoked_at is not None


async def test_webhook_charge_refunded_reenviado_no_duplica_importe(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(stripe_client, "get_settings", _settings_con_stripe)
    stripe_account_id = await _crear_organizacion_con_stripe(organizacion)
    event_id, _, payment_id = await _crear_evento_pagado(
        organizacion, stripe_account_id=stripe_account_id, payment_intent_id="pi_dup_1"
    )
    monkeypatch.setattr(
        "app.core.tasks.process_stripe_webhook_task.kiq",
        AsyncMock(side_effect=payments_webhooks.procesar_evento),
    )

    evt_id = f"evt_{uuid.uuid4().hex}"
    cuerpo = _cuerpo_charge_refunded(
        event_id=evt_id, payment_intent="pi_dup_1", amount_refunded=400, account=stripe_account_id
    )
    firma = _firmar(cuerpo, int(time.time()))

    primera = await cliente.post(WEBHOOK_URL, content=cuerpo, headers={"stripe-signature": firma})
    assert primera.status_code == 200
    segunda = await cliente.post(WEBHOOK_URL, content=cuerpo, headers={"stripe-signature": firma})
    assert segunda.status_code == 200

    async with SessionMaintenance() as session:
        pago = await session.get(EventPayment, payment_id)
        assert pago.refunded_cents == 400
        assert pago.status == "partially_refunded"


async def test_webhook_charge_refunded_organizacion_no_coincide_falla_sin_mutar(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    otra_organizacion: OrganizacionDePrueba,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(stripe_client, "get_settings", _settings_con_stripe)
    stripe_account_id_pago = await _crear_organizacion_con_stripe(organizacion)
    stripe_account_id_otra = f"acct_{otra_organizacion.slug}"
    async with SessionMaintenance() as session:
        session.add(
            OrganizationStripeAccount(
                organization_id=otra_organizacion.id, stripe_account_id=stripe_account_id_otra
            )
        )
        await session.commit()
    _, _, payment_id = await _crear_evento_pagado(
        organizacion, stripe_account_id=stripe_account_id_pago, payment_intent_id="pi_cruzado_1"
    )
    monkeypatch.setattr(
        "app.core.tasks.process_stripe_webhook_task.kiq",
        AsyncMock(side_effect=payments_webhooks.procesar_evento),
    )

    evt_id = f"evt_{uuid.uuid4().hex}"
    cuerpo = _cuerpo_charge_refunded(
        event_id=evt_id,
        payment_intent="pi_cruzado_1",
        amount_refunded=1000,
        account=stripe_account_id_otra,
    )
    firma = _firmar(cuerpo, int(time.time()))
    respuesta = await cliente.post(WEBHOOK_URL, content=cuerpo, headers={"stripe-signature": firma})
    assert respuesta.status_code == 200

    async with SessionMaintenance() as session:
        pago = await session.get(EventPayment, payment_id)
        assert pago.refunded_cents == 0
        assert pago.status == "paid"
        fila = await payments_repository.get_webhook_event(session, evt_id)
        assert fila.status == "failed"


async def test_dos_parciales_sucesivos_suman_total_y_revocan(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(stripe_client, "get_settings", _settings_con_stripe)
    stripe_account_id = await _crear_organizacion_con_stripe(organizacion)
    event_id, registration_id, payment_id = await _crear_evento_pagado(
        organizacion, stripe_account_id=stripe_account_id, payment_intent_id="pi_parciales_1"
    )
    monkeypatch.setattr(
        "app.core.tasks.process_stripe_webhook_task.kiq",
        AsyncMock(side_effect=payments_webhooks.procesar_evento),
    )

    primer_evento = f"evt_{uuid.uuid4().hex}"
    primer_cuerpo = _cuerpo_charge_refunded(
        event_id=primer_evento,
        payment_intent="pi_parciales_1",
        amount_refunded=400,
        account=stripe_account_id,
    )
    await cliente.post(
        WEBHOOK_URL,
        content=primer_cuerpo,
        headers={"stripe-signature": _firmar(primer_cuerpo, int(time.time()))},
    )
    async with SessionMaintenance() as session:
        pago = await session.get(EventPayment, payment_id)
        assert pago.status == "partially_refunded"
        ticket = await session.scalar(
            select(EventTicket).where(EventTicket.registration_id == registration_id)
        )
        assert ticket.revoked_at is None

    segundo_evento = f"evt_{uuid.uuid4().hex}"
    segundo_cuerpo = _cuerpo_charge_refunded(
        event_id=segundo_evento,
        payment_intent="pi_parciales_1",
        amount_refunded=1000,
        account=stripe_account_id,
    )
    await cliente.post(
        WEBHOOK_URL,
        content=segundo_cuerpo,
        headers={"stripe-signature": _firmar(segundo_cuerpo, int(time.time()))},
    )
    async with SessionMaintenance() as session:
        pago = await session.get(EventPayment, payment_id)
        assert pago.status == "refunded"
        assert pago.refunded_cents == 1000
        ticket = await session.scalar(
            select(EventTicket).where(EventTicket.registration_id == registration_id)
        )
        assert ticket.revoked_at is not None


async def test_reembolso_con_revocacion_manual_parcial_revoca_desde_el_webhook(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un reembolso parcial con la casilla marcada revoca aunque el pago siga
    `partially_refunded` (Decisión #15)."""
    monkeypatch.setattr(stripe_client, "get_settings", _settings_con_stripe)
    stripe_account_id = await _crear_organizacion_con_stripe(organizacion)
    event_id, registration_id, payment_id = await _crear_evento_pagado(
        organizacion, stripe_account_id=stripe_account_id, payment_intent_id="pi_marcada_1"
    )

    async with SessionApp() as session:
        async with session.begin():
            await set_organization_context(session, organizacion.id)
            await refunds_service.solicitar_reembolso_manual(
                session,
                organization_id=organizacion.id,
                payment_id=payment_id,
                amount_cents=300,
                revoke_ticket=True,
            )

    async with SessionMaintenance() as session:
        reembolso = await session.scalar(
            select(EventPaymentRefund).where(EventPaymentRefund.payment_id == payment_id)
        )
        reembolso.status = "succeeded"
        reembolso.stripe_refund_id = "re_marcada"
        await session.commit()

    monkeypatch.setattr(
        "app.core.tasks.process_stripe_webhook_task.kiq",
        AsyncMock(side_effect=payments_webhooks.procesar_evento),
    )
    evt_id = f"evt_{uuid.uuid4().hex}"
    cuerpo = _cuerpo_charge_refunded(
        event_id=evt_id,
        payment_intent="pi_marcada_1",
        amount_refunded=300,
        account=stripe_account_id,
    )
    await cliente.post(
        WEBHOOK_URL, content=cuerpo, headers={"stripe-signature": _firmar(cuerpo, int(time.time()))}
    )

    async with SessionMaintenance() as session:
        pago = await session.get(EventPayment, payment_id)
        assert pago.status == "partially_refunded"
        ticket = await session.scalar(
            select(EventTicket).where(EventTicket.registration_id == registration_id)
        )
        assert ticket.revoked_at is not None


# --- No se ha ampliado `event_tickets` ---------------------------------------


def test_no_se_ha_anadido_ninguna_columna_a_event_tickets() -> None:
    from app.modules.tickets.models import EventTicket as _EventTicket

    columnas = {columna.name for columna in _EventTicket.__table__.columns}
    assert columnas == {
        "id",
        "organization_id",
        "event_id",
        "registration_id",
        "issued_at",
        "used_at",
        "used_by_event_member_id",
        "revoked_at",
        "created_at",
        "updated_at",
    }
