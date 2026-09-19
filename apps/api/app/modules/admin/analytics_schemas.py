"""Esquemas de analítica externa de la plataforma (fase 1 del plan
`260916-2246-cookies-analitica-externa`)."""

from __future__ import annotations

from datetime import date
from typing import Literal, get_args

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
    gtm_container_id: str | None


class AnalyticsSettingsUpdate(BaseModel):
    """Reemplazo completo de los identificadores: un `PUT` envía los tres
    valores (cada uno puede ser `null` para dejar el proveedor sin usar)."""

    ga4_measurement_id: str | None = Field(default=None, max_length=100)
    meta_pixel_id: str | None = Field(default=None, max_length=100)
    cloudflare_analytics_token: str | None = Field(default=None, max_length=100)
    gtm_container_id: str | None = Field(default=None, max_length=100)


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


# --- Estadísticas de GA4 (fase 2) ------------------------------------------

DiasDeGa4 = Literal[7, 30]
"""Únicos rangos admitidos (hallazgo red-team #4: un `N` sin restringir
permitiría vaciar la caché variándolo en cada petición; con un enum el
número de claves posibles es finito)."""

DIAS_PERMITIDOS = get_args(DiasDeGa4)
"""Valores en runtime del enum anterior: el router valida el query param
contra ellos con un error de dominio (FastAPI entrega los query params como
`str` y no los coerciona contra un `Literal` de enteros)."""

EstadoGa4 = Literal[
    "datos",
    "no_configurado",
    "credencial_invalida",
    "cuota_agotada",
    "error_proveedor",
]


class Ga4StatsResponse(BaseModel):
    """Estadísticas de GA4 de los últimos `dias` días.

    `estado` es siempre explícito: el panel debe poder renderizarse sin
    estadísticas (credencial ausente, JSON de la cuenta de servicio
    corrupto, cuota agotada o la API de Google caída) — nunca un 500 ni un
    error genérico. Los cuatro estados sin datos llevan `detalle` fijo,
    construido en el código: **nunca** interpola el mensaje de la excepción
    de Google, que puede contener fragmentos de la credencial de entrada
    (hallazgo red-team #2). Con `estado == "datos"` las tres métricas van
    informadas; en el resto son `null`.
    """

    estado: EstadoGa4
    detalle: str | None = None
    usuarios_activos: int | None = None
    sesiones: int | None = None
    vistas_pagina: int | None = None
