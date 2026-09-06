"""Validación de los datos de perfil contra los campos definidos por un rol."""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Protocol

from app.shared.errors import ValidationDomainError

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_URL = re.compile(r"^https?://\S+$")
_PHONE = re.compile(r"^[+0-9 ().-]{6,30}$")


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
            raise ValidationDomainError(f"«{etiqueta}» debe ser texto.")
        return valor.strip()

    if tipo == "email":
        if not isinstance(valor, str) or not _EMAIL.match(valor.strip()):
            raise ValidationDomainError(f"«{etiqueta}» debe ser un correo electrónico válido.")
        return valor.strip()

    if tipo == "url":
        if not isinstance(valor, str) or not _URL.match(valor.strip()):
            raise ValidationDomainError(f"«{etiqueta}» debe ser una URL que empiece por http(s).")
        return valor.strip()

    if tipo == "phone":
        if not isinstance(valor, str) or not _PHONE.match(valor.strip()):
            raise ValidationDomainError(f"«{etiqueta}» debe ser un teléfono válido.")
        return valor.strip()

    if tipo == "boolean":
        if not isinstance(valor, bool):
            raise ValidationDomainError(f"«{etiqueta}» debe ser verdadero o falso.")
        return valor

    if tipo == "date":
        if not isinstance(valor, str):
            raise ValidationDomainError(f"«{etiqueta}» debe ser una fecha ISO (AAAA-MM-DD).")
        try:
            date.fromisoformat(valor)
        except ValueError as exc:
            raise ValidationDomainError(
                f"«{etiqueta}» debe ser una fecha ISO (AAAA-MM-DD)."
            ) from exc
        return valor

    if tipo == "select":
        opciones = list((spec.options or {}).get("choices", []))
        if valor not in opciones:
            raise ValidationDomainError(
                f"«{etiqueta}» debe ser uno de: {', '.join(str(o) for o in opciones)}."
            )
        return valor

    raise ValidationDomainError(f"Tipo de campo no soportado: {tipo}.")


def validate_profile_data(campos: list[FieldSpec], datos: dict[str, Any] | None) -> dict[str, Any]:
    """Valida y normaliza `profile_data`.

    Las claves desconocidas se rechazan en lugar de ignorarse: un dato que no
    corresponde a ningún campo suele ser un error del cliente, y aceptarlo dejaría
    basura en el JSONB que nadie volvería a mirar.
    """
    entrada = dict(datos or {})
    por_clave = {campo.key: campo for campo in campos}

    desconocidas = sorted(set(entrada) - set(por_clave))
    if desconocidas:
        raise ValidationDomainError(
            f"Campos no definidos para este rol: {', '.join(desconocidas)}.",
            extra={"campos_desconocidos": desconocidas},
        )

    resultado: dict[str, Any] = {}
    for clave, campo in por_clave.items():
        if clave not in entrada or entrada[clave] in (None, ""):
            if campo.is_required:
                raise ValidationDomainError(f"«{campo.label}» es obligatorio.")
            continue
        resultado[clave] = _validar_valor(campo, entrada[clave])
    return resultado
