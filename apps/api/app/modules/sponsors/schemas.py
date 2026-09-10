"""Esquemas de niveles de patrocinio y patrocinadores.

`contribution_type` fuerza qué otro campo va relleno (Decisión de modelo:
`Sponsor.contribution_amount`/`contribution_description` son mutuamente
excluyentes según el tipo, ver `models.py:94-100`). Esa exclusividad se valida
aquí en el alta (`SponsorCreate`) y se revalida en el servicio para el `PATCH`
parcial, donde el esquema por sí solo no conoce los valores ya guardados.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

LogoSize = Literal["large", "medium", "small"]
ContributionType = Literal["monetaria", "en_especie"]


def _prohibir_null_explicito(instancia: BaseModel, campos: tuple[str, ...]) -> None:
    """Corta en seco un `null` explícito en un `PATCH` parcial para columnas
    `NOT NULL` en BD.

    Pydantic no distingue «campo omitido» de «campo enviado a `null`» por su
    tipo (`X | None = None`) — solo `model_fields_set` lo sabe. Sin esta
    comprobación, `{"name": null}` llegaba intacto hasta el `INSERT`/`UPDATE`
    y la BD lo rechazaba con un `IntegrityError` de `NOT NULL` que el
    servicio interpretaba erróneamente como conflicto de nombre duplicado
    (`UNIQUE(organization_id, name)`), o —en el caso de `tier_id`— ni
    siquiera llegaba a la BD porque `uuid.UUID(None)` explota antes con un
    `TypeError` no capturado (500 en vez de 422)."""
    enviados_a_null = [
        campo
        for campo in campos
        if campo in instancia.model_fields_set and getattr(instancia, campo) is None
    ]
    if enviados_a_null:
        raise ValueError(f"Los campos {', '.join(enviados_a_null)} no admiten «null» explícito.")


def validate_contribution(
    contribution_type: str, amount: Decimal | None, description: str | None
) -> None:
    """`monetaria` exige un importe positivo y ningún texto; `en_especie` exige un
    texto no vacío y ningún importe — nunca los dos a la vez, nunca ninguno."""
    if contribution_type == "monetaria":
        if amount is None or amount <= 0:
            raise ValueError("Una aportación monetaria exige un importe positivo.")
        if description:
            raise ValueError("Una aportación monetaria no lleva descripción.")
    elif contribution_type == "en_especie":
        if not description or not description.strip():
            raise ValueError("Una aportación en especie exige una descripción.")
        if amount is not None:
            raise ValueError("Una aportación en especie no lleva importe.")


class SponsorTierCreate(BaseModel):
    """Alta de un nivel de patrocinio."""

    name: Annotated[str, Field(min_length=1, max_length=120)]
    display_order: int = 0
    logo_size: LogoSize = "medium"
    benefits: Annotated[str, Field(max_length=4000)] | None = None


class SponsorTierUpdate(BaseModel):
    """Campos editables de un nivel de patrocinio. `display_order` es lo que
    reordena: el panel envía el nuevo valor de cada nivel afectado."""

    name: Annotated[str, Field(min_length=1, max_length=120)] | None = None
    display_order: int | None = None
    logo_size: LogoSize | None = None
    benefits: Annotated[str, Field(max_length=4000)] | None = None

    @model_validator(mode="after")
    def _validar_null_explicito(self) -> SponsorTierUpdate:
        _prohibir_null_explicito(self, ("name", "display_order", "logo_size"))
        return self


class SponsorTierResponse(BaseModel):
    """Nivel de patrocinio tal y como lo ve el panel."""

    id: str
    name: str
    display_order: int
    logo_size: LogoSize
    benefits: str | None


class SponsorCreate(BaseModel):
    """Alta de un patrocinador en un evento."""

    tier_id: str
    name: Annotated[str, Field(min_length=1, max_length=160)]
    website: Annotated[str, Field(max_length=300)] | None = None
    contribution_type: ContributionType
    contribution_amount: Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)] | None = (
        None
    )
    contribution_description: Annotated[str, Field(max_length=4000)] | None = None

    @model_validator(mode="after")
    def _validar_aportacion(self) -> SponsorCreate:
        try:
            validate_contribution(
                self.contribution_type, self.contribution_amount, self.contribution_description
            )
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        return self


class SponsorUpdate(BaseModel):
    """Campos editables de un patrocinador. Parcial: la exclusividad de la
    aportación se revalida en el servicio contra el estado ya guardado."""

    tier_id: str | None = None
    name: Annotated[str, Field(min_length=1, max_length=160)] | None = None
    website: Annotated[str, Field(max_length=300)] | None = None
    contribution_type: ContributionType | None = None
    contribution_amount: Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)] | None = (
        None
    )
    contribution_description: Annotated[str, Field(max_length=4000)] | None = None

    @model_validator(mode="after")
    def _validar_null_explicito(self) -> SponsorUpdate:
        _prohibir_null_explicito(self, ("tier_id", "name", "contribution_type"))
        return self


class SponsorResponse(BaseModel):
    """Patrocinador tal y como lo ve el panel del evento (incluye la aportación)."""

    id: str
    tier_id: str
    name: str
    logo_url: str | None
    website: str | None
    contribution_type: ContributionType
    contribution_amount: Decimal | None
    contribution_description: str | None


class PublicSponsor(BaseModel):
    """Patrocinador tal y como se muestra en la página pública del evento.

    Nunca lleva el importe de la aportación: el PRD no pide hacer pública la
    valoración económica de nadie (ver Fase 2 de trabajo del plan,
    Requirements). `contribution_description` sí se expone cuando la
    aportación es en especie — describe *qué* aporta, no cuánto vale."""

    id: str
    name: str
    logo_url: str | None
    website: str | None
    contribution_type: ContributionType
    contribution_description: str | None


class PublicSponsorTier(BaseModel):
    """Nivel de patrocinio con sus patrocinadores, para el bloque público."""

    name: str
    logo_size: LogoSize
    sponsors: list[PublicSponsor]


class PublicSponsorHistoryItem(BaseModel):
    """Otra edición en la que este mismo patrocinador (mismo nombre, misma
    organización) ha aparecido — derivado de los patrocinadores reales de
    otros eventos publicados, nunca de un importe inventado."""

    event_slug: str
    event_title: str
    starts_at: datetime
    tier_name: str


class PublicSponsorDetail(BaseModel):
    """Ficha pública de un patrocinador concreto."""

    id: str
    name: str
    logo_url: str | None
    website: str | None
    contribution_type: ContributionType
    contribution_description: str | None
    tier_name: str
    tier_benefits: str | None
    event_slug: str
    event_title: str
    history: list[PublicSponsorHistoryItem]
