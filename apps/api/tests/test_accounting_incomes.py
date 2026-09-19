"""Vista compuesta de ingresos y CRUD de `accounting_incomes`/
`sponsor_payment_details` (fase 2 de trabajo).

Cubre los criterios de éxito de `phase-02-ingresos-y-datos-de-patrocinio.md`:
predicado real de "cobrado" para patrocinios, `origin` fijo a `subvencion`,
ingreso neto de entradas descontando reembolsos confirmados y en curso, e
ingresos en moneda distinta excluidos con aviso.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi import BackgroundTasks

from app.core.database import SessionApp, SessionMaintenance, set_organization_context
from app.modules.accounting import repository as accounting_repository
from app.modules.accounting import service as accounting_service
from app.modules.accounting.models import AccountingIncome, SponsorPaymentDetail
from app.modules.events.models import Event
from app.modules.payments.models import EventPayment, EventPaymentRefund, EventTicketType
from app.modules.sponsors.models import Sponsor, SponsorTier
from app.shared.errors import ValidationDomainError
from tests.conftest import OrganizacionDePrueba

AHORA = datetime.now(UTC).replace(microsecond=0)


async def _crear_evento(
    organizacion: OrganizacionDePrueba, *, accounting_currency: str = "eur"
) -> uuid.UUID:
    async with SessionMaintenance() as session:
        evento = Event(
            organization_id=organizacion.id,
            slug=f"evento-ingresos-{uuid.uuid4().hex[:8]}",
            title="Evento de ingresos",
            status="published",
            visibility="public",
            starts_at=AHORA,
            ends_at=AHORA + timedelta(days=1),
            location_mode="online",
            accounting_currency=accounting_currency,
        )
        session.add(evento)
        await session.commit()
        return evento.id


async def _crear_sponsor(
    organizacion: OrganizacionDePrueba,
    event_id: uuid.UUID,
    *,
    contribution_type: str,
    contribution_amount: Decimal | None = None,
    contribution_description: str | None = None,
    in_kind_valuation_cents: int | None = None,
) -> uuid.UUID:
    async with SessionMaintenance() as session:
        nivel = SponsorTier(
            organization_id=organizacion.id, name=f"Nivel {uuid.uuid4().hex[:6]}", display_order=1
        )
        session.add(nivel)
        await session.flush()
        patrocinador = Sponsor(
            event_id=event_id,
            tier_id=nivel.id,
            organization_id=organizacion.id,
            name=f"Patrocinador {uuid.uuid4().hex[:6]}",
            contribution_type=contribution_type,
            contribution_amount=contribution_amount,
            contribution_description=contribution_description,
            in_kind_valuation_cents=in_kind_valuation_cents,
        )
        session.add(patrocinador)
        await session.commit()
        return patrocinador.id


async def _crear_pago(
    organizacion: OrganizacionDePrueba,
    event_id: uuid.UUID,
    *,
    amount_cents: int,
    refunded_cents: int = 0,
    currency: str = "eur",
    status: str = "paid",
) -> uuid.UUID:
    async with SessionMaintenance() as session:
        tipo = EventTicketType(
            organization_id=organizacion.id,
            event_id=event_id,
            name="General",
            price_cents=amount_cents,
        )
        session.add(tipo)
        await session.flush()
        pago = EventPayment(
            organization_id=organizacion.id,
            event_id=event_id,
            stripe_account_id="acct_test",
            ticket_type_id=tipo.id,
            stripe_payment_intent_id=f"pi_{uuid.uuid4().hex[:10]}",
            amount_cents=amount_cents,
            refunded_cents=refunded_cents,
            currency=currency,
            status=status,
            paid_at=AHORA,
        )
        session.add(pago)
        await session.commit()
        return pago.id


async def _listar(
    organizacion: OrganizacionDePrueba, event_id: uuid.UUID, moneda: str = "eur"
) -> accounting_repository.VistaDeIngresos:
    async with SessionApp() as session:
        async with session.begin():
            await set_organization_context(session, organizacion.id)
            return await accounting_repository.listar_ingresos(
                session, organization_id=organizacion.id, event_id=event_id, moneda_evento=moneda
            )


# --- `helper_euros_a_centimos`: redondeo -------------------------------------


@pytest.mark.parametrize(
    ("euros", "esperado"),
    [
        (Decimal("10.005"), 1001),  # `.005` redondea hacia arriba
        (Decimal("10.004"), 1000),  # `.004` redondea hacia abajo
        (Decimal("0.00"), 0),
        (Decimal("-10.005"), -1001),  # ROUND_HALF_UP: el empate se aleja de cero
    ],
)
def test_helper_euros_a_centimos_redondea_con_round_half_up(euros: Decimal, esperado: int) -> None:
    assert accounting_repository.helper_euros_a_centimos(euros) == esperado


# --- Predicado real de "cobrado" para patrocinios ----------------------------


async def test_patrocinador_monetario_sin_collected_at_no_suma_en_ingresos(
    organizacion: OrganizacionDePrueba,
) -> None:
    event_id = await _crear_evento(organizacion)
    sponsor_id = await _crear_sponsor(
        organizacion, event_id, contribution_type="monetaria", contribution_amount=Decimal("500.00")
    )

    vista = await _listar(organizacion, event_id)

    assert not any(linea.referencia_id == str(sponsor_id) for linea in vista.ingresos)
    assert any(linea.referencia_id == str(sponsor_id) for linea in vista.comprometido)
    assert vista.total_ingresos_cents == 0


async def test_marcar_collected_at_mueve_el_patrocinador_a_ingresos_sin_duplicar(
    organizacion: OrganizacionDePrueba,
) -> None:
    event_id = await _crear_evento(organizacion)
    sponsor_id = await _crear_sponsor(
        organizacion, event_id, contribution_type="monetaria", contribution_amount=Decimal("500.00")
    )

    async with SessionApp() as session:
        async with session.begin():
            await set_organization_context(session, organizacion.id)
            await accounting_service.fijar_datos_de_cobro_de_patrocinador(
                session,
                BackgroundTasks(),
                actor_user_id=organizacion.owner_id,
                organization_id=organizacion.id,
                sponsor_id=sponsor_id,
                datos={"collected_at": AHORA},
            )

    vista = await _listar(organizacion, event_id)
    assert any(linea.referencia_id == str(sponsor_id) for linea in vista.ingresos)
    assert not any(linea.referencia_id == str(sponsor_id) for linea in vista.comprometido)
    assert vista.total_ingresos_cents == 50_000

    async with SessionMaintenance() as session:
        filas = (
            await session.execute(
                SponsorPaymentDetail.__table__.select().where(
                    SponsorPaymentDetail.sponsor_id == sponsor_id
                )
            )
        ).all()
    assert len(filas) == 1, "marcar collected_at no debe crear una segunda fila"


async def test_patrocinador_en_especie_cuenta_siempre_en_ingresos(
    organizacion: OrganizacionDePrueba,
) -> None:
    event_id = await _crear_evento(organizacion)
    sponsor_id = await _crear_sponsor(
        organizacion,
        event_id,
        contribution_type="en_especie",
        contribution_description="Material audiovisual",
        in_kind_valuation_cents=30_000,
    )

    vista = await _listar(organizacion, event_id)

    linea = next(fila for fila in vista.ingresos if fila.referencia_id == str(sponsor_id))
    assert linea.importe_cents == 30_000
    assert vista.total_ingresos_cents == 30_000
    # "Peso sobre el total" solo tiene sentido en "Ingresos", nunca almacenado.
    assert linea.peso_sobre_el_total == Decimal("1")
    # La marca que distingue una valoración en especie de un cobro bancario:
    # cuenta como ingreso, pero una foto de caja la excluye.
    assert linea.en_especie is True


# --- `crear_ingreso_manual`: origin fijo a `subvencion` ----------------------


async def test_crear_ingreso_manual_con_origin_distinto_de_subvencion_da_422(
    organizacion: OrganizacionDePrueba,
) -> None:
    event_id = await _crear_evento(organizacion)

    with pytest.raises(ValidationDomainError):
        async with SessionApp() as session:
            async with session.begin():
                await set_organization_context(session, organizacion.id)
                await accounting_service.crear_ingreso_manual(
                    session,
                    BackgroundTasks(),
                    actor_user_id=organizacion.owner_id,
                    organization_id=organizacion.id,
                    event_id=event_id,
                    datos={
                        "origin": "colaborador",
                        "concept": "Aportación de un colaborador",
                        "amount_cents": 1_000,
                        "status": "pending",
                        "expected_at": None,
                        "collected_at": None,
                    },
                )


async def test_crear_ingreso_manual_subvencion_collected_va_a_ingresos(
    organizacion: OrganizacionDePrueba,
) -> None:
    event_id = await _crear_evento(organizacion)

    async with SessionApp() as session:
        async with session.begin():
            await set_organization_context(session, organizacion.id)
            await accounting_service.crear_ingreso_manual(
                session,
                BackgroundTasks(),
                actor_user_id=organizacion.owner_id,
                organization_id=organizacion.id,
                event_id=event_id,
                datos={
                    "origin": "subvencion",
                    "concept": "Ayuntamiento",
                    "amount_cents": 20_000,
                    "status": "collected",
                    "expected_at": None,
                    "collected_at": AHORA,
                },
            )

    vista = await _listar(organizacion, event_id)
    assert vista.total_ingresos_cents == 20_000
    assert any(fila.origen == "subvencion" for fila in vista.ingresos)


# --- Entradas: reembolsos confirmados y en curso -----------------------------


async def test_ingreso_neto_de_entradas_resta_reembolsos_confirmados_y_en_curso(
    organizacion: OrganizacionDePrueba,
) -> None:
    event_id = await _crear_evento(organizacion)
    # 10000 cobrados, 2000 ya reembolsados (confirmado por webhook) y 3000 en
    # curso (outbox `pending`, todavía sin `charge.refunded`): neto = 5000.
    payment_id = await _crear_pago(
        organizacion,
        event_id,
        amount_cents=10_000,
        refunded_cents=2_000,
        status="partially_refunded",
    )
    async with SessionMaintenance() as session:
        session.add(
            EventPaymentRefund(
                organization_id=organizacion.id,
                payment_id=payment_id,
                amount_cents=3_000,
                reason="manual",
                revoke_ticket=False,
                status="pending",
            )
        )
        await session.commit()

    vista = await _listar(organizacion, event_id)
    linea = next(fila for fila in vista.ingresos if fila.referencia_id == str(payment_id))
    assert linea.importe_cents == 5_000


async def test_ingreso_en_moneda_distinta_se_excluye_del_total_con_aviso(
    organizacion: OrganizacionDePrueba,
) -> None:
    event_id = await _crear_evento(organizacion, accounting_currency="eur")
    await _crear_pago(organizacion, event_id, amount_cents=10_000, currency="usd")

    vista = await _listar(organizacion, event_id, moneda="eur")

    assert vista.total_ingresos_cents == 0
    assert vista.ingresos_excluidos_por_moneda == 1
    assert not vista.ingresos


# --- "Peso sobre el total": no es una columna en ninguna tabla ---------------


def test_peso_sobre_el_total_no_es_una_columna_de_ningun_modelo() -> None:
    """Confirmación explícita (no un test de comportamiento): ninguna tabla
    del módulo persiste este valor, se calcula siempre en la consulta."""
    columnas_income = {c.name for c in AccountingIncome.__table__.columns}
    columnas_detalle = {c.name for c in SponsorPaymentDetail.__table__.columns}
    assert "peso_sobre_el_total" not in columnas_income
    assert "peso_sobre_el_total" not in columnas_detalle
