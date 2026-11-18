"""Un `null` explícito en un `PATCH` parcial dice qué campos no lo admiten."""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

from app.core.mensajes.validacion import mensaje_de_validacion
from app.modules.payments.schemas import DiscountCodeUpdate, TicketTypeUpdate
from app.modules.sponsors.schemas import SponsorTierUpdate, SponsorUpdate


@pytest.mark.parametrize(
    ("esquema", "datos", "campos"),
    [
        (SponsorTierUpdate, {"name": None, "display_order": None}, "name, display_order"),
        (SponsorUpdate, {"tier_id": None}, "tier_id"),
        (TicketTypeUpdate, {"price_cents": None, "is_active": None}, "price_cents, is_active"),
        (DiscountCodeUpdate, {"code": None}, "code"),
    ],
)
def test_el_mensaje_nombra_los_campos_enviados_a_null(
    esquema: type[BaseModel], datos: dict[str, object], campos: str
) -> None:
    with pytest.raises(ValidationError) as error:
        esquema.model_validate(datos)
    (detalle,) = error.value.errors()
    assert mensaje_de_validacion(dict(detalle)) == (
        f"Los campos {campos} no admiten «null» explícito: omítelos para no cambiarlos."
    )
