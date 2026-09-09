"""Aislamiento entre organizaciones para las cinco tablas de dominio de pagos.

Mismo patrón que `test_sponsors_rls_isolation.py` (fase 5): una comprobación
de lectura (RLS) y otra de escritura cruzada (las FK compuestas contra `(id,
organization_id)` del padre, o la propia política RLS cuando no hay FK que
cruzar) para cada una de las cinco tablas de dominio de la fase 6.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.database import SessionApp, SessionMaintenance, set_organization_context
from app.modules.events.models import Event
from app.modules.organizations.repository import unsafe_select_all
from app.modules.payments.models import (
    EventDiscountCode,
    EventPayment,
    EventPaymentRefund,
    EventTicketType,
    OrganizationStripeAccount,
)
from tests.conftest import OrganizacionDePrueba

AHORA = datetime.now(UTC)

TABLAS_CON_ORGANIZACION = (
    OrganizationStripeAccount,
    EventTicketType,
    EventDiscountCode,
    EventPayment,
    EventPaymentRefund,
)


class DatosDePrueba:
    __slots__ = (
        "event_id",
        "stripe_account_id",
        "ticket_type_id",
        "discount_code_id",
        "payment_id",
        "refund_id",
    )

    def __init__(
        self,
        *,
        event_id: uuid.UUID,
        stripe_account_id: uuid.UUID,
        ticket_type_id: uuid.UUID,
        discount_code_id: uuid.UUID,
        payment_id: uuid.UUID,
        refund_id: uuid.UUID,
    ) -> None:
        self.event_id = event_id
        self.stripe_account_id = stripe_account_id
        self.ticket_type_id = ticket_type_id
        self.discount_code_id = discount_code_id
        self.payment_id = payment_id
        self.refund_id = refund_id


async def _crear_datos_de_prueba(organizacion: OrganizacionDePrueba) -> DatosDePrueba:
    async with SessionMaintenance() as session:
        evento = Event(
            organization_id=organizacion.id,
            slug=f"evento-pagos-{organizacion.slug}",
            title="Evento de pago de prueba",
            status="published",
            visibility="public",
            starts_at=AHORA,
            ends_at=AHORA + timedelta(days=1),
            location_mode="online",
            registration_mode="paid",
        )
        session.add(evento)
        await session.flush()

        cuenta = OrganizationStripeAccount(
            organization_id=organizacion.id,
            stripe_account_id=f"acct_{organizacion.slug}",
        )
        session.add(cuenta)
        await session.flush()

        tipo = EventTicketType(
            event_id=evento.id,
            organization_id=organizacion.id,
            name="General",
            price_cents=1000,
            currency="eur",
        )
        session.add(tipo)
        await session.flush()

        codigo = EventDiscountCode(
            event_id=evento.id,
            organization_id=organizacion.id,
            code=f"DESC-{organizacion.slug.upper()}",
            discount_type="percentage",
            discount_value=10,
        )
        session.add(codigo)
        await session.flush()

        pago = EventPayment(
            organization_id=organizacion.id,
            event_id=evento.id,
            stripe_account_id=cuenta.stripe_account_id,
            ticket_type_id=tipo.id,
            amount_cents=1000,
            currency="eur",
        )
        session.add(pago)
        await session.flush()

        reembolso = EventPaymentRefund(
            organization_id=organizacion.id,
            payment_id=pago.id,
            amount_cents=1000,
            reason="manual",
            revoke_ticket=False,
        )
        session.add(reembolso)
        await session.flush()

        await session.commit()
        return DatosDePrueba(
            event_id=evento.id,
            stripe_account_id=cuenta.id,
            ticket_type_id=tipo.id,
            discount_code_id=codigo.id,
            payment_id=pago.id,
            refund_id=reembolso.id,
        )


@pytest.mark.parametrize("modelo", TABLAS_CON_ORGANIZACION)
async def test_una_sesion_solo_ve_las_filas_de_su_organizacion(
    organizacion: OrganizacionDePrueba,
    otra_organizacion: OrganizacionDePrueba,
    modelo: type,
) -> None:
    await _crear_datos_de_prueba(organizacion)
    await _crear_datos_de_prueba(otra_organizacion)

    async with SessionApp() as session:
        async with session.begin():
            await set_organization_context(session, organizacion.id)
            filas = await unsafe_select_all(session, modelo)

    assert filas, f"debería ver sus propias filas de {modelo.__tablename__}"
    ajenas = [f for f in filas if f.organization_id != organizacion.id]
    assert not ajenas, f"{modelo.__tablename__} filtró filas de otra organización"


async def test_no_se_puede_crear_una_cuenta_stripe_con_organization_id_ajeno(
    organizacion: OrganizacionDePrueba, otra_organizacion: OrganizacionDePrueba
) -> None:
    with pytest.raises(DBAPIError):
        async with SessionApp() as session:
            async with session.begin():
                await set_organization_context(session, organizacion.id)
                session.add(
                    OrganizationStripeAccount(
                        organization_id=otra_organizacion.id,
                        stripe_account_id="acct_intruso",
                    )
                )
                await session.flush()

    async with SessionMaintenance() as session:
        encontrado = await session.scalar(
            text(
                "SELECT count(*) FROM organization_stripe_accounts "
                "WHERE stripe_account_id = 'acct_intruso'"
            )
        )
    assert encontrado == 0


async def test_no_se_puede_crear_un_tipo_de_entrada_sobre_un_evento_ajeno(
    organizacion: OrganizacionDePrueba, otra_organizacion: OrganizacionDePrueba
) -> None:
    datos_ajenos = await _crear_datos_de_prueba(otra_organizacion)

    with pytest.raises(DBAPIError):
        async with SessionApp() as session:
            async with session.begin():
                await set_organization_context(session, organizacion.id)
                session.add(
                    EventTicketType(
                        event_id=datos_ajenos.event_id,
                        organization_id=organizacion.id,
                        name="Tipo intruso",
                        price_cents=500,
                        currency="eur",
                    )
                )
                await session.flush()

    async with SessionMaintenance() as session:
        encontrado = await session.scalar(
            text("SELECT count(*) FROM event_ticket_types WHERE name = 'Tipo intruso'")
        )
    assert encontrado == 0


async def test_no_se_puede_crear_un_codigo_de_descuento_con_tipo_de_entrada_ajeno(
    organizacion: OrganizacionDePrueba, otra_organizacion: OrganizacionDePrueba
) -> None:
    datos_propios = await _crear_datos_de_prueba(organizacion)
    datos_ajenos = await _crear_datos_de_prueba(otra_organizacion)

    with pytest.raises(DBAPIError):
        async with SessionApp() as session:
            async with session.begin():
                await set_organization_context(session, organizacion.id)
                session.add(
                    EventDiscountCode(
                        event_id=datos_propios.event_id,
                        organization_id=organizacion.id,
                        code="INTRUSO",
                        discount_type="percentage",
                        discount_value=10,
                        ticket_type_id=datos_ajenos.ticket_type_id,
                    )
                )
                await session.flush()

    async with SessionMaintenance() as session:
        encontrado = await session.scalar(
            text("SELECT count(*) FROM event_discount_codes WHERE code = 'INTRUSO'")
        )
    assert encontrado == 0


async def test_no_se_puede_crear_un_pago_sobre_un_evento_ajeno(
    organizacion: OrganizacionDePrueba, otra_organizacion: OrganizacionDePrueba
) -> None:
    datos_propios = await _crear_datos_de_prueba(organizacion)
    datos_ajenos = await _crear_datos_de_prueba(otra_organizacion)

    with pytest.raises(DBAPIError):
        async with SessionApp() as session:
            async with session.begin():
                await set_organization_context(session, organizacion.id)
                session.add(
                    EventPayment(
                        organization_id=organizacion.id,
                        event_id=datos_ajenos.event_id,
                        stripe_account_id="acct_intruso",
                        ticket_type_id=datos_propios.ticket_type_id,
                        amount_cents=1000,
                        currency="eur",
                    )
                )
                await session.flush()

    async with SessionMaintenance() as session:
        encontrado = await session.scalar(
            text(
                "SELECT count(*) FROM event_payments WHERE stripe_account_id = 'acct_intruso'"
            )
        )
    assert encontrado == 0


async def test_no_se_puede_crear_un_reembolso_sobre_un_pago_ajeno(
    organizacion: OrganizacionDePrueba, otra_organizacion: OrganizacionDePrueba
) -> None:
    datos_ajenos = await _crear_datos_de_prueba(otra_organizacion)

    with pytest.raises(DBAPIError):
        async with SessionApp() as session:
            async with session.begin():
                await set_organization_context(session, organizacion.id)
                session.add(
                    EventPaymentRefund(
                        organization_id=organizacion.id,
                        payment_id=datos_ajenos.payment_id,
                        amount_cents=500,
                        reason="manual",
                        revoke_ticket=False,
                    )
                )
                await session.flush()

    async with SessionMaintenance() as session:
        encontrado = await session.scalar(
            text("SELECT count(*) FROM event_payment_refunds WHERE amount_cents = 500")
        )
    assert encontrado == 0
