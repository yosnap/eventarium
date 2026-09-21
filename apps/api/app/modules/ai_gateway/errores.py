"""Errores de dominio de la pasarela de IA.

Todos heredan de `DomainError`, así que salen como `problem+json` con su
estado HTTP y **nunca** como un 500: una validación fallida, una clave que no
descifra o una instalación sin cifrado configurado son estados previstos, no
fallos inesperados.

Cada uno lleva un `code` estable en el cuerpo (`extra`), que es lo que el
frontend (fase 3) distingue, no el texto.

La segunda mitad del fichero es la **taxonomía cerrada de `error_code`** de
las llamadas al proveedor (fase 2). Sin panel de diagnóstico (no-objetivo del
PRD), la columna `ai_usage_records.error_code` es la única pista de por qué
falló una llamada, así que el conjunto de valores es cerrado y está declarado
aquí: `clasificar` no puede devolver nada que no esté en `CODIGOS_DE_ERROR`.
"""

from __future__ import annotations

import base64
from typing import Any
from urllib.parse import quote

from app.modules.ai_gateway import litellm_runtime
from app.shared.errors import (
    ConflictError,
    ExternalServiceError,
    ServiceUnavailableError,
    ValidationDomainError,
)


def sanear(texto: str, clave: str) -> str:
    """Sustituye el literal de la clave del proveedor por `***`, y también
    sus formas transformadas más comunes en un mensaje de error eco.

    Se aplica a **todo** texto que venga del proveedor antes de tocar un log
    o una respuesta: los mensajes de error de varias APIs OpenAI-compatible
    reproducen la petición recibida, cabeceras incluidas, y con ellas la
    clave. Vive aquí, y no en el cliente de generación, porque lo necesitan
    por igual ese cliente y el descubrimiento de modelos.

    El literal en texto plano no es la única forma en que la clave puede
    aparecer: un proveedor `custom` con auth HTTP Basic la manda como
    `base64("<clave>:")`, y una URL puede llevarla percent-encoded en un
    parámetro de query. Ninguna sustitución adicional cubre todos los casos
    posibles (una clave partida entre líneas, por ejemplo, seguiría
    escapando) — es defensa en profundidad, no una garantía absoluta.
    """
    if not clave:
        return texto
    saneado = texto.replace(clave, "***")
    saneado = saneado.replace(base64.b64encode(f"{clave}:".encode()).decode(), "***")
    percent_encoded = quote(clave, safe="")
    if percent_encoded != clave:
        saneado = saneado.replace(percent_encoded, "***")
    return saneado


class ErrorDeConfiguracionDeIa(ValidationDomainError):
    """422 con un `code` estable. Base de las reglas del `PUT`."""

    code = "configuracion_de_ia_invalida"

    def __init__(self, detail: str, *, extra: dict[str, Any] | None = None) -> None:
        datos: dict[str, Any] = {"code": self.code}
        datos.update(extra or {})
        super().__init__(detail, extra=datos)


class ProveedorDesconocido(ErrorDeConfiguracionDeIa):
    code = "proveedor_desconocido"


class ModeloDesconocido(ErrorDeConfiguracionDeIa):
    code = "modelo_desconocido"


class ApiBaseNoPermitido(ErrorDeConfiguracionDeIa):
    """`api_base` enviado a un proveedor cuya base URL es constante nuestra.

    Aceptarlo permitiría apuntar `nan_builders`/`cheaper_inference` a un host
    del atacante y quedarse con la clave que viaja en la cabecera.
    """

    code = "api_base_no_permitido"


class ApiBaseRequerido(ErrorDeConfiguracionDeIa):
    code = "api_base_requerido"


class ClaveRequerida(ErrorDeConfiguracionDeIa):
    """Override parcial: la resolución es todo-o-nada por fila (V-5).

    Una fila de override sin clave no existe por construcción: mezclar la
    clave compartida de plataforma con un `api_base` del tenant sería
    exfiltrarla a un endpoint del organizador.
    """

    code = "clave_requerida"


class ProveedorRequerido(ErrorDeConfiguracionDeIa):
    """La otra mitad de V-5: una clave sin proveedor ni modelo no es una
    configuración, y guardarla dejaría una fila incoherente."""

    code = "proveedor_requerido"


class LimitePorEncimaDelTecho(ErrorDeConfiguracionDeIa):
    code = "limite_por_encima_del_techo"


class ServicioDesconocido(ErrorDeConfiguracionDeIa):
    code = "service_key_desconocido"


class CifradoNoConfigurado(ServiceUnavailableError):
    """Sin `AI_SETTINGS_ENCRYPTION_KEY` no se puede guardar ninguna clave.

    503 y no 422: no es un dato mal enviado, es la instalación sin configurar.
    Una instalación que no usa IA arranca igual; solo falla aquí, al intentar
    guardar o leer una credencial.
    """

    def __init__(self, detail: str | None = None) -> None:
        super().__init__(
            detail
            or (
                "La instalación no tiene AI_SETTINGS_ENCRYPTION_KEY configurada: "
                "no se puede guardar ni leer ninguna clave de proveedor de IA."
            ),
            extra={"code": "cifrado_no_configurado"},
        )


class CredencialIlegible(ServiceUnavailableError):
    """La clave guardada no descifra con la clave de cifrado actual.

    Ocurre si se rota `AI_SETTINGS_ENCRYPTION_KEY` sin re-cifrar las filas
    (ver `app/cli.py rotate-ai-encryption-key`). Error de dominio explícito
    para que el panel pueda decir qué pasa, en vez de un 500 opaco.
    """

    error_code = "credencial_ilegible"

    def __init__(self, detail: str | None = None) -> None:
        super().__init__(
            detail
            or (
                "La clave guardada no se puede descifrar con la clave de cifrado actual. "
                "Vuelve a guardarla o ejecuta el procedimiento de rotación."
            ),
            extra={"code": CredencialIlegible.error_code},
        )


class SinConfiguracion(ServiceUnavailableError):
    """Ni la organización ni la plataforma tienen configuración de IA usable.

    Es el estado al que degrada borrar la config de plataforma (V-12): las
    organizaciones herederas se quedan sin proveedor, con un error de dominio
    claro y nunca un 500.
    """

    error_code = "sin_configuracion"

    def __init__(self, detail: str | None = None) -> None:
        super().__init__(
            detail or "No hay ninguna configuración de IA disponible para esta organización.",
            extra={"code": self.error_code},
        )


# --- Taxonomía cerrada de `ai_usage_records.error_code` -----------------------

#: El admin apagó el servicio `ai`, global o para esta organización.
SERVICIO_DESACTIVADO = "servicio_desactivado"
#: Ni la organización ni la plataforma tienen configuración de IA.
SIN_CONFIGURACION = "sin_configuracion"
#: El gasto del periodo alcanzó el límite efectivo.
LIMITE_SUPERADO = "limite_superado"
#: La clave guardada no descifra (rotación sin re-cifrar, fila copiada…).
CREDENCIAL_ILEGIBLE = "credencial_ilegible"
#: Fallo transitorio del proveedor: red, 5xx, timeout, rate limit.
PROVEEDOR_ERROR = "proveedor_error"
#: El proveedor rechaza el contenido de imagen del mensaje.
MODELO_SIN_VISION = "modelo_sin_vision"
#: El proveedor rechaza la credencial (401/403).
CLAVE_RECHAZADA = "clave_rechazada"
#: Entrada rechazada por el proveedor: 413, contexto excedido, formato.
PAYLOAD_INVALIDO = "payload_invalido"
#: El barrido rescató una reserva que nadie liquidó.
RESERVA_ABANDONADA = "reserva_abandonada"

#: Conjunto cerrado. `clasificar` no devuelve nada fuera de aquí, y la
#: migración lo replica en un `CHECK` para que ninguna escritura posterior
#: pueda inventarse un código que el panel no sepa traducir.
CODIGOS_DE_ERROR: frozenset[str] = frozenset(
    {
        SERVICIO_DESACTIVADO,
        SIN_CONFIGURACION,
        LIMITE_SUPERADO,
        CREDENCIAL_ILEGIBLE,
        PROVEEDOR_ERROR,
        MODELO_SIN_VISION,
        CLAVE_RECHAZADA,
        PAYLOAD_INVALIDO,
        RESERVA_ABANDONADA,
    }
)

#: Pistas textuales de «el modelo no acepta imágenes». Los proveedores
#: OpenAI-compatible devuelven esto como un 400 genérico indistinguible de
#: cualquier otro `payload_invalido`, así que la única señal disponible es el
#: mensaje. Se busca en minúsculas y sin acentos de por medio.
_PISTAS_DE_VISION = (
    "image",
    "vision",
    "multimodal",
    "image_url",
)


class ServicioDesactivado(ServiceUnavailableError):
    """El interruptor `ai` está apagado (global o para esta organización).

    503 y no 403: no es un permiso de quien pide, es una capacidad que la
    instalación tiene apagada. Se comprueba **antes** de resolver ninguna
    credencial, para que apagar el servicio impida incluso descifrar la clave.
    """

    error_code = SERVICIO_DESACTIVADO

    def __init__(self, detail: str | None = None) -> None:
        super().__init__(
            detail or "El servicio de IA está desactivado para esta organización.",
            extra={"code": self.error_code},
        )


class LimiteDeGastoSuperado(ConflictError):
    """El gasto del periodo alcanzó el límite efectivo.

    409 y **código propio**, distinto de `proveedor_error` a propósito: este
    es reintentable en cuanto se amplía el límite, mientras que un fallo del
    proveedor no lo es necesariamente. La fase 4 usa esa diferencia para no
    dejar facturas irrecuperables.
    """

    error_code = LIMITE_SUPERADO

    def __init__(self, detail: str | None = None, *, extra: dict[str, Any] | None = None) -> None:
        datos: dict[str, Any] = {"code": self.error_code}
        datos.update(extra or {})
        super().__init__(
            detail or "Se ha alcanzado el límite de gasto en IA de este periodo.", extra=datos
        )


class ErrorDeProveedor(ExternalServiceError):
    """La llamada al proveedor falló. Nunca lleva el mensaje crudo.

    `error_code` distingue el motivo dentro de la taxonomía cerrada. El texto
    del proveedor **no** viaja al cliente ni a los logs sin sanear: puede
    contener el cuerpo de la petición y, con él, la clave.
    """

    def __init__(self, error_code: str, detail: str | None = None) -> None:
        self.error_code = error_code
        super().__init__(
            detail or "El proveedor de IA no ha podido atender la petición.",
            extra={"code": error_code},
        )


def _parece_falta_de_vision(mensaje: str) -> bool:
    bajo = mensaje.lower()
    return any(pista in bajo for pista in _PISTAS_DE_VISION)


def clasificar(exc: BaseException) -> str:
    """Traduce una excepción de LiteLLM a un `error_code` de la taxonomía.

    Solo mira el **tipo** de la excepción y, para separar `modelo_sin_vision`
    de `payload_invalido`, el texto de su mensaje: nunca sus atributos
    internos (`litellm_params`, `request`, `response`), por donde viaja la
    clave del proveedor.

    LiteLLM se importa aquí dentro, no en el encabezado: importar el paquete
    cuesta más de un segundo y arrastra `tokenizers`/`openai`, y este módulo
    lo importa todo el árbol de errores del dominio. Y se importa por
    `litellm_runtime`, que es lo que garantiza que el paquete quede
    configurado (y sin descargar su mapa de precios) sea cual sea el primer
    sitio del proceso que lo cargue.
    """
    litellm_runtime.cargar()
    from litellm import exceptions as litellm_errores

    if isinstance(exc, CredencialIlegible):
        return CREDENCIAL_ILEGIBLE

    if isinstance(exc, litellm_errores.AuthenticationError | litellm_errores.PermissionDeniedError):
        return CLAVE_RECHAZADA

    if isinstance(exc, litellm_errores.ContextWindowExceededError):
        return PAYLOAD_INVALIDO

    if isinstance(
        exc,
        litellm_errores.BadRequestError
        | litellm_errores.UnprocessableEntityError
        | litellm_errores.UnsupportedParamsError,
    ):
        return MODELO_SIN_VISION if _parece_falta_de_vision(str(exc)) else PAYLOAD_INVALIDO

    return PROVEEDOR_ERROR
