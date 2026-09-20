"""Aislamiento entre organizaciones para las cinco tablas de `accounting`.

Mismo patrón que `test_sponsors_rls_isolation.py`/`test_payments_rls_isolation.py`
(si existiera): una comprobación de lectura (RLS), otra de escritura cruzada
(las FK compuestas contra `(id, organization_id)` del padre) y otra de
`ON DELETE RESTRICT` hacia `events` (plan.md Decisión #19).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.core.database import SessionApp, SessionMaintenance, set_organization_context
from app.modules.accounting.models import (
    AccountingBudgetLine,
    AccountingExpense,
    AccountingExpenseDraft,
    AccountingIncome,
    SponsorPaymentDetail,
)
from app.modules.events.models import Event
from app.modules.organizations.repository import unsafe_select_all
from app.modules.sponsors.models import Sponsor, SponsorTier
from tests.conftest import OrganizacionDePrueba

TABLAS_CON_ORGANIZACION = (
    AccountingBudgetLine,
    AccountingIncome,
    AccountingExpense,
    AccountingExpenseDraft,
    SponsorPaymentDetail,
)

AHORA = datetime.now(UTC)


class DatosDePrueba:
    __slots__ = ("event_id", "sponsor_id", "budget_line_id", "draft_id", "expense_id")

    def __init__(
        self,
        *,
        event_id: uuid.UUID,
        sponsor_id: uuid.UUID,
        budget_line_id: uuid.UUID,
        draft_id: uuid.UUID,
        expense_id: uuid.UUID,
    ) -> None:
        self.event_id = event_id
        self.sponsor_id = sponsor_id
        self.budget_line_id = budget_line_id
        self.draft_id = draft_id
        self.expense_id = expense_id


async def _crear_datos_de_prueba(organizacion: OrganizacionDePrueba) -> DatosDePrueba:
    async with SessionMaintenance() as session:
        evento = Event(
            organization_id=organizacion.id,
            slug=f"evento-{organizacion.slug}",
            title="Evento de prueba",
            status="published",
            visibility="public",
            starts_at=AHORA,
            ends_at=AHORA + timedelta(days=1),
            location_mode="online",
        )
        session.add(evento)
        await session.flush()

        nivel = SponsorTier(
            organization_id=organizacion.id, name=f"Oro {organizacion.slug}", display_order=1
        )
        session.add(nivel)
        await session.flush()

        patrocinador = Sponsor(
            event_id=evento.id,
            tier_id=nivel.id,
            organization_id=organizacion.id,
            name=f"Patrocinador {organizacion.slug}",
            contribution_type="en_especie",
            in_kind_valuation_cents=50_000,
        )
        session.add(patrocinador)
        await session.flush()

        partida = AccountingBudgetLine(
            event_id=evento.id,
            organization_id=organizacion.id,
            name="Catering",
            budgeted_cents=100_000,
        )
        session.add(partida)
        await session.flush()

        session.add(
            AccountingIncome(
                event_id=evento.id,
                organization_id=organizacion.id,
                origin="subvencion",
                concept="Ayuntamiento",
                amount_cents=200_000,
            )
        )

        draft = AccountingExpenseDraft(
            event_id=evento.id,
            organization_id=organizacion.id,
            receipt_object_key=f"orgs/{organizacion.id}/accounting-receipts/{uuid.uuid4().hex}.pdf",
            ocr_provider="test-provider",
        )
        session.add(draft)
        await session.flush()

        gasto = AccountingExpense(
            event_id=evento.id,
            organization_id=organizacion.id,
            budget_line_id=partida.id,
            sponsor_id=patrocinador.id,
            provider_name="Catering S.L.",
            expense_date=AHORA,
            base_cents=50_000,
            total_cents=50_000,
            draft_id=draft.id,
        )
        session.add(gasto)
        await session.flush()

        session.add(
            SponsorPaymentDetail(
                sponsor_id=patrocinador.id,
                organization_id=organizacion.id,
                contact_name="Persona de contacto",
            )
        )

        await session.commit()
        return DatosDePrueba(
            event_id=evento.id,
            sponsor_id=patrocinador.id,
            budget_line_id=partida.id,
            draft_id=draft.id,
            expense_id=gasto.id,
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


async def test_no_se_puede_crear_una_partida_sobre_un_evento_ajeno(
    organizacion: OrganizacionDePrueba, otra_organizacion: OrganizacionDePrueba
) -> None:
    datos_ajenos = await _crear_datos_de_prueba(otra_organizacion)

    with pytest.raises(DBAPIError):
        async with SessionApp() as session:
            async with session.begin():
                await set_organization_context(session, organizacion.id)
                session.add(
                    AccountingBudgetLine(
                        event_id=datos_ajenos.event_id,
                        organization_id=organizacion.id,
                        name="Partida intrusa",
                        budgeted_cents=1_000,
                    )
                )
                await session.flush()


async def test_no_se_puede_crear_un_gasto_con_patrocinador_ajeno(
    organizacion: OrganizacionDePrueba, otra_organizacion: OrganizacionDePrueba
) -> None:
    datos_propios = await _crear_datos_de_prueba(organizacion)
    datos_ajenos = await _crear_datos_de_prueba(otra_organizacion)

    with pytest.raises(DBAPIError):
        async with SessionApp() as session:
            async with session.begin():
                await set_organization_context(session, organizacion.id)
                session.add(
                    AccountingExpense(
                        event_id=datos_propios.event_id,
                        organization_id=organizacion.id,
                        budget_line_id=datos_propios.budget_line_id,
                        sponsor_id=datos_ajenos.sponsor_id,
                        provider_name="Intruso",
                        expense_date=AHORA,
                        base_cents=1_000,
                        total_cents=1_000,
                    )
                )
                await session.flush()


async def test_borrar_un_evento_con_contabilidad_falla_por_integridad(
    organizacion: OrganizacionDePrueba,
) -> None:
    """Ninguna de las cinco tablas nuevas usa `CASCADE` hacia `events`
    (plan.md Decisión #19): borrar un evento con partidas, ingresos, gastos y
    drafts debe fallar hasta que esa contabilidad se borre explícitamente."""
    datos = await _crear_datos_de_prueba(organizacion)

    with pytest.raises((DBAPIError, IntegrityError)):
        async with SessionMaintenance() as session:
            await session.execute(Event.__table__.delete().where(Event.id == datos.event_id))
            await session.commit()
