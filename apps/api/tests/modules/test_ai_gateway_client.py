"""`ai_gateway.completar`: reserva, llamada y liquidación (fase 2).

Ningún test de este módulo usa una clave real ni sale a Internet: el
transporte HTTP de LiteLLM lo sustituye `proveedor_simulado` y la resolución
DNS de la validación SSRF la sustituye `dns_publico` (ver
`tests/ai_gateway_test_helpers.py`).
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import traceback
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select

from app.core.database import SessionApp, SessionMaintenance, set_organization_context
from app.modules.ai_gateway import client as ai_client
from app.modules.ai_gateway import errores, litellm_runtime, repository
from app.modules.ai_gateway.errores import (
    ErrorDeProveedor,
    LimiteDeGastoSuperado,
    ServicioDesactivado,
    SinConfiguracion,
)
from app.modules.ai_gateway.models import AiUsageRecord, OrganizationService
from tests.ai_gateway_test_helpers import (
    CLAVE_DE_PROVEEDOR,
    ProveedorSimulado,
    configurar_organizacion,
    configurar_plataforma,
    respuesta_de_chat,
)
from tests.conftest import OrganizacionDePrueba

MENSAJES = [{"role": "user", "content": "extrae los datos de esta factura"}]


async def _usos(organizacion: OrganizacionDePrueba) -> list[AiUsageRecord]:
    """Filas de uso de una organización, leídas con su propio contexto RLS."""
    async with SessionApp() as session, session.begin():
        await set_organization_context(session, organizacion.id)
        filas = await session.scalars(
            select(AiUsageRecord).order_by(AiUsageRecord.created_at, AiUsageRecord.id)
        )
        return list(filas)


async def _completar(organizacion: OrganizacionDePrueba, **extra: object) -> ai_client.Resultado:
    return await ai_client.completar(
        organization_id=organizacion.id,
        use_case="accounting_ocr",
        messages=MENSAJES,
        **extra,  # type: ignore[arg-type]
    )


# --- Comprobaciones previas: nunca se sale a la red ---------------------------


async def test_sin_configuracion_no_llama_al_proveedor(
    organizacion: OrganizacionDePrueba,
    cifrado: str,
    proveedor_simulado: ProveedorSimulado,
    dns_publico: None,
) -> None:
    """Ni la organización ni la plataforma tienen credenciales: error de
    dominio explícito, nunca un 500 ni una llamada de red."""
    with pytest.raises(SinConfiguracion):
        await _completar(organizacion)

    assert proveedor_simulado.peticiones == []
    assert await _usos(organizacion) == []


async def test_sin_configuracion_no_usa_la_clave_del_entorno(
    organizacion: OrganizacionDePrueba,
    cifrado: str,
    proveedor_simulado: ProveedorSimulado,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Con `OPENAI_API_KEY` en el entorno, la organización sin configurar
    sigue fallando: cada llamada pasa su clave explícita y LiteLLM no tiene
    ninguna clave global (Predict #14)."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-de-entorno-no-debe-usarse")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-de-entorno-no-debe-usarse")

    with pytest.raises(SinConfiguracion):
        await _completar(organizacion)

    assert proveedor_simulado.peticiones == []
    assert ai_client._litellm().api_key is None
    assert ai_client._litellm().telemetry is False


async def test_servicio_desactivado_corta_antes_de_resolver_credenciales(
    organizacion: OrganizacionDePrueba,
    cifrado: str,
    proveedor_simulado: ProveedorSimulado,
    dns_publico: None,
) -> None:
    """El interruptor se mira antes que la configuración: con el servicio
    apagado no se descifra ninguna clave ni se sale a la red."""
    await configurar_plataforma()
    async with SessionMaintenance() as session:
        session.add(
            OrganizationService(organization_id=organizacion.id, service_key="ai", enabled=False)
        )
        await session.commit()

    with pytest.raises(ServicioDesactivado):
        await _completar(organizacion)

    assert proveedor_simulado.peticiones == []
    assert await _usos(organizacion) == []


# --- Camino feliz y liquidación -----------------------------------------------


async def test_llamada_heredada_liquida_la_fila_de_la_organizacion(
    organizacion: OrganizacionDePrueba,
    cifrado: str,
    proveedor_simulado: ProveedorSimulado,
    dns_publico: None,
) -> None:
    """El caso del worker de taskiq: sin petición HTTP, con la configuración
    heredada de plataforma, resuelta en la misma `SessionApp` y escrita en la
    fila de la organización correcta (regresión de V-3/V-4 y B-10)."""
    await configurar_plataforma()

    resultado = await _completar(organizacion)

    assert resultado.contenido == "respuesta simulada"
    assert resultado.provider == "nan_builders"
    assert resultado.model == "deepseek-v4-flash"
    assert resultado.input_tokens == 10
    assert resultado.output_tokens == 3

    filas = await _usos(organizacion)
    assert len(filas) == 1
    assert filas[0].organization_id == organizacion.id
    assert filas[0].status == "liquidado"
    assert filas[0].use_case == "accounting_ocr"
    assert filas[0].error_code is None
    assert filas[0].latency_ms is not None


async def test_modelo_sin_precio_conserva_la_estimacion_y_no_es_auditable(
    organizacion: OrganizacionDePrueba,
    cifrado: str,
    proveedor_simulado: ProveedorSimulado,
    dns_publico: None,
) -> None:
    """`nan_builders`/`deepseek-v4-flash` está fuera del mapa de precios de
    LiteLLM: la liquidación conserva la estimación de la reserva y marca el
    importe como no auditable. Nunca `0` y nunca `NULL`."""
    await configurar_plataforma(provider="nan_builders", default_model="deepseek-v4-flash")

    resultado = await _completar(organizacion)

    assert resultado.cost_auditable is False
    assert resultado.cost_usd == ai_client.COSTE_DE_SEGURIDAD_USD
    fila = (await _usos(organizacion))[0]
    assert fila.cost_usd == ai_client.COSTE_DE_SEGURIDAD_USD
    assert fila.cost_auditable is False


async def test_modelo_con_precio_liquida_el_coste_real(
    organizacion: OrganizacionDePrueba,
    cifrado: str,
    proveedor_simulado: ProveedorSimulado,
    dns_publico: None,
) -> None:
    """Con OpenRouter el coste sí está en el mapa de LiteLLM: el importe es
    real, auditable y distinto de la estimación.

    El modelo es uno de los que trae el mapa **local** del paquete, que es el
    que usa la instalación: el remoto no se descarga (ver
    `test_el_mapa_de_precios_de_litellm_no_se_descarga_de_internet`)."""
    await configurar_organizacion(
        organizacion.id, provider="openrouter", default_model="openai/gpt-4o"
    )
    proveedor_simulado.cuerpo = respuesta_de_chat(model="openai/gpt-4o")

    resultado = await _completar(organizacion)

    assert resultado.cost_auditable is True
    assert Decimal("0") < resultado.cost_usd < ai_client.COSTE_DE_SEGURIDAD_USD
    fila = (await _usos(organizacion))[0]
    assert fila.cost_auditable is True
    assert fila.cost_usd == resultado.cost_usd


async def test_la_reserva_escribe_siempre_un_coste_no_nulo(
    organizacion: OrganizacionDePrueba,
    cifrado: str,
    proveedor_simulado: ProveedorSimulado,
    dns_publico: None,
) -> None:
    """La fila `reservado` existe con importe **antes** de salir a la red: si
    fuera nula no contaría para el límite y este quedaría ciego (V-1)."""
    await configurar_plataforma()
    proveedor_simulado.retardo_s = 0.3

    tarea = asyncio.create_task(_completar(organizacion))
    await asyncio.sleep(0.12)
    en_vuelo = await _usos(organizacion)
    assert len(en_vuelo) == 1
    assert en_vuelo[0].status == "reservado"
    assert en_vuelo[0].cost_usd > Decimal("0")
    await tarea


# --- Límite de gasto -----------------------------------------------------------


async def test_limite_superado_rechaza_sin_llamar_al_proveedor(
    organizacion: OrganizacionDePrueba,
    cifrado: str,
    proveedor_simulado: ProveedorSimulado,
    dns_publico: None,
) -> None:
    await configurar_plataforma(techo_usd=Decimal("0.06"))

    await _completar(organizacion)
    llamadas = len(proveedor_simulado.peticiones)
    with pytest.raises(LimiteDeGastoSuperado):
        await _completar(organizacion)

    assert len(proveedor_simulado.peticiones) == llamadas


async def test_el_rechazo_por_limite_queda_en_el_historico(
    organizacion: OrganizacionDePrueba,
    cifrado: str,
    proveedor_simulado: ProveedorSimulado,
    dns_publico: None,
) -> None:
    """«Límite agotado» es lo único de la taxonomía que el organizador
    necesita entender, así que deja fila como cualquier otro fallo: sin ella
    el panel (fase 3) no podría enseñar por qué dejó de funcionar.

    La fila guarda lo que se habría gastado y, por ser `fallido`, no suma al
    gasto del periodo.
    """
    await configurar_plataforma(techo_usd=Decimal("0.06"))

    await _completar(organizacion)
    with pytest.raises(LimiteDeGastoSuperado):
        await _completar(organizacion)

    filas = await _usos(organizacion)
    assert len(filas) == 2
    rechazo = filas[-1]
    assert rechazo.status == "fallido"
    assert rechazo.error_code == errores.LIMITE_SUPERADO
    assert rechazo.use_case == "accounting_ocr"
    assert rechazo.provider == "nan_builders"
    assert rechazo.model == "deepseek-v4-flash"
    assert rechazo.cost_usd == ai_client.COSTE_DE_SEGURIDAD_USD
    assert rechazo.cost_auditable is False

    async with SessionApp() as session, session.begin():
        await set_organization_context(session, organizacion.id)
        gasto = await repository.gasto_del_periodo(
            session, organizacion.id, repository.periodo_actual()
        )
        recientes = await repository.ultimos_errores(session, organizacion.id, limite=5)
    # Solo cuenta la llamada que sí se hizo: el rechazo no gasta.
    assert gasto == ai_client.COSTE_DE_SEGURIDAD_USD
    assert [e.error_code for e in recientes] == [errores.LIMITE_SUPERADO]


async def test_el_limite_de_la_organizacion_manda_sobre_el_techo_mayor(
    organizacion: OrganizacionDePrueba,
    cifrado: str,
    proveedor_simulado: ProveedorSimulado,
    dns_publico: None,
) -> None:
    """El efectivo es el mínimo de los dos: con techo alto y límite propio
    bajo, corta el propio."""
    await configurar_plataforma(techo_usd=Decimal("100"))
    await configurar_organizacion(
        organizacion.id,
        provider="nan_builders",
        default_model="deepseek-v4-flash",
        limite_usd=Decimal("0.06"),
    )

    await _completar(organizacion)
    with pytest.raises(LimiteDeGastoSuperado):
        await _completar(organizacion)


async def test_dos_llamadas_concurrentes_cerca_del_limite_solo_pasa_una(
    organizacion: OrganizacionDePrueba,
    cifrado: str,
    proveedor_simulado: ProveedorSimulado,
    dns_publico: None,
) -> None:
    """Regresión de V-1: la organización **hereda** de plataforma y no tiene
    fila propia que bloquear, así que el mutex va sobre `ai_usage_periods`.
    Sin él, las dos llamadas leerían el mismo gasto acumulado (cero) y las
    dos pasarían el límite."""
    await configurar_plataforma(techo_usd=Decimal("0.06"))
    proveedor_simulado.retardo_s = 0.2

    resultados = await asyncio.gather(
        _completar(organizacion), _completar(organizacion), return_exceptions=True
    )

    rechazadas = [r for r in resultados if isinstance(r, LimiteDeGastoSuperado)]
    aceptadas = [r for r in resultados if isinstance(r, ai_client.Resultado)]
    assert len(aceptadas) == 1
    assert len(rechazadas) == 1
    assert len(proveedor_simulado.peticiones) == 1


async def test_dos_reservas_concurrentes_suman_las_dos(
    organizacion: OrganizacionDePrueba,
    cifrado: str,
    proveedor_simulado: ProveedorSimulado,
    dns_publico: None,
) -> None:
    """Sin límite, las dos pasan y el gasto del periodo es la suma: la
    segunda reserva no pisa a la primera."""
    await configurar_plataforma()

    await asyncio.gather(_completar(organizacion), _completar(organizacion))

    periodo = repository.periodo_actual()
    async with SessionApp() as session, session.begin():
        await set_organization_context(session, organizacion.id)
        gasto = await repository.gasto_del_periodo(session, organizacion.id, periodo)
    assert gasto == ai_client.COSTE_DE_SEGURIDAD_USD * 2


async def test_el_bloqueo_no_se_retiene_durante_la_llamada_de_red(
    organizacion: OrganizacionDePrueba,
    cifrado: str,
    proveedor_simulado: ProveedorSimulado,
    dns_publico: None,
) -> None:
    """Dos llamadas de la misma organización se solapan en la red.

    Si el `FOR UPDATE` se retuviera durante la llamada al proveedor, las dos
    irían en serie y el total rondaría los 0,8 s. Se comprueba que el tiempo
    total está mucho más cerca de una sola llamada que de dos encadenadas.
    """
    await configurar_plataforma()
    proveedor_simulado.retardo_s = 0.4

    arranque = time.monotonic()
    await asyncio.gather(_completar(organizacion), _completar(organizacion))
    transcurrido = time.monotonic() - arranque

    assert transcurrido < 0.7, f"las llamadas se serializaron ({transcurrido:.2f}s)"


# --- Fallos del proveedor ------------------------------------------------------


async def test_clave_rechazada_marca_la_fila_y_no_filtra_la_clave_en_los_logs(
    organizacion: OrganizacionDePrueba,
    cifrado: str,
    proveedor_simulado: ProveedorSimulado,
    dns_publico: None,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Criterio de la fase: tras forzar un error del proveedor, buscar el
    literal de la clave en la salida de logs da cero resultados."""
    await configurar_plataforma()
    proveedor_simulado.estado = 401
    proveedor_simulado.cuerpo = {
        "error": {
            "message": f"invalid api key: {CLAVE_DE_PROVEEDOR}",
            "code": "invalid_api_key",
        }
    }

    with caplog.at_level(logging.DEBUG), pytest.raises(ErrorDeProveedor) as fallo:
        await _completar(organizacion)

    assert fallo.value.error_code == errores.CLAVE_RECHAZADA
    assert CLAVE_DE_PROVEEDOR not in caplog.text
    assert "***" in caplog.text

    fila = (await _usos(organizacion))[0]
    assert fila.status == "fallido"
    assert fila.error_code == errores.CLAVE_RECHAZADA


async def test_el_error_de_dominio_no_encadena_la_excepcion_cruda_del_proveedor(
    organizacion: OrganizacionDePrueba,
    cifrado: str,
    proveedor_simulado: ProveedorSimulado,
    dns_publico: None,
) -> None:
    """El saneado de este módulo protege su log, pero no la traza que pinte
    quien deje propagar el error (un worker de taskiq, por ejemplo): si la
    excepción de LiteLLM viajara como `__cause__`, esa traza imprimiría la
    clave. Por eso se lanza `from None`."""
    await configurar_plataforma()
    proveedor_simulado.estado = 401
    proveedor_simulado.cuerpo = {
        "error": {"message": f"invalid api key: {CLAVE_DE_PROVEEDOR}", "code": "invalid_api_key"}
    }

    with pytest.raises(ErrorDeProveedor) as fallo:
        await _completar(organizacion)

    assert fallo.value.__cause__ is None
    assert fallo.value.__suppress_context__ is True
    traza = "".join(traceback.format_exception(fallo.value))
    assert CLAVE_DE_PROVEEDOR not in traza


async def test_error_transitorio_del_proveedor_deja_la_fila_fallida(
    organizacion: OrganizacionDePrueba,
    cifrado: str,
    proveedor_simulado: ProveedorSimulado,
    dns_publico: None,
) -> None:
    """Un 500 del proveedor es `proveedor_error`, distinto de
    `limite_superado`: la fase 4 usa esa diferencia para decidir si reintenta."""
    await configurar_plataforma()
    proveedor_simulado.estado = 500
    proveedor_simulado.cuerpo = {"error": {"message": "upstream caído"}}

    with pytest.raises(ErrorDeProveedor) as fallo:
        await _completar(organizacion)

    assert fallo.value.error_code == errores.PROVEEDOR_ERROR
    fila = (await _usos(organizacion))[0]
    assert fila.status == "fallido"
    assert fila.error_code == errores.PROVEEDOR_ERROR
    # El gasto de una llamada fallida no cuenta para el límite.
    async with SessionApp() as session, session.begin():
        await set_organization_context(session, organizacion.id)
        gasto = await repository.gasto_del_periodo(
            session, organizacion.id, repository.periodo_actual()
        )
    assert gasto == Decimal("0")


async def test_api_base_hacia_la_red_interna_se_rechaza_al_usar(
    organizacion: OrganizacionDePrueba,
    cifrado: str,
    proveedor_simulado: ProveedorSimulado,
    dns_interno: None,
) -> None:
    """El `api_base` se revalida en cada llamada: si el host del proveedor
    pasa a resolver a una IP interna entre guardar y usar, no se llama."""
    await configurar_plataforma()

    with pytest.raises(ErrorDeProveedor) as fallo:
        await _completar(organizacion)

    assert fallo.value.error_code == errores.PROVEEDOR_ERROR
    assert proveedor_simulado.peticiones == []
    fila = (await _usos(organizacion))[0]
    assert fila.status == "fallido"


async def test_credencial_ilegible_no_se_confunde_con_un_fallo_del_proveedor(
    organizacion: OrganizacionDePrueba,
    cifrado: str,
    proveedor_simulado: ProveedorSimulado,
    dns_publico: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rotar la clave de cifrado sin re-cifrar deja la credencial ilegible:
    error propio, no `proveedor_error`, y sin salir a la red."""
    from cryptography.fernet import Fernet

    await configurar_plataforma()
    monkeypatch.setenv("AI_SETTINGS_ENCRYPTION_KEY", Fernet.generate_key().decode())
    from app.core.config import get_settings

    get_settings.cache_clear()

    with pytest.raises(errores.CredencialIlegible):
        await _completar(organizacion)

    assert proveedor_simulado.peticiones == []
    fila = (await _usos(organizacion))[0]
    assert fila.status == "fallido"
    assert fila.error_code == errores.CREDENCIAL_ILEGIBLE


# --- Aislamiento entre organizaciones -----------------------------------------


async def test_el_uso_de_una_organizacion_no_es_visible_desde_otra(
    organizacion: OrganizacionDePrueba,
    otra_organizacion: OrganizacionDePrueba,
    cifrado: str,
    proveedor_simulado: ProveedorSimulado,
    dns_publico: None,
) -> None:
    await configurar_plataforma()

    await _completar(organizacion)

    assert len(await _usos(organizacion)) == 1
    assert await _usos(otra_organizacion) == []


# --- Barrido de reservas colgadas ---------------------------------------------


async def test_el_barrido_cierra_las_reservas_abandonadas(
    organizacion: OrganizacionDePrueba,
    cifrado: str,
    proveedor_simulado: ProveedorSimulado,
    dns_publico: None,
) -> None:
    """Una reserva que nadie liquidó (el proceso murió entre la red y la
    liquidación) se cierra como `reserva_abandonada`: el gasto se cuenta como
    potencialmente consumido, nunca se ignora."""
    await configurar_plataforma()
    async with SessionApp() as session, session.begin():
        await set_organization_context(session, organizacion.id)
        periodo = repository.periodo_actual()
        await repository.asegurar_periodo(session, organizacion.id, periodo)
        fila = await repository.reservar_uso(
            session,
            organization_id=organizacion.id,
            periodo=periodo,
            use_case="accounting_ocr",
            provider="nan_builders",
            model="deepseek-v4-flash",
            coste_estimado_usd=Decimal("0.05"),
            limite_usd=None,
        )
        record_id = fila.id

    # Con `minutos=0` toda reserva ya existente está «colgada».
    cerradas = await ai_client.cerrar_reservas_abandonadas(minutos=0)

    assert cerradas == 1
    fila_cerrada = next(f for f in await _usos(organizacion) if f.id == record_id)
    assert fila_cerrada.status == "fallido"
    assert fila_cerrada.error_code == errores.RESERVA_ABANDONADA
    assert fila_cerrada.cost_usd == Decimal("0.05")


async def test_el_barrido_no_toca_una_llamada_en_vuelo(
    organizacion: OrganizacionDePrueba,
    cifrado: str,
    proveedor_simulado: ProveedorSimulado,
    dns_publico: None,
) -> None:
    """Con el plazo por defecto, una reserva recién creada no se cierra: el
    barrido solo rescata lo que lleva parado mucho más que un timeout."""
    await configurar_plataforma()
    proveedor_simulado.retardo_s = 0.3
    tarea = asyncio.create_task(_completar(organizacion))
    await asyncio.sleep(0.12)

    assert await ai_client.cerrar_reservas_abandonadas(minutos=30) == 0

    await tarea
    assert (await _usos(organizacion))[0].status == "liquidado"


# --- Carga de LiteLLM: ni red ni import bajo el bloqueo ------------------------


def test_el_mapa_de_precios_de_litellm_no_se_descarga_de_internet() -> None:
    """Al importarse, LiteLLM resuelve su mapa de precios con un `httpx.get`
    **síncrono** contra GitHub. Con `LITELLM_LOCAL_MODEL_COST_MAP` usa la
    copia que trae el paquete: ni salida a Internet en cada proceso (ni en
    cada ejecución de la suite) ni cinco segundos de timeout bloqueando el
    bucle de eventos.

    Se comprueba en la propia contabilidad de LiteLLM (`is_env_forced`), no
    solo en la variable de entorno: es la que dice de dónde salió el mapa que
    de verdad está cargado.
    """
    ai_client._litellm()
    from litellm.litellm_core_utils.get_model_cost_map import get_model_cost_map_source_info

    assert os.environ[litellm_runtime.VARIABLE_DE_MAPA_LOCAL] == "True"
    origen = get_model_cost_map_source_info()
    assert origen["is_env_forced"] is True
    assert origen["source"] == "local"


async def test_litellm_ya_esta_importado_cuando_se_toma_el_bloqueo(
    organizacion: OrganizacionDePrueba,
    cifrado: str,
    proveedor_simulado: ProveedorSimulado,
    dns_publico: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """El import de LiteLLM (más de un segundo, y síncrono) se paga antes de
    coger el mutex del periodo, nunca dentro: si `estimar_coste` fuera quien
    lo disparara, la primera llamada de cada proceso bloquearía el bucle de
    eventos con el `FOR UPDATE` de la organización retenido.
    """
    await configurar_plataforma()
    cargado_al_bloquear: list[bool] = []
    bloquear_real = repository.bloquear_periodo

    async def espiar_bloqueo(*args: Any, **kwargs: Any) -> None:
        cargado_al_bloquear.append(litellm_runtime.ya_cargado())
        await bloquear_real(*args, **kwargs)

    monkeypatch.setattr(repository, "bloquear_periodo", espiar_bloqueo)
    # Como si el proceso acabara de arrancar y nadie hubiera importado aún.
    monkeypatch.setattr(litellm_runtime, "_modulo", None)

    await _completar(organizacion)

    assert cargado_al_bloquear == [True]


# --- Estimación y mapeo (unidades puras) --------------------------------------


def test_modelo_de_litellm_usa_el_prefijo_del_catalogo() -> None:
    assert ai_client.modelo_de_litellm("nan_builders", "glm5.3") == "openai/glm5.3"
    assert ai_client.modelo_de_litellm("cheaper_inference", "gpt-5.4") == "openai/gpt-5.4"
    assert ai_client.modelo_de_litellm("openrouter", "openai/gpt-4o") == "openrouter/openai/gpt-4o"


def test_la_estimacion_nunca_es_cero() -> None:
    """Dentro y fuera del mapa de precios, la reserva siempre aparta algo."""
    fuera = ai_client.estimar_coste(
        model_litellm="openai/deepseek-v4-flash", messages=MENSAJES, max_tokens=None
    )
    dentro = ai_client.estimar_coste(
        model_litellm="openrouter/openai/gpt-4o", messages=MENSAJES, max_tokens=None
    )
    assert fuera == ai_client.COSTE_DE_SEGURIDAD_USD
    assert dentro > Decimal("0")


def test_un_coste_cero_de_litellm_no_degrada_la_reserva(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Si LiteLLM deja de lanzar para un modelo desconocido y devuelve
    `(0.0, 0.0)`, la reserva no puede caer al suelo de precisión: apartar una
    millonésima deja el límite tan ciego como no apartar nada. Ese caso es
    «no sé cuánto cuesta», que es el valor de seguridad."""
    litellm = ai_client._litellm()
    monkeypatch.setattr(litellm, "cost_per_token", lambda **_kwargs: (0.0, 0.0))

    estimado = ai_client.estimar_coste(
        model_litellm="openrouter/openai/gpt-4o", messages=MENSAJES, max_tokens=None
    )

    assert estimado == ai_client.COSTE_DE_SEGURIDAD_USD


def test_la_estimacion_ignora_el_base64_de_las_imagenes() -> None:
    """Contar la imagen como texto dispararía la reserva; el techo de salida
    ya la cubre."""
    con_imagen = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "extrae"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64," + "A" * 5000}},
            ],
        }
    ]
    assert ai_client._tokens_de_entrada_estimados(con_imagen) < 10


def test_clasificar_distingue_vision_de_payload_invalido() -> None:
    # Por `litellm_runtime` y no con un `import litellm` pelado: si este test
    # fuera el primero del proceso en cargar el paquete, un import sin la
    # variable de mapa local descargaría el mapa de precios de Internet.
    litellm_runtime.cargar()
    from litellm.exceptions import BadRequestError, ContextWindowExceededError

    sin_vision = BadRequestError(
        message="This model does not support image input", model="m", llm_provider="openai"
    )
    otro = BadRequestError(message="unknown parameter", model="m", llm_provider="openai")
    contexto = ContextWindowExceededError(
        message="context length exceeded", model="m", llm_provider="openai"
    )

    assert errores.clasificar(sin_vision) == errores.MODELO_SIN_VISION
    assert errores.clasificar(otro) == errores.PAYLOAD_INVALIDO
    assert errores.clasificar(contexto) == errores.PAYLOAD_INVALIDO
    assert errores.clasificar(RuntimeError("cualquier cosa")) == errores.PROVEEDOR_ERROR


def test_todos_los_codigos_clasificados_estan_en_la_taxonomia() -> None:
    litellm_runtime.cargar()
    from litellm.exceptions import APIConnectionError, AuthenticationError

    codigos = {
        errores.clasificar(AuthenticationError(message="no", llm_provider="openai", model="m")),
        errores.clasificar(APIConnectionError(message="no", llm_provider="openai", model="m")),
        errores.clasificar(errores.CredencialIlegible()),
    }
    assert codigos <= errores.CODIGOS_DE_ERROR


def test_la_respuesta_sin_coste_conserva_la_estimacion() -> None:
    """`response_cost` a `None` o a `0` no puede convertirse en un importe
    cero: escondería gasto real y dejaría el límite sin nada que sumar."""

    class _Respuesta:
        _hidden_params: dict[str, object] = {"response_cost": None}

    class _RespuestaCero:
        _hidden_params: dict[str, object] = {"response_cost": 0.0}

    estimado = Decimal("0.05")
    assert ai_client._coste_liquidado(_Respuesta(), estimado) == (estimado, False)
    assert ai_client._coste_liquidado(_RespuestaCero(), estimado) == (estimado, False)


def test_el_periodo_es_el_mes_natural_en_utc() -> None:
    from datetime import UTC, datetime

    assert repository.periodo_actual(datetime(2026, 9, 19, 23, 30, tzinfo=UTC)) == "2026-09"
    inicio, fin = repository.rango_del_periodo("2026-12")
    assert inicio == datetime(2026, 12, 1, tzinfo=UTC)
    assert fin == datetime(2027, 1, 1, tzinfo=UTC)


def test_la_respuesta_de_chat_de_prueba_no_lleva_claves() -> None:
    """Guardarraíl del propio banco de pruebas: la respuesta simulada no debe
    arrastrar ninguna credencial."""
    assert CLAVE_DE_PROVEEDOR not in str(respuesta_de_chat())
