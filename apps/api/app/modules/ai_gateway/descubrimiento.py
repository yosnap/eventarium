"""Listado **en vivo** de los modelos de un proveedor de IA.

Capa baja: habla HTTP con el proveedor y devuelve modelos del catálogo. No
toca base de datos, ni caché, ni configuración efectiva — de eso se encarga
`catalogo_dinamico.py`, que es quien decide con qué clave se llama aquí y qué
hacer cuando esto falla.

**Por qué un cliente propio y no LiteLLM.** `litellm.get_valid_models()`
devuelve la lista **estática** de su mapa de precios salvo que se le pase
`check_provider_endpoint=True`; incluso entonces solo devuelve identificadores
(`list[str]`), sin ningún dato de capacidades, y su cobertura por proveedor es
desigual (verificado en el paquete instalado, 2026-09-20). La marca de visión
es justo lo que este módulo existe para averiguar, así que LiteLLM no sirve.

**Direcciones de descubrimiento.** `proveedores.api_base_fijo` describe la
base de la llamada de **generación**, y en los proveedores que LiteLLM conoce
de serie (OpenAI, Anthropic, Gemini, OpenRouter) es `None` porque la pone
LiteLLM. Para listar modelos hay que conocerla igualmente, así que se declara
aquí, junto al resto de detalles de cada API (`_ADAPTADORES`).

**Seguridad.**

- La clave viaja **solo** en la cabecera de la petición saliente. En Gemini se
  usa `x-goog-api-key` y no el `?key=` de sus ejemplos: un secreto en la query
  string acaba en logs de proxy, en `Referer` y en trazas de error.
- Ningún texto del proveedor llega a un log sin pasar por `errores.sanear`:
  varias APIs OpenAI-compatible devuelven la petición recibida —cabeceras
  incluidas— dentro del mensaje de error.
- Nunca se sigue una redirección: un 3xx del proveedor hacia otro host
  reenviaría la cabecera con la clave a ese host.
- El `api_base` se valida siempre con `validacion.validar_api_base`, para
  los siete proveedores, no solo `custom` — mismo criterio que
  `client.py::_validar_destino` en la llamada de generación: aunque la
  dirección venga del catálogo, el DNS del proveedor puede haber cambiado
  entre desplegar y usarla, y el coste de revalidar es despreciable.

**La marca de visión nunca se inventa.** Solo se marca `True` cuando el propio
proveedor lo declara en un campo interpretable. Si no lo declara, este módulo
devuelve `None` («no consta») y es `catalogo_dinamico` quien decide el valor
final cayendo al catálogo estático. Un `False` de más solo impide usar ese
modelo para OCR; un `True` de más rompe la llamada real, que es peor.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import get_settings
from app.modules.ai_gateway import proveedores as catalogo
from app.modules.ai_gateway.errores import (
    CLAVE_RECHAZADA,
    PROVEEDOR_ERROR,
    ApiBaseRequerido,
    sanear,
)
from app.modules.ai_gateway.proveedores import Modelo
from app.modules.ai_gateway.validacion import validar_api_base

logger = logging.getLogger(__name__)

#: Tope de la llamada saliente. El panel espera por ella: si el proveedor no
#: contesta en este tiempo es preferible caer al catálogo estático que dejar
#: el desplegable girando. Conectar tiene un tope más corto que el total.
TIMEOUT = httpx.Timeout(8.0, connect=4.0)

#: Cota del listado que se acepta. OpenRouter publica varios cientos de
#: modelos, y un proveedor hostil (o un `custom` mal configurado) podría
#: devolver un listado sin fin: sin cota, ese cuerpo entero acabaría en Redis
#: y en la respuesta del panel.
MAXIMO_MODELOS = 500

#: Cota del cuerpo que se lee del proveedor, por el mismo motivo (4 MiB). Se
#: aplica **mientras** se descarga (ver `_leer_acotado`): comprobarla sobre la
#: respuesta ya recibida llegaría tarde, porque para entonces el cuerpo entero
#: estaría ya en memoria del worker.
MAXIMO_BYTES = 4 * 1024 * 1024

# --- Motivos por los que el listado en vivo no sale ----------------------------
#
# **No** forman parte de `errores.CODIGOS_DE_ERROR`: aquella es la taxonomía
# cerrada de `ai_usage_records.error_code`, replicada en un `CHECK` de la
# migración, y aquí no se registra ninguna llamada de generación. Los dos que
# coinciden en significado reutilizan la misma cadena a propósito, para que el
# frontend traduzca un solo vocabulario.

#: No hay ninguna clave utilizable para llamar a este proveedor.
SIN_CLAVE = "sin_clave"
#: El proveedor no respondió a tiempo.
TIEMPO_AGOTADO = "tiempo_agotado"
#: Respondió, pero no con un listado de modelos que se pueda interpretar.
RESPUESTA_INESPERADA = "respuesta_inesperada"
#: Los otros dos motivos son `errores.CLAVE_RECHAZADA` (401/403) y
#: `errores.PROVEEDOR_ERROR` (red, 5xx, cualquier otro estado), importados de
#: allí para que el frontend traduzca un solo vocabulario.

#: Vocabulario completo del campo `motivo` de la respuesta.
MOTIVOS: frozenset[str] = frozenset(
    {SIN_CLAVE, TIEMPO_AGOTADO, RESPUESTA_INESPERADA, CLAVE_RECHAZADA, PROVEEDOR_ERROR}
)


class ListadoNoDisponible(Exception):
    """No se ha podido obtener el listado en vivo. Lleva el motivo, nunca el
    texto crudo del proveedor."""

    def __init__(self, motivo: str) -> None:
        self.motivo = motivo
        super().__init__(motivo)


@dataclass(frozen=True, slots=True)
class Adaptador:
    """Cómo se le pide el listado de modelos a un proveedor concreto."""

    #: Base de la llamada de descubrimiento. `None` en `custom`: la escribe
    #: quien configura y llega por parámetro.
    api_base: str | None
    #: Cabecera en la que viaja la clave.
    cabecera_de_clave: str = "Authorization"
    #: Plantilla del valor. `{clave}` se sustituye por la clave en claro.
    formato_de_clave: str = "Bearer {clave}"
    #: Cabeceras fijas obligatorias de la API.
    cabeceras_extra: dict[str, str] | None = None
    #: `True` si el listado es público y sale igual sin clave (OpenRouter).
    admite_sin_clave: bool = False


#: Un adaptador por clave de `proveedores.PROVEEDORES`. Direcciones y esquemas
#: de autenticación verificados contra la documentación de cada proveedor
#: (2026-09-20).
_ADAPTADORES: dict[str, Adaptador] = {
    # OpenAI-compatible; la base es la constante del catálogo.
    "nan_builders": Adaptador(api_base="https://api.nan.builders/v1"),
    "cheaper_inference": Adaptador(api_base="https://api.cheaperinference.com/v1"),
    # El listado de OpenRouter es público: sale aunque la organización no
    # tenga ninguna clave guardada de este proveedor, que es justo el caso de
    # quien está eligiéndolo por primera vez en el desplegable.
    "openrouter": Adaptador(api_base="https://openrouter.ai/api/v1", admite_sin_clave=True),
    "openai": Adaptador(api_base="https://api.openai.com/v1"),
    "anthropic": Adaptador(
        api_base="https://api.anthropic.com/v1",
        cabecera_de_clave="x-api-key",
        formato_de_clave="{clave}",
        # Obligatoria en toda la API de Anthropic; sin ella responde 400.
        cabeceras_extra={"anthropic-version": "2023-06-01"},
    ),
    "gemini": Adaptador(
        api_base="https://generativelanguage.googleapis.com/v1beta",
        cabecera_de_clave="x-goog-api-key",
        formato_de_clave="{clave}",
    ),
    # Endpoint arbitrario OpenAI-compatible: la base llega por parámetro y se
    # valida antes de salir.
    "custom": Adaptador(api_base=None),
}


def adaptador(provider: str) -> Adaptador | None:
    return _ADAPTADORES.get(provider)


async def _url_de_listado(provider: str, api_base: str | None) -> str:
    """`{base}/models`, la convención OpenAI-compatible que cumplen los siete."""
    entrada = _ADAPTADORES.get(provider)
    if entrada is None:
        raise ListadoNoDisponible(RESPUESTA_INESPERADA)

    base = entrada.api_base or (api_base or "").strip().rstrip("/")
    if not base:
        # Solo puede pasar en `custom`, el único sin base propia: es entrada
        # que falta, no un fallo del proveedor, así que 422 con su `code`.
        raise ApiBaseRequerido(
            "Un proveedor personalizado necesita la dirección de su endpoint "
            "para poder consultar sus modelos."
        )

    # Se revalida siempre, también para un proveedor de base fija
    # (`api_base_editable=False`): mismo criterio que `client.py::_validar_destino`
    # para la llamada de generación real — "aunque la dirección venga del
    # catálogo y no del usuario: el coste es despreciable y protege de un
    # secuestro de DNS del host del proveedor". Antes solo se revalidaba en
    # `custom`, dejando el listado de modelos y la prueba de conexión de los
    # seis proveedores de base fija sin esta defensa, a diferencia de la
    # llamada de generación que sí la aplicaba siempre. Va a un hilo porque
    # `getaddrinfo` es bloqueante y pararía el bucle de eventos.
    base = await asyncio.to_thread(
        validar_api_base, base, es_produccion=get_settings().app_env == "production"
    )

    return f"{base}/models"


def _cabeceras(provider: str, api_key: str | None) -> dict[str, str]:
    entrada = _ADAPTADORES[provider]
    cabeceras = {"Accept": "application/json"}
    cabeceras.update(entrada.cabeceras_extra or {})
    if api_key:
        cabeceras[entrada.cabecera_de_clave] = entrada.formato_de_clave.format(clave=api_key)
    return cabeceras


def _entradas(cuerpo: Any) -> list[dict[str, Any]]:
    """El array de modelos, venga en `data` (OpenAI/Anthropic) o en `models`
    (Gemini)."""
    if not isinstance(cuerpo, dict):
        raise ListadoNoDisponible(RESPUESTA_INESPERADA)
    for campo in ("data", "models"):
        valor = cuerpo.get(campo)
        if isinstance(valor, list):
            return [entrada for entrada in valor if isinstance(entrada, dict)]
    raise ListadoNoDisponible(RESPUESTA_INESPERADA)


def _identificador(entrada: dict[str, Any]) -> str | None:
    bruto = entrada.get("id") or entrada.get("name") or entrada.get("model")
    if not isinstance(bruto, str) or not bruto.strip():
        return None
    clave = bruto.strip()
    # Gemini identifica sus modelos como `models/gemini-2.0-flash`, pero es
    # `gemini-2.0-flash` lo que espera la llamada de generación.
    return clave.removeprefix("models/")


def _etiqueta(entrada: dict[str, Any], clave: str) -> str:
    for campo in ("display_name", "displayName"):
        valor = entrada.get(campo)
        if isinstance(valor, str) and valor.strip():
            return valor.strip()
    # `name` solo es un nombre legible cuando el identificador vive en `id`;
    # en Gemini `name` **es** el identificador y no aporta nada.
    if "id" in entrada:
        valor = entrada.get("name")
        if isinstance(valor, str) and valor.strip():
            return valor.strip()
    return clave


def vision_declarada(entrada: dict[str, Any]) -> bool | None:
    """Lo que el proveedor dice sobre si el modelo acepta imágenes.

    `None` significa «no consta», no «no acepta»: es la señal de que hay que
    caer al catálogo estático. Solo devuelve `True` con una declaración
    explícita del proveedor, nunca por heurística sobre el nombre del modelo.

    Campos reconocidos, verificados proveedor a proveedor (2026-09-20):

    - `architecture.input_modalities` / `architecture.modality` — OpenRouter.
    - `capabilities.vision` — CheaperInference.
    - `capabilities.image_input.supported` — Anthropic (y `capabilities` puede
      llegar a `null` en sus modelos antiguos).

    OpenAI y Gemini **no** publican ninguna capacidad en su endpoint de
    listado: ahí siempre sale `None`.
    """
    arquitectura = entrada.get("architecture")
    if isinstance(arquitectura, dict):
        modalidades = arquitectura.get("input_modalities")
        if isinstance(modalidades, list):
            return any(
                isinstance(modalidad, str) and modalidad.lower() == "image"
                for modalidad in modalidades
            )
        modalidad = arquitectura.get("modality")
        if isinstance(modalidad, str):
            # `"text+image->text"`: solo cuenta la parte de entrada.
            entrada_de_modalidad = modalidad.split("->")[0]
            return "image" in entrada_de_modalidad.lower()

    capacidades = entrada.get("capabilities")
    if isinstance(capacidades, dict):
        vision = capacidades.get("vision")
        if isinstance(vision, bool):
            return vision
        imagen = capacidades.get("image_input")
        if isinstance(imagen, dict) and isinstance(imagen.get("supported"), bool):
            return bool(imagen["supported"])

    return None


@dataclass(frozen=True, slots=True)
class ModeloDescubierto:
    """Un modelo tal y como lo describe el proveedor, antes de resolver la
    marca de visión contra el catálogo estático."""

    clave: str
    etiqueta: str
    #: `None` = el proveedor no lo declara.
    vision: bool | None


def interpretar(cuerpo: Any) -> list[ModeloDescubierto]:
    """Traduce el cuerpo del proveedor a modelos. Ordena por etiqueta: el
    orden en que los devuelve cada API no es estable ni significativo, y el
    desplegable sí necesita uno predecible."""
    descubiertos: dict[str, ModeloDescubierto] = {}
    for entrada in _entradas(cuerpo):
        clave = _identificador(entrada)
        if clave is None or clave in descubiertos:
            continue
        descubiertos[clave] = ModeloDescubierto(
            clave=clave,
            etiqueta=_etiqueta(entrada, clave),
            vision=vision_declarada(entrada),
        )
        if len(descubiertos) >= MAXIMO_MODELOS:
            break

    if not descubiertos:
        # Un 200 con cero modelos no es una credencial válida con catálogo
        # vacío: en todos estos proveedores significa que se ha interpretado
        # mal el cuerpo. Se trata como fallo y se cae al catálogo estático.
        raise ListadoNoDisponible(RESPUESTA_INESPERADA)

    return sorted(descubiertos.values(), key=lambda modelo: modelo.etiqueta.lower())


def resolver_vision(provider: str, descubierto: ModeloDescubierto) -> Modelo:
    """La marca de visión final: la del proveedor si consta; si no, la anotada
    a mano en el catálogo estático; y `False` conservador si el modelo es
    nuevo y el catálogo no lo conocía."""
    if descubierto.vision is not None:
        return Modelo(
            clave=descubierto.clave, etiqueta=descubierto.etiqueta, vision=descubierto.vision
        )

    entrada = catalogo.obtener(provider)
    conocido = entrada.modelo(descubierto.clave) if entrada is not None else None
    return Modelo(
        clave=descubierto.clave,
        etiqueta=descubierto.etiqueta,
        vision=conocido.vision if conocido is not None else False,
    )


def _motivo_de_estado(estado: int) -> str:
    if estado in {401, 403}:
        return CLAVE_RECHAZADA
    return PROVEEDOR_ERROR


def _demasiado_grande(provider: str) -> ListadoNoDisponible:
    logger.warning("El listado de modelos de %s excede el tamaño admitido", provider)
    return ListadoNoDisponible(RESPUESTA_INESPERADA)


async def _leer_acotado(respuesta: httpx.Response, provider: str) -> bytes:
    """El cuerpo, cortando en cuanto supera `MAXIMO_BYTES`.

    Se lee por trozos y se corta a mitad de descarga: un host hostil (o un
    `custom` mal configurado) no puede hacer que el worker retenga un cuerpo
    arbitrariamente grande antes de que la cota actúe.

    El `Content-Length` declarado se comprueba antes de leer nada, pero no
    sustituye al corte: no es fiable —puede faltar, mentir o llegar una
    respuesta con `Transfer-Encoding: chunked`—, solo evita descargar lo que
    ya se sabe que sobra.
    """
    declarado = respuesta.headers.get("content-length")
    if declarado is not None and declarado.isdigit() and int(declarado) > MAXIMO_BYTES:
        raise _demasiado_grande(provider)

    trozos: list[bytes] = []
    total = 0
    async for trozo in respuesta.aiter_bytes():
        total += len(trozo)
        if total > MAXIMO_BYTES:
            raise _demasiado_grande(provider)
        trozos.append(trozo)
    return b"".join(trozos)


async def listar_modelos(
    provider: str,
    *,
    api_key: str | None,
    api_base: str | None = None,
) -> list[Modelo]:
    """Pide el listado al proveedor y lo devuelve ya con la visión resuelta.

    Lanza `ListadoNoDisponible` con el motivo si no se puede: quien llama
    decide si eso es un fallback al catálogo estático (el desplegable) o un
    resultado negativo que enseñar (la prueba de conexión).
    """
    entrada = _ADAPTADORES.get(provider)
    if entrada is None:
        raise ListadoNoDisponible(RESPUESTA_INESPERADA)
    if not api_key and not entrada.admite_sin_clave:
        raise ListadoNoDisponible(SIN_CLAVE)

    url = await _url_de_listado(provider, api_base)
    cabeceras = _cabeceras(provider, api_key)

    try:
        # `follow_redirects=False`: un 3xx hacia otro host reenviaría la
        # cabecera con la clave a ese host.
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False) as propio:
            # En streaming, no con `get`: así el cuerpo pasa por la cota de
            # `_leer_acotado` mientras baja, en vez de bufferizarse entero
            # antes de que nadie pueda mirarlo.
            async with propio.stream("GET", url, headers=cabeceras) as respuesta:
                if respuesta.status_code >= 400:
                    motivo = _motivo_de_estado(respuesta.status_code)
                    logger.info(
                        "El listado de modelos de %s ha respondido %s (%s)",
                        provider,
                        respuesta.status_code,
                        motivo,
                    )
                    raise ListadoNoDisponible(motivo)
                crudo = await _leer_acotado(respuesta, provider)
    except httpx.TimeoutException as error:
        _registrar(provider, "tiempo agotado", error, api_key)
        raise ListadoNoDisponible(TIEMPO_AGOTADO) from error
    except httpx.HTTPError as error:
        _registrar(provider, "error de red", error, api_key)
        raise ListadoNoDisponible(PROVEEDOR_ERROR) from error

    try:
        # `json.loads` y no `respuesta.json()`: la respuesta se ha consumido en
        # streaming, así que su cuerpo ya no está disponible como atributo.
        # `UnicodeDecodeError` es un `ValueError`, así que un cuerpo que ni
        # siquiera es texto cae aquí igual que un JSON roto.
        cuerpo = json.loads(crudo)
    except ValueError as error:
        _registrar(provider, "respuesta no es JSON", error, api_key)
        raise ListadoNoDisponible(RESPUESTA_INESPERADA) from error

    return [resolver_vision(provider, descubierto) for descubierto in interpretar(cuerpo)]


def _registrar(provider: str, que: str, error: BaseException, api_key: str | None) -> None:
    """Un log sin `exc_info` y con el texto saneado.

    `exc_info` volcaría la excepción entera de `httpx`, que arrastra la
    petición y sus cabeceras — y con ellas la clave. Solo sale el texto, y
    solo después de sustituir el literal de la clave.
    """
    logger.info(
        "No se ha podido listar los modelos de %s (%s): %s",
        provider,
        que,
        sanear(str(error), api_key or "")[:300],
    )
