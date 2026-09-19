"""Errores de dominio de la pasarela de IA.

Todos heredan de `DomainError`, así que salen como `problem+json` con su
estado HTTP y **nunca** como un 500: una validación fallida, una clave que no
descifra o una instalación sin cifrado configurado son estados previstos, no
fallos inesperados.

Cada uno lleva un `code` estable en el cuerpo (`extra`), que es lo que el
frontend (fase 3) distingue, no el texto. La taxonomía de `error_code` de las
llamadas al proveedor (fase 2) se añadirá a este mismo fichero.
"""

from __future__ import annotations

from typing import Any

from app.shared.errors import ServiceUnavailableError, ValidationDomainError


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

    def __init__(self, detail: str | None = None) -> None:
        super().__init__(
            detail
            or (
                "La clave guardada no se puede descifrar con la clave de cifrado actual. "
                "Vuelve a guardarla o ejecuta el procedimiento de rotación."
            ),
            extra={"code": "credencial_ilegible"},
        )


class SinConfiguracion(ServiceUnavailableError):
    """Ni la organización ni la plataforma tienen configuración de IA usable.

    Es el estado al que degrada borrar la config de plataforma (V-12): las
    organizaciones herederas se quedan sin proveedor, con un error de dominio
    claro y nunca un 500.
    """

    def __init__(self, detail: str | None = None) -> None:
        super().__init__(
            detail or "No hay ninguna configuración de IA disponible para esta organización.",
            extra={"code": "sin_configuracion"},
        )
