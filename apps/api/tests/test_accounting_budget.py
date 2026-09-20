"""Presupuesto, gastos y contingencia (fase 3 de trabajo).

Cubre los criterios de éxito de `phase-03-gastos-partidas-y-contingencia.md`
a nivel de servicio: aprobación/reapertura con el bloqueo correcto, partidas
de solo lectura tras aprobar, exclusión de los gastos en especie del consumo
de contingencia, y el upsert real (`UNIQUE(sponsor_id)`) de
`fijar_valoracion_en_especie`. La concurrencia real (dos peticiones HTTP
simultáneas) vive en `test_accounting_budget_router.py`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi import BackgroundTasks

from app.core.database import SessionApp, SessionMaintenance, set_organization_context
from app.modules.accounting import service as accounting_service
from app.modules.accounting.models import AccountingBudgetLine, AccountingExpense
from app.modules.events.models import Event
from app.modules.sponsors.models import Sponsor, SponsorTier
from app.shared.errors import ConflictError, NotFoundError, ValidationDomainError
from tests.conftest import OrganizacionDePrueba

AHORA = datetime.now(UTC).replace(microsecond=0)


async def _crear_evento(
    organizacion: OrganizacionDePrueba, *, contingency_fund_percent: Decimal = Decimal("10.00")
) -> uuid.UUID:
    async with SessionMaintenance() as session:
        evento = Event(
            organization_id=organizacion.id,
            slug=f"evento-presupuesto-{uuid.uuid4().hex[:8]}",
            title="Evento de presupuesto",
            status="published",
            visibility="public",
            starts_at=AHORA,
            ends_at=AHORA + timedelta(days=1),
            location_mode="online",
            contingency_fund_percent=contingency_fund_percent,
        )
        session.add(evento)
        await session.commit()
        return evento.id


async def _crear_sponsor(
    organizacion: OrganizacionDePrueba,
    event_id: uuid.UUID,
    *,
    contribution_type: str,
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
            contribution_amount=Decimal("100.00") if contribution_type == "monetaria" else None,
            in_kind_valuation_cents=in_kind_valuation_cents,
        )
        session.add(patrocinador)
        await session.commit()
        return patrocinador.id


async def _crear_partida(
    organizacion: OrganizacionDePrueba,
    event_id: uuid.UUID,
    *,
    budgeted_cents: int,
    name: str = "Partida",
) -> uuid.UUID:
    async with SessionMaintenance() as session:
        partida = AccountingBudgetLine(
            event_id=event_id,
            organization_id=organizacion.id,
            name=name,
            budgeted_cents=budgeted_cents,
        )
        session.add(partida)
        await session.commit()
        return partida.id


async def _crear_gasto(
    organizacion: OrganizacionDePrueba,
    event_id: uuid.UUID,
    *,
    budget_line_id: uuid.UUID | None,
    total_cents: int,
    sponsor_id: uuid.UUID | None = None,
) -> uuid.UUID:
    async with SessionMaintenance() as session:
        gasto = AccountingExpense(
            event_id=event_id,
            organization_id=organizacion.id,
            budget_line_id=budget_line_id,
            sponsor_id=sponsor_id,
            provider_name="Proveedor de prueba",
            expense_date=AHORA,
            base_cents=total_cents,
            total_cents=total_cents,
        )
        session.add(gasto)
        await session.commit()
        return gasto.id


async def _get_event(organizacion: OrganizacionDePrueba, event_id: uuid.UUID) -> Event:
    async with SessionMaintenance() as session:
        evento = await session.get(Event, event_id)
        assert evento is not None
        return evento


# --- Aprobación / reapertura del presupuesto ---------------------------------


async def test_aprobar_presupuesto_calcula_contingencia_y_fija_fecha(
    organizacion: OrganizacionDePrueba,
) -> None:
    event_id = await _crear_evento(organizacion, contingency_fund_percent=Decimal("10.00"))
    await _crear_partida(organizacion, event_id, budgeted_cents=100_000)
    await _crear_partida(organizacion, event_id, budgeted_cents=50_000)

    async with SessionApp() as session:
        async with session.begin():
            await set_organization_context(session, organizacion.id)
            evento = await accounting_service.aprobar_presupuesto(
                session,
                BackgroundTasks(),
                actor_user_id=organizacion.owner_id,
                organization_id=organizacion.id,
                event_id=event_id,
            )
            assert evento.budget_approved_at is not None
            # 10% de 150_000 = 15_000.
            assert evento.contingency_fund_cents == 15_000


async def test_segunda_aprobacion_secuencial_da_409(organizacion: OrganizacionDePrueba) -> None:
    event_id = await _crear_evento(organizacion)
    await _crear_partida(organizacion, event_id, budgeted_cents=10_000)

    async with SessionApp() as session:
        async with session.begin():
            await set_organization_context(session, organizacion.id)
            await accounting_service.aprobar_presupuesto(
                session,
                BackgroundTasks(),
                actor_user_id=organizacion.owner_id,
                organization_id=organizacion.id,
                event_id=event_id,
            )

    with pytest.raises(ConflictError):
        async with SessionApp() as session:
            async with session.begin():
                await set_organization_context(session, organizacion.id)
                await accounting_service.aprobar_presupuesto(
                    session,
                    BackgroundTasks(),
                    actor_user_id=organizacion.owner_id,
                    organization_id=organizacion.id,
                    event_id=event_id,
                )


async def test_aprobar_evento_ajeno_da_404(
    organizacion: OrganizacionDePrueba, otra_organizacion: OrganizacionDePrueba
) -> None:
    event_id_ajeno = await _crear_evento(otra_organizacion)

    with pytest.raises(NotFoundError):
        async with SessionApp() as session:
            async with session.begin():
                await set_organization_context(session, organizacion.id)
                await accounting_service.aprobar_presupuesto(
                    session,
                    BackgroundTasks(),
                    actor_user_id=organizacion.owner_id,
                    organization_id=organizacion.id,
                    event_id=event_id_ajeno,
                )


async def test_reabrir_sin_motivo_da_422(organizacion: OrganizacionDePrueba) -> None:
    event_id = await _crear_evento(organizacion)
    async with SessionApp() as session:
        async with session.begin():
            await set_organization_context(session, organizacion.id)
            await accounting_service.aprobar_presupuesto(
                session,
                BackgroundTasks(),
                actor_user_id=organizacion.owner_id,
                organization_id=organizacion.id,
                event_id=event_id,
            )

    with pytest.raises(ValidationDomainError):
        async with SessionApp() as session:
            async with session.begin():
                await set_organization_context(session, organizacion.id)
                await accounting_service.reabrir_presupuesto(
                    session,
                    BackgroundTasks(),
                    actor_user_id=organizacion.owner_id,
                    organization_id=organizacion.id,
                    event_id=event_id,
                    motivo="   ",
                )


async def test_reabrir_con_motivo_permite_editar_partidas_y_recalcula(
    organizacion: OrganizacionDePrueba,
) -> None:
    event_id = await _crear_evento(organizacion, contingency_fund_percent=Decimal("10.00"))
    linea_id = await _crear_partida(organizacion, event_id, budgeted_cents=100_000)

    async with SessionApp() as session:
        async with session.begin():
            await set_organization_context(session, organizacion.id)
            await accounting_service.aprobar_presupuesto(
                session,
                BackgroundTasks(),
                actor_user_id=organizacion.owner_id,
                organization_id=organizacion.id,
                event_id=event_id,
            )

    # Mientras está aprobado, la partida es de solo lectura.
    with pytest.raises(ConflictError):
        async with SessionApp() as session:
            async with session.begin():
                await set_organization_context(session, organizacion.id)
                await accounting_service.editar_partida_presupuesto(
                    session,
                    BackgroundTasks(),
                    actor_user_id=organizacion.owner_id,
                    organization_id=organizacion.id,
                    budget_line_id=linea_id,
                    datos={"budgeted_cents": 200_000},
                )

    async with SessionApp() as session:
        async with session.begin():
            await set_organization_context(session, organizacion.id)
            await accounting_service.reabrir_presupuesto(
                session,
                BackgroundTasks(),
                actor_user_id=organizacion.owner_id,
                organization_id=organizacion.id,
                event_id=event_id,
                motivo="Error de tecleo en la partida de catering.",
            )

    evento_reabierto = await _get_event(organizacion, event_id)
    assert evento_reabierto.budget_approved_at is None
    # `contingency_fund_cents` no se borra hasta la siguiente aprobación.
    assert evento_reabierto.contingency_fund_cents == 10_000

    async with SessionApp() as session:
        async with session.begin():
            await set_organization_context(session, organizacion.id)
            await accounting_service.editar_partida_presupuesto(
                session,
                BackgroundTasks(),
                actor_user_id=organizacion.owner_id,
                organization_id=organizacion.id,
                budget_line_id=linea_id,
                datos={"budgeted_cents": 200_000},
            )
            evento = await accounting_service.aprobar_presupuesto(
                session,
                BackgroundTasks(),
                actor_user_id=organizacion.owner_id,
                organization_id=organizacion.id,
                event_id=event_id,
            )
            # 10% de 200_000 (recalculado desde cero, no arrastra el 10_000 previo).
            assert evento.contingency_fund_cents == 20_000


async def test_borrar_partida_con_presupuesto_aprobado_da_409(
    organizacion: OrganizacionDePrueba,
) -> None:
    event_id = await _crear_evento(organizacion)
    linea_id = await _crear_partida(organizacion, event_id, budgeted_cents=10_000)

    async with SessionApp() as session:
        async with session.begin():
            await set_organization_context(session, organizacion.id)
            await accounting_service.aprobar_presupuesto(
                session,
                BackgroundTasks(),
                actor_user_id=organizacion.owner_id,
                organization_id=organizacion.id,
                event_id=event_id,
            )

    with pytest.raises(ConflictError):
        async with SessionApp() as session:
            async with session.begin():
                await set_organization_context(session, organizacion.id)
                await accounting_service.borrar_partida_presupuesto(
                    session,
                    BackgroundTasks(),
                    actor_user_id=organizacion.owner_id,
                    organization_id=organizacion.id,
                    budget_line_id=linea_id,
                )


# --- Contingencia: exclusión de gastos en especie, exceso por partida --------


async def test_gasto_en_especie_no_consume_contingencia(organizacion: OrganizacionDePrueba) -> None:
    event_id = await _crear_evento(organizacion, contingency_fund_percent=Decimal("10.00"))
    sponsor_id = await _crear_sponsor(
        organizacion, event_id, contribution_type="en_especie", in_kind_valuation_cents=80_000
    )
    linea_id = await _crear_partida(
        organizacion, event_id, budgeted_cents=50_000, name="Solo en especie"
    )
    # El gasto en especie (80_000) supera con mucho la partida (50_000), pero
    # `sponsor_id IS NOT NULL` lo excluye por completo del cómputo.
    await _crear_gasto(
        organizacion, event_id, budget_line_id=linea_id, total_cents=80_000, sponsor_id=sponsor_id
    )

    async with SessionApp() as session:
        async with session.begin():
            await set_organization_context(session, organizacion.id)
            await accounting_service.aprobar_presupuesto(
                session,
                BackgroundTasks(),
                actor_user_id=organizacion.owner_id,
                organization_id=organizacion.id,
                event_id=event_id,
            )
            resumen = await accounting_service.resumen_presupuesto(
                session, organization_id=organizacion.id, event_id=event_id
            )

    assert resumen.consumido_contingencia_cents == 0
    assert resumen.disponible_contingencia_cents == resumen.contingency_fund_cents
    assert resumen.contingency_fund_cents == 5_000  # 10% de 50_000
    # Criterio de éxito 7: el gasto en especie aparece como cifra separada,
    # nunca mezclado con `por_partida` (que sigue vacío: `sponsor_id IS NOT
    # NULL` lo excluye del cómputo por partida, no solo del de contingencia).
    assert resumen.ejecutado_en_especie_cents == 80_000
    assert resumen.por_partida == []


async def test_gasto_que_supera_partida_consume_solo_el_exceso(
    organizacion: OrganizacionDePrueba,
) -> None:
    event_id = await _crear_evento(organizacion, contingency_fund_percent=Decimal("20.00"))
    linea_id = await _crear_partida(organizacion, event_id, budgeted_cents=10_000, name="Catering")
    await _crear_gasto(organizacion, event_id, budget_line_id=linea_id, total_cents=13_000)

    async with SessionApp() as session:
        async with session.begin():
            await set_organization_context(session, organizacion.id)
            await accounting_service.aprobar_presupuesto(
                session,
                BackgroundTasks(),
                actor_user_id=organizacion.owner_id,
                organization_id=organizacion.id,
                event_id=event_id,
            )
            resumen = await accounting_service.resumen_presupuesto(
                session, organization_id=organizacion.id, event_id=event_id
            )

    assert resumen.consumido_contingencia_cents == 3_000  # exceso, no el gasto entero
    assert resumen.contingency_fund_cents == 2_000  # 20% de 10_000
    assert resumen.disponible_contingencia_cents == -1_000


async def test_gasto_sin_partida_consume_contingencia_por_su_importe_integro(
    organizacion: OrganizacionDePrueba,
) -> None:
    event_id = await _crear_evento(organizacion, contingency_fund_percent=Decimal("50.00"))
    await _crear_partida(organizacion, event_id, budgeted_cents=10_000)
    await _crear_gasto(organizacion, event_id, budget_line_id=None, total_cents=1_000)

    async with SessionApp() as session:
        async with session.begin():
            await set_organization_context(session, organizacion.id)
            await accounting_service.aprobar_presupuesto(
                session,
                BackgroundTasks(),
                actor_user_id=organizacion.owner_id,
                organization_id=organizacion.id,
                event_id=event_id,
            )
            resumen = await accounting_service.resumen_presupuesto(
                session, organization_id=organizacion.id, event_id=event_id
            )

    assert resumen.gasto_sin_partida_cents == 1_000
    assert resumen.consumido_contingencia_cents == 1_000


# --- Valoración en especie de un patrocinador --------------------------------


async def test_fijar_valoracion_en_especie_sobre_sponsor_monetario_da_422(
    organizacion: OrganizacionDePrueba,
) -> None:
    event_id = await _crear_evento(organizacion)
    sponsor_id = await _crear_sponsor(organizacion, event_id, contribution_type="monetaria")
    linea_id = await _crear_partida(organizacion, event_id, budgeted_cents=1_000)

    with pytest.raises(ValidationDomainError):
        async with SessionApp() as session:
            async with session.begin():
                await set_organization_context(session, organizacion.id)
                await accounting_service.fijar_valoracion_en_especie(
                    session,
                    BackgroundTasks(),
                    actor_user_id=organizacion.owner_id,
                    organization_id=organizacion.id,
                    sponsor_id=sponsor_id,
                    valoracion_cents=10_000,
                    budget_line_id=linea_id,
                )


async def test_fijar_valoracion_en_especie_sin_partida_da_422(
    organizacion: OrganizacionDePrueba,
) -> None:
    event_id = await _crear_evento(organizacion)
    sponsor_id = await _crear_sponsor(organizacion, event_id, contribution_type="en_especie")

    with pytest.raises(ValidationDomainError):
        async with SessionApp() as session:
            async with session.begin():
                await set_organization_context(session, organizacion.id)
                await accounting_service.fijar_valoracion_en_especie(
                    session,
                    BackgroundTasks(),
                    actor_user_id=organizacion.owner_id,
                    organization_id=organizacion.id,
                    sponsor_id=sponsor_id,
                    valoracion_cents=10_000,
                    budget_line_id=None,
                )


async def test_cambiar_valoracion_actualiza_el_mismo_gasto_no_crea_otro(
    organizacion: OrganizacionDePrueba,
) -> None:
    event_id = await _crear_evento(organizacion)
    sponsor_id = await _crear_sponsor(organizacion, event_id, contribution_type="en_especie")
    linea_id = await _crear_partida(organizacion, event_id, budgeted_cents=1_000)

    async with SessionApp() as session:
        async with session.begin():
            await set_organization_context(session, organizacion.id)
            resultado = await accounting_service.fijar_valoracion_en_especie(
                session,
                BackgroundTasks(),
                actor_user_id=organizacion.owner_id,
                organization_id=organizacion.id,
                sponsor_id=sponsor_id,
                valoracion_cents=30_000,
                budget_line_id=linea_id,
            )
            primer_gasto_id = resultado.gasto.id

    async with SessionApp() as session:
        async with session.begin():
            await set_organization_context(session, organizacion.id)
            resultado = await accounting_service.fijar_valoracion_en_especie(
                session,
                BackgroundTasks(),
                actor_user_id=organizacion.owner_id,
                organization_id=organizacion.id,
                sponsor_id=sponsor_id,
                valoracion_cents=45_000,
                budget_line_id=linea_id,
            )
            segundo_gasto_id = resultado.gasto.id
            assert resultado.gasto.total_cents == 45_000

    assert primer_gasto_id == segundo_gasto_id

    async with SessionMaintenance() as session:
        filas = (
            await session.execute(
                AccountingExpense.__table__.select().where(
                    AccountingExpense.sponsor_id == sponsor_id
                )
            )
        ).all()
    assert len(filas) == 1, "cambiar la valoración no debe crear un segundo gasto"


async def test_poner_valoracion_a_none_borra_el_gasto_enlazado(
    organizacion: OrganizacionDePrueba,
) -> None:
    event_id = await _crear_evento(organizacion)
    sponsor_id = await _crear_sponsor(organizacion, event_id, contribution_type="en_especie")
    linea_id = await _crear_partida(organizacion, event_id, budgeted_cents=1_000)

    async with SessionApp() as session:
        async with session.begin():
            await set_organization_context(session, organizacion.id)
            await accounting_service.fijar_valoracion_en_especie(
                session,
                BackgroundTasks(),
                actor_user_id=organizacion.owner_id,
                organization_id=organizacion.id,
                sponsor_id=sponsor_id,
                valoracion_cents=30_000,
                budget_line_id=linea_id,
            )

    async with SessionApp() as session:
        async with session.begin():
            await set_organization_context(session, organizacion.id)
            resultado = await accounting_service.fijar_valoracion_en_especie(
                session,
                BackgroundTasks(),
                actor_user_id=organizacion.owner_id,
                organization_id=organizacion.id,
                sponsor_id=sponsor_id,
                valoracion_cents=None,
                budget_line_id=None,
            )
            assert resultado.gasto is None
            assert resultado.sponsor.in_kind_valuation_cents is None

    async with SessionMaintenance() as session:
        filas = (
            await session.execute(
                AccountingExpense.__table__.select().where(
                    AccountingExpense.sponsor_id == sponsor_id
                )
            )
        ).all()
    assert filas == []


async def test_gasto_manual_no_permite_partida_de_otro_evento(
    organizacion: OrganizacionDePrueba,
) -> None:
    event_id = await _crear_evento(organizacion)
    otro_event_id = await _crear_evento(organizacion)
    linea_de_otro_evento = await _crear_partida(organizacion, otro_event_id, budgeted_cents=1_000)

    with pytest.raises(ValidationDomainError):
        async with SessionApp() as session:
            async with session.begin():
                await set_organization_context(session, organizacion.id)
                await accounting_service.crear_gasto(
                    session,
                    BackgroundTasks(),
                    actor_user_id=organizacion.owner_id,
                    organization_id=organizacion.id,
                    event_id=event_id,
                    datos={
                        "budget_line_id": linea_de_otro_evento,
                        "provider_name": "Proveedor",
                        "expense_date": AHORA,
                        "base_cents": 1_000,
                        "vat_cents": None,
                        "total_cents": 1_000,
                    },
                )


async def test_editar_gasto_en_especie_por_endpoint_manual_da_409(
    organizacion: OrganizacionDePrueba,
) -> None:
    event_id = await _crear_evento(organizacion)
    sponsor_id = await _crear_sponsor(organizacion, event_id, contribution_type="en_especie")
    linea_id = await _crear_partida(organizacion, event_id, budgeted_cents=1_000)
    gasto_id = await _crear_gasto(
        organizacion, event_id, budget_line_id=linea_id, total_cents=5_000, sponsor_id=sponsor_id
    )

    with pytest.raises(ConflictError):
        async with SessionApp() as session:
            async with session.begin():
                await set_organization_context(session, organizacion.id)
                await accounting_service.editar_gasto(
                    session,
                    BackgroundTasks(),
                    actor_user_id=organizacion.owner_id,
                    organization_id=organizacion.id,
                    expense_id=gasto_id,
                    datos={"total_cents": 6_000},
                )
