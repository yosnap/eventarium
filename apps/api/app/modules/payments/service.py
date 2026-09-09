"""Servicios de conexión Stripe Connect (fase 6 del PRD, fase 2 de trabajo).

Onboarding, reconexión tras desautorización y sincronización de estado. Las
llamadas a Stripe pasan siempre por `stripe_client.py`, y el `acct_id` de
destino siempre por `repository.get_cuenta_activa` — nunca un valor recibido
del cliente.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import base_url_de_organizacion
from app.modules.payments import repository
from app.modules.payments import stripe_client as stripe_gateway
from app.modules.payments.models import OrganizationStripeAccount
from app.shared.errors import NotFoundError

# Ambas rutas vuelven al panel de conexión de Stripe. `refresh` distingue el
# caso «el enlace ha caducado» del retorno normal, aunque las dos disparan la
# misma sincronización manual en el frontend.
_RUTA_RETORNO = "/admin/stripe?onboarding=retorno"
_RUTA_REFRESCO = "/admin/stripe?onboarding=refresco"


async def iniciar_onboarding(session: AsyncSession, *, organization_id: uuid.UUID) -> str:
    """Devuelve la URL de un solo uso del `AccountLink`.

    Si no hay cuenta activa (nunca conectó, o su única fila está
    `deauthorized_at`), crea una cuenta **nueva** y la persiste antes de
    pedir el enlace. Si ya hay una activa, genera un enlace nuevo sobre la
    **misma** cuenta: nunca se crea una segunda cuenta activa para la misma
    organización (el índice único parcial de la fase 1 lo impediría de
    todos modos, pero la comprobación aquí evita el viaje de red innecesario
    a Stripe que terminaría en error).
    """
    cuenta = await repository.get_cuenta_activa(session, organization_id)
    if cuenta is None:
        idempotency_key = f"connect-account-{uuid.uuid4()}"
        creada = await stripe_gateway.crear_cuenta_conectada(idempotency_key=idempotency_key)
        cuenta = await repository.crear_cuenta(
            session,
            organization_id=organization_id,
            stripe_account_id=creada.stripe_account_id,
        )

    base = await base_url_de_organizacion(organization_id)
    return await stripe_gateway.crear_enlace_onboarding(
        cuenta,
        return_url=f"{base}{_RUTA_RETORNO}",
        refresh_url=f"{base}{_RUTA_REFRESCO}",
    )


async def obtener_estado(
    session: AsyncSession, *, organization_id: uuid.UUID
) -> OrganizationStripeAccount | None:
    """Estado persistido, sin llamar nunca a Stripe (decisión #13 del plan):
    `None` si la organización no tiene ninguna cuenta activa."""
    return await repository.get_cuenta_activa(session, organization_id)


async def sincronizar_estado(
    session: AsyncSession, *, organization_id: uuid.UUID
) -> OrganizationStripeAccount:
    """Consulta el `Account` real y refresca las banderas persistidas.

    Es la única operación de este servicio que hace una llamada de red a
    Stripe por petición — de ahí su límite de peticiones propio
    (`STRIPE_SYNC_POR_IP`, `router.py`).
    """
    cuenta = await repository.get_cuenta_activa(session, organization_id)
    if cuenta is None:
        raise NotFoundError("Esta organización no tiene ninguna cuenta de Stripe conectada.")

    estado = await stripe_gateway.consultar_cuenta(cuenta)
    return await repository.actualizar_estado(
        session,
        cuenta,
        charges_enabled=estado.charges_enabled,
        payouts_enabled=estado.payouts_enabled,
        details_submitted=estado.details_submitted,
        last_synced_at=datetime.now(UTC),
    )
