"""Acceso a datos de pagos con Stripe Connect.

`get_cuenta_activa` es el único resolutor del `acct_id` de una organización
(decisión #7 del plan de la fase 6): tanto el router (con contexto RLS) como
el webhook y las tareas de fondo (sobre `maintenance_session`, sin ese
contexto) pasan por aquí, nunca por un `acct_id` que llegue de fuera.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.payments.models import OrganizationStripeAccount


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
