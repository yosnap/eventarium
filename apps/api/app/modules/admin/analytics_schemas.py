"""Esquemas de analítica externa de la plataforma (fase 1 del plan
`260916-2246-cookies-analitica-externa`)."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

UMBRAL_DE_SUPRESION = 5
"""Celdas de agregado con menos de este conteo se devuelven con `total: null`
(hallazgo red-team #1: aunque el agregado sea semanal, un «1» exacto en una
semana de tráfico bajo se cruza con contexto externo para reidentificar una
visita, contradiciendo el diseño anónimo de `CookieConsent`)."""


class AnalyticsSettingsResponse(BaseModel):
    """Los identificadores semi-públicos de los proveedores de analítica.

    Ninguno es un secreto (viajan en el HTML público por diseño de cada
    proveedor) — ver `PlatformAnalyticsSettings`.
    """

    ga4_measurement_id: str | None
    meta_pixel_id: str | None
    cloudflare_analytics_token: str | None


class AnalyticsSettingsUpdate(BaseModel):
    """Reemplazo completo de los identificadores: un `PUT` envía los tres
    valores (cada uno puede ser `null` para dejar el proveedor sin usar)."""

    ga4_measurement_id: str | None = Field(default=None, max_length=100)
    meta_pixel_id: str | None = Field(default=None, max_length=100)
    cloudflare_analytics_token: str | None = Field(default=None, max_length=100)


class CeldaDeConsentimientos(BaseModel):
    """Una celda del agregado semanal: semana (lunes), categoría y total.

    `total: null` significa «celda suprimida por debajo del umbral», no cero —
    el cero real sí se muestra (cero visits no identifica a nadie).
    """

    semana: date
    categoria: str
    total: int | None


class ConsentimientosStatsResponse(BaseModel):
    """Agregado semanal de consentimientos por categoría. Nunca incluye un
    identificador de visita ni una fila individual: solo celdas semana×categoría."""

    celdas: list[CeldaDeConsentimientos]
