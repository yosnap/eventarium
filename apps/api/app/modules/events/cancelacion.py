"""Cancelación de un evento por la organización.

Cancelar no es solo cambiar un estado: cancela todas las inscripciones vivas,
reembolsa íntegramente lo cobrado y avisa a cada inscrito. Por eso ocurre en
dos tiempos:

1. **Transacción corta** (`cancelar_evento`): bloquea el evento con el mismo
   `FOR UPDATE` que usan las altas para el aforo, lo marca `cancelled` y
   confirma. Nada se encola antes de ese `commit`: el router encola el barrido
   como `BackgroundTask`, que corre después del `commit` (ver `core/deps.py`).
   Desde ese instante ninguna alta, verificación, aprobación ni promoción
   puede ocupar plaza, porque `lock_event_for_capacity` vuelve a mirar el
   estado con el bloqueo tomado.
2. **Barrido por lotes** (`barrer_cancelacion`): cancela las inscripciones
   vivas, pide el reembolso de cada pago cobrado y, en una segunda pasada,
   avisa por correo. Cada lote hace su propio `commit` y todo se decide a
   partir de columnas persistidas (`cancelled_with_event`,
   `event_cancellation_notified_at`), así que el barrido se puede reanudar
   donde se quedó sin repetir reembolsos ni correos.

No reutiliza `registrations.service._cancelar_inscripcion`: esa función
promociona la lista de espera al liberar plaza, manda el correo de
cancelación individual y aplica la política de plazo al reembolso — las tres
cosas son incorrectas cuando quien cancela es la organización.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import maintenance_session
from app.modules.events import repository
from app.modules.events.models import Event
from app.modules.payments import refunds_service, stripe_client
from app.modules.payments import repository as payments_repository
from app.modules.payments.models import EventPayment, EventPaymentRefund
from app.modules.payments.repository import INTENTOS_MAXIMOS_REEMBOLSO
from app.modules.registrations import repository as registrations_repository
from app.modules.registrations.models import EventRegistration
from app.modules.tickets.service import revocar_entrada
from app.shared.errors import ConflictError, NotFoundError

logger = logging.getLogger(__name__)

# Inscripciones que todavía ocupan o esperan plaza. Las `cancelled` y
# `rejected` ya están cerradas y no se tocan.
ESTADOS_VIVOS = (
    "pending_verification",
    "pending_approval",
    "pending_payment",
    "confirmed",
    "waitlisted",
)
TAMANO_LOTE = 100


@dataclass(frozen=True, slots=True)
class ResumenCancelacion:
    """Lo que implica cancelar, para confirmarlo antes de hacerlo."""

    inscripciones_afectadas: int
    pagos_a_reembolsar: int
    importe_a_reembolsar_cents: int
    moneda: str | None


async def _evento_publicado(
    session: AsyncSession, organization_id: uuid.UUID, event_id: uuid.UUID
) -> Event:
    evento = await repository.get_event(session, organization_id, event_id)
    if evento is None:
        raise NotFoundError("El evento no existe.")
    if evento.status != "published":
        raise ConflictError("Solo se puede cancelar un evento publicado.")
    return evento


async def resumen_de_cancelacion(
    session: AsyncSession, *, organization_id: uuid.UUID, event_id: uuid.UUID
) -> ResumenCancelacion:
    await _evento_publicado(session, organization_id, event_id)
    afectadas = await session.scalar(
        select(func.count()).where(
            EventRegistration.organization_id == organization_id,
            EventRegistration.event_id == event_id,
            EventRegistration.status.in_(ESTADOS_VIVOS),
        )
    )
    en_curso = (
        select(func.coalesce(func.sum(EventPaymentRefund.amount_cents), 0))
        .where(
            EventPaymentRefund.payment_id == EventPayment.id,
            # Mismo criterio que `payments.repository.suma_reembolsos_en_curso`.
            EventPaymentRefund.status.in_(("pending", "submitted"))
            | (
                (EventPaymentRefund.status == "failed")
                & (EventPaymentRefund.attempts < INTENTOS_MAXIMOS_REEMBOLSO)
            ),
        )
        .scalar_subquery()
    )
    pendiente = EventPayment.amount_cents - EventPayment.refunded_cents - en_curso
    fila = (
        await session.execute(
            select(
                func.count(),
                func.coalesce(func.sum(pendiente), 0),
                func.max(EventPayment.currency),
            ).where(
                EventPayment.organization_id == organization_id,
                EventPayment.event_id == event_id,
                EventPayment.status.in_(refunds_service.ESTADOS_REEMBOLSABLES),
                pendiente > 0,
            )
        )
    ).one()
    return ResumenCancelacion(
        inscripciones_afectadas=int(afectadas or 0),
        pagos_a_reembolsar=int(fila[0]),
        importe_a_reembolsar_cents=int(fila[1]),
        moneda=fila[2],
    )


async def tiene_cobros(
    session: AsyncSession, *, organization_id: uuid.UUID, event_id: uuid.UUID
) -> bool:
    """Si cancelar movería dinero: entonces hace falta además `payments:write`."""
    resumen = await resumen_de_cancelacion(
        session, organization_id=organization_id, event_id=event_id
    )
    return resumen.pagos_a_reembolsar > 0


async def cancelar_evento(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    motivo: str | None,
) -> Event:
    """Paso 1: la transacción corta. El llamador confirma y encola después
    `sweep_event_cancellation_task` (nunca antes del `commit`)."""
    await _evento_publicado(session, organization_id, event_id)
    evento = await registrations_repository.lock_event_for_capacity(
        session, organization_id, event_id, exigir_no_cancelado=False
    )
    # Releído con el bloqueo: otra petición pudo cancelarlo o archivarlo entre
    # la comprobación y el bloqueo.
    if evento.status != "published":
        raise ConflictError("Solo se puede cancelar un evento publicado.")
    evento.status = "cancelled"
    evento.cancelled_at = datetime.now(UTC)
    evento.cancellation_reason = (motivo or "").strip() or None
    await session.flush()
    return evento


async def _cancelar_lote(organization_id: uuid.UUID, event_id: uuid.UUID) -> int:
    """Cancela un lote de inscripciones vivas. Devuelve cuántas ha tratado
    (0 = no queda ninguna)."""
    sesiones_a_expirar: list[str] = []
    hubo_reembolso = False
    async with maintenance_session() as session:
        evento = await session.get(Event, event_id)
        if evento is None or evento.status != "cancelled":
            return 0
        lote = list(
            await session.scalars(
                select(EventRegistration)
                .where(
                    EventRegistration.organization_id == organization_id,
                    EventRegistration.event_id == event_id,
                    EventRegistration.status.in_(ESTADOS_VIVOS),
                )
                .order_by(EventRegistration.id)
                .limit(TAMANO_LOTE)
                .with_for_update()
            )
        )
        if not lote:
            return 0
        ahora = datetime.now(UTC)
        for inscripcion in lote:
            if await refunds_service.preparar_reembolso_por_cancelacion_de_evento(
                session, organization_id=organization_id, registration_id=inscripcion.id
            ):
                hubo_reembolso = True
            pago = await payments_repository.get_payment_by_registration(
                session, organization_id, inscripcion.id
            )
            if pago is not None and pago.status == "pending" and pago.stripe_checkout_session_id:
                sesiones_a_expirar.append(pago.stripe_checkout_session_id)
            await payments_repository.expirar_pago_pendiente_de_inscripcion(
                session, organization_id, inscripcion.id
            )
            await revocar_entrada(
                session, organization_id=organization_id, registration_id=inscripcion.id
            )
            inscripcion.status = "cancelled"
            inscripcion.cancelled_at = ahora
            inscripcion.cancelled_with_event = True
        cuenta = await payments_repository.get_cuenta_activa(session, organization_id)
        await session.commit()

    # Fuera de toda transacción: llamadas de red a Stripe. Una sesión que ya
    # no está abierta no se puede expirar y `expirar_sesion_checkout` lo trata
    # como caso normal. Si alguien llega a pagar igualmente, el webhook lo
    # reembolsa (`checkout_service`).
    if cuenta is not None:
        for sesion_id in sesiones_a_expirar:
            await stripe_client.expirar_sesion_checkout(
                stripe_account_id=cuenta.stripe_account_id,
                stripe_checkout_session_id=sesion_id,
            )
    if hubo_reembolso:
        from app.core.tasks import process_refunds_task

        # El cron de reembolsos lo recoge igualmente cada 2 minutos: si encolar
        # falla, no se reprocesa el lote ya confirmado.
        try:
            await process_refunds_task.kiq()
        except Exception:  # pragma: no cover - Redis caído
            logger.exception("No se pudo encolar el procesado de reembolsos")
    return len(lote)


async def _avisar_lote(organization_id: uuid.UUID, event_id: uuid.UUID) -> int:
    """Avisa por correo a un lote de inscripciones canceladas con el evento
    que aún no se han avisado. Devuelve cuántas ha tratado."""
    from app.core.tasks import send_event_cancelled_email

    async with maintenance_session() as session:
        evento = await session.get(Event, event_id)
        if evento is None:
            return 0
        lote = list(
            await session.scalars(
                select(EventRegistration)
                .where(
                    EventRegistration.organization_id == organization_id,
                    EventRegistration.event_id == event_id,
                    EventRegistration.cancelled_with_event.is_(True),
                    EventRegistration.event_cancellation_notified_at.is_(None),
                )
                .order_by(EventRegistration.id)
                .limit(TAMANO_LOTE)
                .with_for_update()
            )
        )
        if not lote:
            return 0
        con_reembolso = set(
            await session.scalars(
                select(EventPayment.registration_id)
                .join(EventPaymentRefund, EventPaymentRefund.payment_id == EventPayment.id)
                .where(
                    EventPayment.organization_id == organization_id,
                    EventPayment.registration_id.in_([i.id for i in lote]),
                    EventPaymentRefund.reason == "event_cancelled",
                )
            )
        )
        ahora = datetime.now(UTC)
        avisos = []
        for inscripcion in lote:
            inscripcion.event_cancellation_notified_at = ahora
            avisos.append((inscripcion.email, inscripcion.id in con_reembolso))
        titulo, motivo = evento.title, evento.cancellation_reason
        await session.commit()

    # Encolado fuera de la transacción: nunca una llamada de red con las filas
    # bloqueadas. Si el proceso muere entre el `commit` y aquí, esas personas
    # se quedan sin aviso: es el precio de no mandarlo dos veces ni retener
    # bloqueos, y se ve en el log.
    for email, con_reembolso_propio in avisos:
        try:
            await send_event_cancelled_email.kiq(
                email, str(organization_id), titulo, motivo, con_reembolso_propio
            )
        except Exception:  # pragma: no cover - Redis caído
            logger.exception("No se pudo encolar el aviso de cancelación del evento %s", event_id)
    return len(lote)


async def barrer_cancelacion(organization_id: uuid.UUID, event_id: uuid.UUID) -> None:
    """Paso 2: cancela, reembolsa y avisa por lotes hasta terminar. Seguro de
    relanzar: cada pasada parte de lo que queda por hacer."""
    while await _cancelar_lote(organization_id, event_id):
        pass
    while await _avisar_lote(organization_id, event_id):
        pass
    logger.info("Cancelación del evento %s completada", event_id)


async def reanudar_cancelaciones_pendientes() -> None:
    """Red de seguridad del cron: retoma cualquier cancelación con trabajo
    pendiente (el barrido encolado pudo morir a medias)."""
    async with maintenance_session() as session:
        filas = (
            await session.execute(
                select(EventRegistration.organization_id, EventRegistration.event_id)
                .join(Event, Event.id == EventRegistration.event_id)
                .where(
                    Event.status == "cancelled",
                    EventRegistration.status.in_(ESTADOS_VIVOS)
                    | (
                        EventRegistration.cancelled_with_event.is_(True)
                        & EventRegistration.event_cancellation_notified_at.is_(None)
                    ),
                )
                .distinct()
            )
        ).all()
    for organization_id, event_id in filas:
        await barrer_cancelacion(organization_id, event_id)


async def progreso_de_cancelacion(
    session: AsyncSession, *, organization_id: uuid.UUID, event_id: uuid.UUID
) -> dict[str, int]:
    """Para el panel: cuántas inscripciones quedan por cancelar y por avisar,
    y cuántos reembolsos de la cancelación han agotado sus intentos."""
    pendientes = await session.scalar(
        select(func.count()).where(
            EventRegistration.organization_id == organization_id,
            EventRegistration.event_id == event_id,
            EventRegistration.status.in_(ESTADOS_VIVOS),
        )
    )
    sin_avisar = await session.scalar(
        select(func.count()).where(
            EventRegistration.organization_id == organization_id,
            EventRegistration.event_id == event_id,
            EventRegistration.cancelled_with_event.is_(True),
            EventRegistration.event_cancellation_notified_at.is_(None),
        )
    )
    reembolsos_fallidos = await session.scalar(
        select(func.count())
        .select_from(EventPaymentRefund)
        .join(EventPayment, EventPayment.id == EventPaymentRefund.payment_id)
        .where(
            EventPayment.organization_id == organization_id,
            EventPayment.event_id == event_id,
            EventPaymentRefund.reason == "event_cancelled",
            EventPaymentRefund.status == "failed",
            EventPaymentRefund.attempts >= INTENTOS_MAXIMOS_REEMBOLSO,
        )
    )
    return {
        "por_cancelar": int(pendientes or 0),
        "por_avisar": int(sin_avisar or 0),
        "reembolsos_fallidos": int(reembolsos_fallidos or 0),
    }
