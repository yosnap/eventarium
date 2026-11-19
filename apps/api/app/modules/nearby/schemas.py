"""Esquemas de los sitios cercanos: panel y ficha pública."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, Field, model_validator

from app.core.mensajes import marcar

NearbyKind = Literal["hotel", "restaurant", "bar", "parking", "transport", "pharmacy", "other"]
_TELEFONO = r"^\+?[0-9 ().-]{6,20}$"
_WEB = r"^https?://"


def _sin_espacios(valor: str | None) -> str | None:
    return valor.strip() if isinstance(valor, str) else valor


class _Campos(BaseModel):
    custom_kind: Annotated[str, Field(min_length=1, max_length=40)] | None = None
    address: Annotated[str, Field(max_length=300)] | None = None
    # `max_length`: hasta 20 caracteres en total, como la columna (con el `+`).
    phone: Annotated[str, Field(max_length=20, pattern=_TELEFONO)] | None = None
    website: Annotated[str, Field(max_length=500, pattern=_WEB)] | None = None
    notes: Annotated[str, Field(max_length=300)] | None = None


class NearbyPlaceCreate(_Campos):
    kind: NearbyKind
    name: Annotated[str, BeforeValidator(_sin_espacios), Field(min_length=1, max_length=160)]

    @model_validator(mode="after")
    def _tipo_libre_solo_con_otro(self) -> NearbyPlaceCreate:
        if (self.kind == "other") != bool(self.custom_kind and self.custom_kind.strip()):
            raise ValueError("Indica el tipo con nombre libre solo cuando el tipo es «Otro».")
        return self


# `null` explícito en campos obligatorios de `NearbyPlaceUpdate`.
_NO_ADMITE_NULL: dict[str, str] = {
    "kind": marcar("`kind` no admite `null`."),
    "name": marcar("`name` no admite `null`."),
}


class NearbyPlaceUpdate(_Campos):
    kind: NearbyKind | None = None
    name: (
        Annotated[str, BeforeValidator(_sin_espacios), Field(min_length=1, max_length=160)] | None
    ) = None

    @model_validator(mode="after")
    def _sin_nulos_en_obligatorios(self) -> NearbyPlaceUpdate:
        for campo, mensaje in _NO_ADMITE_NULL.items():
            if campo in self.model_fields_set and getattr(self, campo) is None:
                raise ValueError(mensaje)  # mensaje marcado
        return self


class NearbyPlaceOrder(BaseModel):
    ids: list[str]


class NearbyPlaceResponse(BaseModel):
    id: str
    kind: NearbyKind
    custom_kind: str | None
    name: str
    address: str | None
    phone: str | None
    website: str | None
    notes: str | None
    display_order: int
    updated_at: datetime


class PublicNearbyPlace(BaseModel):
    """Lo que ve el público: sin auditoría ni orden interno."""

    kind: NearbyKind
    custom_kind: str | None
    name: str
    address: str | None
    phone: str | None
    website: str | None
    notes: str | None
