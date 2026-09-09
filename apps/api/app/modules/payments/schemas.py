"""Schemas Pydantic de pagos (fase 6 del PRD, fase 2 de trabajo).

Solo la conexión Stripe por ahora: las fases 3-5 amplían este fichero con sus
propias secciones (tipos de entrada, códigos de descuento, pagos,
reembolsos), cada una añadida por su propia fase de trabajo.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class StripeOnboardingResponse(BaseModel):
    """URL de un solo uso del `AccountLink`. Nunca se persiste ni se cachea."""

    onboarding_url: str


class StripeAccountResponse(BaseModel):
    """Estado persistido de la cuenta Stripe de la organización.

    `connected` distingue «hay una fila activa» (aunque `charges_enabled`
    todavía sea `False`, p. ej. durante el KYC) de «no hay ninguna cuenta o
    la única que hubo está desautorizada» — en ese segundo caso el resto de
    campos no tiene sentido y el frontend ofrece directamente el botón de
    conectar.
    """

    connected: bool
    charges_enabled: bool
    payouts_enabled: bool
    details_submitted: bool
    connected_at: datetime | None
    deauthorized_at: datetime | None
    last_synced_at: datetime | None


def estado_no_conectado() -> StripeAccountResponse:
    return StripeAccountResponse(
        connected=False,
        charges_enabled=False,
        payouts_enabled=False,
        details_submitted=False,
        connected_at=None,
        deauthorized_at=None,
        last_synced_at=None,
    )
