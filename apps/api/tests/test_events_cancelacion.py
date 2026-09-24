"""Cancelación de un evento por la organización (`events/cancelacion.py`).

Mismo patrón que `test_registrations_emails_and_cancellation.py`: cliente HTTP
real y las tareas mockeadas con `AsyncMock`. El barrido se ejecuta a mano
(`barrer_cancelacion`) porque en los tests la cola no corre.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.database import SessionMaintenance
from app.core.tasks import (
    process_refunds_task,
    send_event_cancelled_email,
    send_registration_cancelled_email,
    send_waitlist_promotion_email,
    sweep_event_cancellation_task,
)
from app.modules.events.cancelacion import barrer_cancelacion
from app.modules.payments import checkout_service
from app.modules.payments.models import EventPayment, EventPaymentRefund, EventTicketType
from app.modules.registrations import repository as registrations_repository
from app.modules.registrations.models import EventRegistration
from tests.conftest import OrganizacionDePrueba, iniciar_sesion

EVENTS = "/api/v1/events"
AHORA = datetime.now(UTC).replace(microsecond=0)


@pytest.fixture(autouse=True)
def tareas():
    parches = {
        nombre: patch.object(tarea, "kiq", new_callable=AsyncMock)
        for nombre, tarea in {
            "aviso": send_event_cancelled_email,
            "cancelacion_individual": send_registration_cancelled_email,
            "promocion": send_waitlist_promotion_email,
            "barrido": sweep_event_cancellation_task,
            "reembolsos": process_refunds_task,
        }.items()
    }
    mocks = {nombre: parche.start() for nombre, parche in parches.items()}
    yield mocks
    for parche in parches.values():
        parche.stop()


async def _evento_publicado(
    cliente: AsyncClient, cabeceras: dict[str, str], slug: str, **extra: object
) -> dict:
    payload = {
        "slug": slug,
        "title": f"Evento {slug}",
        # Empieza en 12 h: dentro del plazo en el que la política de
        # autocancelación ya no reembolsaría.
        "starts_at": (AHORA + timedelta(hours=12)).isoformat(),
        "ends_at": (AHORA + timedelta(days=2)).isoformat(),
        "location_mode": "in_person",
        "capacity": 1,
        **extra,
    }
    creado = await cliente.post(EVENTS, headers=cabeceras, json=payload)
    assert creado.status_code == 201, creado.text
    publicado = await cliente.patch(
        f"{EVENTS}/{creado.json()['id']}",
        headers=cabeceras,
        json={"status": "published", "visibility": "public"},
    )
    assert publicado.status_code == 200, publicado.text
    return publicado.json()


async def _inscripcion(
    organizacion: OrganizacionDePrueba, evento: dict, email: str, status: str
) -> uuid.UUID:
    async with SessionMaintenance() as session:
        fila = EventRegistration(
            event_id=uuid.UUID(evento["id"]),
            organization_id=organizacion.id,
            email=email,
            full_name="Asistente",
            status=status,
            confirmed_at=AHORA if status == "confirmed" else None,
        )
        session.add(fila)
        await session.commit()
        return fila.id


async def _pago_cobrado(
    organizacion: OrganizacionDePrueba, evento: dict, registration_id: uuid.UUID, *, status: str
) -> uuid.UUID:
    async with SessionMaintenance() as session:
        tipo = EventTicketType(
            organization_id=organizacion.id,
            event_id=uuid.UUID(evento["id"]),
            name=f"General {uuid.uuid4().hex[:6]}",
            price_cents=2500,
            currency="eur",
        )
        session.add(tipo)
        await session.flush()
        pago = EventPayment(
            organization_id=organizacion.id,
            event_id=uuid.UUID(evento["id"]),
            registration_id=registration_id,
            stripe_account_id="acct_test",
            ticket_type_id=tipo.id,
            amount_cents=2500,
            currency="eur",
            status=status,
            paid_at=AHORA if status == "paid" else None,
        )
        session.add(pago)
        await session.commit()
        return pago.id


async def _resumen(cliente: AsyncClient, cabeceras: dict[str, str], evento: dict) -> dict:
    respuesta = await cliente.get(f"{EVENTS}/{evento['id']}/cancel/preview", headers=cabeceras)
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


async def _cancelar(
    cliente: AsyncClient, cabeceras: dict[str, str], evento: dict, resumen: dict
) -> None:
    respuesta = await cliente.post(
        f"{EVENTS}/{evento['id']}/cancel",
        headers=cabeceras,
        json={
            "motivo": "Previsión de temporal",
            "inscripciones_afectadas": resumen["inscripciones_afectadas"],
            "importe_a_reembolsar_cents": resumen["importe_a_reembolsar_cents"],
        },
    )
    assert respuesta.status_code == 200, respuesta.text


async def _inscripciones(evento: dict) -> list[EventRegistration]:
    async with SessionMaintenance() as session:
        return list(
            await session.scalars(
                select(EventRegistration).where(
                    EventRegistration.event_id == uuid.UUID(evento["id"])
                )
            )
        )


class TestEstado:
    async def test_no_se_puede_cancelar_con_un_patch(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _evento_publicado(cliente, cabeceras, "cancelar-por-patch")

        respuesta = await cliente.patch(
            f"{EVENTS}/{evento['id']}", headers=cabeceras, json={"status": "cancelled"}
        )

        assert respuesta.status_code == 422

    async def test_un_evento_cancelado_ya_no_se_edita_ni_se_vuelve_a_cancelar(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _evento_publicado(cliente, cabeceras, "cancelado-terminal")
        await _cancelar(cliente, cabeceras, evento, await _resumen(cliente, cabeceras, evento))

        edicion = await cliente.patch(
            f"{EVENTS}/{evento['id']}", headers=cabeceras, json={"status": "published"}
        )
        segundo = await cliente.get(f"{EVENTS}/{evento['id']}/cancel/preview", headers=cabeceras)

        assert edicion.status_code == 422
        assert segundo.status_code == 409

    async def test_si_las_cifras_cambiaron_desde_el_resumen_no_cancela(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _evento_publicado(cliente, cabeceras, "cifras-cambiadas")
        resumen = await _resumen(cliente, cabeceras, evento)
        await _inscripcion(organizacion, evento, "nueva@example.com", "confirmed")

        respuesta = await cliente.post(
            f"{EVENTS}/{evento['id']}/cancel",
            headers=cabeceras,
            json={
                "inscripciones_afectadas": resumen["inscripciones_afectadas"],
                "importe_a_reembolsar_cents": resumen["importe_a_reembolsar_cents"],
            },
        )

        assert respuesta.status_code == 409


class TestBarrido:
    async def test_cancela_todo_sin_promocionar_y_avisa_una_sola_vez(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba, tareas
    ) -> None:
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _evento_publicado(cliente, cabeceras, "cancelar-con-inscritos")
        await _inscripcion(organizacion, evento, "confirmada@example.com", "confirmed")
        await _inscripcion(organizacion, evento, "espera@example.com", "waitlisted")
        await _inscripcion(organizacion, evento, "aprobar@example.com", "pending_approval")
        await _inscripcion(organizacion, evento, "ya-cancelada@example.com", "cancelled")

        resumen = await _resumen(cliente, cabeceras, evento)
        assert resumen["inscripciones_afectadas"] == 3
        await _cancelar(cliente, cabeceras, evento, resumen)
        tareas["barrido"].assert_awaited_once()

        await barrer_cancelacion(organizacion.id, uuid.UUID(evento["id"]))
        await barrer_cancelacion(organizacion.id, uuid.UUID(evento["id"]))

        filas = {fila.email: fila for fila in await _inscripciones(evento)}
        for email in ("confirmada@example.com", "espera@example.com", "aprobar@example.com"):
            assert filas[email].status == "cancelled"
            assert filas[email].cancelled_with_event is True
            assert filas[email].event_cancellation_notified_at is not None
        assert filas["ya-cancelada@example.com"].cancelled_with_event is False
        assert tareas["aviso"].await_count == 3
        tareas["promocion"].assert_not_awaited()
        tareas["cancelacion_individual"].assert_not_awaited()

    async def test_reembolsa_integro_aunque_falten_menos_de_24_horas(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba, tareas
    ) -> None:
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _evento_publicado(cliente, cabeceras, "cancelar-de-pago")
        inscripcion = await _inscripcion(organizacion, evento, "pago@example.com", "confirmed")
        pago = await _pago_cobrado(organizacion, evento, inscripcion, status="paid")

        resumen = await _resumen(cliente, cabeceras, evento)
        assert resumen["pagos_a_reembolsar"] == 1
        assert resumen["importe_a_reembolsar_cents"] == 2500
        assert resumen["requiere_permiso_de_pagos"] is True
        await _cancelar(cliente, cabeceras, evento, resumen)
        await barrer_cancelacion(organizacion.id, uuid.UUID(evento["id"]))
        await barrer_cancelacion(organizacion.id, uuid.UUID(evento["id"]))

        async with SessionMaintenance() as session:
            reembolsos = list(
                await session.scalars(
                    select(EventPaymentRefund).where(EventPaymentRefund.payment_id == pago)
                )
            )
        assert [(r.reason, r.amount_cents) for r in reembolsos] == [("event_cancelled", 2500)]
        assert tareas["aviso"].await_args.args[4] is True

    async def test_un_pago_que_llega_tras_cancelar_se_reembolsa(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _evento_publicado(cliente, cabeceras, "pago-tardio")
        inscripcion = await _inscripcion(
            organizacion, evento, "tarde@example.com", "pending_payment"
        )
        pago_id = await _pago_cobrado(organizacion, evento, inscripcion, status="pending")
        await _cancelar(cliente, cabeceras, evento, await _resumen(cliente, cabeceras, evento))
        await barrer_cancelacion(organizacion.id, uuid.UUID(evento["id"]))

        async with SessionMaintenance() as session:
            pago = await session.get(EventPayment, pago_id)
            fila = await session.get(EventRegistration, inscripcion)
            assert pago.status == "expired"
            resultado = await checkout_service.confirmar_pago_y_registro(
                session, pago, fila, stripe_payment_intent_id="pi_tardio"
            )
            await session.commit()
            reembolsos = list(
                await session.scalars(
                    select(EventPaymentRefund).where(EventPaymentRefund.payment_id == pago_id)
                )
            )

        assert resultado == "processed"
        assert fila.status == "cancelled"
        assert [(r.reason, r.amount_cents) for r in reembolsos] == [("event_cancelled", 2500)]


class TestWebPublica:
    async def test_la_ficha_sigue_visible_pero_la_inscripcion_no(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _evento_publicado(cliente, cabeceras, "ficha-cancelada")
        await _cancelar(cliente, cabeceras, evento, await _resumen(cliente, cabeceras, evento))

        ficha = await cliente.get("/api/v1/public/events/ficha-cancelada")
        preguntas = await cliente.get(
            "/api/v1/public/events/ficha-cancelada/registration-questions"
        )
        listado = await cliente.get("/api/v1/public/events")

        assert ficha.status_code == 200
        assert ficha.json()["cancelled"] is True
        assert ficha.json()["cancellation_reason"] == "Previsión de temporal"
        assert preguntas.status_code == 404
        assert "ficha-cancelada" not in {e["slug"] for e in listado.json()}

    async def test_mis_eventos_distingue_el_evento_cancelado(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _evento_publicado(cliente, cabeceras, "mis-eventos-cancelado")
        await _inscripcion(organizacion, evento, "mia@example.com", "confirmed")
        await _cancelar(cliente, cabeceras, evento, await _resumen(cliente, cabeceras, evento))

        async with SessionMaintenance() as session:
            filas = await registrations_repository.list_registrations_by_email(
                session, "mia@example.com"
            )

        assert [(f.event_slug, f.event_status) for f in filas] == [
            ("mis-eventos-cancelado", "cancelled")
        ]

    async def test_un_pago_antes_del_barrido_no_confirma_ni_emite_entrada(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _evento_publicado(cliente, cabeceras, "pago-antes-del-barrido")
        inscripcion = await _inscripcion(
            organizacion, evento, "rapida@example.com", "pending_payment"
        )
        pago_id = await _pago_cobrado(organizacion, evento, inscripcion, status="pending")
        # Cancelado, pero el barrido todavía no ha pasado por esta inscripción.
        await _cancelar(cliente, cabeceras, evento, await _resumen(cliente, cabeceras, evento))

        async with SessionMaintenance() as session:
            pago = await session.get(EventPayment, pago_id)
            fila = await session.get(EventRegistration, inscripcion)
            resultado = await checkout_service.confirmar_pago_y_registro(
                session, pago, fila, stripe_payment_intent_id="pi_rapido"
            )
            await session.commit()
            reembolsos = list(
                await session.scalars(
                    select(EventPaymentRefund).where(EventPaymentRefund.payment_id == pago_id)
                )
            )

        assert resultado == "processed"
        assert fila.status == "cancelled"
        assert fila.cancelled_with_event is True
        assert fila.confirmed_at is None
        assert [(r.reason, r.amount_cents) for r in reembolsos] == [("event_cancelled", 2500)]
