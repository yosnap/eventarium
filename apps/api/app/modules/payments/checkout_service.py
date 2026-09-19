"""Compra pública de entradas: Checkout Session, enlaces de pago diferidos y
barrido de pagos pendientes caducados (fase 6 del PRD, fase 4 de trabajo).

**Nunca una llamada de red a Stripe con bloqueos de fila abiertos**. Por eso
la compra son dos transacciones distintas, nunca una sola:

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

from app.core.database import SessionApp, maintenance_session, set_organization_context
from app.core.tenant import base_url_de_organizacion
from app.modules.events.models import Event
from app.modules.payments import repository
from app.modules.payments import service as payments_service
from app.modules.payments import stripe_client as stripe_gateway
from app.modules.payments.models import EventPayment, OrganizationStripeAccount
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

# Margen técnico sobre la ventana del evento: el tiempo entre
# calcular `expires_at` y que Stripe reciba la petición podría, sin margen,
# cruzar su mínimo de 30 minutos cuando la ventana del evento está justo en
# ese mínimo.
_MARGEN_TECNICO = timedelta(seconds=60)


@dataclass(frozen=True, slots=True)
class ResultadoCompra:
    message: str
    checkout_url: str | None


async def _obtener_cuenta_operativa(
    session: AsyncSession, organization_id: uuid.UUID
) -> OrganizationStripeAccount:
    cuenta = await repository.get_cuenta_activa(session, organization_id)
    if cuenta is None or not cuenta.charges_enabled:
        raise ConflictError("Esta organización todavía no puede cobrar entradas.")
    return cuenta


async def iniciar_compra(
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

    Abre su **propia** sesión (`SessionApp`, con el contexto RLS de
    `event.organization_id`), en vez de recibir la del `DbDep` de la
    petición: `get_db` envuelve toda la petición en una única transacción
    (`app/core/deps.py::get_session`), así que un `commit` a mitad de camino
    chocaría con ese contexto exterior. T1 y T2 son, literalmente, dos
    transacciones distintas sobre la misma conexión — nunca la transacción
    de la petición.
    """
    async with SessionApp() as session:
        async with session.begin():
            await set_organization_context(session, event.organization_id)

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
            if inscripcion is None or inscripcion.status not in (
                "pending_payment",
                "pending_verification",
                "pending_approval",
                "waitlisted",
            ):
                # Ya existía y no es reactivable/pagable ahora mismo: la
                # respuesta pública es la misma de siempre, sin revelar en qué
                # estado está. `pending_approval`/`waitlisted` sí siguen: el
                # tipo de entrada y el código de descuento elegidos aquí son
                # los únicos que `approve_registration`/
                # `confirm_waitlist_promotion` tendrán disponibles más
                # adelante, cuando la inscripción llegue a `pending_payment`.
                return ResultadoCompra(message=MENSAJE_GENERICO, checkout_url=None)

            ahora = datetime.now(UTC)
            tipo = await repository.lock_ticket_type(session, event.organization_id, ticket_type_id)
            tipo_vigente = tipo is not None and payments_service.validar_tipo_vigente(tipo, ahora)
            if tipo is None or tipo.event_id != event.id or not tipo_vigente:
                raise ValidationDomainError("Este tipo de entrada no está disponible.")
            if tipo.max_quantity is not None:
                vendidas = await repository.count_used_ticket_type(
                    session, event.organization_id, tipo.id
                )
                if vendidas >= tipo.max_quantity:
                    raise ValidationDomainError("Este tipo de entrada está agotado.")

            discount_type: str | None = None
            discount_value: int | None = None
            discount_code_id: uuid.UUID | None = None
            if code:
                codigo = await repository.get_discount_code_by_code(
                    session, event.organization_id, event.id, code.strip().upper()
                )
                if codigo is not None:
                    codigo = await repository.lock_discount_code(
                        session, event.organization_id, codigo.id
                    )
                if codigo is None:
                    raise ValidationDomainError(payments_service.MENSAJE_CODIGO_NO_VALIDO)
                usos = await repository.count_used_discount_code(
                    session, event.organization_id, codigo.id
                )
                if not payments_service.validar_codigo_vigente(codigo, tipo, usos, ahora):
                    raise ValidationDomainError(payments_service.MENSAJE_CODIGO_NO_VALIDO)
                discount_type = codigo.discount_type
                discount_value = codigo.discount_value
                discount_code_id = codigo.id

            total = payments_service.calcular_precio_final(
                tipo.price_cents, discount_type, discount_value
            )

            pago, sesion_a_expirar = await repository.crear_o_reutilizar_pago(
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
            # Persistidos en la propia inscripción (fase 6 del PRD):
            # `approve_registration` y
            # `confirm_waitlist_promotion` no reciben ningún tipo de entrada
            # ni código de descuento por parámetro, así que sin esto no
            # tendrían forma de saber qué pago reutilizar cuando la
            # inscripción llegue a `pending_payment` más tarde.
            inscripcion.ticket_type_id = tipo.id
            inscripcion.discount_code_id = discount_code_id

            if inscripcion.status == "pending_payment":
                ventana = timedelta(minutes=event.payment_checkout_window_minutes)
                inscripcion.payment_expires_at = ahora + ventana

            payment_id = pago.id
            estado_resultante = inscripcion.status
        # --- fin de T1 (`session.begin()` ha hecho commit al salir del `with`):
        # la fila del pago ya persiste sin ningún bloqueo de fila abierto ---

        if sesion_a_expirar is not None:
            # Fuera de cualquier bloqueo de fila, y también
            # fuera de T2: si esto fallara no debe impedir crear la sesión
            # nueva, que es la parte que de verdad bloquearía la compra
            # (`stripe_client.expirar_sesion_checkout` no deja
            # escapar el error).
            await stripe_gateway.expirar_sesion_checkout(
                stripe_account_id=sesion_a_expirar.stripe_account_id,
                stripe_checkout_session_id=sesion_a_expirar.stripe_checkout_session_id,
            )

        if estado_resultante != "pending_payment":
            # `pending_verification`/`pending_approval`/`waitlisted`: la
            # sesión de pago se crea más tarde, cuando la inscripción llegue a
            # `pending_payment` por verificación, aprobación o promoción
            # (caminos 2, 3 y 4, `dispatch_pending_payment_links_task`). El
            # pago ya quedó creado arriba, en `pending`, sin sesión de Stripe.
            return ResultadoCompra(message=MENSAJE_GENERICO, checkout_url=None)

        async with session.begin():
            # T2, transacción propia: nunca comparte bloqueos con T1. `SET
            # LOCAL` (el contexto RLS) solo dura lo que dura su transacción,
            # así que hay que volver a fijarlo — T1 ya hizo `commit` y lo
            # perdió.
            await set_organization_context(session, event.organization_id)
            checkout_url = await crear_sesion_de_pago(session, payment_id=payment_id)
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
    # `evento` siempre existe en la práctica (la FK de `event_payments` a
    # `events` no admite huérfanos); el `else ""` es solo defensivo, igual que
    # el `else 30` de la línea anterior.
    evento_slug = evento.slug if evento is not None else ""
    base = await base_url_de_organizacion(pago.organization_id)

    inscripcion = (
        await session.get(EventRegistration, pago.registration_id)
        if pago.registration_id is not None
        else None
    )
    # Derivado de `payment_expires_at`, ya persistido por
    # `checkout_service.iniciar_compra`/`registrations.service` al dejar la
    # inscripción en `pending_payment` — **nunca** recalculado con
    # `datetime.now(UTC)` en cada llamada: un reintento (mismo
    # `checkout_attempts`, misma `idempotency_key`) que recalculara
    # `expires_at` en cada intento generaría un `expires_at` distinto cada
    # vez, y Stripe rechaza reutilizar una `idempotency_key` con parámetros
    # distintos.
    if inscripcion is None or inscripcion.payment_expires_at is None:
        # Nunca debería pasar en producción: todos los caminos que llegan
        # aquí fijan `payment_expires_at` antes de llamar a esta función. Si
        # este `logger.warning` aparece alguna vez, un `expires_at`
        # recalculado en cada llamada que rompa la idempotency_key podría
        # estar volviendo de forma silenciosa.
        logger.warning(
            "Pago %s sin payment_expires_at persistido: derivando expires_at con "
            "datetime.now(UTC), lo que puede romper la idempotency_key si esta "
            "función se reintenta.",
            pago.id,
        )
    limite = (
        inscripcion.payment_expires_at
        if inscripcion is not None and inscripcion.payment_expires_at is not None
        else datetime.now(UTC) + timedelta(minutes=ventana_minutos)
    )
    expires_at_epoch = int((limite + _MARGEN_TECNICO).timestamp())

    creada = await stripe_gateway.crear_sesion_checkout(
        cuenta,
        linea=stripe_gateway.LineaDePrecioAdHoc(
            currency=pago.currency,
            unit_amount_cents=pago.amount_cents,
            product_name=tipo.name if tipo is not None else "Entrada",
        ),
        # `slug` viaja en la URL porque el endpoint de estado
        # (`GET /public/events/{slug}/checkout/{registration_id}/status`) está
        # anidado bajo el evento, no solo bajo la inscripción: sin él, la
        # pantalla de retorno no podría ni siquiera preguntar por el estado
        # real del pago.
        success_url=(
            f"{base}/pago/retorno?registration_id={pago.registration_id}&slug={evento_slug}"
        ),
        cancel_url=(
            f"{base}/pago/cancelado?registration_id={pago.registration_id}&slug={evento_slug}"
        ),
        expires_at_epoch=expires_at_epoch,
        idempotency_key=f"checkout_{pago.id}_{pago.checkout_attempts}",
        client_reference_id=str(pago.registration_id) if pago.registration_id else None,
        metadata={"payment_id": str(pago.id), "event_id": str(pago.event_id)},
    )

    pago.stripe_checkout_session_id = creada.stripe_checkout_session_id
    pago.checkout_url = creada.checkout_url
    pago.expires_at = datetime.fromtimestamp(creada.expires_at_epoch, tz=UTC)
    pago.checkout_link_delivered_at = datetime.now(UTC)

    if inscripcion is not None and inscripcion.status == "pending_payment":
        inscripcion.payment_expires_at = pago.expires_at

    await session.flush()
    return pago.checkout_url


async def confirmar_pago_y_registro(
    session: AsyncSession,
    pago: EventPayment,
    inscripcion: EventRegistration,
    *,
    stripe_payment_intent_id: str | None,
) -> str:
    """Aplica el efecto de dominio de un pago cobrado: marca el pago `paid` y
    confirma la inscripción llamando a `_enviar_email_por_estado` — el mismo
    punto único de emisión que usan los otros cuatro caminos. El módulo de
    pagos nunca emite la entrada por su cuenta, ni de forma directa ni
    indirecta (Decisión #6 del plan): ese paso vive por completo en
    `registrations/service.py`.

    Exige el estado de partida exacto — `pago.status == "pending"` **y**
    `inscripcion.status == "pending_payment"` — antes de aplicar nada:
    comprobar cada campo por
    separado (`pago.status != "paid"`, `inscripcion.status != "confirmed"`)
    dejaba confirmar de nuevo un pago `refunded`/`expired` o una inscripción
    `cancelled`, siempre que el otro campo aún no hubiera cambiado. Devuelve
    `"processed"` si aplica el cambio (o si ya estaba aplicado del todo, caso
    idempotente) y `"ignored"` si el estado de partida no es el esperado —
    mismos valores que usa `StripeWebhookEvent.status`, para que el webhook
    los reutilice sin traducir nada.
    """
    if pago.status == "paid" and inscripcion.status == "confirmed":
        return "processed"
    if pago.status != "pending" or inscripcion.status != "pending_payment":
        logger.warning(
            "Se ignora la confirmación del pago %s: pago en %r, inscripción %s en %r.",
            pago.id,
            pago.status,
            inscripcion.id,
            inscripcion.status,
        )
        return "ignored"

    pago.status = "paid"
    pago.paid_at = datetime.now(UTC)
    if stripe_payment_intent_id is not None:
        pago.stripe_payment_intent_id = stripe_payment_intent_id
    inscripcion.status = "confirmed"
    inscripcion.confirmed_at = datetime.now(UTC)
    await registrations_service._enviar_email_por_estado(session, inscripcion)  # noqa: SLF001
    return "processed"


async def dispatch_pending_payment_links() -> None:
    """`dispatch_pending_payment_links_task`: crea (o reintenta) la Checkout
    Session de los caminos 2, 3 y 4, fuera de la petición que verificó,
    aprobó o promovió, y encola el correo con el enlace.
    Idempotente: `crear_sesion_de_pago` no crea una segunda sesión ni un
    segundo correo una vez `checkout_link_delivered_at` está fijado.

    Una `maintenance_session` **por pago**, no una sola para todo el bucle:
    con una única sesión, el
    `flush` del pago anterior deja sus bloqueos de fila abiertos durante la
    llamada de red a Stripe del pago siguiente — justo lo que nunca debe
    ocurrir. El correo se encola **después** de que su sesión haga `commit`
    (fin del `async with` de ese pago), nunca antes: encolarlo dentro de la
    transacción arriesgaría enviar un enlace de una fila que después no
    llegara a persistir.
    """
    from app.core.tasks import send_registration_payment_link_email
    from app.modules.registrations.service import _generar_token_cancelacion  # noqa: SLF001

    async with maintenance_session() as session:
        pagos = await repository.pagos_sin_enlace_entregado(session)

    for payment_id in pagos:
        try:
            async with maintenance_session() as session:
                url = await crear_sesion_de_pago(session, payment_id=payment_id)
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
                email = inscripcion.email
                organization_id = str(inscripcion.organization_id)
            # --- commit de la sesión de este pago: solo ahora se encola el
            # correo, con la URL y el token ya persistidos ---
            await send_registration_payment_link_email.kiq(
                email, organization_id, url, cancel_token, expira_el
            )
        except ExternalServiceError:
            logger.warning("No se pudo crear la sesión de pago %s; se reintentará.", payment_id)
            continue


async def expirar_pagos_pendientes() -> None:
    """`expire_pending_payments_task`: antes de expirar, consulta el estado
    real en Stripe (recupera un webhook perdido) — la única llamada síncrona
    a Stripe fuera del camino de la petición. Nunca bajo un bloqueo de fila:
    la consulta ocurre entre dos secciones bloqueadas por separado.

    `repository.pagos_pendientes_caducados` devuelve dos grupos de
    candidatos: los de
    siempre (`pending_payment` cuya ventana ya venció, sí consultados contra
    Stripe) y los de la red de seguridad (`cancelled`/`rejected` con un pago
    todavía `pending` que se les quedó huérfano) — a estos últimos nunca se
    les creó una Checkout Session real que consultar, así que solo hace falta
    marcar el pago `expired`, sin llamar a Stripe ni volver a tocar la
    inscripción (ya está en su estado terminal).
    """
    async with maintenance_session() as session:
        candidatos = await repository.pagos_pendientes_caducados(session)

    for candidato in candidatos:
        estado_stripe: str | None = None
        if (
            candidato.registration_status == "pending_payment"
            and candidato.stripe_checkout_session_id is not None
        ):
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
            if inscripcion is None:
                continue

            if inscripcion.status in repository.ESTADOS_TERMINALES_SIN_PAGO:
                # Red de seguridad: la inscripción ya está en un estado
                # terminal (por `reject_registration`, `_cancelar_inscripcion`
                # o cualquier otro camino que no haya expirado el pago él
                # mismo) — solo libera el cupo/uso de código, sin llamar a
                # Stripe ni tocar de nuevo la inscripción.
                pago.status = "expired"
                continue

            if inscripcion.status != "pending_payment":
                # Ya confirmada, o cambió de estado entre la lectura de
                # candidatos y este bloqueo por otro camino concurrente
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
