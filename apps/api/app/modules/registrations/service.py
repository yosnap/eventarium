"""Lógica de inscripción de asistentes: alta, verificación, aprobación, lista
de espera con promoción automática, emails transaccionales y autocancelación
(fases 2, 3 y 4 de trabajo de la fase 3 del PRD)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import maintenance_session
from app.core.tasks import (
    process_refunds_task,
    send_registration_cancelled_email,
    send_registration_confirmed_email,
    send_registration_rejected_email,
    send_registration_verification_email,
    send_registration_waitlisted_email,
    send_waitlist_promotion_email,
)
from app.modules.auth.verification import (
    PROPOSITO_CANCELACION_INSCRIPCION,
    PROPOSITO_PROMOCION_LISTA_ESPERA,
    PROPOSITO_VERIFICACION_INSCRIPCION,
    consume_token,
    generate_token,
)
from app.modules.events.models import Event
from app.modules.payments import refunds_service as payments_refunds_service
from app.modules.payments import repository as payments_repository
from app.modules.registrations import repository
from app.modules.registrations.models import (
    EventRegistration,
    EventRegistrationAnswer,
    EventRegistrationConsent,
    EventRegistrationQuestion,
)
from app.modules.registrations.schemas import RegistrationAnswerInput
from app.modules.tickets.service import emitir_entrada, generar_token_qr, revocar_entrada
from app.shared.errors import ConflictError, NotFoundError, ValidationDomainError

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


async def _estado_confirmable(
    session: AsyncSession, evento: Event, registration_id: uuid.UUID | None
) -> str:
    """`"confirmed"` salvo que el evento sea de pago y no exista todavía un
    `event_payments` en `paid` para esta inscripción — en cuyo caso
    `"pending_payment"` (fase 6 del PRD, hallazgo #1 de su red-team).

    Capa 1 de la guarda de pago: invocada desde los dos `return "confirmed"`
    de `_evaluar_estado_por_capacidad` (cubre alta, verificación y
    aprobación, los tres caminos que desembocan ahí) y desde
    `confirm_waitlist_promotion` (el cuarto camino, que asignaba `"confirmed"`
    directamente). `registration_id=None` en el alta —la fila todavía no
    existe— siempre da `"pending_payment"`: nadie ha podido pagar antes de
    inscribirse.
    """
    if evento.registration_mode != "paid":
        return "confirmed"
    if registration_id is None:
        return "pending_payment"
    tiene_pago = await payments_repository.tiene_pago_confirmado(
        session, evento.organization_id, registration_id
    )
    return "confirmed" if tiene_pago else "pending_payment"


async def _evaluar_estado_por_capacidad(
    session: AsyncSession, evento: Event, *, registration_id: uuid.UUID | None
) -> str:
    """`pending_payment`/`confirmed` o `waitlisted` por aforo, sin mirar el
    modo de aprobación — usada tanto por el alta/verificación (a través de
    `_evaluar_estado_por_aforo`) como por `approve_registration`, que ya sabe
    que está saliendo de `pending_approval` y no debe volver a evaluarlo.

    Cuenta `confirmed` **y** `pending_payment` vigente **y** promociones de
    lista de espera todavía dentro de su ventana
    (`count_reserved_registrations`): las tres ocupan un hueco real de
    aforo, aunque la persona todavía no haya pagado ni confirmado. Sin esto,
    una verificación o aprobación concurrente podría colarse en un hueco ya
    reservado por una compra en curso.

    `registration_id` se propaga a `_estado_confirmable` (capa 1 de la
    guarda de pago, hallazgo #1): un evento `paid` nunca sale de aquí en
    `"confirmed"` sin un pago ya verificado.
    """
    if evento.capacity is None:
        return await _estado_confirmable(session, evento, registration_id)
    reservadas = await repository.count_reserved_registrations(
        session, evento.organization_id, evento.id
    )
    if reservadas < evento.capacity:
        return await _estado_confirmable(session, evento, registration_id)
    return "waitlisted"


async def _evaluar_estado_por_aforo(
    session: AsyncSession, evento: Event, *, registration_id: uuid.UUID | None
) -> str:
    """Estado inicial de una inscripción ya verificada (o sin verificación exigida).

    Función única reutilizada por el alta sin verificación y por la
    verificación posterior — evita dos implementaciones paralelas de la misma
    regla de aforo, que es justo el tipo de duplicación que introduciría un
    desajuste silencioso entre ambos caminos.
    """
    if evento.registration_mode == "approval":
        return "pending_approval"
    return await _evaluar_estado_por_capacidad(session, evento, registration_id=registration_id)


def _ttl_cancelacion() -> timedelta:
    return timedelta(days=get_settings().registration_cancel_token_ttl_days)


async def _generar_token_cancelacion(registration_id: uuid.UUID) -> str:
    """El token se genera cada vez que se encola un email que lo ofrece, nunca
    una sola vez al confirmar — así una persona `waitlisted` también puede
    cancelar, no solo una `confirmed` (decisión #5 del PRD)."""
    return await generate_token(
        PROPOSITO_CANCELACION_INSCRIPCION, str(registration_id), ttl=_ttl_cancelacion()
    )


async def _enviar_email_por_estado(session: AsyncSession, inscripcion: EventRegistration) -> None:
    """Encola el email de confirmación o de lista de espera según el estado
    ya asignado a `inscripcion` — usado por el alta sin verificación, la
    verificación posterior, la aprobación manual y la promoción de lista de
    espera, para no repetir esta decisión en cada llamador.

    Es también el único punto por el que pasan los cuatro caminos que pueden
    dejar una inscripción en `confirmed` (fase 4 del PRD): emitir la entrada
    aquí, no en cada llamador, cubre los cuatro de una vez. `emitir_entrada` es
    idempotente, así que el reenvío del formulario con un email ya
    `confirmed` (que no es una confirmación nueva) no crea una segunda
    entrada.

    Cinturón de seguridad (capa 2 de la guarda de pago, fase 6 del PRD,
    hallazgo #1): antes de emitir, si la inscripción está `confirmed` y su
    evento es de pago, exige un `event_payments` en `paid`. La capa 1
    (`_estado_confirmable`) ya impide que los cuatro caminos conocidos
    lleguen aquí en ese estado sin haber pagado; esta capa protege el quinto
    camino que alguien escriba más adelante, en el único sitio por el que
    necesariamente tiene que pasar.
    """
    token_cancelacion = await _generar_token_cancelacion(inscripcion.id)
    organization_id = str(inscripcion.organization_id)
    if inscripcion.status == "confirmed":
        evento = await session.get(Event, inscripcion.event_id)
        if evento is not None and evento.registration_mode == "paid":
            tiene_pago = await payments_repository.tiene_pago_confirmado(
                session, inscripcion.organization_id, inscripcion.id
            )
            if not tiene_pago:
                raise ValidationDomainError(
                    "No se puede confirmar una inscripción de un evento de pago sin un "
                    "pago verificado."
                )
        ticket = await emitir_entrada(session, inscripcion)
        await send_registration_confirmed_email.kiq(
            inscripcion.email, organization_id, token_cancelacion, generar_token_qr(ticket)
        )
    elif inscripcion.status == "waitlisted":
        await send_registration_waitlisted_email.kiq(
            inscripcion.email, organization_id, token_cancelacion
        )


async def _reservar_ventana_de_pago(
    session: AsyncSession, evento: Event, inscripcion: EventRegistration
) -> None:
    """Fija `payment_expires_at` al llegar a `pending_payment` fuera del alta
    directa: verificación de email, aprobación manual o promoción de lista de
    espera (caminos 2, 3 y 4 de la guarda de pago, fase 6 del PRD).

    Exige que ya exista un `event_payments` en `pending` para esta
    inscripción — creado por `checkout_service.iniciar_compra` en el alta,
    el único punto que conoce el tipo de entrada y el código de descuento que
    la persona eligió. Sin esa fila no hay nada que cobrar: dejar pasar la
    inscripción a `pending_payment` de todos modos la dejaría colgada para
    siempre, sin enlace de pago ni caducidad (nunca aparecería en
    `pagos_sin_enlace_entregado` ni en `pagos_pendientes_caducados`, que
    parten ambas de `event_payments`).
    """
    pago = await payments_repository.get_payment_by_registration(
        session, evento.organization_id, inscripcion.id
    )
    if pago is None or pago.status != "pending":
        raise ConflictError(
            "No se puede confirmar el pago pendiente de una inscripción sin una compra "
            "de entrada ya iniciada."
        )
    ventana = timedelta(minutes=evento.payment_checkout_window_minutes)
    inscripcion.payment_expires_at = datetime.now(UTC) + ventana


async def _promote_next_waitlisted(session: AsyncSession, evento: Event) -> None:
    """Promueve a la primera persona en lista de espera, si hay alguna.

    Marca la ventana de promoción y encola el email con el enlace de
    confirmación (`waitlist_promotion_confirm`) y el de autocancelación
    (`registration_cancel`), cada uno con su propio TTL.
    """
    siguiente = await repository.get_oldest_waitlisted(session, evento.organization_id, evento.id)
    if siguiente is None:
        return
    ahora = datetime.now(UTC)
    ventana = timedelta(hours=get_settings().waitlist_promotion_window_hours)
    siguiente.waitlist_promoted_at = ahora
    siguiente.waitlist_promotion_expires_at = ahora + ventana
    confirm_token = await generate_token(
        PROPOSITO_PROMOCION_LISTA_ESPERA, str(siguiente.id), ttl=ventana
    )
    cancel_token = await _generar_token_cancelacion(siguiente.id)
    await send_waitlist_promotion_email.kiq(
        siguiente.email,
        str(siguiente.organization_id),
        confirm_token,
        cancel_token,
        (ahora + ventana).strftime("%d/%m/%Y %H:%M"),
    )


async def _cancelar_inscripcion(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    inscripcion: EventRegistration,
) -> bool:
    """Núcleo compartido de la cancelación: por el organizador o por
    autocancelación pública. Marca `cancelled`, envía el email y, si liberaba
    una plaza reservada, promueve a la lista de espera.

    Devuelve `False` sin hacer nada si ya estaba `cancelled`/`rejected` — el
    llamador decide si eso es un 409 (panel) o un no-op silencioso (enlace
    público, de un solo uso salvo que existan varios tokens vigentes).

    Antes de cambiar el estado (fase 6 del PRD, fase 5 de trabajo): si hay un
    `event_payments` con importe pendiente, persiste una intención de
    reembolso en el outbox (`event_payment_refunds`) — nunca llama a Stripe
    aquí. Los dos llamadores reales (`cancel_registration`,
    `cancel_registration_by_token`) ya tienen la fila de la inscripción
    bloqueada (`FOR UPDATE`) antes de entrar, así que cualquier llamada de
    red en esta función ocurriría con ese bloqueo abierto (hallazgo #12).
    """
    if inscripcion.status in ("cancelled", "rejected"):
        return False

    reembolso = await payments_refunds_service.preparar_reembolso_por_cancelacion(
        session,
        organization_id=organization_id,
        event_id=event_id,
        registration_id=inscripcion.id,
    )
    # `preparar_reembolso_por_cancelacion` solo actúa sobre pagos ya cobrados
    # (`ESTADOS_REEMBOLSABLES`): un pago todavía `pending` (p. ej. una
    # inscripción `pending_payment` cancelada por el organizador antes de
    # pagar) no pasa por ahí y quedaría reteniendo cupo/uso de código para
    # siempre (hallazgo IMP-1 del code review de la fase 6, ronda 3). No-op
    # si ya está `expired` — el barrido de caducados (`expirar_pagos_pendientes`)
    # ya lo deja así antes de llamar a esta misma función.
    await payments_repository.expirar_pago_pendiente_de_inscripcion(
        session, organization_id, inscripcion.id
    )

    # Antes de cambiar el estado: una entrada revocada nunca es válida al
    # escanear, aunque el JWT no haya caducado (fase 4 del PRD). No-op si la
    # inscripción nunca tuvo entrada (`waitlisted`/`pending_approval`).
    await revocar_entrada(session, organization_id=organization_id, registration_id=inscripcion.id)

    # Una plaza está reservada si está `confirmed`, si está `waitlisted` en
    # mitad de una promoción, o si está `pending_payment` (fase 6 del PRD,
    # hallazgo #5) — mismo predicado de estado que usa
    # `count_reserved_registrations` para decidir si una fila ocupa un hueco.
    # Sin condición de vigencia aquí (igual que la rama `waitlisted`, que
    # tampoco la lleva): esta función cancela la fila en el mismo instante en
    # que decide liberar el hueco —incluida la que llama el barrido sobre una
    # compra que **acaba** de caducar—, así que la plaza estaba reservada
    # hasta este preciso momento. Si una cuenta la plaza y la otra no la
    # libera, el aforo se pierde en silencio en cuanto caduca o se cancela la
    # primera compra.
    liberaba_una_plaza = inscripcion.status in ("confirmed", "pending_payment") or (
        inscripcion.status == "waitlisted" and inscripcion.waitlist_promoted_at is not None
    )
    inscripcion.status = "cancelled"
    inscripcion.cancelled_at = datetime.now(UTC)
    await send_registration_cancelled_email.kiq(inscripcion.email, str(organization_id), reembolso)

    if reembolso == "en_curso":
        # Encolado al vuelo (además del cron `*/2 * * * *`): la persona no
        # tiene que esperar hasta dos minutos para que se dispare el intento
        # de reembolso. Nunca bajo el bloqueo de la inscripción: `.kiq()` solo
        # encola el mensaje, no ejecuta la tarea aquí.
        await process_refunds_task.kiq()

    if liberaba_una_plaza:
        evento = await repository.lock_event_for_capacity(session, organization_id, event_id)
        await _promote_next_waitlisted(session, evento)
    return True


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
) -> EventRegistration | None:
    """Da de alta una inscripción, o reencola el correo si el email ya existía.

    Nunca revela al llamador anónimo si el email ya estaba inscrito: la
    respuesta pública del router es siempre la misma pase lo que pase aquí
    dentro (mismo principio que `auth.service.register_user`).

    Devuelve la inscripción cuando esta llamada la crea o la reactiva (fase 6
    del PRD, fase 4 de trabajo): el endpoint de compra pública lo necesita
    para saber si tiene que crear una Checkout Session sin volver a
    consultar. Devuelve `None` en la rama de «ya existía y no es reactivable»
    y en la carrera de `IntegrityError` — ninguno de los dos casos requiere
    una sesión de pago nueva.
    """
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
        # Reintento tras caducar (hallazgo #7): una compra abandonada de un
        # evento de pago que nunca llegó a moverse dinero (su pago sigue en
        # `pending`/`expired`) se reactiva en vez de bloquear a la persona
        # para siempre contra el `UNIQUE(event_id, email)`. Reutiliza la
        # misma fila de `event_registrations`; la fila de `event_payments` la
        # reutiliza `payments.checkout_service` con la misma condición.
        if (
            event.registration_mode == "paid"
            and existente.status == "cancelled"
            and await payments_repository.pago_reactivable(
                session, event.organization_id, existente.id
            )
        ):
            evento_bloqueado = await repository.lock_event_for_capacity(
                session, event.organization_id, event.id
            )
            nuevo_estado = await _evaluar_estado_por_aforo(
                session, evento_bloqueado, registration_id=existente.id
            )
            ahora = datetime.now(UTC)
            existente.status = nuevo_estado
            existente.cancelled_at = None
            existente.confirmed_at = ahora if nuevo_estado == "confirmed" else None
            await _enviar_email_por_estado(session, existente)
            return existente

        # Reenvía siempre el email que corresponda al estado actual (decisión
        # #1 del PRD, fase 3) — la respuesta pública es la misma en cualquier
        # caso, nunca revela en qué estado está la inscripción existente.
        if existente.status == "pending_verification":
            token = await generate_token(PROPOSITO_VERIFICACION_INSCRIPCION, str(existente.id))
            await send_registration_verification_email.kiq(
                email_normalizado, token, str(event.organization_id)
            )
        elif existente.status in ("confirmed", "waitlisted"):
            await _enviar_email_por_estado(session, existente)
        elif existente.status == "rejected":
            await send_registration_rejected_email.kiq(existente.email, str(event.organization_id))
        elif existente.status == "cancelled":
            await send_registration_cancelled_email.kiq(existente.email, str(event.organization_id))
        # `pending_approval`/`pending_payment`: sin plantilla propia, igual
        # que en el alta normal.
        return None

    user_id = await repository.find_user_id_by_email(session, email_normalizado)
    ahora = datetime.now(UTC)

    if event.email_verification_required:
        estado_inicial = "pending_verification"
    else:
        evento_bloqueado = await repository.lock_event_for_capacity(
            session, event.organization_id, event.id
        )
        estado_inicial = await _evaluar_estado_por_aforo(
            session, evento_bloqueado, registration_id=None
        )

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
        return None

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
    else:
        await _enviar_email_por_estado(session, inscripcion)
    return inscripcion


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
    nuevo_estado = await _evaluar_estado_por_aforo(session, evento, registration_id=inscripcion.id)
    inscripcion.status = nuevo_estado
    if nuevo_estado == "confirmed":
        inscripcion.confirmed_at = ahora
    elif nuevo_estado == "pending_payment":
        await _reservar_ventana_de_pago(session, evento, inscripcion)
    await _enviar_email_por_estado(session, inscripcion)
    return inscripcion


# --- Panel de organizador: aprobación, rechazo, cancelación ------------------


async def approve_registration(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    registration_id: uuid.UUID,
) -> EventRegistration:
    """Aprueba una inscripción `pending_approval`, revaluando aforo en ese momento.

    Comparte la misma sección crítica (`lock_event_for_capacity`) que la
    verificación automática, para no confirmar por encima de `capacity` desde
    dos caminos distintos.
    """
    inscripcion = await repository.get_registration(
        session, organization_id, event_id, registration_id
    )
    if inscripcion is None:
        raise NotFoundError("La inscripción no existe.")
    if inscripcion.status != "pending_approval":
        raise ConflictError("Solo se puede aprobar una inscripción pendiente de aprobación.")

    evento = await repository.lock_event_for_capacity(session, organization_id, event_id)
    ahora = datetime.now(UTC)
    inscripcion.approved_at = ahora
    inscripcion.status = await _evaluar_estado_por_capacidad(
        session, evento, registration_id=inscripcion.id
    )
    if inscripcion.status == "confirmed":
        inscripcion.confirmed_at = ahora
    elif inscripcion.status == "pending_payment":
        await _reservar_ventana_de_pago(session, evento, inscripcion)
    await _enviar_email_por_estado(session, inscripcion)
    return inscripcion


async def reject_registration(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    registration_id: uuid.UUID,
) -> EventRegistration:
    """Rechaza una inscripción `pending_approval`.

    Solo válida desde `pending_approval`, que nunca llegó a ocupar una plaza
    `confirmed` — a diferencia de `cancel_registration`, rechazar nunca libera
    aforo ni dispara una promoción de lista de espera.

    Sí libera el pago (hallazgo IMP-1 del code review de la fase 6, ronda 3):
    `checkout_service.iniciar_compra` ya deja un `event_payments` en
    `pending` para una inscripción `pending_approval` (hallazgo C1), y
    ninguna ventana de tiempo lo iba a expirar nunca si la aprobación
    terminaba en rechazo — `expirar_pago_pendiente_de_inscripcion` es un
    no-op si el evento es gratuito y nunca hubo pago que crear.
    """
    inscripcion = await repository.get_registration(
        session, organization_id, event_id, registration_id
    )
    if inscripcion is None:
        raise NotFoundError("La inscripción no existe.")
    if inscripcion.status != "pending_approval":
        raise ConflictError("Solo se puede rechazar una inscripción pendiente de aprobación.")

    await payments_repository.expirar_pago_pendiente_de_inscripcion(
        session, organization_id, inscripcion.id
    )
    inscripcion.status = "rejected"
    inscripcion.rejected_at = datetime.now(UTC)
    await send_registration_rejected_email.kiq(inscripcion.email, str(organization_id))
    return inscripcion


async def cancel_registration(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    registration_id: uuid.UUID,
) -> EventRegistration:
    """Cancela una inscripción desde el panel de organizador.

    Si liberaba una plaza reservada, promueve a la primera persona en lista
    de espera. Bloquea la fila de la inscripción (`get_registration_for_update`)
    antes de decidir: dos cancelaciones concurrentes de la misma inscripción
    no deben poder promover dos veces para un único hueco liberado.
    """
    inscripcion = await repository.get_registration_for_update(
        session, organization_id, event_id, registration_id
    )
    if inscripcion is None:
        raise NotFoundError("La inscripción no existe.")
    if inscripcion.status in ("cancelled", "rejected"):
        raise ConflictError("La inscripción ya está cancelada o rechazada.")

    await _cancelar_inscripcion(
        session, organization_id=organization_id, event_id=event_id, inscripcion=inscripcion
    )
    return inscripcion


async def cancel_registration_by_token(session: AsyncSession, *, token: str) -> None:
    """Autocancelación pública: consume el token de un solo uso (`GETDEL`) y
    aplica la misma cancelación que el panel de organizador.

    Idempotente si la inscripción ya estaba `cancelled`/`rejected` (puede
    haber varios tokens vigentes para la misma inscripción, uno por cada
    email enviado): no es un error, simplemente no hace nada más.
    """
    bruto = await consume_token(PROPOSITO_CANCELACION_INSCRIPCION, token)
    if bruto is None:
        raise ValidationDomainError("El enlace de cancelación no es válido o ha caducado.")

    registration_id = uuid.UUID(bruto)
    # `with_for_update=True`: mismo motivo que `get_registration_for_update`
    # del panel — dos tokens de cancelación vigentes para la misma
    # inscripción no deben poder promover dos veces un único hueco liberado.
    inscripcion = await session.get(EventRegistration, registration_id, with_for_update=True)
    if inscripcion is None:
        return

    await _cancelar_inscripcion(
        session,
        organization_id=inscripcion.organization_id,
        event_id=inscripcion.event_id,
        inscripcion=inscripcion,
    )


async def confirm_waitlist_promotion(session: AsyncSession, *, token: str) -> EventRegistration:
    """Consume el token de una promoción de lista de espera y confirma la plaza.

    Sin bloqueo de aforo: la plaza ya quedó reservada para esta persona en el
    momento de la promoción (`_promote_next_waitlisted`), nadie más puede
    disputársela mientras está `waitlisted` con `waitlist_promoted_at` fijado.

    Cuarto camino de la guarda de pago (fase 6 del PRD, hallazgo #1): no pasa
    por `_evaluar_estado_por_aforo` ni por `_evaluar_estado_por_capacidad`
    (la plaza ya está reservada, no hay aforo que revaluar), así que llama a
    `_estado_confirmable` directamente en vez de asignar `"confirmed"` a
    pelo. En un evento de pago, la promoción reserva la plaza y pide el
    pago: pasa a `pending_payment`, no a `confirmed`.
    """
    bruto = await consume_token(PROPOSITO_PROMOCION_LISTA_ESPERA, token)
    if bruto is None:
        raise ValidationDomainError("El enlace de confirmación no es válido o ha caducado.")

    registration_id = uuid.UUID(bruto)
    inscripcion = await session.get(EventRegistration, registration_id)
    ahora = datetime.now(UTC)
    if (
        inscripcion is None
        or inscripcion.status != "waitlisted"
        or inscripcion.waitlist_promotion_expires_at is None
        or inscripcion.waitlist_promotion_expires_at < ahora
    ):
        raise ValidationDomainError("El enlace de confirmación no es válido o ha caducado.")

    evento = await session.get(Event, inscripcion.event_id)
    if evento is None:  # pragma: no cover - la FK compuesta lo hace imposible
        raise RuntimeError(
            f"Evento {inscripcion.event_id} no encontrado al confirmar una promoción."
        )

    inscripcion.status = await _estado_confirmable(session, evento, inscripcion.id)
    inscripcion.confirmed_at = ahora if inscripcion.status == "confirmed" else None
    if inscripcion.status == "pending_payment":
        await _reservar_ventana_de_pago(session, evento, inscripcion)
    await _enviar_email_por_estado(session, inscripcion)
    return inscripcion


async def expire_waitlist_promotions() -> None:
    """Cron (`app/core/tasks.py`): devuelve al final de la cola las promociones
    caducadas sin confirmar y promueve a la siguiente persona.

    Mismo patrón que `sweep_unverified_accounts`: `maintenance_session`
    (`BYPASSRLS`) porque es una tarea transversal a todas las organizaciones,
    sin petición HTTP de la que resolver un tenant.
    """
    async with maintenance_session() as session:
        eventos = await repository.events_with_expired_waitlist_promotions(session)
        for organization_id, event_id in eventos:
            evento = await repository.lock_event_for_capacity(session, organization_id, event_id)
            caducadas = await repository.get_expired_waitlist_promotions(
                session, organization_id, event_id
            )
            for inscripcion in caducadas:
                await repository.requeue_to_back_of_waitlist(
                    session, organization_id, event_id, inscripcion
                )
                await _promote_next_waitlisted(session, evento)
            await session.commit()


async def get_registration_stats(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    email_verification_required: bool,
) -> dict[str, Any]:
    """Estadísticas de conversión del embudo, para `GET .../registrations/stats`.

    "Iniciados" cuenta toda fila, sea cual sea su estado actual: es el
    denominador de la conversión de verificación. "Emails enviados/entregados/
    abiertos" (PRD §4.3) queda fuera de esta fase por falta de webhooks del
    proveedor de email — decisión de alcance ya documentada en el plan, no una
    omisión.

    Cuando el evento no exige verificación de email, `verified_at` nunca se
    rellena (no hay paso de verificación que lo haga) — contar `verificados`
    a partir de esa columna daría siempre 0% aunque todo el mundo llegue a
    `confirmed`/`waitlisted`. En ese caso "verificados" se informa igual a
    "iniciados": no hay paso de verificación que superar, así que todo el
    mundo lo "pasa" trivialmente.
    """
    por_estado = await repository.count_registrations_by_status(session, organization_id, event_id)
    iniciados = sum(por_estado.values())
    confirmados = por_estado.get("confirmed", 0)

    if email_verification_required:
        verificados = await repository.count_verified_registrations(
            session, organization_id, event_id
        )
    else:
        verificados = iniciados

    return {
        "initiated": iniciados,
        "verified": verificados,
        "pending_approval": por_estado.get("pending_approval", 0),
        "pending_payment": por_estado.get("pending_payment", 0),
        "confirmed": confirmados,
        "rejected": por_estado.get("rejected", 0),
        "cancelled": por_estado.get("cancelled", 0),
        "waitlisted": por_estado.get("waitlisted", 0),
        "verified_conversion_rate": (verificados / iniciados) if iniciados else None,
        "confirmed_conversion_rate": (confirmados / verificados) if verificados else None,
    }


# --- Panel de organizador: gestión de preguntas ------------------------------


def _validar_options_por_tipo(type_: str, options: list[str] | None) -> list[str] | None:
    if type_ == "short_text":
        if options:
            raise ValidationDomainError("Una pregunta de texto libre no lleva opciones.")
        return None
    if not options:
        raise ValidationDomainError("Una pregunta de opción necesita al menos una opción.")
    return options


async def create_registration_question(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    type_: str,
    label: str,
    required: bool,
    sort_order: int,
    options: list[str] | None,
) -> EventRegistrationQuestion:
    """Añadir una pregunta nueva siempre está permitido, tenga o no ya
    inscripciones el evento — la restricción de la decisión #6 solo aplica a
    editar o borrar una pregunta con respuestas asociadas."""
    pregunta = EventRegistrationQuestion(
        event_id=event_id,
        organization_id=organization_id,
        type=type_,
        label=label.strip(),
        required=required,
        sort_order=sort_order,
        options=_validar_options_por_tipo(type_, options),
    )
    session.add(pregunta)
    await session.flush()
    return pregunta


async def update_registration_question(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    question_id: uuid.UUID,
    datos: dict[str, Any],
) -> EventRegistrationQuestion:
    """`label`/`required`/`sort_order` siempre se pueden editar; `type`/`options`
    solo si la pregunta no tiene respuestas asociadas (409 si las tiene) —
    decisión #6 del PRD: no dejar respuestas huérfanas o de un tipo distinto
    al declarado."""
    pregunta = await repository.get_question(session, organization_id, event_id, question_id)
    if pregunta is None:
        raise NotFoundError("La pregunta no existe.")

    cambia_forma = "type" in datos or "options" in datos
    if cambia_forma and await repository.question_has_answers(
        session, organization_id, pregunta.id
    ):
        raise ConflictError(
            "No se puede cambiar el tipo ni las opciones de una pregunta con respuestas guardadas."
        )

    nuevo_tipo = datos.get("type", pregunta.type)
    if "type" in datos or "options" in datos:
        pregunta.options = _validar_options_por_tipo(
            nuevo_tipo, datos.get("options", pregunta.options)
        )
        pregunta.type = nuevo_tipo
    if "label" in datos:
        pregunta.label = datos["label"].strip()
    if "required" in datos:
        pregunta.required = datos["required"]
    if "sort_order" in datos:
        pregunta.sort_order = datos["sort_order"]
    return pregunta


async def delete_registration_question(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    question_id: uuid.UUID,
) -> None:
    pregunta = await repository.get_question(session, organization_id, event_id, question_id)
    if pregunta is None:
        raise NotFoundError("La pregunta no existe.")
    if await repository.question_has_answers(session, organization_id, pregunta.id):
        raise ConflictError("No se puede borrar una pregunta con respuestas guardadas.")
    await session.delete(pregunta)
