"""Catálogo de mensajes del servidor: errores, títulos y textos que ve una persona.

El texto en español es la clave (como `msgid` en gettext): el código escribe el
mensaje en español, con `{parámetros}` si los lleva, y aquí se busca su versión en
el idioma de la petición (`app/core/locale.py`). Así un mensaje nuevo funciona en
español desde el primer momento y el resto de idiomas se generan con
`pnpm i18n:traducir`, igual que la interfaz web.

- `en-US.json`: `{"texto en español": "texto en inglés"}`.
- Si falta una traducción, se usa el español (y se registra una vez en el log).
  Solo se registran claves conocidas (las del catálogo de referencia
  español→inglés): un texto que no lo sea
  (p. ej. un mensaje de una librería con datos del usuario) se devuelve tal cual,
  sin guardarlo ni escribirlo en el log.
- `tests/test_mensajes_del_servidor.py` exige que todo mensaje del código sea
  un literal (sin f-strings) y que tenga su traducción en cada catálogo.
"""

from __future__ import annotations

import json
import logging
from functools import cache
from pathlib import Path
from string import Formatter
from typing import Any

from app.core.locale import DEFAULT_LOCALE, Locale, idioma_actual

logger = logging.getLogger(__name__)

CARPETA = Path(__file__).resolve().parent
#: Catálogo que hace de inventario de claves conocidas: todo mensaje del código
#: tiene su entrada en inglés (lo exige `tests/test_mensajes_del_servidor.py`).
LOCALE_DE_REFERENCIA: Locale = "en-US"
#: Tope de avisos «sin traducir» recordados, para que el conjunto no crezca sin fin.
MAX_AVISADOS = 1024
_avisados: set[tuple[str, str]] = set()


@cache
def catalogo(locale: Locale) -> dict[str, str]:
    """Traducciones de un idioma: texto en español → texto en `locale`."""
    if locale == DEFAULT_LOCALE:
        return {}
    ruta = CARPETA / f"{locale}.json"
    if not ruta.exists():
        return {}
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    return {str(clave): str(valor) for clave, valor in datos.items()}


class _Parametros(dict[str, Any]):
    """Un `{parametro}` que falta se deja tal cual en vez de lanzar `KeyError`."""

    def __missing__(self, clave: str) -> str:
        return "{" + clave + "}"


def formatear(plantilla: str, params: dict[str, Any] | None) -> str:
    if not params:
        return plantilla
    try:
        return plantilla.format_map(_Parametros(params))
    except (ValueError, IndexError):
        # Llaves literales que no son parámetros: se devuelve sin formatear.
        return plantilla


def es_clave_conocida(texto: str) -> bool:
    """`texto` es un mensaje del código: está en el catálogo de referencia. Lo
    demás (texto de terceros, de librerías) no es una clave."""
    return texto in catalogo(LOCALE_DE_REFERENCIA)


def t(texto: str, locale: Locale | None = None, **params: Any) -> str:
    """`texto` (en español, con `{parámetros}`) en `locale` o en el de la petición.

    Un texto que no es una clave conocida se devuelve tal cual (formateado con
    `params`, si los hay), sin registrarlo: puede llevar datos de quien escribe.
    """
    destino = locale or idioma_actual()
    traducido = catalogo(destino).get(texto) if destino != DEFAULT_LOCALE else None
    if traducido is None:
        traducido = texto
        if destino != DEFAULT_LOCALE and es_clave_conocida(texto):
            _avisar_sin_traducir(destino, texto)
    return formatear(traducido, params)


def _avisar_sin_traducir(destino: Locale, texto: str) -> None:
    """Una vez por (idioma, clave), y con el conjunto acotado a `MAX_AVISADOS`."""
    if (destino, texto) in _avisados or len(_avisados) >= MAX_AVISADOS:
        return
    _avisados.add((destino, texto))
    logger.warning("Mensaje sin traducir a %s: %r", destino, texto[:80])


def marcar(texto: str) -> str:
    """Registra `texto` como mensaje traducible sin traducirlo aún (`gettext_noop`).

    Para mensajes que se eligen de una tabla y se lanzan después con una variable:
    el literal queda en el catálogo y el `raise` que lo usa lleva el comentario
    `# mensaje marcado`, que le exime del test de literales.
    """
    return texto


class ErrorDeValidacion(ValueError):
    """`ValueError` de un validador con plantilla traducible y parámetros.

    Pydantic conserva la excepción en `ctx["error"]` y `mensajes/validacion.py`
    traduce `plantilla` con `params`; fuera de Pydantic, quien la captura puede
    convertirla en `ValidationDomainError(exc.plantilla, params=exc.params)`.
    `plantilla` es un literal (lo extrae `extraer.py` como cualquier `ValueError`).
    `codigo` distingue el caso para quien lo trate por programa.
    """

    def __init__(
        self, plantilla: str, params: dict[str, Any] | None = None, *, codigo: str | None = None
    ) -> None:
        self.plantilla = plantilla
        self.params = params or {}
        self.codigo = codigo
        super().__init__(formatear(plantilla, self.params))


def parametros_de(plantilla: str) -> set[str]:
    """Nombres de los `{parámetros}` de una plantilla."""
    return {campo for _, campo, _, _ in Formatter().parse(plantilla) if campo}
