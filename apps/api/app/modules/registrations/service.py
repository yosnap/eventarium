"""Lógica de inscripción de asistentes: alta pública y verificación de correo.

Aprobación bajo demanda, lista de espera con promoción automática y las
emails restantes son de las fases 3 y 4 de trabajo; esta fase entrega el alta
completa hasta el punto en que la inscripción queda `confirmed`,
`pending_approval` o `waitlisted`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tasks import send_registration_verification_email
from app.modules.auth.verification import (
    PROPOSITO_VERIFICACION_INSCRIPCION,
    consume_token,
    generate_token,
)
from app.modules.events.models import Event
from app.modules.registrations import repository
from app.modules.registrations.models import (
    EventRegistration,
    EventRegistrationAnswer,
    EventRegistrationConsent,
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
            raise ValidationDomainError(f"La respuesta a «{pregunta.label}» debe ser texto.")
        texto = valor.strip()
        if not texto:
            return None
        if len(texto) > _LONGITUD_MAXIMA_TEXTO_LIBRE:
            raise ValidationDomainError(f"La respuesta a «{pregunta.label}» es demasiado larga.")
        return texto

    opciones = set(pregunta.options or [])

    if pregunta.type == "single_choice":
        if valor is None:
            return None
        if not isinstance(valor, str) or valor not in opciones:
            raise ValidationDomainError(
                f"La respuesta a «{pregunta.label}» no es una opción válida."
            )
        return valor

    # multiple_choice
    if valor is None:
        return None
    if not isinstance(valor, list) or not all(isinstance(elemento, str) for elemento in valor):
        raise ValidationDomainError(
            f"La respuesta a «{pregunta.label}» debe ser una lista de opciones."
        )
    if not set(valor).issubset(opciones):
        raise ValidationDomainError(
            f"La respuesta a «{pregunta.label}» incluye una opción no válida."
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
                f"La pregunta «{pregunta.label}» tiene más de una respuesta."
            )
        vistas.add(question_id)

        valor = _validar_valor(pregunta, respuesta.value)
        if valor is not None:
            respondidas.add(question_id)
            validadas.append(_RespuestaValidada(question_id=question_id, value=valor))

    for pregunta in preguntas:
        if pregunta.required and pregunta.id not in respondidas:
            raise ValidationDomainError(f"La pregunta «{pregunta.label}» es obligatoria.")

    return validadas


async def _evaluar_estado_por_aforo(session: AsyncSession, evento: Event) -> str:
    """Estado inicial de una inscripción ya verificada (o sin verificación exigida).

    Función única reutilizada por el alta sin verificación y por la
    verificación posterior — evita dos implementaciones paralelas de la misma
    regla de aforo, que es justo el tipo de duplicación que introduciría un
    desajuste silencioso entre ambos caminos.
    """
    if evento.registration_mode == "approval":
        return "pending_approval"
    if evento.capacity is None:
        return "confirmed"
    confirmados = await repository.count_confirmed_registrations(
        session, evento.organization_id, evento.id
    )
    return "confirmed" if confirmados < evento.capacity else "waitlisted"


async def submit_registration(
    session: AsyncSession,
    *,
    event: Event,
    email: str,
    full_name: str,
    answers: list[RegistrationAnswerInput],
    data_processing_accepted: bool,
    marketing_accepted: bool,
    recording_accepted: bool,
) -> None:
    """Da de alta una inscripción, o reencola el correo si el email ya existía.

    Nunca revela al llamador anónimo si el email ya estaba inscrito: la
    respuesta pública del router es siempre la misma pase lo que pase aquí
    dentro (mismo principio que `auth.service.register_user`).
    """
    if event.registration_mode == "paid":
        raise ValidationDomainError(
            "Este evento requiere pago; la inscripción todavía no está disponible."
        )
    if not data_processing_accepted:
        raise ValidationDomainError("Debes aceptar el tratamiento de datos para inscribirte.")

    email_normalizado = email.strip().lower()
    nombre = full_name.strip()

    preguntas = await repository.get_questions(session, event.organization_id, event.id)
    respuestas_validas = _validar_respuestas(preguntas, answers)

    existente = await repository.get_registration_by_event_and_email(
        session, event.organization_id, event.id, email_normalizado
    )
    if existente is not None:
        if existente.status == "pending_verification":
            token = await generate_token(PROPOSITO_VERIFICACION_INSCRIPCION, str(existente.id))
            await send_registration_verification_email.kiq(
                email_normalizado, token, str(event.organization_id)
            )
        # Los demás estados no tienen plantilla de correo todavía (llegan en la
        # fase 4 de trabajo); la respuesta pública es la misma en cualquier caso.
        return

    user_id = await repository.find_user_id_by_email(session, email_normalizado)
    ahora = datetime.now(UTC)

    if event.email_verification_required:
        estado_inicial = "pending_verification"
    else:
        evento_bloqueado = await repository.lock_event_for_capacity(
            session, event.organization_id, event.id
        )
        estado_inicial = await _evaluar_estado_por_aforo(session, evento_bloqueado)

    inscripcion = EventRegistration(
        event_id=event.id,
        organization_id=event.organization_id,
        email=email_normalizado,
        full_name=nombre,
        user_id=user_id,
        status=estado_inicial,
        confirmed_at=ahora if estado_inicial == "confirmed" else None,
    )
    session.add(inscripcion)
    try:
        await session.flush()
    except IntegrityError:
        # Condición de carrera: otra petición con el mismo email ganó entre la
        # comprobación de arriba y este `flush`. El `UNIQUE(event_id, email)`
        # es la única fuente de verdad; misma respuesta pública que si hubiera
        # entrado por la rama de "ya existe".
        return

    for respuesta in respuestas_validas:
        session.add(
            EventRegistrationAnswer(
                registration_id=inscripcion.id,
                question_id=respuesta.question_id,
                organization_id=event.organization_id,
                value=respuesta.value,
            )
        )

    session.add(
        EventRegistrationConsent(
            registration_id=inscripcion.id,
            organization_id=event.organization_id,
            data_processing_accepted_at=ahora,
            marketing_accepted_at=ahora if marketing_accepted else None,
            recording_accepted_at=ahora if recording_accepted else None,
        )
    )

    if estado_inicial == "pending_verification":
        token = await generate_token(PROPOSITO_VERIFICACION_INSCRIPCION, str(inscripcion.id))
        await send_registration_verification_email.kiq(
            email_normalizado, token, str(event.organization_id)
        )


async def verify_registration(session: AsyncSession, *, token: str) -> EventRegistration:
    """Consume el token de verificación y evalúa el estado siguiente.

    `session.get()` ya aplica RLS: un token válido de otra organización (que
    nunca debería llegar aquí, pero por si acaso) simplemente no encuentra la
    fila, y cae en el mismo error genérico que un token caducado o inventado.
    """
    bruto = await consume_token(PROPOSITO_VERIFICACION_INSCRIPCION, token)
    if bruto is None:
        raise ValidationDomainError("El enlace de verificación no es válido o ha caducado.")

    registration_id = uuid.UUID(bruto)
    inscripcion = await session.get(EventRegistration, registration_id)
    if inscripcion is None or inscripcion.status != "pending_verification":
        raise ValidationDomainError("El enlace de verificación no es válido o ha caducado.")

    ahora = datetime.now(UTC)
    inscripcion.verified_at = ahora

    evento = await repository.lock_event_for_capacity(
        session, inscripcion.organization_id, inscripcion.event_id
    )
    nuevo_estado = await _evaluar_estado_por_aforo(session, evento)
    inscripcion.status = nuevo_estado
    if nuevo_estado == "confirmed":
        inscripcion.confirmed_at = ahora
    return inscripcion
