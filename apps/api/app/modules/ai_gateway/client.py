"""Cliente de generación: la única forma de pedir una respuesta de IA.

Cualquier módulo del backend llama a `completar(...)` y no sabe nada más:
ni qué proveedor hay detrás, ni dónde está la clave, ni cómo se contabiliza
el gasto. Es también el **único** punto del proyecto donde existe el texto
plano de una clave de proveedor, y no sale de aquí: no se devuelve, no se
guarda y no se escribe en ningún log.

Secuencia, en tres tramos (rediseñada tras el red-team de la sesión 3):

1. **Transacción corta**: se crea y bloquea la fila de periodo, se comprueba
   el interruptor del servicio, se resuelve la configuración efectiva y se
   aparta («reserva») el coste estimado. `commit`, que suelta el bloqueo.
2. **Llamada de red, sin ningún bloqueo retenido.** Es la regla que ya
   aplica `payments/refunds_service.py`: retener un bloqueo de fila durante
   una llamada externa detendría a toda la organización durante segundos y
   convertiría un lote de N documentos en N llamadas en serie.
3. **Transacción corta**: se liquida la fila con el coste y los tokens
   reales, o se marca fallida con su `error_code`.

Si el proceso muere entre 2 y 3, la fila queda `reservado` con su coste
estimado —es decir, el gasto **sigue contando** para el límite— y
`sweep_stuck_ai_reservations_task` la cierra más tarde como
`reserva_abandonada`. El hueco se cierra por exceso de prudencia, nunca
dejando de contar gasto que pudo consumirse.

`resolver_config_efectiva` (fase 1) es la única fuente de verdad de qué
credenciales usa una llamada, la misma que pinta el panel: así lo que el
organizador ve y lo que de verdad se usa no pueden discrepar.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from decimal import ROUND_UP, Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import SessionApp, set_organization_context
from app.modules.ai_gateway import (
    errores,
    litellm_runtime,
    proveedores,
    repository,
    service,
    servicios,
)
from app.modules.ai_gateway.crypto import descifrar_clave
from app.modules.ai_gateway.errores import (
    ErrorDeProveedor,
    LimiteDeGastoSuperado,
    ServicioDesactivado,
    SinConfiguracion,
)
from app.modules.ai_gateway.service import ConfigEfectiva
from app.modules.ai_gateway.validacion import validar_api_base

if TYPE_CHECKING:  # pragma: no cover - solo para el comprobador de tipos
    from collections.abc import AsyncIterator
    from types import ModuleType

logger = logging.getLogger(__name__)

#: Techo de tokens de salida que asume la reserva cuando quien llama no fija
#: `max_tokens`. No limita la respuesta: solo sirve para estimar por arriba
#: lo que podría costar, que es lo que debe apartarse.
TOKENS_DE_SALIDA_ESTIMADOS = 1024

#: Caracteres por token de la estimación de entrada. Aproximación grosera y
#: deliberada: contar de verdad exigiría el tokenizador del modelo, que
#: LiteLLM descarga bajo demanda —una llamada de red dentro de la
#: transacción que sostiene el bloqueo, justo lo que esta fase evita—. Basta
#: con que el orden de magnitud sea correcto: el importe exacto lo escribe la
#: liquidación.
CARACTERES_POR_TOKEN = 4

#: Importe que aparta la reserva cuando el modelo no está en el mapa de
#: precios de LiteLLM (los dos gateways OpenAI-compatible y `custom`). Es un
#: valor de seguridad, no un coste medido: la fila queda con
#: `cost_auditable=False` y el panel avisa de que ese gasto no es auditable.
#: Cinco céntimos de dólar es caro para una extracción de una página y barato
#: para una conversación larga: apartar de más solo adelanta el momento de
#: tocar el límite, apartar de menos lo dejaría ciego.
COSTE_DE_SEGURIDAD_USD = Decimal("0.05")

#: Seis decimales, los mismos que la columna `Numeric(14, 6)`.
_PRECISION_USD = Decimal("0.000001")

#: Timeout por defecto de la llamada al proveedor, en segundos. Sin él,
#: LiteLLM espera hasta diez minutos y la reserva queda en vuelo todo ese
#: rato.
TIMEOUT_POR_DEFECTO_S = 120.0


def _litellm() -> ModuleType:
    """LiteLLM ya importado y configurado (ver `litellm_runtime`)."""
    return litellm_runtime.cargar()


async def _precalentar_litellm() -> None:
    """Paga el import de LiteLLM **fuera** de cualquier bloqueo de fila.

    El import cuesta más de un segundo y es síncrono: hacerlo dentro de la
    transacción que sostiene el `FOR UPDATE` del periodo bloquearía el bucle
    de eventos con el mutex de la organización cogido, justo lo que esta fase
    prohíbe. Así que se hace antes, en un hilo aparte, y para cuando
    `estimar_coste` lo necesite ya está cargado.
    """
    if litellm_runtime.ya_cargado():
        return
    await asyncio.to_thread(litellm_runtime.cargar)


@dataclass(frozen=True, slots=True, repr=False)
class ArgumentosDeLlamada:
    """Lo que se le pasa a `litellm.acompletion`, ya traducido del catálogo.

    Sin `repr`: lleva la clave en claro y un `repr` automático la volcaría en
    cualquier traza o mensaje de assert.
    """

    model: str
    api_key: str
    api_base: str | None


@dataclass(frozen=True, slots=True)
class Resultado:
    """Lo que devuelve `completar`. Nunca lleva la clave ni el objeto crudo."""

    contenido: str
    provider: str
    model: str
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: Decimal
    #: `False` si el importe es la estimación de la reserva, no un coste real.
    cost_auditable: bool
    latency_ms: int
    usage_record_id: uuid.UUID


def modelo_de_litellm(provider: str, model: str) -> str:
    """`(proveedor, modelo)` → el `model` que espera LiteLLM.

    El prefijo sale del catálogo (`proveedores.py`), nunca de una cadena
    literal escrita aquí: `nan_builders` y `cheaper_inference` enrutan por
    `openai/...` porque sus APIs son OpenAI-compatible, y si mañana cambia
    el enrutado de uno de ellos se cambia en el catálogo.
    """
    entrada = proveedores.obtener(provider)
    prefijo = entrada.prefijo_litellm if entrada is not None else "openai"
    return f"{prefijo}/{model}"


def _sanear(texto: str, clave: str) -> str:
    """Sustituye el literal de la clave por `***`.

    Se aplica a **todo** texto que venga del proveedor antes de tocar un log:
    los mensajes de error de algunas APIs OpenAI-compatible reproducen la
    petición recibida, cabeceras incluidas.
    """
    if not clave:
        return texto
    return texto.replace(clave, "***")


def _tokens_de_entrada_estimados(messages: list[dict[str, Any]]) -> int:
    caracteres = 0
    for mensaje in messages:
        contenido = mensaje.get("content")
        if isinstance(contenido, str):
            caracteres += len(contenido)
        elif isinstance(contenido, list):
            for parte in contenido:
                if isinstance(parte, dict):
                    # Las partes de imagen llevan la imagen entera en base64;
                    # contarla como texto dispararía la estimación. Se cuenta
                    # solo el texto, y la imagen la cubre el techo de salida.
                    texto = parte.get("text")
                    if isinstance(texto, str):
                        caracteres += len(texto)
    return max(1, caracteres // CARACTERES_POR_TOKEN)


def estimar_coste(
    *, model_litellm: str, messages: list[dict[str, Any]], max_tokens: int | None
) -> Decimal:
    """Cuánto aparta la reserva. **Nunca cero y nunca nulo.**

    Con el modelo en el mapa de precios de LiteLLM se estima por arriba
    (tokens de entrada aproximados + techo de salida). Fuera del mapa —los
    dos gateways OpenAI-compatible y `custom`— se aparta el valor de
    seguridad: la alternativa sería no contar nada, y entonces el límite de
    gasto no limitaría nada.
    """
    entrada = _tokens_de_entrada_estimados(messages)
    salida = max_tokens if max_tokens is not None else TOKENS_DE_SALIDA_ESTIMADOS
    try:
        coste_entrada, coste_salida = _litellm().cost_per_token(
            model=model_litellm, prompt_tokens=entrada, completion_tokens=salida
        )
    except Exception:  # noqa: BLE001 - LiteLLM lanza `Exception` pelada aquí
        return COSTE_DE_SEGURIDAD_USD
    bruto = Decimal(str(coste_entrada)) + Decimal(str(coste_salida))
    if bruto <= 0:
        # «Cero» aquí no significa gratis, significa que LiteLLM no sabe
        # calcularlo (algunas versiones devuelven `(0.0, 0.0)` para un modelo
        # desconocido en vez de lanzar). Apartar una millonésima dejaría el
        # límite tan ciego como no apartar nada, así que es el mismo caso que
        # el `except` de arriba: valor de seguridad.
        return COSTE_DE_SEGURIDAD_USD
    # El suelo de precisión solo evita que un coste real diminuto pero
    # legítimo se guarde como cero en una columna de seis decimales.
    return max(_a_usd(bruto), _PRECISION_USD)


def _a_usd(valor: Decimal) -> Decimal:
    """Redondea **hacia arriba** a los seis decimales de la columna.

    Hacia arriba y no al más cercano: en una reserva, redondear a la baja es
    regalar gasto que el límite deja de ver.
    """
    return valor.quantize(_PRECISION_USD, rounding=ROUND_UP)


@asynccontextmanager
async def _sesion_de_organizacion(organization_id: uuid.UUID) -> AsyncIterator[AsyncSession]:
    """Sesión propia con el rol `app_user` y el contexto RLS ya fijado.

    Propia y no la de la petición: `completar` necesita hacer `commit` a
    mitad de camino (soltar el bloqueo antes de la red) y la sesión de un
    `DbDep` envuelve toda la petición en una única transacción.

    `SessionApp` y **nunca** `maintenance_session()`: esta función la llaman
    también los workers de taskiq, que no tienen petición HTTP; como las
    tablas llevan `FORCE ROW LEVEL SECURITY`, la alternativa habría sido
    saltarse RLS con el rol de mantenimiento y escribir el uso de una
    organización sin ninguna red de seguridad que lo impidiera (Red-team
    B-10). `platform_ai_settings` tiene `GRANT SELECT` a `app_user`
    precisamente para que la configuración heredada se resuelva aquí, en la
    misma sesión (V-3/V-4).
    """
    async with SessionApp() as session:
        async with session.begin():
            await set_organization_context(session, organization_id)
            yield session


@dataclass(frozen=True, slots=True, repr=False)
class _Reserva:
    record_id: uuid.UUID
    config: ConfigEfectiva
    provider: str
    model: str
    coste_estimado_usd: Decimal


async def _reservar(
    *,
    organization_id: uuid.UUID,
    use_case: str,
    messages: list[dict[str, Any]],
    max_tokens: int | None,
    periodo: str,
) -> _Reserva:
    """Tramo 1: mutex, comprobaciones y reserva. Sale con el bloqueo soltado.

    El rechazo por límite se propaga **fuera** del `async with` a propósito:
    lanzarlo dentro haría que la transacción se deshiciera y con ella la fila
    `fallido`/`limite_superado` que deja constancia del intento. Se guarda,
    se cierra la transacción con normalidad y se lanza después.
    """
    rechazo: LimiteDeGastoSuperado | None = None
    async with _sesion_de_organizacion(organization_id) as tx:
        # (0) El mutex existe siempre, también para la organización que
        #     hereda la configuración de plataforma y no tiene fila propia.
        await repository.asegurar_periodo(tx, organization_id, periodo)
        await repository.bloquear_periodo(tx, organization_id, periodo)

        # (a) Interruptor del servicio, **antes** de tocar ninguna credencial:
        #     con el servicio apagado no se descifra ni se resuelve nada.
        if not await service.servicio_activo(tx, organization_id, servicios.SERVICIO_IA):
            raise ServicioDesactivado()

        # (b) Configuración efectiva: la misma función que pinta el panel.
        config = await service.resolver_config_efectiva(tx, organization_id)
        if not config.usable or config.provider is None or config.default_model is None:
            raise SinConfiguracion()

        # (c) y (d): estimación, límite efectivo y reserva, todo bajo el
        #     bloqueo que se suelta al salir del `async with`.
        model_litellm = modelo_de_litellm(config.provider, config.default_model)
        estimado = estimar_coste(
            model_litellm=model_litellm, messages=messages, max_tokens=max_tokens
        )
        try:
            fila = await repository.reservar_uso(
                tx,
                organization_id=organization_id,
                periodo=periodo,
                use_case=use_case,
                provider=config.provider,
                model=config.default_model,
                coste_estimado_usd=estimado,
                limite_usd=config.limite_efectivo_usd,
            )
        except LimiteDeGastoSuperado as limite:
            rechazo = limite
        else:
            return _Reserva(
                record_id=fila.id,
                config=config,
                provider=config.provider,
                model=config.default_model,
                coste_estimado_usd=estimado,
            )

    raise rechazo


def _argumentos(config: ConfigEfectiva) -> ArgumentosDeLlamada:
    """Traduce el catálogo a los argumentos de `litellm.acompletion`.

    Único punto que conoce esa correspondencia. `api_base` sale del catálogo
    en los proveedores de dirección fija (`nan_builders`,
    `cheaper_inference`) y es `None` en los que LiteLLM ya sabe enrutar
    (`openrouter`, `anthropic`, `openai`, `gemini`); solo `custom` usa el que
    escribió quien configuró.
    """
    if config.provider is None or config.default_model is None or config.api_key_encrypted is None:
        raise SinConfiguracion()
    return ArgumentosDeLlamada(
        model=modelo_de_litellm(config.provider, config.default_model),
        api_key=descifrar_clave(config.api_key_encrypted),
        api_base=config.api_base,
    )


async def _validar_destino(api_base: str | None) -> None:
    """Revalida el `api_base` justo antes de usarlo.

    Se revalida aunque la dirección venga del catálogo y no del usuario: el
    coste es despreciable y protege de un secuestro de DNS del host del
    proveedor que reenviara la clave a una IP interna. Lo que **no** se hace
    es validarla en el `PUT` de un proveedor de dirección fija, porque ahí el
    usuario no la envía.

    En un hilo aparte: la validación resuelve DNS con `socket`, que es
    bloqueante, y aquí estamos en el bucle de eventos.

    Residuo aceptado y documentado: entre resolver y conectar queda una
    ventana TOCTOU (DNS rebinding) que solo se cerraría fijando la IP
    resuelta en la conexión. Endurecimiento futuro, no de esta entrega.
    """
    if api_base is None:
        return
    await asyncio.to_thread(
        validar_api_base, api_base, es_produccion=get_settings().app_env == "production"
    )


async def _llamar_proveedor(
    argumentos: ArgumentosDeLlamada,
    *,
    messages: list[dict[str, Any]],
    max_tokens: int | None,
    temperature: float | None,
    response_format: dict[str, Any] | None,
    timeout: float,
) -> Any:
    """La llamada real. Nunca loguea la excepción cruda ni la respuesta.

    El objeto de excepción de LiteLLM arrastra `litellm_params` y el
    `request` original, donde viaja la `api_key`; el `ModelResponse` arrastra
    lo mismo en `_hidden_params`. Por eso aquí no se usa `logger.exception`
    ni se interpola `exc`: se construye el mensaje con el **nombre del tipo**
    y con `str(exc)` ya saneado, sustituyendo el literal de la clave por
    `***`. Criterio de la fase: buscar el literal de la clave en los logs
    tras forzar un fallo real da cero resultados.
    """
    litellm = _litellm()
    opciones: dict[str, Any] = {
        "model": argumentos.model,
        "messages": messages,
        "api_key": argumentos.api_key,
        "api_base": argumentos.api_base,
        "timeout": timeout,
    }
    if max_tokens is not None:
        opciones["max_tokens"] = max_tokens
    if temperature is not None:
        opciones["temperature"] = temperature
    if response_format is not None:
        opciones["response_format"] = response_format

    try:
        return await litellm.acompletion(**opciones)
    except Exception as exc:
        logger.warning(
            "Fallo del proveedor de IA (%s) con el modelo %s: %s",
            type(exc).__name__,
            argumentos.model,
            _sanear(str(exc), argumentos.api_key)[:500],
        )
        raise


def _coste_liquidado(respuesta: Any, estimado: Decimal) -> tuple[Decimal, bool]:
    """Coste real del proveedor, o la estimación marcada como no auditable.

    Nunca `0` ni `NULL`: un cero silencioso escondería gasto real y un nulo
    sacaría la fila de la suma del límite.
    """
    ocultos = getattr(respuesta, "_hidden_params", None) or {}
    bruto = ocultos.get("response_cost") if isinstance(ocultos, dict) else None
    if bruto is None:
        return estimado, False
    try:
        real = _a_usd(Decimal(str(bruto)))
    except (ArithmeticError, ValueError):
        return estimado, False
    if real <= 0:
        # LiteLLM devuelve 0.0 tanto para «gratis» como para «no lo sé». No
        # se distingue, así que se conserva la estimación: tratar el 0 como
        # coste real dejaría el límite sin nada que sumar.
        return estimado, False
    return real, True


def _tokens(respuesta: Any) -> tuple[int | None, int | None]:
    uso = getattr(respuesta, "usage", None)
    if uso is None:
        return None, None
    entrada = getattr(uso, "prompt_tokens", None)
    salida = getattr(uso, "completion_tokens", None)
    return (
        int(entrada) if entrada is not None else None,
        int(salida) if salida is not None else None,
    )


def _contenido(respuesta: Any) -> str:
    opciones = getattr(respuesta, "choices", None) or []
    if not opciones:
        return ""
    mensaje = getattr(opciones[0], "message", None)
    contenido = getattr(mensaje, "content", None)
    return contenido if isinstance(contenido, str) else ""


async def completar(
    *,
    organization_id: uuid.UUID,
    use_case: str,
    messages: list[dict[str, Any]],
    max_tokens: int | None = None,
    temperature: float | None = None,
    response_format: dict[str, Any] | None = None,
    timeout: float = TIMEOUT_POR_DEFECTO_S,
) -> Resultado:
    """Pide una respuesta de IA a nombre de una organización.

    `use_case` identifica quién la pide (`"accounting_ocr"`, …) y es lo que
    el panel agrupa; no cambia el comportamiento.

    Lanza, todas ellas errores de dominio (nunca un 500):

    - `ServicioDesactivado` si el admin apagó el servicio `ai`;
    - `SinConfiguracion` si ni la organización ni la plataforma tienen
      credenciales;
    - `LimiteDeGastoSuperado` si el gasto del periodo alcanzó el límite;
    - `CredencialIlegible` si la clave guardada no descifra;
    - `ErrorDeProveedor` (con su `error_code`) si la llamada falla.

    Las tres primeras ocurren **antes** de cualquier salida a la red.
    """
    await _precalentar_litellm()
    periodo = repository.periodo_actual()
    reserva = await _reservar(
        organization_id=organization_id,
        use_case=use_case,
        messages=messages,
        max_tokens=max_tokens,
        periodo=periodo,
    )

    arranque = time.monotonic()
    try:
        argumentos = _argumentos(reserva.config)
        await _validar_destino(argumentos.api_base)
        respuesta = await _llamar_proveedor(
            argumentos,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            response_format=response_format,
            timeout=timeout,
        )
    except Exception as exc:
        latencia = int((time.monotonic() - arranque) * 1000)
        codigo = errores.clasificar(exc)
        async with _sesion_de_organizacion(organization_id) as tx:
            await repository.liquidar_fallo(
                tx,
                organization_id=organization_id,
                record_id=reserva.record_id,
                error_code=codigo,
                latency_ms=latencia,
            )
        if isinstance(exc, errores.CredencialIlegible):
            raise
        # `from None` y no `from exc`: la excepción cruda de LiteLLM lleva la
        # `api_key` dentro (`litellm_params`, `request`), y encadenarla haría
        # que cualquier consumidor que la dejara propagar —un worker de
        # taskiq, por ejemplo— imprimiera esa clave al renderizar el
        # `__cause__`. No se pierde diagnóstico: el `error_code` queda en la
        # fila y el mensaje saneado ya está en el log de arriba.
        raise ErrorDeProveedor(codigo) from None

    latencia = int((time.monotonic() - arranque) * 1000)
    coste, auditable = _coste_liquidado(respuesta, reserva.coste_estimado_usd)
    entrada, salida = _tokens(respuesta)
    async with _sesion_de_organizacion(organization_id) as tx:
        await repository.liquidar(
            tx,
            organization_id=organization_id,
            record_id=reserva.record_id,
            coste_usd=coste,
            cost_auditable=auditable,
            input_tokens=entrada,
            output_tokens=salida,
            latency_ms=latencia,
        )

    return Resultado(
        contenido=_contenido(respuesta),
        provider=reserva.provider,
        model=reserva.model,
        input_tokens=entrada,
        output_tokens=salida,
        cost_usd=coste,
        cost_auditable=auditable,
        latency_ms=latencia,
        usage_record_id=reserva.record_id,
    )


async def cerrar_reservas_abandonadas(*, minutos: int) -> int:
    """Cuerpo de `sweep_stuck_ai_reservations_task`. Devuelve cuántas cerró.

    Dos pasos a propósito. El **descubrimiento** de qué organizaciones tienen
    reservas colgadas es transversal por naturaleza y va con la sesión de
    mantenimiento, en modo solo lectura. La **escritura** va organización a
    organización con `SessionApp` + `set_organization_context`, es decir bajo
    RLS, que es lo que exige B-10 para un worker sin petición HTTP.
    """
    from app.core.database import maintenance_session

    async with maintenance_session() as lectura:
        organizaciones = await repository.organizaciones_con_reservas_colgadas(
            lectura, minutos=minutos
        )

    cerradas = 0
    for organization_id in organizaciones:
        async with _sesion_de_organizacion(organization_id) as tx:
            cerradas += await repository.marcar_reservas_abandonadas(
                tx, organization_id, minutos=minutos, error_code=errores.RESERVA_ABANDONADA
            )
    if cerradas:
        logger.warning(
            "El barrido ha cerrado %s reserva(s) de IA sin liquidar: su gasto se "
            "cuenta como consumido.",
            cerradas,
        )
    return cerradas
