"""Validación de los datos de perfil contra los campos definidos por un rol."""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Protocol

from app.shared.errors import ValidationDomainError

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_URL = re.compile(r"^https?://\S+$")
_PHONE = re.compile(r"^[+0-9 ().-]{6,30}$")

# Topes por tipo de campo: estos datos los escriben también personas invitadas
# (la ficha de un ponente) y se sirven en su perfil público.
_LONGITUD_MAXIMA = {"text": 300, "textarea": 5000, "url": 500, "email": 254}


def _exigir_longitud(etiqueta: str, valor: str, maximo: int) -> None:
    if len(valor) > maximo:
        raise ValidationDomainError(
            "«{etiqueta}» admite como máximo {maximo} caracteres (tiene {longitud}).",
            params={"etiqueta": etiqueta, "maximo": maximo, "longitud": len(valor)},
        )


class FieldSpec(Protocol):
    """Definición de un campo, compatible con `RoleProfileField` y sus plantillas."""

    key: str
    label: str
    field_type: str
    is_required: bool
    options: dict[str, Any] | None


def _validar_valor(spec: FieldSpec, valor: Any) -> Any:
    etiqueta = spec.label
    tipo = spec.field_type

    if tipo in {"text", "textarea"}:
        if not isinstance(valor, str):
            raise ValidationDomainError(
                "«{etiqueta}» debe ser texto.", params={"etiqueta": etiqueta}
            )
        limpio = valor.strip()
        _exigir_longitud(etiqueta, limpio, _LONGITUD_MAXIMA[tipo])
        return limpio

    if tipo == "email":
        if not isinstance(valor, str) or not _EMAIL.match(valor.strip()):
            raise ValidationDomainError(
                "«{etiqueta}» debe ser un correo electrónico válido.", params={"etiqueta": etiqueta}
            )
        _exigir_longitud(etiqueta, valor.strip(), _LONGITUD_MAXIMA["email"])
        return valor.strip()

    if tipo == "url":
        if not isinstance(valor, str) or not _URL.match(valor.strip()):
            raise ValidationDomainError(
                "«{etiqueta}» debe ser una URL que empiece por http(s).",
                params={"etiqueta": etiqueta},
            )
        _exigir_longitud(etiqueta, valor.strip(), _LONGITUD_MAXIMA["url"])
        return valor.strip()

    if tipo == "phone":
        if not isinstance(valor, str) or not _PHONE.match(valor.strip()):
            raise ValidationDomainError(
                "«{etiqueta}» debe ser un teléfono válido.", params={"etiqueta": etiqueta}
            )
        return valor.strip()

    if tipo == "boolean":
        if not isinstance(valor, bool):
            raise ValidationDomainError(
                "«{etiqueta}» debe ser verdadero o falso.", params={"etiqueta": etiqueta}
            )
        return valor

    if tipo == "date":
        if not isinstance(valor, str):
            raise ValidationDomainError(
                "«{etiqueta}» debe ser una fecha ISO (AAAA-MM-DD).", params={"etiqueta": etiqueta}
            )
        try:
            date.fromisoformat(valor)
        except ValueError as exc:
            raise ValidationDomainError(
                "«{etiqueta}» debe ser una fecha ISO (AAAA-MM-DD).", params={"etiqueta": etiqueta}
            ) from exc
        return valor

    if tipo == "select":
        opciones = list((spec.options or {}).get("choices", []))
        if valor not in opciones:
            raise ValidationDomainError(
                "«{etiqueta}» debe ser uno de: {opciones}.",
                params={"etiqueta": etiqueta, "opciones": ", ".join(str(o) for o in opciones)},
            )
        return valor

    raise ValidationDomainError("Tipo de campo no soportado: {tipo}.", params={"tipo": tipo})


def validate_profile_data(
    campos: list[FieldSpec],
    datos: dict[str, Any] | None,
    *,
    enforce_required: bool = True,
) -> dict[str, Any]:
    """Valida y normaliza `profile_data`.

    Las claves desconocidas se rechazan en lugar de ignorarse: un dato que no
    corresponde a ningún campo suele ser un error del cliente, y aceptarlo dejaría
    basura en el JSONB que nadie volvería a mirar.

    `enforce_required=False` (fase 3 del plan de invitaciones): quien llega
    por invitación no rellena su ficha en el momento del alta — ni quien
    invita la conoce (una biografía de ponente, p. ej.), ni se le pide al
    aceptar. Los campos obligatorios del rol (`speaker.bio`) se completan
    después; exigirlos aquí haría imposible aceptar una invitación a un rol
    con algún campo obligatorio. El alta manual (`admin/members`) seguirá
    exigiéndolos: no cambia su llamada.
    """
    entrada = dict(datos or {})
    por_clave = {campo.key: campo for campo in campos}

    desconocidas = sorted(set(entrada) - set(por_clave))
    if desconocidas:
        raise ValidationDomainError(
            "Campos no definidos para este rol: {campos}.",
            params={"campos": ", ".join(desconocidas)},
            extra={"campos_desconocidos": desconocidas},
        )

    resultado: dict[str, Any] = {}
    for clave, campo in por_clave.items():
        if clave not in entrada or entrada[clave] in (None, ""):
            if campo.is_required and enforce_required:
                raise ValidationDomainError(
                    "«{etiqueta}» es obligatorio.", params={"etiqueta": campo.label}
                )
            continue
        resultado[clave] = _validar_valor(campo, entrada[clave])
    return resultado
