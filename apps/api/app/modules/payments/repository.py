"""Acceso a datos de pagos con Stripe Connect.

`get_cuenta_activa` es el único resolutor del `acct_id` de una organización
(decisión #7 del plan de la fase 6): tanto el router (con contexto RLS) como
el webhook y las tareas de fondo (sobre `maintenance_session`, sin ese
contexto) pasan por aquí, nunca por un `acct_id` que llegue de fuera.

Fase 3 de trabajo: catálogos de tipos de entrada y códigos de descuento, con
sus dos recuentos derivados (`ESTADOS_CONSUMIBLES`) — nunca un contador
denormalizado, ver `models.py`. Las variantes `lock_*` aplican `SELECT ...
FOR UPDATE` y las consume la fase 4 de trabajo dentro de la transacción que
crea un pago, respetando el orden de bloqueo único del módulo documentado en
`service.py`.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.payments.models import (
    EventDiscountCode,
    EventPayment,
    EventPaymentRefund,
    EventTicketType,
    OrganizationStripeAccount,
    StripeWebhookEvent,
)
from app.modules.registrations.models import EventRegistration

logger = logging.getLogger(__name__)

# Estados de `event_payments` que cuentan como cupo/uso consumido: un pago
# `pending` todavía puede completarse y uno `expired` deja de contar sin que
# nadie lo decremente (hallazgo #19 del red-team de la fase 6).
ESTADOS_CONSUMIBLES = ("pending", "paid", "partially_refunded", "refunded")


async def get_cuenta_activa(
    session: AsyncSession, organization_id: uuid.UUID
) -> OrganizationStripeAccount | None:
    """La fila `deauthorized_at IS NULL` de la organización, o `None`.

    Una organización sin ninguna fila, o cuya única fila está
    `deauthorized_at`, se trata como «sin cuenta» — es lo que permite la
    reconexión sin intervención manual (hallazgo #17 del red-team).
    """
    resultado: OrganizationStripeAccount | None = await session.scalar(
        select(OrganizationStripeAccount).where(
            OrganizationStripeAccount.organization_id == organization_id,
            OrganizationStripeAccount.deauthorized_at.is_(None),
        )
    )
    return resultado


async def get_cuenta_por_stripe_account_id(
    session: AsyncSession, stripe_account_id: str
) -> OrganizationStripeAccount | None:
    """Resuelve una fila por `acct_...`, usada por el webhook para ubicar la
    organización a partir de `event.account` (decisión #9 del plan): la
    columna es única en toda la instalación, así que no hace falta acotar por
    `organization_id`, que es precisamente lo que todavía no se conoce en ese
    punto."""
    resultado: OrganizationStripeAccount | None = await session.scalar(
        select(OrganizationStripeAccount).where(
            OrganizationStripeAccount.stripe_account_id == stripe_account_id
        )
    )
    return resultado


async def crear_cuenta(
    session: AsyncSession, *, organization_id: uuid.UUID, stripe_account_id: str
) -> OrganizationStripeAccount:
    """Persiste la fila **antes** de pedir el `AccountLink` (mitigación del
    riesgo de la fase de trabajo: un `Account` creado en Stripe no es
    reversible desde la plataforma; si la persistencia fallara después de
    crear la cuenta, quedaría huérfana)."""
    cuenta = OrganizationStripeAccount(
        organization_id=organization_id, stripe_account_id=stripe_account_id
    )
    session.add(cuenta)
    await session.flush()
    return cuenta


async def actualizar_estado(
    session: AsyncSession,
    cuenta: OrganizationStripeAccount,
    *,
    charges_enabled: bool,
    payouts_enabled: bool,
    details_submitted: bool,
    last_synced_at: datetime,
) -> OrganizationStripeAccount:
    """Refresca las banderas tras consultar el `Account` real (sincronización
    manual o `account.updated` en la fase 4 de trabajo)."""
    cuenta.charges_enabled = charges_enabled
    cuenta.payouts_enabled = payouts_enabled
    cuenta.details_submitted = details_submitted
    cuenta.last_synced_at = last_synced_at
    if charges_enabled and cuenta.connected_at is None:
        cuenta.connected_at = last_synced_at
    await session.flush()
    return cuenta


async def marcar_desautorizada(
    session: AsyncSession, cuenta: OrganizationStripeAccount, *, momento: datetime
) -> OrganizationStripeAccount:
    """`account.application.deauthorized` (fase 4 de trabajo): la fila se
    conserva con su `deauthorized_at`, no se borra — sigue haciendo falta
    para reembolsar los pagos cobrados con esa cuenta."""
    cuenta.deauthorized_at = momento
    cuenta.charges_enabled = False
    cuenta.payouts_enabled = False
    await session.flush()
    return cuenta


# --- Tipos de entrada --------------------------------------------------------


async def get_ticket_types(
    session: AsyncSession, organization_id: uuid.UUID, event_id: uuid.UUID
) -> list[EventTicketType]:
    filas = await session.scalars(
        select(EventTicketType)
        .where(
            EventTicketType.organization_id == organization_id,
            EventTicketType.event_id == event_id,
        )
        .order_by(EventTicketType.sort_order, EventTicketType.created_at)
    )
    return list(filas)


async def get_ticket_type(
    session: AsyncSession,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    ticket_type_id: uuid.UUID,
) -> EventTicketType | None:
    resultado: EventTicketType | None = await session.scalar(
        select(EventTicketType).where(
            EventTicketType.id == ticket_type_id,
            EventTicketType.event_id == event_id,
            EventTicketType.organization_id == organization_id,
        )
    )
    return resultado


async def lock_ticket_type(
    session: AsyncSession, organization_id: uuid.UUID, ticket_type_id: uuid.UUID
) -> EventTicketType | None:
    """`SELECT ... FOR UPDATE` sobre un tipo de entrada.

    Contrato de bloqueo de la fase 3 de trabajo, consumido por la fase 4:
    orden único `event_registrations` → `events` → `event_ticket_types` →
    `event_discount_codes`, dentro de la misma transacción que crea el pago.
    """
    resultado: EventTicketType | None = await session.scalar(
        select(EventTicketType)
        .where(
            EventTicketType.id == ticket_type_id,
            EventTicketType.organization_id == organization_id,
        )
        .with_for_update()
    )
    return resultado


async def count_used_ticket_type(
    session: AsyncSession, organization_id: uuid.UUID, ticket_type_id: uuid.UUID
) -> int:
    """Cupo consumido de un tipo de entrada, **derivado** de `event_payments`
    (nunca un contador denormalizado, ver `models.py:EventTicketType`)."""
    total = await session.scalar(
        select(func.count())
        .select_from(EventPayment)
        .where(
            EventPayment.organization_id == organization_id,
            EventPayment.ticket_type_id == ticket_type_id,
            EventPayment.status.in_(ESTADOS_CONSUMIBLES),
        )
    )
    return int(total or 0)


async def ticket_type_has_dependencies(
    session: AsyncSession, organization_id: uuid.UUID, ticket_type_id: uuid.UUID
) -> bool:
    """`True` si el tipo tiene algún código de descuento o pago asociado —
    condición explícita antes del 409, además de la FK `RESTRICT` que actúa
    como red de seguridad si esta comprobación se saltara."""
    tiene_codigos = await session.scalar(
        select(EventDiscountCode.id)
        .where(
            EventDiscountCode.organization_id == organization_id,
            EventDiscountCode.ticket_type_id == ticket_type_id,
        )
        .limit(1)
    )
    if tiene_codigos is not None:
        return True
    tiene_pagos = await session.scalar(
        select(EventPayment.id)
        .where(
            EventPayment.organization_id == organization_id,
            EventPayment.ticket_type_id == ticket_type_id,
        )
        .limit(1)
    )
    return tiene_pagos is not None


async def create_ticket_type(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    datos: dict[str, object],
) -> EventTicketType:
    tipo = EventTicketType(organization_id=organization_id, event_id=event_id, **datos)
    session.add(tipo)
    await session.flush()
    return tipo


# --- Códigos de descuento -----------------------------------------------------


async def get_discount_codes(
    session: AsyncSession, organization_id: uuid.UUID, event_id: uuid.UUID
) -> list[EventDiscountCode]:
    filas = await session.scalars(
        select(EventDiscountCode)
        .where(
            EventDiscountCode.organization_id == organization_id,
            EventDiscountCode.event_id == event_id,
        )
        .order_by(EventDiscountCode.created_at)
    )
    return list(filas)


async def get_discount_code(
    session: AsyncSession,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    discount_code_id: uuid.UUID,
) -> EventDiscountCode | None:
    resultado: EventDiscountCode | None = await session.scalar(
        select(EventDiscountCode).where(
            EventDiscountCode.id == discount_code_id,
            EventDiscountCode.event_id == event_id,
            EventDiscountCode.organization_id == organization_id,
        )
    )
    return resultado


async def get_discount_code_by_code(
    session: AsyncSession, organization_id: uuid.UUID, event_id: uuid.UUID, code: str
) -> EventDiscountCode | None:
    """`code` ya debe llegar normalizado a mayúsculas: la comparación es exacta,
    nunca `ILIKE`, para no convertir el presupuesto en un oráculo de fuerza
    bruta más permisivo de lo que ya es."""
    resultado: EventDiscountCode | None = await session.scalar(
        select(EventDiscountCode).where(
            EventDiscountCode.organization_id == organization_id,
            EventDiscountCode.event_id == event_id,
            EventDiscountCode.code == code,
        )
    )
    return resultado


async def lock_discount_code(
    session: AsyncSession, organization_id: uuid.UUID, discount_code_id: uuid.UUID
) -> EventDiscountCode | None:
    """`SELECT ... FOR UPDATE` sobre un código de descuento, último eslabón del
    orden de bloqueo único del módulo (ver `lock_ticket_type`)."""
    resultado: EventDiscountCode | None = await session.scalar(
        select(EventDiscountCode)
        .where(
            EventDiscountCode.id == discount_code_id,
            EventDiscountCode.organization_id == organization_id,
        )
        .with_for_update()
    )
    return resultado


async def count_used_discount_code(
    session: AsyncSession, organization_id: uuid.UUID, discount_code_id: uuid.UUID
) -> int:
    """Uso consumido de un código, **derivado** de `event_payments` — sin
    columna `used_count` que respalde este número (hallazgo #19)."""
    total = await session.scalar(
        select(func.count())
        .select_from(EventPayment)
        .where(
            EventPayment.organization_id == organization_id,
            EventPayment.discount_code_id == discount_code_id,
            EventPayment.status.in_(ESTADOS_CONSUMIBLES),
        )
    )
    return int(total or 0)


async def discount_code_has_payments(
    session: AsyncSession, organization_id: uuid.UUID, discount_code_id: uuid.UUID
) -> bool:
    existe = await session.scalar(
        select(EventPayment.id)
        .where(
            EventPayment.organization_id == organization_id,
            EventPayment.discount_code_id == discount_code_id,
        )
        .limit(1)
    )
    return existe is not None


async def create_discount_code(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    datos: dict[str, object],
) -> EventDiscountCode:
    codigo = EventDiscountCode(organization_id=organization_id, event_id=event_id, **datos)
    session.add(codigo)
    await session.flush()
    return codigo


# --- Guarda de pago (fase 6 del PRD, fase 4 de trabajo) ----------------------


async def tiene_pago_confirmado(
    session: AsyncSession, organization_id: uuid.UUID, registration_id: uuid.UUID
) -> bool:
    """`True` si existe un `event_payments` en `paid` para esta inscripción.

    Único predicado que consultan las dos capas de la guarda de pago
    (`registrations/service.py::_estado_confirmable` y el cinturón de
    seguridad de `_enviar_email_por_estado`) — una sola implementación, para
    que ninguna de las dos pueda desincronizarse de la otra.
    """
    existe = await session.scalar(
        select(EventPayment.id)
        .where(
            EventPayment.organization_id == organization_id,
            EventPayment.registration_id == registration_id,
            EventPayment.status == "paid",
        )
        .limit(1)
    )
    return existe is not None


async def get_payment_by_registration(
    session: AsyncSession, organization_id: uuid.UUID, registration_id: uuid.UUID
) -> EventPayment | None:
    return await session.scalar(
        select(EventPayment).where(
            EventPayment.organization_id == organization_id,
            EventPayment.registration_id == registration_id,
        )
    )


async def pago_reactivable(
    session: AsyncSession, organization_id: uuid.UUID, registration_id: uuid.UUID
) -> bool:
    """`True` si una inscripción `cancelled` se puede reactivar (hallazgo #7):
    su pago existe y nunca llegó a moverse dinero (`pending`/`expired`).
    `paid`/`refunded`/`partially_refunded` no se reactiva — una segunda
    compra exigiría una segunda fila de pago, que `UNIQUE(registration_id)`
    no admite; límite explícito de esta fase, no un olvido.
    """
    pago = await get_payment_by_registration(session, organization_id, registration_id)
    return pago is not None and pago.status in ("pending", "expired")


async def crear_o_reutilizar_pago(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    registration_id: uuid.UUID,
    stripe_account_id: str,
    ticket_type_id: uuid.UUID,
    discount_code_id: uuid.UUID | None,
    amount_cents: int,
    discount_cents: int,
    currency: str,
) -> EventPayment:
    """T1 del checkout (hallazgo #7 y #12): crea la fila de pago, o reutiliza
    la existente de una inscripción reactivada tras caducar sin cobrar —
    nunca una segunda fila (`UNIQUE(registration_id)`). Deja siempre el pago
    en `pending`, sin sesión de Stripe: esa la crea T2, fuera de cualquier
    bloqueo de fila.
    """
    existente = await get_payment_by_registration(session, organization_id, registration_id)
    if existente is not None:
        existente.stripe_account_id = stripe_account_id
        existente.ticket_type_id = ticket_type_id
        existente.discount_code_id = discount_code_id
        existente.amount_cents = amount_cents
        existente.discount_cents = discount_cents
        existente.currency = currency
        existente.status = "pending"
        existente.checkout_attempts += 1
        existente.stripe_checkout_session_id = None
        existente.checkout_url = None
        existente.checkout_link_delivered_at = None
        existente.expires_at = None
        await session.flush()
        return existente

    pago = EventPayment(
        organization_id=organization_id,
        event_id=event_id,
        registration_id=registration_id,
        stripe_account_id=stripe_account_id,
        ticket_type_id=ticket_type_id,
        discount_code_id=discount_code_id,
        amount_cents=amount_cents,
        discount_cents=discount_cents,
        currency=currency,
        status="pending",
        checkout_attempts=1,
    )
    session.add(pago)
    await session.flush()
    return pago


async def get_payment_by_checkout_session_id(
    session: AsyncSession, stripe_checkout_session_id: str
) -> EventPayment | None:
    """Único punto de búsqueda del webhook (hallazgo #2 del red-team de la
    fase 6): **nunca** por `metadata` ni `client_reference_id`, que el
    organizador de una cuenta Connect Standard controla desde su propio
    Dashboard."""
    return await session.scalar(
        select(EventPayment).where(
            EventPayment.stripe_checkout_session_id == stripe_checkout_session_id
        )
    )


async def get_payment_by_payment_intent_id(
    session: AsyncSession, stripe_payment_intent_id: str
) -> EventPayment | None:
    """Único punto de búsqueda de `charge.refunded` (hallazgo #2, ampliado en
    la fase 5 de trabajo): **nunca** por `metadata`, que el organizador de una
    cuenta Connect Standard controla desde su propio Dashboard."""
    return await session.scalar(
        select(EventPayment).where(
            EventPayment.stripe_payment_intent_id == stripe_payment_intent_id
        )
    )


async def get_payment(
    session: AsyncSession, organization_id: uuid.UUID, payment_id: uuid.UUID
) -> EventPayment | None:
    return await session.scalar(
        select(EventPayment).where(
            EventPayment.id == payment_id, EventPayment.organization_id == organization_id
        )
    )


async def list_payments_for_event(
    session: AsyncSession, organization_id: uuid.UUID, event_id: uuid.UUID
) -> list[EventPayment]:
    filas = await session.scalars(
        select(EventPayment)
        .where(EventPayment.organization_id == organization_id, EventPayment.event_id == event_id)
        .order_by(EventPayment.created_at.desc())
    )
    return list(filas)


@dataclass(frozen=True, slots=True)
class _PagoPendienteLigero:
    """Proyección mínima para el barrido y la tarea de enlaces: nunca objetos
    ORM que sobrevivan a una llamada de red a Stripe (evitaría instancias
    «detached» y, sobre todo, dejaría el objeto pegado a una fila bloqueada
    mientras dura la llamada — justo lo que el hallazgo #12 prohíbe)."""

    payment_id: uuid.UUID
    organization_id: uuid.UUID
    stripe_account_id: str
    stripe_checkout_session_id: str | None
    registration_id: uuid.UUID | None


async def pagos_pendientes_caducados(session: AsyncSession) -> list[_PagoPendienteLigero]:
    """Pagos `pending` cuya inscripción `pending_payment` asociada ya superó
    su ventana — candidatos del barrido `expire_pending_payments_task`. Sin
    `FOR UPDATE`: el bloqueo se adquiere fila a fila, después de la consulta
    a Stripe, nunca durante ella (hallazgo #12)."""
    filas = (
        await session.execute(
            select(
                EventPayment.id,
                EventPayment.organization_id,
                EventPayment.stripe_account_id,
                EventPayment.stripe_checkout_session_id,
                EventPayment.registration_id,
            )
            .join(EventRegistration, EventRegistration.id == EventPayment.registration_id)
            .where(
                EventPayment.status == "pending",
                EventRegistration.status == "pending_payment",
                EventRegistration.payment_expires_at.is_not(None),
                EventRegistration.payment_expires_at < datetime.now(UTC),
            )
        )
    ).all()
    return [
        _PagoPendienteLigero(
            payment_id=fila.id,
            organization_id=fila.organization_id,
            stripe_account_id=fila.stripe_account_id,
            stripe_checkout_session_id=fila.stripe_checkout_session_id,
            registration_id=fila.registration_id,
        )
        for fila in filas
    ]


async def pagos_sin_enlace_entregado(session: AsyncSession) -> list[uuid.UUID]:
    """`payment_id` de los caminos 2, 3 y 4 (fase 6 del PRD): la inscripción
    ya está `pending_payment` (verificada, aprobada o promovida) y su pago
    todavía no tiene sesión de Stripe entregada por correo —
    `dispatch_pending_payment_links_task` la crea fuera de la petición
    (hallazgo #12)."""
    filas = await session.scalars(
        select(EventPayment.id)
        .join(EventRegistration, EventRegistration.id == EventPayment.registration_id)
        .where(
            EventPayment.status == "pending",
            EventPayment.checkout_link_delivered_at.is_(None),
            EventRegistration.status == "pending_payment",
        )
    )
    return list(filas)


# --- Idempotencia de webhooks (fase 6 del PRD, fase 4 de trabajo) -----------


async def registrar_evento_recibido(
    session: AsyncSession,
    *,
    event_id: str,
    event_type: str,
    stripe_account_id: str,
    payload: dict[str, object],
) -> bool:
    """`INSERT ... ON CONFLICT DO NOTHING`: `True` si esta llamada ha creado
    la fila (evento nuevo, hay que encolar la tarea), `False` si ya existía
    (Stripe está reintentando una entrega, decisión #10 del plan)."""
    resultado = await session.execute(
        pg_insert(StripeWebhookEvent)
        .values(
            id=event_id,
            event_type=event_type,
            stripe_account_id=stripe_account_id,
            payload=payload,
            status="received",
            received_at=datetime.now(UTC),
        )
        .on_conflict_do_nothing(index_elements=["id"])
    )
    return bool(resultado.rowcount)


async def registrar_evento_ignorado_sin_cuenta(
    session: AsyncSession, *, event_id: str, event_type: str, payload: dict[str, object]
) -> None:
    """Un evento sin `account` de nivel superior (hallazgo #10): se marca
    `ignored` sin encolar ninguna tarea. `ON CONFLICT DO NOTHING`: una
    reentrega del mismo evento no debe fallar por chocar con la PK."""
    await session.execute(
        pg_insert(StripeWebhookEvent)
        .values(
            id=event_id,
            event_type=event_type,
            stripe_account_id=None,
            payload=payload,
            status="ignored",
            received_at=datetime.now(UTC),
            processed_at=datetime.now(UTC),
        )
        .on_conflict_do_nothing(index_elements=["id"])
    )


async def get_webhook_event(session: AsyncSession, event_id: str) -> StripeWebhookEvent | None:
    return await session.get(StripeWebhookEvent, event_id)


async def eventos_para_reencolar(session: AsyncSession) -> list[str]:
    """`sweep_stuck_webhook_events_task` (hallazgo #9): filas `received` con
    más de 10 minutos (perdidas entre la cola y el worker) y `failed` con
    reintentos disponibles. Las `failed` que agotaron sus reintentos se
    registran en `ERROR` en vez de reencolarse otra vez."""
    limite = datetime.now(UTC) - timedelta(minutes=10)
    atascados = list(
        await session.scalars(
            select(StripeWebhookEvent.id).where(
                StripeWebhookEvent.status == "received",
                StripeWebhookEvent.received_at < limite,
            )
        )
    )
    reintentables = list(
        await session.scalars(
            select(StripeWebhookEvent.id).where(
                StripeWebhookEvent.status == "failed",
                StripeWebhookEvent.attempts < 5,
            )
        )
    )
    agotados = list(
        await session.scalars(
            select(StripeWebhookEvent.id).where(
                StripeWebhookEvent.status == "failed",
                StripeWebhookEvent.attempts >= 5,
            )
        )
    )
    for event_id in agotados:
        logger.error("Webhook de Stripe %s ha agotado sus reintentos.", event_id)
    return [*atascados, *reintentables]


async def purgar_eventos_antiguos(session: AsyncSession, *, dias: int) -> int:
    """`purge_stripe_webhook_events_task` (hallazgo #15): borra filas con más
    de `dias` de antigüedad."""
    limite = datetime.now(UTC) - timedelta(days=dias)
    filas = list(
        await session.scalars(
            select(StripeWebhookEvent).where(StripeWebhookEvent.received_at < limite)
        )
    )
    for fila in filas:
        await session.delete(fila)
    return len(filas)


# --- Reembolsos: outbox (fase 6 del PRD, fase 5 de trabajo) ------------------


async def crear_intencion_reembolso(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    payment_id: uuid.UUID,
    amount_cents: int,
    reason: str,
    revoke_ticket: bool,
) -> EventPaymentRefund:
    """Persiste la intención **antes** de cualquier llamada a Stripe
    (hallazgos #11 y #12): la fila existe siempre antes de que exista la
    posibilidad de que el dinero se mueva."""
    intencion = EventPaymentRefund(
        organization_id=organization_id,
        payment_id=payment_id,
        amount_cents=amount_cents,
        reason=reason,
        revoke_ticket=revoke_ticket,
    )
    session.add(intencion)
    await session.flush()
    return intencion


async def get_refunds_for_payment(
    session: AsyncSession, organization_id: uuid.UUID, payment_id: uuid.UUID
) -> list[EventPaymentRefund]:
    filas = await session.scalars(
        select(EventPaymentRefund)
        .where(
            EventPaymentRefund.organization_id == organization_id,
            EventPaymentRefund.payment_id == payment_id,
        )
        .order_by(EventPaymentRefund.created_at)
    )
    return list(filas)


async def tiene_reembolso_con_revocacion(session: AsyncSession, payment_id: uuid.UUID) -> bool:
    """`True` si algún reembolso ya `succeeded` de este pago pedía revocar la
    entrada — la casilla del panel en un reembolso parcial (decisión #15).
    El webhook de `charge.refunded` la consulta para saber si debe revocar
    cuando el importe acumulado todavía no es el total."""
    existe = await session.scalar(
        select(EventPaymentRefund.id)
        .where(
            EventPaymentRefund.payment_id == payment_id,
            EventPaymentRefund.revoke_ticket.is_(True),
            EventPaymentRefund.status == "succeeded",
        )
        .limit(1)
    )
    return existe is not None


async def refunds_pendientes(session: AsyncSession) -> list[uuid.UUID]:
    """Filas `pending`, listas para su primer intento — la tarea principal
    (`process_refunds_task`), nunca las `submitted` atascadas (esas las
    recoge `refunds_atascados`, un barrido distinto para no competir con una
    ejecución concurrente en curso, ver hallazgo #11)."""
    filas = await session.scalars(
        select(EventPaymentRefund.id).where(EventPaymentRefund.status == "pending")
    )
    return list(filas)


async def refunds_atascados(session: AsyncSession) -> list[uuid.UUID]:
    """Filas `submitted` cuya llamada a Stripe pudo tener éxito pero cuya
    escritura posterior falló (hallazgo #11): atascadas hace más de 10
    minutos, igual que `eventos_para_reencolar` para webhooks. Las `failed`
    con reintentos disponibles también se retoman aquí; las agotadas se
    registran en `ERROR`."""
    limite = datetime.now(UTC) - timedelta(minutes=10)
    atascados = list(
        await session.scalars(
            select(EventPaymentRefund.id).where(
                EventPaymentRefund.status == "submitted",
                EventPaymentRefund.submitted_at < limite,
            )
        )
    )
    reintentables = list(
        await session.scalars(
            select(EventPaymentRefund.id).where(
                EventPaymentRefund.status == "failed",
                EventPaymentRefund.attempts < 5,
            )
        )
    )
    agotados = await session.scalars(
        select(EventPaymentRefund.id).where(
            EventPaymentRefund.status == "failed",
            EventPaymentRefund.attempts >= 5,
        )
    )
    for refund_id in agotados:
        logger.error(
            "Reembolso %s ha agotado sus reintentos: dinero pendiente de devolver.", refund_id
        )
    return [*atascados, *reintentables]
