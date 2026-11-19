"""Validación de las respuestas al formulario de inscripción contra sus preguntas."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from app.modules.registrations.models import (
    EventRegistrationQuestion,
)
from app.modules.registrations.schemas import RegistrationAnswerInput
from app.shared.errors import ValidationDomainError

# Límite de longitud para una respuesta de texto libre: no hay columna que lo
# imponga (es `jsonb`), así que se acota aquí para no aceptar payloads enormes.
_LONGITUD_MAXIMA_TEXTO_LIBRE = 2000


@dataclass(frozen=True, slots=True)
class _RespuestaValidada:
    question_id: uuid.UUID
    value: Any


def _validar_valor(pregunta: EventRegistrationQuestion, valor: object) -> Any | None:
    """Normaliza y valida una respuesta contra el tipo de su pregunta.

    Devuelve `None` cuando la respuesta está vacía (nunca se guarda una
    respuesta vacía como si fuera una fila real).
    """
    if pregunta.type == "short_text":
        if valor is None:
            return None
        if not isinstance(valor, str):
            raise ValidationDomainError(
                "La respuesta a «{pregunta}» debe ser texto.", params={"pregunta": pregunta.label}
            )
        texto = valor.strip()
        if not texto:
            return None
        if len(texto) > _LONGITUD_MAXIMA_TEXTO_LIBRE:
            raise ValidationDomainError(
                "La respuesta a «{pregunta}» es demasiado larga.",
                params={"pregunta": pregunta.label},
            )
        return texto

    opciones = set(pregunta.options or [])

    if pregunta.type == "single_choice":
        if valor is None:
            return None
        if not isinstance(valor, str) or valor not in opciones:
            raise ValidationDomainError(
                "La respuesta a «{pregunta}» no es una opción válida.",
                params={"pregunta": pregunta.label},
            )
        return valor

    # multiple_choice
    if valor is None:
        return None
    if not isinstance(valor, list) or not all(isinstance(elemento, str) for elemento in valor):
        raise ValidationDomainError(
            "La respuesta a «{pregunta}» debe ser una lista de opciones.",
            params={"pregunta": pregunta.label},
        )
    if not set(valor).issubset(opciones):
        raise ValidationDomainError(
            "La respuesta a «{pregunta}» incluye una opción no válida.",
            params={"pregunta": pregunta.label},
        )
    return valor or None


def _validar_respuestas(
    preguntas: list[EventRegistrationQuestion], respuestas: list[RegistrationAnswerInput]
) -> list[_RespuestaValidada]:
    preguntas_por_id = {pregunta.id: pregunta for pregunta in preguntas}

    vistas: set[uuid.UUID] = set()
    respondidas: set[uuid.UUID] = set()
    validadas: list[_RespuestaValidada] = []

    for respuesta in respuestas:
        try:
            question_id = uuid.UUID(respuesta.question_id)
        except ValueError as exc:
            raise ValidationDomainError(
                "Una de las respuestas no corresponde a ninguna pregunta de este evento."
            ) from exc

        pregunta = preguntas_por_id.get(question_id)
        if pregunta is None:
            raise ValidationDomainError(
                "Una de las respuestas no corresponde a ninguna pregunta de este evento."
            )
        if question_id in vistas:
            raise ValidationDomainError(
                "La pregunta «{pregunta}» tiene más de una respuesta.",
                params={"pregunta": pregunta.label},
            )
        vistas.add(question_id)

        valor = _validar_valor(pregunta, respuesta.value)
        if valor is not None:
            respondidas.add(question_id)
            validadas.append(_RespuestaValidada(question_id=question_id, value=valor))

    for pregunta in preguntas:
        if pregunta.required and pregunta.id not in respondidas:
            raise ValidationDomainError(
                "La pregunta «{pregunta}» es obligatoria.", params={"pregunta": pregunta.label}
            )

    return validadas
