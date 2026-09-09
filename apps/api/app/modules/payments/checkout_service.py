"""Compra pública de entradas: Checkout Session, enlaces de pago diferidos y
barrido de pagos pendientes caducados (fase 6 del PRD, fase 4 de trabajo).

**Nunca una llamada de red a Stripe con bloqueos de fila abiertos**
(hallazgo #12 del red-team). Por eso la compra son dos transacciones
distintas, nunca una sola:

- **T1** (`iniciar_compra`, hasta su `await session.commit()`): con
  bloqueos, sin red. Crea o reactiva la inscripción
  (`registrations.service.submit_registration`), bloquea y valida el tipo de
  entrada y el código de descuento, y crea o reutiliza la fila de
  `event_payments` en `pending`. Termina con un `commit`: a partir de ahí la
  plaza, el cupo y el uso del código están reservados por filas persistidas,
  no por bloqueos de fila abiertos.
- **T2** (`crear_sesion_de_pago`): con red, sin bloqueos. Crea la Checkout
  Session y persiste su URL. La reutilizan tanto la compra (justo después de
  T1) como `dispatch_pending_payment_links_task` (caminos 2, 3 y 4) — la
  única diferencia es la sesión de base de datos que cada llamador le pasa.

`expirar_pagos_pendientes` (el barrido) sigue el mismo principio: primero
lee los candidatos sin bloquearlos, después consulta Stripe sin ningún
bloqueo abierto, y solo entonces vuelve a bloquear la fila concreta —ya
revalidada— para aplicar la confirmación o la expiración.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import maintenance_session
from app.core.tenant import base_url_de_organizacion
from app.modules.events.models import Event
from app.modules.payments import repository
from app.modules.payments import service as payments_service
from app.modules.payments import stripe_client as stripe_gateway
from app.modules.payments.models import EventPayment
from app.modules.registrations import service as registrations_service
from app.modules.registrations.models import EventRegistration
from app.modules.registrations.schemas import RegistrationAnswerInput
from app.shared.errors import ConflictError, ExternalServiceError, ValidationDomainError

logger = logging.getLogger(__name__)

# Nunca revela si el email ya estaba inscrito, ni en qué estado — mismo
# mensaje que el resto del embudo público (`registrations/public_router.py`).
MENSAJE_GENERICO = (
    "Si los datos son correctos, en breve recibirás un correo con los siguientes pasos."
)

# Margen técnico sobre la ventana del evento (hallazgo #16): el tiempo entre
# calcular `expires_at` y que Stripe reciba la petición podría, sin margen,
# cruzar su mínimo de 30 minutos cuando la ventana del evento está justo en
# ese mínimo.
_MARGEN_TECNICO = timedelta(seconds=60)


@dataclass(frozen=True, slots=True)
class ResultadoCompra:
    message: str
    checkout_url: str | None


async def _obtener_cuenta_operativa(session: AsyncSession, organization_id: uuid.UUID):
    cuenta = await repository.get_cuenta_activa(session, organization_id)
    if cuenta is None or not cuenta.charges_enabled:
        raise ConflictError("Esta organización todavía no puede cobrar entradas.")
    return cuenta


async def iniciar_compra(
    session: AsyncSession,
    *,
    event: Event,
    email: str,
    full_name: str,
    answers: list[RegistrationAnswerInput],
    data_processing_accepted: bool,
    marketing_accepted: bool,
    recording_accepted: bool,
    ticket_type_id: uuid.UUID,
    code: str | None,
) -> ResultadoCompra:
    """T1 + T2 encadenadas: crea la inscripción y el pago bajo bloqueo, hace
    `commit`, y solo entonces llama a Stripe.
    """
    cuenta = await _obtener_cuenta_operativa(session, event.organization_id)

    inscripcion = await registrations_service.submit_registration(
        session,
        event=event,
        email=email,
        full_name=full_name,
        answers=answers,
        data_processing_accepted=data_processing_accepted,
        marketing_accepted=marketing_accepted,
        recording_accepted=recording_accepted,
    )
    if inscripcion is None or inscripcion.status not in ("pending_payment", "pending_verification"):
        # Ya existía y no es reactivable/pagable ahora mismo, o cupo lleno
        # (`waitlisted`): la respuesta pública es la misma de siempre, sin
        # revelar en qué estado está.
        await session.commit()
        return ResultadoCompra(message=MENSAJE_GENERICO, checkout_url=None)

    ahora = datetime.now(UTC)
    tipo = await repository.lock_ticket_type(session, event.organization_id, ticket_type_id)
    tipo_vigente = tipo is not None and payments_service.validar_tipo_vigente(tipo, ahora)
    if tipo is None or tipo.event_id != event.id or not tipo_vigente:
        await session.rollback()
        raise ValidationDomainError("Este tipo de entrada no está disponible.")
    if tipo.max_quantity is not None:
        vendidas = await repository.count_used_ticket_type(session, event.organization_id, tipo.id)
        if vendidas >= tipo.max_quantity:
            await session.rollback()
            raise ValidationDomainError("Este tipo de entrada está agotado.")

    discount_type: str | None = None
    discount_value: int | None = None
    discount_code_id: uuid.UUID | None = None
    if code:
        codigo = await repository.get_discount_code_by_code(
            session, event.organization_id, event.id, code.strip().upper()
        )
        if codigo is not None:
            codigo = await repository.lock_discount_code(session, event.organization_id, codigo.id)
        if codigo is None:
            await session.rollback()
            raise ValidationDomainError(payments_service.MENSAJE_CODIGO_NO_VALIDO)
        usos = await repository.count_used_discount_code(session, event.organization_id, codigo.id)
        if not payments_service.validar_codigo_vigente(codigo, tipo, usos, ahora):
            await session.rollback()
            raise ValidationDomainError(payments_service.MENSAJE_CODIGO_NO_VALIDO)
        discount_type = codigo.discount_type
        discount_value = codigo.discount_value
        discount_code_id = codigo.id

    total = payments_service.calcular_precio_final(tipo.price_cents, discount_type, discount_value)

    pago = await repository.crear_o_reutilizar_pago(
        session,
        organization_id=event.organization_id,
        event_id=event.id,
        registration_id=inscripcion.id,
        stripe_account_id=cuenta.stripe_account_id,
        ticket_type_id=tipo.id,
        discount_code_id=discount_code_id,
        amount_cents=total,
        discount_cents=tipo.price_cents - total,
        currency=tipo.currency,
    )

    if inscripcion.status == "pending_payment":
        ventana = timedelta(minutes=event.payment_checkout_window_minutes)
        inscripcion.payment_expires_at = ahora + ventana

    payment_id = pago.id
    estado_resultante = inscripcion.status

    await session.commit()
    # --- fin de T1: la fila del pago ya persiste sin ningún bloqueo abierto ---

    if estado_resultante != "pending_payment":
        # `pending_verification`: la sesión de pago se crea más tarde, cuando
        # se verifique el email (camino 2, `dispatch_pending_payment_links_task`).
        return ResultadoCompra(message=MENSAJE_GENERICO, checkout_url=None)

    try:
        checkout_url = await crear_sesion_de_pago(session, payment_id=payment_id)
    except ExternalServiceError:
        # La fila queda `pending` sin sesión; el barrido la expira por su
        # ventana y libera todo. Nunca queda dinero cobrado sin fila, porque
        # el cobro no ha empezado.
        raise
    return ResultadoCompra(message=MENSAJE_GENERICO, checkout_url=checkout_url)


async def crear_sesion_de_pago(session: AsyncSession, *, payment_id: uuid.UUID) -> str | None:
    """T2: crea la Checkout Session en Stripe y persiste la URL — nunca bajo
    bloqueos de fila. La reutilizan la compra y
    `dispatch_pending_payment_links_task` (caminos 2, 3 y 4).

    Devuelve `None` (idempotente, no crea una segunda sesión) si el pago ya
    no está en `pending` o si ya tiene el enlace entregado.
    """
    pago = await session.get(EventPayment, payment_id)
    if pago is None:
        return None
    if pago.status != "pending" or pago.checkout_link_delivered_at is not None:
        return pago.checkout_url

    cuenta = await repository.get_cuenta_por_stripe_account_id(session, pago.stripe_account_id)
    if cuenta is None:  # pragma: no cover - la cuenta que cobró siempre queda persistida
        raise ExternalServiceError("La cuenta de Stripe de esta compra ya no está disponible.")

    tipo = await repository.get_ticket_type(
        session, pago.organization_id, pago.event_id, pago.ticket_type_id
    )
    evento = await session.get(Event, pago.event_id)
    ventana_minutos = evento.payment_checkout_window_minutes if evento is not None else 30
    base = await base_url_de_organizacion(pago.organization_id)

    expires_at_epoch = int(
        (datetime.now(UTC) + timedelta(minutes=ventana_minutos) + _MARGEN_TECNICO).timestamp()
    )

    creada = await stripe_gateway.crear_sesion_checkout(
        cuenta,
        linea=stripe_gateway.LineaDePrecioAdHoc(
            currency=pago.currency,
            unit_amount_cents=pago.amount_cents,
            product_name=tipo.name if tipo is not None else "Entrada",
        ),
        success_url=f"{base}/pago/retorno?registration_id={pago.registration_id}",
        cancel_url=f"{base}/pago/cancelado?registration_id={pago.registration_id}",
        expires_at_epoch=expires_at_epoch,
        idempotency_key=f"checkout_{pago.id}_{pago.checkout_attempts}",
        client_reference_id=str(pago.registration_id) if pago.registration_id else None,
        metadata={"payment_id": str(pago.id), "event_id": str(pago.event_id)},
    )

    pago.stripe_checkout_session_id = creada.stripe_checkout_session_id
    pago.checkout_url = creada.checkout_url
    pago.expires_at = datetime.fromtimestamp(creada.expires_at_epoch, tz=UTC)
    pago.checkout_link_delivered_at = datetime.now(UTC)

    if pago.registration_id is not None:
        inscripcion = await session.get(EventRegistration, pago.registration_id)
        if inscripcion is not None and inscripcion.status == "pending_payment":
            inscripcion.payment_expires_at = pago.expires_at

    await session.commit()
    return pago.checkout_url


async def confirmar_pago_y_registro(
    session: AsyncSession,
    pago: EventPayment,
    inscripcion: EventRegistration,
    *,
    stripe_payment_intent_id: str | None,
) -> None:
    """Aplica el efecto de dominio de un pago cobrado: marca el pago `paid` y
    confirma la inscripción llamando a `_enviar_email_por_estado` — el mismo
    punto único de emisión que usan los otros cuatro caminos. El módulo de
    pagos **nunca** llama a `emitir_entrada` directamente (Decisión #6 del
    plan). Idempotente por partida doble: no-op si el pago ya estaba `paid` o
    la inscripción ya `confirmed`.
    """
    if pago.status != "paid":
        pago.status = "paid"
        pago.paid_at = datetime.now(UTC)
        if stripe_payment_intent_id is not None:
            pago.stripe_payment_intent_id = stripe_payment_intent_id
    if inscripcion.status != "confirmed":
        inscripcion.status = "confirmed"
        inscripcion.confirmed_at = datetime.now(UTC)
        await registrations_service._enviar_email_por_estado(session, inscripcion)  # noqa: SLF001


async def dispatch_pending_payment_links() -> None:
    """`dispatch_pending_payment_links_task`: crea (o reintenta) la Checkout
    Session de los caminos 2, 3 y 4, fuera de la petición que verificó,
    aprobó o promovió (hallazgo #12), y encola el correo con el enlace.
    Idempotente: `crear_sesion_de_pago` no crea una segunda sesión ni un
    segundo correo una vez `checkout_link_delivered_at` está fijado.
    """
    from app.core.tasks import send_registration_payment_link_email
    from app.modules.registrations.service import _generar_token_cancelacion  # noqa: SLF001

    async with maintenance_session() as session:
        pagos = await repository.pagos_sin_enlace_entregado(session)
        for payment_id in pagos:
            try:
                url = await crear_sesion_de_pago(session, payment_id=payment_id)
            except ExternalServiceError:
                logger.warning("No se pudo crear la sesión de pago %s; se reintentará.", payment_id)
                continue
            if url is None:
                continue

            pago = await session.get(EventPayment, payment_id)
            if pago is None or pago.registration_id is None:
                continue
            inscripcion = await session.get(EventRegistration, pago.registration_id)
            if inscripcion is None:
                continue

            cancel_token = await _generar_token_cancelacion(inscripcion.id)
            expira_el = pago.expires_at.strftime("%d/%m/%Y %H:%M") if pago.expires_at else ""
            await send_registration_payment_link_email.kiq(
                inscripcion.email, str(inscripcion.organization_id), url, cancel_token, expira_el
            )


async def expirar_pagos_pendientes() -> None:
    """`expire_pending_payments_task`: antes de expirar, consulta el estado
    real en Stripe (recupera un webhook perdido) — la única llamada síncrona
    a Stripe fuera del camino de la petición. Nunca bajo un bloqueo de fila:
    la consulta ocurre entre dos secciones bloqueadas por separado."""
    async with maintenance_session() as session:
        candidatos = await repository.pagos_pendientes_caducados(session)

    for candidato in candidatos:
        estado_stripe: str | None = None
        if candidato.stripe_checkout_session_id is not None:
            try:
                estado_stripe = await stripe_gateway.consultar_sesion_checkout(
                    stripe_account_id=candidato.stripe_account_id,
                    stripe_checkout_session_id=candidato.stripe_checkout_session_id,
                )
            except ExternalServiceError:
                logger.warning(
                    "No se pudo consultar la sesión %s antes de expirar el pago %s.",
                    candidato.stripe_checkout_session_id,
                    candidato.payment_id,
                )

        async with maintenance_session() as session:
            pago = await session.get(EventPayment, candidato.payment_id, with_for_update=True)
            if pago is None or pago.status != "pending" or pago.registration_id is None:
                continue
            inscripcion = await session.get(
                EventRegistration, pago.registration_id, with_for_update=True
            )
            if inscripcion is None or inscripcion.status != "pending_payment":
                # Ya confirmada o cancelada por otro camino concurrente
                # (webhook, autocancelación): nada que hacer aquí.
                continue

            if estado_stripe == "paid":
                await confirmar_pago_y_registro(
                    session, pago, inscripcion, stripe_payment_intent_id=None
                )
                continue

            pago.status = "expired"
            await registrations_service._cancelar_inscripcion(  # noqa: SLF001
                session,
                organization_id=inscripcion.organization_id,
                event_id=inscripcion.event_id,
                inscripcion=inscripcion,
            )
