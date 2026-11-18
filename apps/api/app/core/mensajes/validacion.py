"""Mensajes de los errores de validación de Pydantic, en el idioma de la petición.

Pydantic los escribe en inglés y con su propio texto. Aquí se rehacen por `type`
con los datos de su `ctx` (longitudes, límites, valores esperados), en español
como clave del catálogo. Los `ValueError` de los validadores del proyecto llegan
como `"Value error, <mensaje>"` y se traducen por su mensaje.
"""

from __future__ import annotations

from typing import Any

from app.core.mensajes import t

PLANTILLAS: dict[str, str] = {
    "missing": "Este campo es obligatorio.",
    "string_too_short": "Debe tener al menos {min_length} caracteres.",
    "string_too_long": "Puede tener como máximo {max_length} caracteres.",
    "too_short": "Debe tener al menos {min_length} elementos.",
    "too_long": "Puede tener como máximo {max_length} elementos.",
    "greater_than": "Debe ser mayor que {gt}.",
    "greater_than_equal": "Debe ser mayor o igual que {ge}.",
    "less_than": "Debe ser menor que {lt}.",
    "less_than_equal": "Debe ser menor o igual que {le}.",
    "string_pattern_mismatch": "El formato no es válido.",
    "literal_error": "Valor no permitido. Valores aceptados: {expected}.",
    "enum": "Valor no permitido. Valores aceptados: {expected}.",
    "string_type": "Debe ser un texto.",
    "int_parsing": "Debe ser un número entero.",
    "int_type": "Debe ser un número entero.",
    "float_parsing": "Debe ser un número.",
    "float_type": "Debe ser un número.",
    "bool_parsing": "Debe ser verdadero o falso.",
    "bool_type": "Debe ser verdadero o falso.",
    "uuid_parsing": "El identificador no es válido.",
    "uuid_type": "El identificador no es válido.",
    "datetime_parsing": "La fecha y hora no son válidas.",
    "datetime_from_date_parsing": "La fecha y hora no son válidas.",
    "date_parsing": "La fecha no es válida.",
    "date_from_datetime_parsing": "La fecha no es válida.",
    "time_parsing": "La hora no es válida.",
    "url_parsing": "La dirección web no es válida.",
    "url_scheme": "La dirección web debe empezar por http:// o https://.",
    "json_invalid": "El cuerpo de la petición no es JSON válido.",
    "extra_forbidden": "Este campo no está permitido.",
    "list_type": "Debe ser una lista.",
    "dict_type": "Debe ser un objeto.",
    "model_attributes_type": "Debe ser un objeto.",
    "decimal_parsing": "Debe ser un número.",
    "multiple_of": "Debe ser múltiplo de {multiple_of}.",
}

_PREFIJO_VALUE_ERROR = "Value error, "


def mensaje_de_validacion(error: dict[str, Any]) -> str:
    tipo = str(error.get("type", ""))
    contexto = dict(error.get("ctx") or {})
    if tipo == "value_error":
        mensaje = str(error.get("msg", ""))
        if mensaje.startswith(_PREFIJO_VALUE_ERROR):
            mensaje = mensaje[len(_PREFIJO_VALUE_ERROR) :]
        return t(mensaje)
    plantilla = PLANTILLAS.get(tipo)
    if plantilla is None:
        return str(error.get("msg", ""))
    return t(plantilla, **contexto)
