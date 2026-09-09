"""Reembolsos con outbox, política de plazo y listado de pagos del panel
(fase 6 del PRD, fase 5 de trabajo).

Tres reglas no negociables, todas con su propio test:

- **Ninguna llamada de red a Stripe ocurre bajo un bloqueo de fila abierto**.
  `preparar_reembolso_por_cancelacion` solo persiste una
  intención en `event_payment_refunds`; el llamador real
  (`registrations.service._cancelar_inscripcion`) ya tiene la fila de la
  inscripción bloqueada, así que aquí no puede haber ni una sola llamada de
  red. `_ejecutar_reembolso` sí llama a Stripe, pero **fuera** de cualquier
  transacción con bloqueos: bloquea la fila del reembolso, marca `submitted`
  y hace `commit` antes de la llamada.
- **Una sola implementación del reembolso.** El automático
  (`preparar_reembolso_por_cancelacion`) y el manual
  (`solicitar_reembolso_manual`) escriben la misma fila de
  `event_payment_refunds`; los ejecuta la misma función
  (`_ejecutar_reembolso`), invocada por las mismas dos tareas
  (`process_refunds_task`/`sweep_stuck_refunds_task` en `core/tasks.py`).
- **`idempotency_key = f"refund_{refund.id}"`**, derivada de la PK ya
  persistida: un reintento — de la tarea o del barrido de
  atascados — nunca genera una clave distinta, así que nunca duplica el
  cargo en Stripe.

`refunded_cents` **no se escribe aquí**: lo fija el webhook de
`charge.refunded` (`payments/webhooks.py`), la única fuente de verdad del
importe real devuelto — incluidos los reembolsos hechos por el organizador
desde su propio Dashboard de Stripe, que esta capa nunca ve.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import maintenance_session
from app.modules.events.models import Event
from app.modules.payments import repository
from app.modules.payments import stripe_client as stripe_gateway
from app.modules.payments.models import EventPayment, EventPaymentRefund
from app.modules.registrations.models import EventRegistration
from app.modules.tickets import repository as tickets_repository
from app.shared.errors import ConflictError, ExternalServiceError, NotFoundError

logger = logging.getLogger(__name__)

# Estados de pago que todavía admiten reembolso: uno ya `refunded` no tiene
# importe pendiente, y `pending`/`expired` nunca llegaron a cobrarse.
ESTADOS_REEMBOLSABLES = ("paid", "partially_refunded")

MotivoSinReembolso = str  # "evento_ya_empezado" | "entrada_usada" | "fuera_de_plazo"

# Tope de reintentos compartido por `_ejecutar_reembolso` y
# `repository.refunds_atascados`/`suma_reembolsos_en_curso`: pasado este
# número de intentos fallidos, se deja de reencolar y se registra en `ERROR`
# en vez de seguir intentando en silencio. Única fuente de verdad en
# `repository.INTENTOS_MAXIMOS_REEMBOLSO`: antes era un literal `5`
# duplicado en ambos módulos.
_INTENTOS_MAXIMOS = repository.INTENTOS_MAXIMOS_REEMBOLSO


@dataclass(frozen=True, slots=True)
class EvaluacionPolitica:
    procede: bool
    motivo: MotivoSinReembolso | None


def evaluar_politica_reembolso_automatico(
    *, evento: Event, ticket_used_at: datetime | None, ahora: datetime
) -> EvaluacionPolitica:
    """Las cuatro condiciones del reembolso automático: pago
    con importe pendiente (comprobado por el llamador), evento no empezado,
    entrada no usada, y al menos `payment_refund_cutoff_hours` de margen
    hasta `starts_at`. Pura: no toca la base de datos, así que el mismo
    resultado sirve tanto para decidir en `_cancelar_inscripcion` como para
    mostrar el motivo en el panel de pagos.
    """
    if ahora >= evento.starts_at:
        return EvaluacionPolitica(procede=False, motivo="evento_ya_empezado")
    if ticket_used_at is not None:
        return EvaluacionPolitica(procede=False, motivo="entrada_usada")
    limite = evento.starts_at - timedelta(hours=get_settings().payment_refund_cutoff_hours)
    if ahora >= limite:
        return EvaluacionPolitica(procede=False, motivo="fuera_de_plazo")
    return EvaluacionPolitica(procede=True, motivo=None)


async def preparar_reembolso_por_cancelacion(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    registration_id: uuid.UUID,
) -> str | None:
    """Paso de outbox de `_cancelar_inscripcion`, invocado **antes** de
    cambiar el estado de la inscripción. Nunca llama a Stripe.

    Devuelve `"en_curso"` si ha creado la intención de reembolso,
    `"sin_reembolso"` si había importe pendiente pero la política de plazo lo
    descarta, o `None` si no hay nada que reembolsar (evento gratuito, o un
    pago que nunca llegó a cobrarse).
    """
    pago = await repository.get_payment_by_registration(session, organization_id, registration_id)
    if pago is None or pago.status not in ESTADOS_REEMBOLSABLES:
        return None
    en_curso = await repository.suma_reembolsos_en_curso(session, organization_id, pago.id)
    pendiente = pago.amount_cents - pago.refunded_cents - en_curso
    if pendiente <= 0:
        return None

    evento = await session.get(Event, event_id)
    if evento is None:  # pragma: no cover - la FK de `event_payments` lo impide en la práctica
        return None
    ticket = await tickets_repository.get_ticket_by_registration(
        session, organization_id, registration_id
    )
    evaluacion = evaluar_politica_reembolso_automatico(
        evento=evento,
        ticket_used_at=ticket.used_at if ticket is not None else None,
        ahora=datetime.now(UTC),
    )
    if not evaluacion.procede:
        return "sin_reembolso"

    await repository.crear_intencion_reembolso(
        session,
        organization_id=organization_id,
        payment_id=pago.id,
        amount_cents=pendiente,
        reason="cancellation",
        revoke_ticket=True,
    )
    return "en_curso"


async def solicitar_reembolso_manual(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    payment_id: uuid.UUID,
    amount_cents: int | None,
    revoke_ticket: bool,
) -> EventPaymentRefund:
    """Reembolso manual desde el panel: valida importe y estado, y escribe en
    el **mismo** outbox que el automático — nunca llama a Stripe (Non-functional
    de la fase: un solo camino de ejecución para los dos).

    Total (importe pedido == importe pendiente) revoca siempre, ignorando
    `revoke_ticket`; parcial no revoca salvo que se pida explícitamente
    (Decisión #15 del plan).
    """
    pago = await repository.get_payment(session, organization_id, payment_id)
    if pago is None:
        raise NotFoundError("El pago no existe.")
    if pago.status not in ESTADOS_REEMBOLSABLES:
        raise ConflictError("Este pago no admite un reembolso en su estado actual.")

    en_curso = await repository.suma_reembolsos_en_curso(session, organization_id, pago.id)
    pendiente = pago.amount_cents - pago.refunded_cents - en_curso
    importe = amount_cents if amount_cents is not None else pendiente
    if importe <= 0 or importe > pendiente:
        raise ConflictError("El importe a reembolsar supera el importe pendiente de este pago.")

    es_total = importe == pendiente
    revoke = True if es_total else revoke_ticket

    return await repository.crear_intencion_reembolso(
        session,
        organization_id=organization_id,
        payment_id=pago.id,
        amount_cents=importe,
        reason="manual",
        revoke_ticket=revoke,
    )


# --- Ejecución contra Stripe (tareas de `core/tasks.py`) ---------------------


def _marcar_intento_fallido(reembolso: EventPaymentRefund, mensaje: str) -> None:
    """Incrementa `attempts` en **toda** salida no exitosa de
    `_ejecutar_reembolso` — tanto si arranca en `pending` (primer intento)
    como si arranca ya en `submitted`/`failed` (reintento de
    `reencolar_reembolsos_atascados`): sin esto, un reembolso que siempre
    falla en un reintento nunca alcanza `attempts >= 5` y se reencola para
    siempre sin ninguna alarma."""
    reembolso.status = "failed"
    reembolso.attempts += 1
    reembolso.error = mensaje
    if reembolso.attempts >= _INTENTOS_MAXIMOS:
        logger.error(
            "Reembolso %s ha agotado sus reintentos: dinero pendiente de devolver.", reembolso.id
        )


async def _ejecutar_reembolso(refund_id: uuid.UUID, *, estados_permitidos: tuple[str, ...]) -> None:
    """Ejecuta una intención ya persistida. Nunca bajo un bloqueo de fila
    mientras dura la llamada de red: bloquea, marca
    `submitted` y hace `commit` (fin del `async with`) antes de llamar a
    Stripe; vuelve a abrir transacción para escribir el resultado.

    Dos ejecuciones concurrentes sobre la misma fila `pending`: la segunda
    queda bloqueada por el `SELECT ... FOR UPDATE` de la primera y, al
    desbloquearse, encuentra el estado ya fuera de `estados_permitidos` — no
    llama a Stripe una segunda vez.
    """
    async with maintenance_session() as session:
        reembolso = await session.get(EventPaymentRefund, refund_id, with_for_update=True)
        if reembolso is None or reembolso.status not in estados_permitidos:
            return
        pago = await session.get(EventPayment, reembolso.payment_id)
        if pago is None or pago.stripe_payment_intent_id is None:
            _marcar_intento_fallido(reembolso, "El pago asociado no tiene un cobro que reembolsar.")
            return
        if reembolso.status == "pending":
            reembolso.status = "submitted"
            reembolso.submitted_at = datetime.now(UTC)
        stripe_account_id = pago.stripe_account_id
        stripe_payment_intent_id = pago.stripe_payment_intent_id
        amount_cents = reembolso.amount_cents

    idempotency_key = f"refund_{refund_id}"
    try:
        creado = await stripe_gateway.crear_reembolso(
            stripe_account_id=stripe_account_id,
            stripe_payment_intent_id=stripe_payment_intent_id,
            amount_cents=amount_cents,
            idempotency_key=idempotency_key,
        )
    except ExternalServiceError as exc:
        async with maintenance_session() as session:
            reembolso = await session.get(EventPaymentRefund, refund_id, with_for_update=True)
            if reembolso is not None:
                _marcar_intento_fallido(reembolso, str(exc)[:2000])
        return

    async with maintenance_session() as session:
        reembolso = await session.get(EventPaymentRefund, refund_id, with_for_update=True)
        if reembolso is not None:
            reembolso.stripe_refund_id = creado.stripe_refund_id
            reembolso.status = "succeeded"


async def procesar_reembolsos_pendientes() -> None:
    """`process_refunds_task`: cron cada 2 minutos y encolado al vuelo tras
    cada cancelación con reembolso automático. Solo toca filas `pending`."""
    async with maintenance_session() as session:
        pendientes = await repository.refunds_pendientes(session)
    for refund_id in pendientes:
        await _ejecutar_reembolso(refund_id, estados_permitidos=("pending",))


async def reencolar_reembolsos_atascados() -> None:
    """`sweep_stuck_refunds_task`, hermana de
    `sweep_stuck_webhook_events_task`: retoma un reembolso cuya llamada a
    Stripe pudo tener éxito pero cuya escritura posterior falló. La misma
    `idempotency_key` evita duplicar el cargo en Stripe."""
    async with maintenance_session() as session:
        atascados = await repository.refunds_atascados(session)
    for refund_id in atascados:
        await _ejecutar_reembolso(refund_id, estados_permitidos=("submitted", "failed"))


# --- Listado de pagos del panel -----------------------------------------------


@dataclass(frozen=True, slots=True)
class RefundOut:
    id: uuid.UUID
    amount_cents: int
    reason: str
    revoke_ticket: bool
    status: str
    error: str | None
    attempts: int


@dataclass(frozen=True, slots=True)
class PaymentOut:
    payment: EventPayment
    ticket_type_name: str | None
    email: str | None
    refunds: list[RefundOut]
    no_auto_refund_reason: MotivoSinReembolso | None


async def _motivo_sin_reembolso_automatico(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    pago: EventPayment,
    inscripcion: EventRegistration | None,
    ya_tiene_reembolsos: bool,
) -> MotivoSinReembolso | None:
    """Motivo **derivado**, nunca una columna guardada (mismo criterio que
    `used_count` de un código de descuento): se recalcula en
    cada lectura para no arrastrar un motivo obsoleto si el organizador
    reembolsa a mano después. Solo tiene sentido mostrarlo cuando la
    inscripción está cancelada, el pago sigue con importe pendiente y todavía
    no existe ningún reembolso (ni automático ni manual) para él."""
    if ya_tiene_reembolsos:
        return None
    if pago.status not in ESTADOS_REEMBOLSABLES:
        return None
    if pago.refunded_cents >= pago.amount_cents:
        return None
    if inscripcion is None or inscripcion.status != "cancelled":
        return None

    evento = await session.get(Event, event_id)
    if evento is None:  # pragma: no cover - defensivo
        return None
    ticket = await tickets_repository.get_ticket_by_registration(
        session, organization_id, inscripcion.id
    )
    evaluacion = evaluar_politica_reembolso_automatico(
        evento=evento,
        ticket_used_at=ticket.used_at if ticket is not None else None,
        ahora=datetime.now(UTC),
    )
    return evaluacion.motivo


async def listar_pagos_del_evento(
    session: AsyncSession, *, organization_id: uuid.UUID, event_id: uuid.UUID
) -> list[PaymentOut]:
    pagos = await repository.list_payments_for_event(session, organization_id, event_id)
    resultado: list[PaymentOut] = []
    for pago in pagos:
        tipo = await repository.get_ticket_type(
            session, organization_id, event_id, pago.ticket_type_id
        )
        inscripcion = (
            await session.get(EventRegistration, pago.registration_id)
            if pago.registration_id is not None
            else None
        )
        filas_reembolso = await repository.get_refunds_for_payment(
            session, organization_id, pago.id
        )
        motivo = await _motivo_sin_reembolso_automatico(
            session,
            organization_id=organization_id,
            event_id=event_id,
            pago=pago,
            inscripcion=inscripcion,
            ya_tiene_reembolsos=bool(filas_reembolso),
        )
        resultado.append(
            PaymentOut(
                payment=pago,
                ticket_type_name=tipo.name if tipo is not None else None,
                email=inscripcion.email if inscripcion is not None else None,
                refunds=[
                    RefundOut(
                        id=fila.id,
                        amount_cents=fila.amount_cents,
                        reason=fila.reason,
                        revoke_ticket=fila.revoke_ticket,
                        status=fila.status,
                        error=fila.error,
                        attempts=fila.attempts,
                    )
                    for fila in filas_reembolso
                ],
                no_auto_refund_reason=motivo,
            )
        )
    return resultado
