"""Esquemas de entrada y salida de la configuración de IA (ambos niveles).

Dos reglas que no se negocian en estos esquemas:

- `api_key` es **write-only** (`SecretStr` + `writeOnly` en el JSON Schema) y
  **no existe** en ningún esquema de salida. Nadie, ni el admin que la
  guardó, puede volver a leerla: el `GET` expone `has_key`, la pista de los
  últimos caracteres y la fecha.
- `provider`/`default_model`/`service_key` viajan como cadenas, no como
  `Enum` de Pydantic, **a propósito**: el catálogo cerrado
  (`proveedores.py`, `servicios.py`) se publica igual en el `openapi.json`
  (`json_schema_extra={"enum": …}`, que es lo que consume el desplegable de
  la fase 3), pero la validación la hace el servicio para poder devolver un
  422 con su `code` de dominio (`proveedor_desconocido`,
  `modelo_desconocido`, `service_key_desconocido`) en vez del error genérico
  de Pydantic, que no distingue el motivo.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, SecretStr

from app.modules.ai_gateway.models import LONGITUD_API_BASE
from app.modules.ai_gateway.proveedores import (
    CLAVES_DE_PROVEEDOR,
    LONGITUD_MODELO,
    LONGITUD_PROVEEDOR,
)
from app.modules.ai_gateway.servicios import CLAVES_DE_SERVICIO, LONGITUD_SERVICE_KEY

#: Cota de los importes en USD: el máximo que cabe en `Numeric(14,6)`. Sin
#: ella, un importe mayor no lo rechazaría Pydantic sino `asyncpg`, con un
#: 500 en vez de un 422 sobre entrada no confiable (mismo criterio que
#: `accounting/schemas.py`).
IMPORTE_USD_MAXIMO = Decimal("99999999.999999")

ImporteUsd = Annotated[Decimal, Field(ge=Decimal("0"), le=IMPORTE_USD_MAXIMO, decimal_places=6)]

Proveedor = Annotated[
    str,
    Field(
        min_length=1,
        max_length=LONGITUD_PROVEEDOR,
        json_schema_extra={"enum": list(CLAVES_DE_PROVEEDOR)},
    ),
]
ModeloPorDefecto = Annotated[str, Field(min_length=1, max_length=LONGITUD_MODELO)]
ApiBase = Annotated[str, Field(min_length=1, max_length=LONGITUD_API_BASE)]
ServiceKey = Annotated[
    str,
    Field(
        min_length=1,
        max_length=LONGITUD_SERVICE_KEY,
        json_schema_extra={"enum": list(CLAVES_DE_SERVICIO)},
    ),
]
ClaveDeApi = Annotated[
    SecretStr,
    Field(min_length=8, max_length=400, json_schema_extra={"writeOnly": True}),
]

#: De dónde sale la configuración que usa una organización.
OrigenDeConfig = Literal["propia", "heredada", "sin_configuracion"]


class PlatformAiSettingsUpdate(BaseModel):
    """`PUT /admin/ai-settings`. Parcial: solo se toca lo enviado.

    Coherencia (la aplica el servicio, no el esquema, para poder dar el
    `code` exacto): enviar `provider` o `api_base` exige `api_key`, y enviar
    `api_key` exige `provider` y `default_model`.
    """

    provider: Proveedor | None = None
    default_model: ModeloPorDefecto | None = None
    api_base: ApiBase | None = None
    api_key: ClaveDeApi | None = None
    #: Techo de gasto mensual de la instalación. `null` explícito = sin techo.
    monthly_ceiling_usd: ImporteUsd | None = None


class OrganizationAiSettingsUpdate(BaseModel):
    """`PUT /organizations/me/ai-settings`.

    Mismas reglas de coherencia que el nivel plataforma, más la del techo:
    `monthly_limit_usd` no puede superar el `monthly_ceiling_usd` vigente.
    """

    provider: Proveedor | None = None
    default_model: ModeloPorDefecto | None = None
    api_base: ApiBase | None = None
    api_key: ClaveDeApi | None = None
    #: Límite propio. `null` explícito = sin límite propio.
    monthly_limit_usd: ImporteUsd | None = None


class PlatformAiSettingsOut(BaseModel):
    """Estado de la configuración de plataforma. Nunca lleva la clave."""

    provider: str | None
    default_model: str | None
    #: Base URL con la que se llamará de verdad (la del catálogo en los
    #: proveedores de `api_base` fijo). Informativa salvo en `custom`.
    api_base: str | None
    #: `true` solo en `custom`: el formulario únicamente pide `api_base` ahí.
    api_base_editable: bool
    has_key: bool
    #: Últimos caracteres de la clave **de plataforma**. Solo lo ve el admin.
    api_key_hint: str | None
    monthly_ceiling_usd: Decimal | None
    updated_at: datetime | None


class OrganizationAiSettingsOut(BaseModel):
    """Configuración efectiva que ve el organizador.

    `api_key_hint` es `null` cuando la configuración es **heredada** (V-11):
    la clave de plataforma es compartida por toda la instalación y enseñar
    sus últimos caracteres a cada tenant sería una fuga entre organizaciones.
    """

    origen: OrigenDeConfig
    provider: str | None
    default_model: str | None
    api_base: str | None
    api_base_editable: bool
    has_key: bool
    api_key_hint: str | None
    #: Límite propio de la organización (`null` = no ha fijado ninguno).
    monthly_limit_usd: Decimal | None
    #: Techo de la instalación, para que el panel sepa contra qué valida.
    monthly_ceiling_usd: Decimal | None
    #: El menor de los dos, con la semántica del `NULL` de la fase (V-6).
    limite_efectivo_usd: Decimal | None
    #: `false` si el admin apagó el servicio `ai` globalmente o para esta
    #: organización. El organizador no puede reactivarlo.
    servicio_ia_activo: bool
    updated_at: datetime | None


class ServiceOut(BaseModel):
    """Un interruptor global con su descripción del catálogo."""

    service_key: str
    etiqueta: str
    descripcion: str
    enabled: bool


class ServiceToggle(BaseModel):
    service_key: ServiceKey
    enabled: bool


class PlatformServicesUpdate(BaseModel):
    """`PUT /admin/services`: cambia uno o varios interruptores globales."""

    services: Annotated[list[ServiceToggle], Field(min_length=1, max_length=50)]


class OrganizationServiceOut(BaseModel):
    """Estado de un servicio para una organización concreta."""

    service_key: str
    etiqueta: str
    #: Estado del interruptor global.
    global_enabled: bool
    #: `true` si esta organización lo tiene forzado a apagado.
    overridden_off: bool
    #: `global_enabled AND NOT overridden_off`.
    enabled: bool


class OrganizationServicesUpdate(BaseModel):
    """`PUT /admin/organizations/{id}/services`.

    `enabled=false` fuerza el servicio a apagado para esa organización;
    `enabled=true` **no** lo enciende por encima de la decisión global: borra
    el override y vuelve a heredar (V-7).
    """

    services: Annotated[list[ServiceToggle], Field(min_length=1, max_length=50)]
