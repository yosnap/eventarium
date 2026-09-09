"""Constraints de base de datos del esquema de pagos (fase 6 del PRD, fase 1
de trabajo): índice único parcial de la cuenta Stripe activa, `CHECK` de
`event_ticket_types`/`event_discount_codes`, y ausencia de `used_count`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.database import SessionMaintenance
from app.modules.events.models import Event
from app.modules.payments.models import (
    EventDiscountCode,
    EventTicketType,
    OrganizationStripeAccount,
)
from tests.conftest import OrganizacionDePrueba

AHORA = datetime.now(UTC)


async def _crear_evento(organizacion: OrganizacionDePrueba) -> Event:
    async with SessionMaintenance() as session:
        evento = Event(
            organization_id=organizacion.id,
            slug=f"evento-constraints-{organizacion.slug}",
            title="Evento de prueba",
            status="draft",
            visibility="public",
            starts_at=AHORA,
            ends_at=AHORA + timedelta(days=1),
            location_mode="online",
            registration_mode="paid",
        )
        session.add(evento)
        await session.commit()
        await session.refresh(evento)
    return evento


async def test_dos_cuentas_stripe_activas_para_la_misma_organizacion_se_rechazan(
    organizacion: OrganizacionDePrueba,
) -> None:
    async with SessionMaintenance() as session:
        session.add(
            OrganizationStripeAccount(
                organization_id=organizacion.id, stripe_account_id="acct_primera"
            )
        )
        await session.commit()

    with pytest.raises(IntegrityError):
        async with SessionMaintenance() as session:
            session.add(
                OrganizationStripeAccount(
                    organization_id=organizacion.id, stripe_account_id="acct_segunda"
                )
            )
            await session.commit()


async def test_una_organizacion_puede_reconectar_tras_desconectar_su_cuenta(
    organizacion: OrganizacionDePrueba,
) -> None:
    """Una fila `deauthorized_at` informada no cuenta para el índice único
    parcial: la organización puede tener una **segunda** fila activa."""
    async with SessionMaintenance() as session:
        session.add(
            OrganizationStripeAccount(
                organization_id=organizacion.id,
                stripe_account_id="acct_desconectada",
                deauthorized_at=AHORA,
            )
        )
        await session.commit()

    async with SessionMaintenance() as session:
        session.add(
            OrganizationStripeAccount(
                organization_id=organizacion.id, stripe_account_id="acct_reconectada"
            )
        )
        await session.commit()

    async with SessionMaintenance() as session:
        total = await session.scalar(
            text("SELECT count(*) FROM organization_stripe_accounts WHERE organization_id = :id"),
            {"id": organizacion.id},
        )
    assert total == 2


async def test_price_cents_negativo_se_rechaza_por_check(
    organizacion: OrganizacionDePrueba,
) -> None:
    evento = await _crear_evento(organizacion)
    with pytest.raises(IntegrityError):
        async with SessionMaintenance() as session:
            session.add(
                EventTicketType(
                    event_id=evento.id,
                    organization_id=organizacion.id,
                    name="Tipo inválido",
                    price_cents=-100,
                    currency="eur",
                )
            )
            await session.commit()


async def test_discount_value_150_en_porcentaje_se_rechaza_por_check(
    organizacion: OrganizacionDePrueba,
) -> None:
    evento = await _crear_evento(organizacion)
    with pytest.raises(IntegrityError):
        async with SessionMaintenance() as session:
            session.add(
                EventDiscountCode(
                    event_id=evento.id,
                    organization_id=organizacion.id,
                    code="INVALIDO150",
                    discount_type="percentage",
                    discount_value=150,
                )
            )
            await session.commit()


async def test_discount_value_cero_en_importe_fijo_se_rechaza_por_check(
    organizacion: OrganizacionDePrueba,
) -> None:
    evento = await _crear_evento(organizacion)
    with pytest.raises(IntegrityError):
        async with SessionMaintenance() as session:
            session.add(
                EventDiscountCode(
                    event_id=evento.id,
                    organization_id=organizacion.id,
                    code="INVALIDOFIJO",
                    discount_type="fixed_amount",
                    discount_value=0,
                )
            )
            await session.commit()


async def test_no_existe_la_columna_used_count_en_event_discount_codes() -> None:
    async with SessionMaintenance() as session:
        columnas = (
            await session.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'event_discount_codes'"
                )
            )
        ).scalars()
    assert "used_count" not in set(columnas)
