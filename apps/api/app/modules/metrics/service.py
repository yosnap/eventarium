"""Métricas del escritorio de un evento.

Compone en una sola respuesta lo que hoy está repartido entre seis módulos
(inscripciones, entradas, pagos, contabilidad, patrocinadores y agenda). No
recalcula nada que ya exista: el embudo viene de
`registrations.service.get_registration_stats` y las cifras económicas, de las
sumas de `accounting.repository`.

**El filtrado por permiso se hace aquí, no en la interfaz.** El escritorio junta
recursos que tienen permisos propios, y quien mira no tiene por qué poder verlos
todos: devolver el número y esconderlo en pantalla sería mandarlo igual. Los
bloques sin permiso se omiten (`None`) antes de construir la respuesta.

RLS hace su parte, pero **no sustituye a esto**: las políticas filtran por
organización, no por rol, así que un miembro de la organización con el permiso
justo para entrar al evento recibiría sin este filtro conteos de recursos que no
puede abrir.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import Permission
from app.modules.accounting import repository as accounting_repository
from app.modules.accounting.models import AccountingExpense
from app.modules.events.models import Event, EventSession, EventVenue
from app.modules.metrics.schemas import (
    CifrasOut,
    DineroOut,
    EmbudoOut,
    MetricasDelEventoOut,
    OcupacionOut,
    PiezaOut,
)
from app.modules.payments.models import EventDiscountCode, EventTicketType
from app.modules.registrations import repository as registrations_repository
from app.modules.registrations import service as registrations_service
from app.modules.sponsors.models import Sponsor
from app.modules.tickets.models import EventTicket


async def _contar(session: AsyncSession, modelo: Any, **filtros: Any) -> int:
    total = await session.scalar(select(func.count()).select_from(modelo).filter_by(**filtros))
    return int(total or 0)


async def _embudo(session: AsyncSession, evento: Event) -> EmbudoOut:
    """Los cuatro escalones, de la misma fuente que usa el panel de inscripciones."""
    estadisticas = await registrations_service.get_registration_stats(
        session,
        organization_id=evento.organization_id,
        event_id=evento.id,
        email_verification_required=evento.email_verification_required,
    )
    return EmbudoOut(
        formulario=estadisticas["initiated"],
        verificado=estadisticas["verified"],
        aprobado=estadisticas["approved"],
        emitido=estadisticas["issued"],
        sin_verificacion_exigida=not evento.email_verification_required,
    )


async def _ocupacion(session: AsyncSession, evento: Event) -> OcupacionOut:
    """El aforo tal como lo aplica el sistema, no solo las confirmadas."""
    reservadas = await registrations_repository.count_reserved_registrations(
        session, evento.organization_id, evento.id
    )
    return OcupacionOut(reservadas=reservadas, aforo=evento.capacity)


async def _cifras(session: AsyncSession, evento: Event) -> CifrasOut:
    por_estado = await registrations_repository.count_registrations_by_status(
        session, evento.organization_id, evento.id
    )
    # Confirmadas con entrada emitida y sin usar: las personas que aún no han
    # entrado, que no es lo mismo que «entradas emitidas» (puede haber entradas
    # de gente que ya pasó, o revocadas).
    sin_entrar = await session.scalar(
        select(func.count())
        .select_from(EventTicket)
        .where(
            EventTicket.organization_id == evento.organization_id,
            EventTicket.event_id == evento.id,
            EventTicket.revoked_at.is_(None),
            EventTicket.used_at.is_(None),
        )
    )
    return CifrasOut(
        por_estado=por_estado,
        lista_de_espera=por_estado.get("waitlisted", 0),
        por_aprobar=por_estado.get("pending_approval", 0),
        sin_entrar=int(sin_entrar or 0),
    )


async def _piezas(session: AsyncSession, evento: Event) -> list[PiezaOut]:
    """Estado de cada parte del evento, para saber qué falta antes de abrirlo.

    No todo lo que está a cero es un problema: un evento gratuito no necesita
    tipos de entrada. Por eso cada pieza declara si **aplica**, y la interfaz
    solo avisa de las que faltan teniendo que estar.
    """
    org = evento.organization_id
    event_id = evento.id

    sesiones = await _contar(session, EventSession, organization_id=org, event_id=event_id)
    sedes = await _contar(session, EventVenue, organization_id=org, event_id=event_id)
    tipos_de_entrada = await _contar(
        session, EventTicketType, organization_id=org, event_id=event_id
    )
    descuentos = await _contar(session, EventDiscountCode, organization_id=org, event_id=event_id)
    patrocinadores = await _contar(session, Sponsor, organization_id=org, event_id=event_id)

    acepta_pagos = evento.registration_mode == "paid"

    def pieza(clave: str, cantidad: int, *, aplica: bool) -> PiezaOut:
        if not aplica:
            return PiezaOut(clave=clave, estado="no_aplica", cantidad=cantidad)
        return PiezaOut(
            clave=clave, estado="lista" if cantidad > 0 else "pendiente", cantidad=cantidad
        )

    return [
        pieza("agenda", sesiones, aplica=True),
        pieza("sedes", sedes, aplica=True),
        pieza("tipos_de_entrada", tipos_de_entrada, aplica=acepta_pagos),
        pieza("descuentos", descuentos, aplica=acepta_pagos),
        pieza("patrocinadores", patrocinadores, aplica=True),
    ]


async def _gasto_ejecutado_cents(
    session: AsyncSession, organization_id: uuid.UUID, event_id: uuid.UUID
) -> int:
    """Suma de todos los gastos del evento, en metálico y en especie.

    La comparación contra el presupuesto se hace sobre esta cifra total: el
    desglose «metálico / en especie» es para el panel de contabilidad, que ya lo
    tiene. Aquí solo interesa cuánto se ha ejecutado del presupuesto.
    """
    total = await session.scalar(
        select(func.coalesce(func.sum(AccountingExpense.total_cents), 0)).where(
            AccountingExpense.organization_id == organization_id,
            AccountingExpense.event_id == event_id,
        )
    )
    return int(total or 0)


async def _dinero(session: AsyncSession, evento: Event) -> DineroOut:
    """Ingresos y presupuesto, reutilizando las sumas de contabilidad.

    `listar_ingresos` ya excluye las monedas ajenas al evento y no suma euros con
    dólares, así que se usa su total en vez de reimplementar la consulta.
    """
    vista = await accounting_repository.listar_ingresos(
        session,
        organization_id=evento.organization_id,
        event_id=evento.id,
        moneda_evento=evento.accounting_currency,
    )
    presupuesto = await accounting_repository.sum_budgeted_cents(
        session, evento.organization_id, evento.id
    )
    ejecutado = await _gasto_ejecutado_cents(session, evento.organization_id, evento.id)
    return DineroOut(
        ingresos_cobrados_cents=vista.total_ingresos_cents,
        presupuesto_cents=presupuesto,
        ejecutado_cents=ejecutado,
        moneda=evento.accounting_currency,
    )


async def metricas_del_evento(
    session: AsyncSession, evento: Event, permisos: set[Permission]
) -> MetricasDelEventoOut:
    """Compone la vista, omitiendo los bloques para los que falta permiso."""
    puede_inscripciones = Permission.REGISTRATIONS_READ in permisos
    puede_dinero = Permission.ACCOUNTING_READ in permisos or Permission.PAYMENTS_READ in permisos

    embudo: EmbudoOut | None = None
    cifras: CifrasOut | None = None
    if puede_inscripciones:
        embudo = await _embudo(session, evento)
        cifras = await _cifras(session, evento)

    dinero = await _dinero(session, evento) if puede_dinero else None

    return MetricasDelEventoOut(
        event_id=str(evento.id),
        embudo=embudo,
        ocupacion=await _ocupacion(session, evento),
        cifras=cifras,
        piezas=await _piezas(session, evento),
        dinero=dinero,
    )
