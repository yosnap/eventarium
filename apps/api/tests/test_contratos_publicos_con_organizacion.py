"""Todo contrato que expone el slug de un evento lleva también su organización.

La URL pública de un evento es `/{org}/{evento}`: un esquema con `event_slug` y
sin `organization` obligaría al cliente a adivinar la mitad del enlace.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil

from pydantic import BaseModel

import app.modules as modulos

# Esquemas con `event_slug` que no son contratos públicos (los ve solo el equipo
# de la organización, que ya conoce la suya).
EXCEPCIONES: frozenset[str] = frozenset()

# Contratos públicos que identifican el evento con `slug` (no `event_slug`).
CON_SLUG_DE_EVENTO = frozenset({"PublicEventSummary", "PublicEventDetail", "EventCalendarInfo"})


def _esquemas() -> list[type[BaseModel]]:
    encontrados: list[type[BaseModel]] = []
    for info in pkgutil.walk_packages(modulos.__path__, prefix="app.modules."):
        if not info.name.endswith("schemas"):
            continue
        modulo = importlib.import_module(info.name)
        for _, clase in inspect.getmembers(modulo, inspect.isclass):
            if issubclass(clase, BaseModel) and clase.__module__ == modulo.__name__:
                encontrados.append(clase)
    return encontrados


def test_ningun_esquema_con_event_slug_omite_la_organizacion() -> None:
    esquemas = _esquemas()
    assert esquemas, "no se ha encontrado ningún esquema"
    sin_organizacion = sorted(
        f"{clase.__module__}.{clase.__name__}"
        for clase in esquemas
        if ("event_slug" in clase.model_fields or clase.__name__ in CON_SLUG_DE_EVENTO)
        and "organization" not in clase.model_fields
        and clase.__name__ not in EXCEPCIONES
    )
    assert sin_organizacion == []
