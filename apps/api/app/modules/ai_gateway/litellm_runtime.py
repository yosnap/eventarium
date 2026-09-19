"""Carga de LiteLLM: un único punto que lo importa y lo deja configurado.

Importación diferida a propósito: el paquete arrastra `openai`, `tokenizers`
y `tiktoken` y tarda más de un segundo en cargar. Con un `import` de
cabecera, ese coste lo pagaría el arranque de la API entera, que casi nunca
llama a un modelo.

Por eso también está aquí y no en `client.py`: `errores.clasificar` necesita
las excepciones de LiteLLM y, si las importara por su cuenta, sería ese
`import` —y no este— el primero del proceso, quedándose sin los ajustes de
abajo.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - solo para el comprobador de tipos
    from types import ModuleType

#: LiteLLM resuelve el mapa de precios **al importarse**. Sin esta variable
#: lo descarga de `raw.githubusercontent.com` con un `httpx.get` síncrono
#: (timeout de 5 s) que bloquea el bucle de eventos entero; con ella usa la
#: copia que el propio paquete trae. Dos motivos para forzarla: el import
#: puede ocurrir mientras se sostiene el bloqueo del periodo de una
#: organización, y ninguna ejecución de la suite debe necesitar Internet.
VARIABLE_DE_MAPA_LOCAL = "LITELLM_LOCAL_MODEL_COST_MAP"

_modulo: ModuleType | None = None


def ya_cargado() -> bool:
    """Si el import ya se pagó en este proceso."""
    return _modulo is not None


def cargar() -> ModuleType:
    """Importa LiteLLM la primera vez y lo deja configurado.

    Tres ajustes obligatorios al cargarlo (Predict #14):

    - `telemetry = False`: LiteLLM no debe reportar nada hacia fuera.
    - `api_key = None`: sin clave global. Cada llamada pasa la suya
      explícitamente, así que una organización sin configurar falla con
      `sin_configuracion` en vez de gastar a cuenta de una clave de entorno
      (`OPENAI_API_KEY`/`ANTHROPIC_API_KEY`) que alguien dejó puesta.
    - `suppress_debug_info = True`: evita que LiteLLM imprima su banner de
      depuración —con el cuerpo de la petición dentro— en cada fallo.

    La variable de entorno se fija **antes** del `import`, que es cuando
    LiteLLM decide de dónde sale el mapa de precios. `setdefault` y no una
    asignación: una instalación que quiera el mapa remoto puede seguir
    poniéndola a otro valor en su entorno.
    """
    global _modulo
    if _modulo is None:
        os.environ.setdefault(VARIABLE_DE_MAPA_LOCAL, "True")

        import litellm

        litellm.telemetry = False
        litellm.api_key = None
        litellm.suppress_debug_info = True
        _modulo = litellm
    return _modulo
