"""Único fichero del proyecto que importa la API de Datos de GA4
(`google-analytics-data`), fase 2 del plan `260916-2246-cookies-analitica-externa`.

Contrato no negociable (hallazgos red-team #2 y #4, ya aplicados en el plan):

- La credencial de la cuenta de servicio llega por entorno
  (`GA4_SERVICE_ACCOUNT_JSON`: JSON inline o ruta a fichero) y **nunca** se
  guarda en base de datos. Si el parseo falla, ni los logs ni las respuestas
  contienen fragmentos del valor de entrada: todo mensaje es fijo y
  construido en este módulo — el texto de la excepción puede incluir parte
  del JSON.
- Todo fallo se traduce a un `Ga4StatsResponse` con `estado` explícito:
  la pantalla del panel debe poder renderizarse sin estadísticas, nunca
  recibir un 500 genérico.
- El resultado exitoso se cachea en **Redis** (compartido entre workers),
  no en memoria del proceso: la API de Google cobra cuota por llamada.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from google.analytics.data_v1beta import BetaAnalyticsDataAsyncClient
from google.analytics.data_v1beta.types import DateRange, Metric, RunReportRequest
from google.api_core.exceptions import (
    GoogleAPIError,
    NotFound,
    ResourceExhausted,
)
from google.oauth2 import service_account

from app.core.config import get_settings
from app.core.redis_client import get_redis
from app.modules.admin.analytics_schemas import DiasDeGa4, Ga4StatsResponse

logger = logging.getLogger(__name__)

_TIMEOUT_SEGUNDOS = 15
"""La pantalla es una consulta de panel, no un informe interactivo: si Google
no responde en ese margen, se muestra el estado de error."""

SCOPE_LECTURA = "https://www.googleapis.com/auth/analytics.readonly"
TTL_CACHE_SEGUNDOS = 3600
"""Una hora: el panel no necesita dato en vivo y la cuota diaria de la API
de Datos es corta (hallazgo red-team #4). Solo se cachea el estado `datos`;
los demás se reintentan en la siguiente petición."""

_CLAVE_CACHE = "ga4_stats:{dias}"

_SIN_CREDENCIAL = (
    "No hay credencial de la cuenta de servicio de Google configurada "
    "(GA4_SERVICE_ACCOUNT_JSON)."
)
_SIN_PROPERTY = "No hay property ID de GA4 configurado (GA4_PROPERTY_ID)."
_CREDENCIAL_ILEGIBLE = (
    "La credencial de la cuenta de servicio de Google no se ha podido cargar. "
    "Revisa GA4_SERVICE_ACCOUNT_JSON."
)
_CUOTA_AGOTADA = "Se ha agotado la cuota de la API de Datos de GA4. Inténtalo de nuevo más tarde."
_PROPERTY_INUTIL = "El property ID de GA4 no existe o la cuenta de servicio no tiene acceso a él."
_API_FALLIDA = "La API de Datos de GA4 no ha respondido. Inténtalo de nuevo más tarde."

_cliente: BetaAnalyticsDataAsyncClient | None = None


def _cargar_credenciales(json_o_ruta: str) -> service_account.Credentials | None:
    """Parsea el valor de `GA4_SERVICE_ACCOUNT_JSON`: JSON inline o ruta a
    fichero. Devuelve `None` —con el motivo solo en el log, sin detalles— si
    no es utilizable."""
    texto = json_o_ruta.strip()
    try:
        if texto.startswith("{"):
            informacion = json.loads(texto)
        else:
            informacion = json.loads(Path(texto).read_text(encoding="utf-8"))
        credenciales: service_account.Credentials = (
            service_account.Credentials.from_service_account_info(  # type: ignore[no-untyped-call]
                informacion, scopes=[SCOPE_LECTURA]
            )
        )
        return credenciales
    except Exception:
        # Deliberadamente sin el mensaje de la excepción: json.loads y la
        # carga de la cuenta de servicio pueden ecoar fragmentos del JSON de
        # entrada (hallazgo red-team #2).
        logger.warning(
            "GA4: la credencial de la cuenta de servicio no se ha podido "
            "cargar (JSON o ruta no válidos)."
        )
        return None


def _reservar_cliente(credenciales: service_account.Credentials) -> BetaAnalyticsDataAsyncClient:
    """Cliente único por proceso (canal gRPC reutilizado), como `get_redis`."""
    global _cliente
    if _cliente is None:
        _cliente = BetaAnalyticsDataAsyncClient(credentials=credenciales)
    return _cliente


def _de_fila(respuesta: Any, indice: int) -> int:
    """Convierte el valor de métrica `i` de la única fila del informe.

    Sin dimensiones, la API devuelve una fila como mucho; sin tráfico en el
    rango puede no devolver ninguna — eso es 0, no un error.
    """
    if not respuesta.rows:
        return 0
    bruto = respuesta.rows[0].metric_values[indice].value
    try:
        return int(bruto)
    except ValueError:
        return 0


async def _consultar(dias: DiasDeGa4) -> Ga4StatsResponse:
    settings = get_settings()

    if not settings.ga4_service_account_json:
        return Ga4StatsResponse(estado="no_configurado", detalle=_SIN_CREDENCIAL)
    if not settings.ga4_property_id:
        return Ga4StatsResponse(estado="no_configurado", detalle=_SIN_PROPERTY)

    credenciales = _cargar_credenciales(settings.ga4_service_account_json)
    if credenciales is None:
        return Ga4StatsResponse(estado="credencial_invalida", detalle=_CREDENCIAL_ILEGIBLE)

    cliente = _reservar_cliente(credenciales)
    try:
        respuesta = await cliente.run_report(
            request=RunReportRequest(
                property=f"properties/{settings.ga4_property_id}",
                metrics=[
                    Metric(name="activeUsers"),
                    Metric(name="sessions"),
                    Metric(name="screenPageViews"),
                ],
                date_ranges=[DateRange(start_date=f"{dias}daysAgo", end_date="today")],
            ),
            timeout=_TIMEOUT_SEGUNDOS,
        )
    except ResourceExhausted:
        logger.warning("GA4: cuota de la API de Datos agotada.")
        return Ga4StatsResponse(estado="cuota_agotada", detalle=_CUOTA_AGOTADA)
    except NotFound:
        # El detalle distingue este caso de un fallo genérico porque es el
        # único que depende de la configuración del despliegue, no de Google.
        logger.warning("GA4: la propiedad indicada no existe o la cuenta no tiene acceso.")
        return Ga4StatsResponse(estado="error_proveedor", detalle=_PROPERTY_INUTIL)
    except GoogleAPIError as error:
        logger.warning("GA4: error de la API de Datos (%s).", type(error).__name__)
        return Ga4StatsResponse(estado="error_proveedor", detalle=_API_FALLIDA)

    return Ga4StatsResponse(
        estado="datos",
        usuarios_activos=_de_fila(respuesta, 0),
        sesiones=_de_fila(respuesta, 1),
        vistas_pagina=_de_fila(respuesta, 2),
    )


async def estadisticas_ultimos_dias(dias: DiasDeGa4) -> Ga4StatsResponse:
    """Punto de entrada del endpoint: consulta (o caché) de GA4.

    Si Redis no responde se sigue sin caché: un panel de lectura no debe
    quedarse sin estadísticas por una dependencia de infraestructura; el
    coste puntual de una llamada extra a Google es asumible.
    """
    redis = get_redis()
    clave = _CLAVE_CACHE.format(dias=dias)
    try:
        en_cache = await redis.get(clave)
    except Exception:
        logger.warning("GA4: Redis no responde; se consulta la API sin caché.")
        en_cache = None
    if en_cache:
        return Ga4StatsResponse.model_validate_json(en_cache)

    resultado = await _consultar(dias)

    if resultado.estado == "datos":
        try:
            await redis.set(clave, resultado.model_dump_json(), ex=TTL_CACHE_SEGUNDOS)
        except Exception:
            logger.warning("GA4: no se ha podido guardar el resultado en la caché.")
    return resultado
