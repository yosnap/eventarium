"""Métricas del escritorio de la organización.

Compone, en una sola llamada, lo que el organizador necesita para saber cómo va
todo lo suyo: sus eventos con sus cifras, los totales de la organización, quién
tiene acceso, el estado de su cuenta de Stripe y —si puede verlo— el dinero.

**Todo son agregados en SQL, no listas que el cliente recorra.** Un organizador
con veinte eventos y miles de inscripciones no debe provocar que la pantalla se
traiga las filas para contarlas: las cifras por evento salen de una sola
consulta agrupada.

**El filtrado por permiso se hace aquí.** Los bloques económicos se omiten si
quien pide no tiene `payments:read` ni `accounting:read`, y los de estructura si
no tiene `members:read`. Devolver el número y esconderlo al pintarlo sería
mandarlo igual.

RLS hace su parte y **no sustituye a esto**: las políticas filtran por
organización, no por rol, así que sin este filtro un miembro de la organización
recibiría conteos de recursos que no puede abrir.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import Permission
from app.modules.accounting.models import AccountingBudgetLine, AccountingExpense
from app.modules.events.models import Event
from app.modules.organizations.metrics_schemas import (
    CifrasDeOrganizacionOut,
    DineroDeOrganizacionOut,
    EstadoDeStripeOut,
    EstructuraOut,
    EventoDelEscritorioOut,
    MetricasDeOrganizacionOut,
)
from app.modules.organizations.models import OrganizationMember
from app.modules.payments import repository as payments_repository
from app.modules.payments.models import EventPayment
from app.modules.registrations.models import EventRegistration
from app.modules.roles.models import Role
from app.modules.sponsors.models import Sponsor


async def _eventos_con_cifras(
    session: AsyncSession,
    organization_id: uuid.UUID,
    *,
    con_inscripciones: bool,
    con_dinero: bool,
) -> list[EventoDelEscritorioOut]:
    """La tabla de eventos, con sus cifras contadas en la misma consulta.

    Se agrupa por evento con subconsultas escalares en vez de una consulta por
    fila: pintar el escritorio de una organización con muchos eventos no debe
    costar un viaje por cada uno.

    Las columnas que dependen de un permiso se calculan **solo si lo tiene**: un
    miembro sin `registrations:read` no debe recibir el número de aprobaciones
    pendientes de cada evento, aunque la pantalla sea la misma y el dato venga
    dentro de una fila en vez de en su propio bloque.
    """
    columnas: list[Any] = [
        Event.id,
        Event.title,
        Event.slug,
        Event.status,
        Event.starts_at,
        Event.capacity,
    ]

    if con_inscripciones:
        sub_por_aprobar = (
            select(func.count())
            .select_from(EventRegistration)
            .where(
                EventRegistration.event_id == Event.id,
                EventRegistration.status == "pending_approval",
            )
            .scalar_subquery()
        )
        sub_confirmadas = (
            select(func.count())
            .select_from(EventRegistration)
            .where(
                EventRegistration.event_id == Event.id,
                EventRegistration.status == "confirmed",
            )
            .scalar_subquery()
        )
        columnas.append(sub_confirmadas.label("confirmadas"))
        columnas.append(sub_por_aprobar.label("por_aprobar"))
    if con_dinero:
        # El neto de cada evento: lo cobrado menos lo devuelto, incluidas las
        # devoluciones parciales (que también son dinero cobrado).
        sub_ingresos = (
            select(
                func.coalesce(func.sum(EventPayment.amount_cents - EventPayment.refunded_cents), 0)
            )
            .where(
                EventPayment.event_id == Event.id,
                EventPayment.status.in_(("paid", "partially_refunded")),
            )
            .scalar_subquery()
        )
        columnas.append(sub_ingresos.label("ingresos_cents"))

    filas = (
        await session.execute(
            select(*columnas)
            .where(Event.organization_id == organization_id)
            .order_by(Event.starts_at.desc())
        )
    ).all()

    eventos: list[EventoDelEscritorioOut] = []
    for fila in filas:
        valores = list(fila)
        # El orden de las columnas opcionales depende de qué permisos haya, así
        # que se consumen en el mismo orden en que se añadieron.
        resto = valores[6:]
        confirmadas = int(resto.pop(0) or 0) if con_inscripciones else None
        por_aprobar = int(resto.pop(0) or 0) if con_inscripciones else None
        ingresos = int(resto.pop(0) or 0) if con_dinero else None
        eventos.append(
            EventoDelEscritorioOut(
                id=str(valores[0]),
                title=valores[1],
                slug=valores[2],
                status=valores[3],
                starts_at=valores[4].isoformat(),
                aforo=valores[5],
                confirmadas=confirmadas,
                por_aprobar=por_aprobar,
                ingresos_cents=ingresos,
            )
        )
    return eventos


async def _cifras(session: AsyncSession, organization_id: uuid.UUID) -> CifrasDeOrganizacionOut:
    eventos = {
        estado: int(total)
        for estado, total in (
            await session.execute(
                select(Event.status, func.count())
                .where(Event.organization_id == organization_id)
                .group_by(Event.status)
            )
        ).all()
    }
    inscripciones = {
        estado: int(total)
        for estado, total in (
            await session.execute(
                select(EventRegistration.status, func.count())
                .where(EventRegistration.organization_id == organization_id)
                .group_by(EventRegistration.status)
            )
        ).all()
    }

    # Las plazas reservadas de toda la organización, con el mismo criterio que
    # aplica el sistema evento a evento: confirmadas, promociones de lista de
    # espera vigentes y pagos dentro de su ventana.
    reservadas = await session.scalar(
        select(func.count())
        .select_from(EventRegistration)
        .where(
            EventRegistration.organization_id == organization_id,
            EventRegistration.status.in_(("confirmed", "pending_payment")),
        )
    )
    aforo_total = await session.scalar(
        select(func.coalesce(func.sum(Event.capacity), 0)).where(
            Event.organization_id == organization_id,
            Event.capacity.is_not(None),
        )
    )
    hay_aforo = await session.scalar(
        select(func.count())
        .select_from(Event)
        .where(
            Event.organization_id == organization_id,
            Event.capacity.is_not(None),
        )
    )

    return CifrasDeOrganizacionOut(
        eventos_por_estado=eventos,
        inscripciones_por_estado=inscripciones,
        reservadas=int(reservadas or 0),
        # `None` si ningún evento fija aforo: no es «cero plazas».
        aforo_total=int(aforo_total or 0) if hay_aforo else None,
        por_aprobar=inscripciones.get("pending_approval", 0),
        lista_de_espera=inscripciones.get("waitlisted", 0),
    )


async def _estructura(session: AsyncSession, organization_id: uuid.UUID) -> EstructuraOut:
    miembros = await session.scalar(
        select(func.count())
        .select_from(OrganizationMember)
        .where(OrganizationMember.organization_id == organization_id)
    )
    roles = await session.scalar(
        select(func.count()).select_from(Role).where(Role.organization_id == organization_id)
    )
    patrocinadores = await session.scalar(
        select(func.count()).select_from(Sponsor).where(Sponsor.organization_id == organization_id)
    )
    return EstructuraOut(
        miembros=int(miembros or 0),
        roles=int(roles or 0),
        patrocinadores=int(patrocinadores or 0),
    )


async def _dinero(session: AsyncSession, organization_id: uuid.UUID) -> DineroDeOrganizacionOut:
    """Los importes de la organización, agrupados por moneda.

    No se da un total único: sumar euros con dólares daría una cifra que no
    significa nada. El caso normal es una sola moneda.
    """
    ingresos = (
        await session.execute(
            select(
                EventPayment.currency,
                func.coalesce(func.sum(EventPayment.amount_cents - EventPayment.refunded_cents), 0),
            )
            .where(
                EventPayment.organization_id == organization_id,
                EventPayment.status.in_(("paid", "partially_refunded")),
            )
            .group_by(EventPayment.currency)
        )
    ).all()

    moneda = await session.scalar(
        select(Event.accounting_currency).where(Event.organization_id == organization_id).limit(1)
    )
    clave = moneda or "eur"

    presupuesto = await session.scalar(
        select(func.coalesce(func.sum(AccountingBudgetLine.budgeted_cents), 0)).where(
            AccountingBudgetLine.organization_id == organization_id
        )
    )
    ejecutado = await session.scalar(
        select(func.coalesce(func.sum(AccountingExpense.total_cents), 0)).where(
            AccountingExpense.organization_id == organization_id
        )
    )

    return DineroDeOrganizacionOut(
        por_moneda={currency: int(total or 0) for currency, total in ingresos},
        presupuesto_por_moneda={clave: int(presupuesto or 0)},
        ejecutado_por_moneda={clave: int(ejecutado or 0)},
    )


async def _stripe(session: AsyncSession, organization_id: uuid.UUID) -> EstadoDeStripeOut:
    cuenta = await payments_repository.get_cuenta_activa(session, organization_id)
    if cuenta is None:
        return EstadoDeStripeOut(
            conectada=False, charges_enabled=False, payouts_enabled=False, details_submitted=False
        )
    return EstadoDeStripeOut(
        conectada=True,
        charges_enabled=cuenta.charges_enabled,
        payouts_enabled=cuenta.payouts_enabled,
        details_submitted=cuenta.details_submitted,
    )


async def metricas_de_la_organizacion(
    session: AsyncSession, organization_id: uuid.UUID, permisos: set[Permission]
) -> MetricasDeOrganizacionOut:
    """Compone la vista, omitiendo los bloques para los que falta permiso."""
    puede_inscripciones = Permission.REGISTRATIONS_READ in permisos
    puede_dinero = Permission.PAYMENTS_READ in permisos or Permission.ACCOUNTING_READ in permisos

    eventos = await _eventos_con_cifras(
        session, organization_id, con_inscripciones=puede_inscripciones, con_dinero=puede_dinero
    )
    eventos_en_borrador = sum(1 for evento in eventos if evento.status == "draft")

    return MetricasDeOrganizacionOut(
        eventos_en_borrador=eventos_en_borrador,
        eventos=eventos,
        cifras=await _cifras(session, organization_id) if puede_inscripciones else None,
        estructura=await _estructura(session, organization_id),
        dinero=await _dinero(session, organization_id) if puede_dinero else None,
        stripe=await _stripe(session, organization_id),
    )
