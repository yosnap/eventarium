"""Endpoints de conexión Stripe Connect.

`/organizations/{organization_id}/stripe...`, no `/organizations/me/...`
(patrón de `organizations/router.py`/`sponsors/router.py`): el Success
Criteria de aislamiento exige que un organizador de la organización A reciba
404 al pedir el `{organization_id}` de B, así que el identificador tiene que
viajar en la ruta para poder probarlo. `_organizacion_propia` es quien cierra
ese hueco: nunca se confía en el `{organization_id}` de la URL por sí solo,
se exige que coincida con el de la sesión autenticada.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.config import get_settings
from app.core.deps import CurrentUserDep, DbDep, require_permission
from app.core.permissions import Permission
from app.core.ratelimit import STRIPE_SYNC_POR_IP, limit_per_ip
from app.modules.payments import service
from app.modules.payments.models import OrganizationStripeAccount
from app.modules.payments.schemas import (
    StripeAccountResponse,
    StripeOnboardingResponse,
    estado_no_conectado,
)
from app.shared.errors import NotFoundError, ServiceUnavailableError

router = APIRouter(prefix="/organizations/{organization_id}/stripe", tags=["pagos"])


def _organizacion_propia(organization_id: str, usuario: CurrentUserDep) -> uuid.UUID:
    """Exige que el `{organization_id}` de la ruta sea el de la sesión.

    Un usuario solo pertenece a una organización por sesión (`CurrentUser`,
    fijado por el `Host`), así que cualquier otro valor es, por definición,
    de otra organización: se responde 404 (no 403) para no confirmar ni
    siquiera que ese identificador exista.
    """
    try:
        id_de_la_ruta = uuid.UUID(organization_id)
    except ValueError as exc:
        raise NotFoundError("Esa organización no existe.") from exc
    if id_de_la_ruta != usuario.organization_id:
        raise NotFoundError("Esa organización no existe.")
    return id_de_la_ruta


OrganizationIdDep = Annotated[uuid.UUID, Depends(_organizacion_propia)]


def _exigir_pagos_habilitados() -> None:
    if not get_settings().payments_enabled:
        raise ServiceUnavailableError(
            "Los pagos no están configurados en esta instalación. Contacta con quien "
            "administra la plataforma."
        )


def _account_response(cuenta: OrganizationStripeAccount | None) -> StripeAccountResponse:
    if cuenta is None:
        return estado_no_conectado()
    return StripeAccountResponse(
        connected=True,
        charges_enabled=cuenta.charges_enabled,
        payouts_enabled=cuenta.payouts_enabled,
        details_submitted=cuenta.details_submitted,
        connected_at=cuenta.connected_at,
        deauthorized_at=cuenta.deauthorized_at,
        last_synced_at=cuenta.last_synced_at,
    )


@router.post(
    "/onboarding",
    summary="Iniciar (o reiniciar) el onboarding de Stripe Connect",
    description=(
        "Crea una cuenta Standard si no hay ninguna activa (o si la única fila está "
        "desautorizada) y devuelve la URL de un solo uso del Account Link. Nunca crea "
        "una segunda cuenta activa."
    ),
    response_model=StripeOnboardingResponse,
    dependencies=[
        require_permission(Permission.PAYMENTS_WRITE),
        Depends(_exigir_pagos_habilitados),
    ],
)
async def start_onboarding(
    organization_id: OrganizationIdDep, session: DbDep
) -> StripeOnboardingResponse:
    url = await service.iniciar_onboarding(session, organization_id=organization_id)
    return StripeOnboardingResponse(onboarding_url=url)


@router.get(
    "",
    summary="Estado persistido de la conexión con Stripe",
    description="Lee únicamente lo persistido: nunca llama a Stripe.",
    response_model=StripeAccountResponse,
    dependencies=[
        require_permission(Permission.PAYMENTS_READ),
        Depends(_exigir_pagos_habilitados),
    ],
)
async def get_stripe_status(
    organization_id: OrganizationIdDep, session: DbDep
) -> StripeAccountResponse:
    cuenta = await service.obtener_estado(session, organization_id=organization_id)
    return _account_response(cuenta)


@router.post(
    "/sync",
    summary="Sincronizar el estado con el `Account` real de Stripe",
    description=(
        "Única ruta del panel que provoca una llamada de red a Stripe por petición: "
        "el frontend la invoca al volver del onboarding y desde el botón manual."
    ),
    response_model=StripeAccountResponse,
    dependencies=[
        require_permission(Permission.PAYMENTS_WRITE),
        Depends(_exigir_pagos_habilitados),
        limit_per_ip("stripe-sync", STRIPE_SYNC_POR_IP),
    ],
)
async def sync_stripe_status(
    organization_id: OrganizationIdDep, session: DbDep
) -> StripeAccountResponse:
    cuenta = await service.sincronizar_estado(session, organization_id=organization_id)
    return _account_response(cuenta)
