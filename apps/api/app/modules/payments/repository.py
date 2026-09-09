"""Acceso a datos de pagos con Stripe Connect.

`get_cuenta_activa` es el único resolutor del `acct_id` de una organización
(decisión #7 del plan de la fase 6): tanto el router (con contexto RLS) como
el webhook y las tareas de fondo (sobre `maintenance_session`, sin ese
contexto) pasan por aquí, nunca por un `acct_id` que llegue de fuera.

Fase 3 de trabajo: catálogos de tipos de entrada y códigos de descuento, con
sus dos recuentos derivados (`ESTADOS_CONSUMIBLES`) — nunca un contador
denormalizado, ver `models.py`. Las variantes `lock_*` aplican `SELECT ...
FOR UPDATE` y las consume la fase 4 de trabajo dentro de la transacción que
crea un pago, respetando el orden de bloqueo único del módulo documentado en
`service.py`.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.payments.models import (
    EventDiscountCode,
    EventPayment,
    EventTicketType,
    OrganizationStripeAccount,
)

# Estados de `event_payments` que cuentan como cupo/uso consumido: un pago
# `pending` todavía puede completarse y uno `expired` deja de contar sin que
# nadie lo decremente (hallazgo #19 del red-team de la fase 6).
ESTADOS_CONSUMIBLES = ("pending", "paid", "partially_refunded", "refunded")


async def get_cuenta_activa(
    session: AsyncSession, organization_id: uuid.UUID
) -> OrganizationStripeAccount | None:
    """La fila `deauthorized_at IS NULL` de la organización, o `None`.

    Una organización sin ninguna fila, o cuya única fila está
    `deauthorized_at`, se trata como «sin cuenta» — es lo que permite la
    reconexión sin intervención manual (hallazgo #17 del red-team).
    """
    resultado: OrganizationStripeAccount | None = await session.scalar(
        select(OrganizationStripeAccount).where(
            OrganizationStripeAccount.organization_id == organization_id,
            OrganizationStripeAccount.deauthorized_at.is_(None),
        )
    )
    return resultado


async def get_cuenta_por_stripe_account_id(
    session: AsyncSession, stripe_account_id: str
) -> OrganizationStripeAccount | None:
    """Resuelve una fila por `acct_...`, usada por el webhook para ubicar la
    organización a partir de `event.account` (decisión #9 del plan): la
    columna es única en toda la instalación, así que no hace falta acotar por
    `organization_id`, que es precisamente lo que todavía no se conoce en ese
    punto."""
    resultado: OrganizationStripeAccount | None = await session.scalar(
        select(OrganizationStripeAccount).where(
            OrganizationStripeAccount.stripe_account_id == stripe_account_id
        )
    )
    return resultado


async def crear_cuenta(
    session: AsyncSession, *, organization_id: uuid.UUID, stripe_account_id: str
) -> OrganizationStripeAccount:
    """Persiste la fila **antes** de pedir el `AccountLink` (mitigación del
    riesgo de la fase de trabajo: un `Account` creado en Stripe no es
    reversible desde la plataforma; si la persistencia fallara después de
    crear la cuenta, quedaría huérfana)."""
    cuenta = OrganizationStripeAccount(
        organization_id=organization_id, stripe_account_id=stripe_account_id
    )
    session.add(cuenta)
    await session.flush()
    return cuenta


async def actualizar_estado(
    session: AsyncSession,
    cuenta: OrganizationStripeAccount,
    *,
    charges_enabled: bool,
    payouts_enabled: bool,
    details_submitted: bool,
    last_synced_at: datetime,
) -> OrganizationStripeAccount:
    """Refresca las banderas tras consultar el `Account` real (sincronización
    manual o `account.updated` en la fase 4 de trabajo)."""
    cuenta.charges_enabled = charges_enabled
    cuenta.payouts_enabled = payouts_enabled
    cuenta.details_submitted = details_submitted
    cuenta.last_synced_at = last_synced_at
    if charges_enabled and cuenta.connected_at is None:
        cuenta.connected_at = last_synced_at
    await session.flush()
    return cuenta


async def marcar_desautorizada(
    session: AsyncSession, cuenta: OrganizationStripeAccount, *, momento: datetime
) -> OrganizationStripeAccount:
    """`account.application.deauthorized` (fase 4 de trabajo): la fila se
    conserva con su `deauthorized_at`, no se borra — sigue haciendo falta
    para reembolsar los pagos cobrados con esa cuenta."""
    cuenta.deauthorized_at = momento
    cuenta.charges_enabled = False
    cuenta.payouts_enabled = False
    await session.flush()
    return cuenta


# --- Tipos de entrada --------------------------------------------------------


async def get_ticket_types(
    session: AsyncSession, organization_id: uuid.UUID, event_id: uuid.UUID
) -> list[EventTicketType]:
    filas = await session.scalars(
        select(EventTicketType)
        .where(
            EventTicketType.organization_id == organization_id,
            EventTicketType.event_id == event_id,
        )
        .order_by(EventTicketType.sort_order, EventTicketType.created_at)
    )
    return list(filas)


async def get_ticket_type(
    session: AsyncSession,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    ticket_type_id: uuid.UUID,
) -> EventTicketType | None:
    resultado: EventTicketType | None = await session.scalar(
        select(EventTicketType).where(
            EventTicketType.id == ticket_type_id,
            EventTicketType.event_id == event_id,
            EventTicketType.organization_id == organization_id,
        )
    )
    return resultado


async def lock_ticket_type(
    session: AsyncSession, organization_id: uuid.UUID, ticket_type_id: uuid.UUID
) -> EventTicketType | None:
    """`SELECT ... FOR UPDATE` sobre un tipo de entrada.

    Contrato de bloqueo de la fase 3 de trabajo, consumido por la fase 4:
    orden único `event_registrations` → `events` → `event_ticket_types` →
    `event_discount_codes`, dentro de la misma transacción que crea el pago.
    """
    resultado: EventTicketType | None = await session.scalar(
        select(EventTicketType)
        .where(
            EventTicketType.id == ticket_type_id,
            EventTicketType.organization_id == organization_id,
        )
        .with_for_update()
    )
    return resultado


async def count_used_ticket_type(
    session: AsyncSession, organization_id: uuid.UUID, ticket_type_id: uuid.UUID
) -> int:
    """Cupo consumido de un tipo de entrada, **derivado** de `event_payments`
    (nunca un contador denormalizado, ver `models.py:EventTicketType`)."""
    total = await session.scalar(
        select(func.count())
        .select_from(EventPayment)
        .where(
            EventPayment.organization_id == organization_id,
            EventPayment.ticket_type_id == ticket_type_id,
            EventPayment.status.in_(ESTADOS_CONSUMIBLES),
        )
    )
    return int(total or 0)


async def ticket_type_has_dependencies(
    session: AsyncSession, organization_id: uuid.UUID, ticket_type_id: uuid.UUID
) -> bool:
    """`True` si el tipo tiene algún código de descuento o pago asociado —
    condición explícita antes del 409, además de la FK `RESTRICT` que actúa
    como red de seguridad si esta comprobación se saltara."""
    tiene_codigos = await session.scalar(
        select(EventDiscountCode.id)
        .where(
            EventDiscountCode.organization_id == organization_id,
            EventDiscountCode.ticket_type_id == ticket_type_id,
        )
        .limit(1)
    )
    if tiene_codigos is not None:
        return True
    tiene_pagos = await session.scalar(
        select(EventPayment.id)
        .where(
            EventPayment.organization_id == organization_id,
            EventPayment.ticket_type_id == ticket_type_id,
        )
        .limit(1)
    )
    return tiene_pagos is not None


async def create_ticket_type(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    datos: dict[str, object],
) -> EventTicketType:
    tipo = EventTicketType(organization_id=organization_id, event_id=event_id, **datos)
    session.add(tipo)
    await session.flush()
    return tipo


# --- Códigos de descuento -----------------------------------------------------


async def get_discount_codes(
    session: AsyncSession, organization_id: uuid.UUID, event_id: uuid.UUID
) -> list[EventDiscountCode]:
    filas = await session.scalars(
        select(EventDiscountCode)
        .where(
            EventDiscountCode.organization_id == organization_id,
            EventDiscountCode.event_id == event_id,
        )
        .order_by(EventDiscountCode.created_at)
    )
    return list(filas)


async def get_discount_code(
    session: AsyncSession,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    discount_code_id: uuid.UUID,
) -> EventDiscountCode | None:
    resultado: EventDiscountCode | None = await session.scalar(
        select(EventDiscountCode).where(
            EventDiscountCode.id == discount_code_id,
            EventDiscountCode.event_id == event_id,
            EventDiscountCode.organization_id == organization_id,
        )
    )
    return resultado


async def get_discount_code_by_code(
    session: AsyncSession, organization_id: uuid.UUID, event_id: uuid.UUID, code: str
) -> EventDiscountCode | None:
    """`code` ya debe llegar normalizado a mayúsculas: la comparación es exacta,
    nunca `ILIKE`, para no convertir el presupuesto en un oráculo de fuerza
    bruta más permisivo de lo que ya es."""
    resultado: EventDiscountCode | None = await session.scalar(
        select(EventDiscountCode).where(
            EventDiscountCode.organization_id == organization_id,
            EventDiscountCode.event_id == event_id,
            EventDiscountCode.code == code,
        )
    )
    return resultado


async def lock_discount_code(
    session: AsyncSession, organization_id: uuid.UUID, discount_code_id: uuid.UUID
) -> EventDiscountCode | None:
    """`SELECT ... FOR UPDATE` sobre un código de descuento, último eslabón del
    orden de bloqueo único del módulo (ver `lock_ticket_type`)."""
    resultado: EventDiscountCode | None = await session.scalar(
        select(EventDiscountCode)
        .where(
            EventDiscountCode.id == discount_code_id,
            EventDiscountCode.organization_id == organization_id,
        )
        .with_for_update()
    )
    return resultado


async def count_used_discount_code(
    session: AsyncSession, organization_id: uuid.UUID, discount_code_id: uuid.UUID
) -> int:
    """Uso consumido de un código, **derivado** de `event_payments` — sin
    columna `used_count` que respalde este número (hallazgo #19)."""
    total = await session.scalar(
        select(func.count())
        .select_from(EventPayment)
        .where(
            EventPayment.organization_id == organization_id,
            EventPayment.discount_code_id == discount_code_id,
            EventPayment.status.in_(ESTADOS_CONSUMIBLES),
        )
    )
    return int(total or 0)


async def discount_code_has_payments(
    session: AsyncSession, organization_id: uuid.UUID, discount_code_id: uuid.UUID
) -> bool:
    existe = await session.scalar(
        select(EventPayment.id)
        .where(
            EventPayment.organization_id == organization_id,
            EventPayment.discount_code_id == discount_code_id,
        )
        .limit(1)
    )
    return existe is not None


async def create_discount_code(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    datos: dict[str, object],
) -> EventDiscountCode:
    codigo = EventDiscountCode(organization_id=organization_id, event_id=event_id, **datos)
    session.add(codigo)
    await session.flush()
    return codigo
