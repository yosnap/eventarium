"""Servicios de conexión Stripe Connect (fase 6 del PRD, fase 2 de trabajo).

Onboarding, reconexión tras desautorización y sincronización de estado. Las
llamadas a Stripe pasan siempre por `stripe_client.py`, y el `acct_id` de
destino siempre por `repository.get_cuenta_activa` — nunca un valor recibido
del cliente.

**Orden de adquisición de bloqueos, único para todo este módulo** (fase 3 de
trabajo, hallazgo #12 del red-team): `event_registrations` → `events` →
`event_ticket_types` → `event_discount_codes`. Es el mismo orden que ya usan
los caminos existentes (`registrations/service.py:_cancelar_inscripcion`
bloquea la inscripción y después el evento vía `lock_event_for_capacity`);
invertirlo en el camino de compra (fase 4 de trabajo) provocaría
interbloqueos entre una compra y una cancelación concurrentes. Ningún
llamador de este módulo debe adquirir `event_ticket_types`/
`event_discount_codes` antes que `events`, ni `event_discount_codes` antes
que `event_ticket_types`.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import base_url_de_organizacion
from app.modules.payments import repository
from app.modules.payments import stripe_client as stripe_gateway
from app.modules.payments.models import (
    EventDiscountCode,
    EventTicketType,
    OrganizationStripeAccount,
)
from app.shared.errors import ConflictError, NotFoundError, ValidationDomainError

logger = logging.getLogger(__name__)

# Mensaje único de cara al público para cualquiera de los cuatro motivos por
# los que un código de descuento no se acepta (caducado, agotado, inexistente
# o de otro tipo de entrada) — Success Criteria de la fase 3 de trabajo: un
# oráculo que distinguiera el motivo permitiría enumerar códigos por fuerza
# bruta. El motivo exacto solo se registra en el log del servidor.
MENSAJE_CODIGO_NO_VALIDO = "Este código no es válido para esta entrada."

# Ambas rutas vuelven al panel de conexión de Stripe. `refresh` distingue el
# caso «el enlace ha caducado» del retorno normal, aunque las dos disparan la
# misma sincronización manual en el frontend.
_RUTA_RETORNO = "/admin/stripe?onboarding=retorno"
_RUTA_REFRESCO = "/admin/stripe?onboarding=refresco"


async def iniciar_onboarding(session: AsyncSession, *, organization_id: uuid.UUID) -> str:
    """Devuelve la URL de un solo uso del `AccountLink`.

    Si no hay cuenta activa (nunca conectó, o su única fila está
    `deauthorized_at`), crea una cuenta **nueva** y la persiste antes de
    pedir el enlace. Si ya hay una activa, genera un enlace nuevo sobre la
    **misma** cuenta: nunca se crea una segunda cuenta activa para la misma
    organización (el índice único parcial de la fase 1 lo impediría de
    todos modos, pero la comprobación aquí evita el viaje de red innecesario
    a Stripe que terminaría en error).
    """
    cuenta = await repository.get_cuenta_activa(session, organization_id)
    if cuenta is None:
        idempotency_key = f"connect-account-{uuid.uuid4()}"
        creada = await stripe_gateway.crear_cuenta_conectada(idempotency_key=idempotency_key)
        cuenta = await repository.crear_cuenta(
            session,
            organization_id=organization_id,
            stripe_account_id=creada.stripe_account_id,
        )

    base = await base_url_de_organizacion(organization_id)
    return await stripe_gateway.crear_enlace_onboarding(
        cuenta,
        return_url=f"{base}{_RUTA_RETORNO}",
        refresh_url=f"{base}{_RUTA_REFRESCO}",
    )


async def obtener_estado(
    session: AsyncSession, *, organization_id: uuid.UUID
) -> OrganizationStripeAccount | None:
    """Estado persistido, sin llamar nunca a Stripe (decisión #13 del plan):
    `None` si la organización no tiene ninguna cuenta activa."""
    return await repository.get_cuenta_activa(session, organization_id)


async def sincronizar_estado(
    session: AsyncSession, *, organization_id: uuid.UUID
) -> OrganizationStripeAccount:
    """Consulta el `Account` real y refresca las banderas persistidas.

    Es la única operación de este servicio que hace una llamada de red a
    Stripe por petición — de ahí su límite de peticiones propio
    (`STRIPE_SYNC_POR_IP`, `router.py`).
    """
    cuenta = await repository.get_cuenta_activa(session, organization_id)
    if cuenta is None:
        raise NotFoundError("Esta organización no tiene ninguna cuenta de Stripe conectada.")

    estado = await stripe_gateway.consultar_cuenta(cuenta)
    return await repository.actualizar_estado(
        session,
        cuenta,
        charges_enabled=estado.charges_enabled,
        payouts_enabled=estado.payouts_enabled,
        details_submitted=estado.details_submitted,
        last_synced_at=datetime.now(UTC),
    )


# --- Cálculo de precio y vigencia (funciones puras, sin base de datos) -------
#
# Única implementación del cálculo de precio de todo el proyecto (Success
# Criteria de la fase 3 de trabajo): la fase 4 reutiliza `calcular_precio_final`
# tal cual para el importe que envía a Stripe, así que el presupuesto público y
# el cobro real salen siempre del mismo número.


def calcular_precio_final(
    price_cents: int, discount_type: str | None, discount_value: int | None
) -> int:
    """Aplica el descuento de un código sobre un precio y **satura en 0**.

    `percentage`: redondeo a la baja al céntimo (división entera). Un `100%`
    da 0. `fixed_amount` mayor que el precio también da 0, nunca negativo. Sin
    código (`discount_type`/`discount_value` a `None`) devuelve el precio tal
    cual, saturado igualmente por si `price_cents` llegara negativo.
    """
    if price_cents < 0:
        price_cents = 0
    if discount_type is None or discount_value is None:
        return price_cents
    if discount_type == "percentage":
        descuento = (price_cents * discount_value) // 100
    elif discount_type == "fixed_amount":
        descuento = discount_value
    else:
        raise ValueError(f"discount_type desconocido: {discount_type!r}")
    return max(price_cents - descuento, 0)


def validar_tipo_vigente(tipo: EventTicketType, ahora: datetime) -> bool:
    """`True` si el tipo se puede vender en `ahora`: activo y dentro de su
    ventana de venta (ambos extremos opcionales)."""
    if not tipo.is_active:
        return False
    if tipo.sales_start_at is not None and ahora < tipo.sales_start_at:
        return False
    if tipo.sales_end_at is not None and ahora > tipo.sales_end_at:
        return False
    return True


def validar_codigo_vigente(
    codigo: EventDiscountCode, tipo: EventTicketType, usos: int, ahora: datetime
) -> bool:
    """`True` si `codigo` se puede aplicar a `tipo` en `ahora`, con `usos` ya
    derivados de `event_payments` (nunca un contador denormalizado).

    Comprueba, en este orden, la ventana de vigencia, el tope de usos frente al
    derivado, y que el código no esté restringido a otro tipo de entrada
    (`ticket_type_id IS NULL` significa "aplica a todos").
    """
    if codigo.valid_from is not None and ahora < codigo.valid_from:
        return False
    if codigo.valid_until is not None and ahora > codigo.valid_until:
        return False
    if codigo.max_uses is not None and usos >= codigo.max_uses:
        return False
    if codigo.ticket_type_id is not None and codigo.ticket_type_id != tipo.id:
        return False
    return True


# --- Tipos de entrada: CRUD del panel -----------------------------------------


async def list_ticket_types(
    session: AsyncSession, *, organization_id: uuid.UUID, event_id: uuid.UUID
) -> list[EventTicketType]:
    return await repository.get_ticket_types(session, organization_id, event_id)


async def list_public_ticket_types(
    session: AsyncSession, *, organization_id: uuid.UUID, event_id: uuid.UUID
) -> list[EventTicketType]:
    """Tipos de entrada que el formulario público de compra puede ofrecer:
    vigentes en el instante de la consulta (fase 4 de trabajo de la fase 6
    del PRD). Reutiliza `validar_tipo_vigente` — la misma función que decide
    si un `checkout/quote` acepta el tipo — para que listado y validación
    nunca diverjan."""
    ahora = datetime.now(UTC)
    tipos = await repository.get_ticket_types(session, organization_id, event_id)
    return [tipo for tipo in tipos if validar_tipo_vigente(tipo, ahora)]


async def create_ticket_type(
    session: AsyncSession, *, organization_id: uuid.UUID, event_id: uuid.UUID, datos: dict[str, Any]
) -> EventTicketType:
    try:
        return await repository.create_ticket_type(
            session, organization_id=organization_id, event_id=event_id, datos=datos
        )
    except IntegrityError as exc:
        raise ConflictError(
            f"Ya existe un tipo de entrada llamado «{datos.get('name')}» en este evento."
        ) from exc


async def update_ticket_type(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    ticket_type_id: uuid.UUID,
    datos: dict[str, Any],
) -> EventTicketType:
    tipo = await repository.get_ticket_type(session, organization_id, event_id, ticket_type_id)
    if tipo is None:
        raise NotFoundError("El tipo de entrada no existe.")

    for campo, valor in datos.items():
        setattr(tipo, campo, valor)

    try:
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError(
            f"Ya existe un tipo de entrada llamado «{datos.get('name', tipo.name)}» en este evento."
        ) from exc
    return tipo


async def delete_ticket_type(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    ticket_type_id: uuid.UUID,
) -> None:
    """Borra un tipo de entrada; 409 si tiene códigos de descuento o pagos
    asociados — comprobado explícitamente aquí (mensaje claro) y respaldado
    por la FK sin `ondelete` de la fase 1 (nunca un 500 sin traducir)."""
    tipo = await repository.get_ticket_type(session, organization_id, event_id, ticket_type_id)
    if tipo is None:
        raise NotFoundError("El tipo de entrada no existe.")

    if await repository.ticket_type_has_dependencies(session, organization_id, tipo.id):
        raise ConflictError(
            "No se puede borrar un tipo de entrada con códigos de descuento o pagos "
            "asociados. Desactívalo en su lugar (`is_active = false`)."
        )

    await session.delete(tipo)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError(
            "No se puede borrar un tipo de entrada con dependencias asociadas."
        ) from exc


# --- Códigos de descuento: CRUD del panel -------------------------------------


def _normalizar_codigo(code: str) -> str:
    normalizado = code.strip().upper()
    if not normalizado:
        raise ValidationDomainError("El código de descuento no puede estar vacío.")
    return normalizado


async def _asegurar_tipo_del_evento(
    session: AsyncSession,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    ticket_type_id: uuid.UUID,
) -> None:
    tipo = await repository.get_ticket_type(session, organization_id, event_id, ticket_type_id)
    if tipo is None:
        raise ValidationDomainError("El tipo de entrada indicado no existe en este evento.")


async def list_discount_codes(
    session: AsyncSession, *, organization_id: uuid.UUID, event_id: uuid.UUID
) -> list[tuple[EventDiscountCode, int]]:
    """Cada código junto a su `used_count` derivado, para el panel."""
    codigos = await repository.get_discount_codes(session, organization_id, event_id)
    return [
        (codigo, await repository.count_used_discount_code(session, organization_id, codigo.id))
        for codigo in codigos
    ]


async def create_discount_code(
    session: AsyncSession, *, organization_id: uuid.UUID, event_id: uuid.UUID, datos: dict[str, Any]
) -> EventDiscountCode:
    datos = dict(datos)
    datos["code"] = _normalizar_codigo(datos["code"])
    ticket_type_id = datos.get("ticket_type_id")
    if ticket_type_id is not None:
        await _asegurar_tipo_del_evento(session, organization_id, event_id, ticket_type_id)

    try:
        return await repository.create_discount_code(
            session, organization_id=organization_id, event_id=event_id, datos=datos
        )
    except IntegrityError as exc:
        raise ConflictError(f"Ya existe un código «{datos['code']}» en este evento.") from exc


async def update_discount_code(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    discount_code_id: uuid.UUID,
    datos: dict[str, Any],
) -> EventDiscountCode:
    codigo = await repository.get_discount_code(
        session, organization_id, event_id, discount_code_id
    )
    if codigo is None:
        raise NotFoundError("El código de descuento no existe.")

    if "code" in datos:
        datos["code"] = _normalizar_codigo(datos["code"])
    if datos.get("ticket_type_id") is not None:
        await _asegurar_tipo_del_evento(session, organization_id, event_id, datos["ticket_type_id"])

    for campo, valor in datos.items():
        setattr(codigo, campo, valor)

    try:
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError(
            f"Ya existe un código «{datos.get('code', codigo.code)}» en este evento."
        ) from exc
    return codigo


async def delete_discount_code(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    discount_code_id: uuid.UUID,
) -> None:
    codigo = await repository.get_discount_code(
        session, organization_id, event_id, discount_code_id
    )
    if codigo is None:
        raise NotFoundError("El código de descuento no existe.")

    if await repository.discount_code_has_payments(session, organization_id, codigo.id):
        raise ConflictError("No se puede borrar un código de descuento con pagos asociados.")

    await session.delete(codigo)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError(
            "No se puede borrar un código de descuento con pagos asociados."
        ) from exc


# --- Presupuesto público (`POST /public/events/{slug}/checkout/quote`) ------


class PresupuestoDeCompra:
    """Resultado de un presupuesto: puramente informativo, no reserva cupo ni
    consume uso de código (ver `calcular_presupuesto`)."""

    __slots__ = ("price_cents", "discount_cents", "total_cents", "currency")

    def __init__(
        self, *, price_cents: int, discount_cents: int, total_cents: int, currency: str
    ) -> None:
        self.price_cents = price_cents
        self.discount_cents = discount_cents
        self.total_cents = total_cents
        self.currency = currency


async def calcular_presupuesto(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    ticket_type_id: uuid.UUID,
    code: str | None,
) -> PresupuestoDeCompra:
    """Presupuesto de compra: **nunca** reserva cupo ni consume uso de código,
    es puramente informativo (Non-functional de la fase 3 de trabajo). Solo
    lee filas, no las bloquea: el bloqueo (`FOR UPDATE`) es exclusivo del
    camino de cobro real, fase 4 de trabajo.
    """
    ahora = datetime.now(UTC)

    tipo = await repository.get_ticket_type(session, organization_id, event_id, ticket_type_id)
    if tipo is None or not validar_tipo_vigente(tipo, ahora):
        raise ValidationDomainError("Este tipo de entrada no está disponible.")

    if tipo.max_quantity is not None:
        vendidas = await repository.count_used_ticket_type(session, organization_id, tipo.id)
        if vendidas >= tipo.max_quantity:
            raise ValidationDomainError("Este tipo de entrada está agotado.")

    discount_type: str | None = None
    discount_value: int | None = None

    if code:
        code_normalizado = code.strip().upper()
        codigo = await repository.get_discount_code_by_code(
            session, organization_id, event_id, code_normalizado
        )
        if codigo is None:
            logger.info(
                "Presupuesto rechazado: código %r inexistente para el evento %s",
                code_normalizado,
                event_id,
            )
            raise ValidationDomainError(MENSAJE_CODIGO_NO_VALIDO)

        usos = await repository.count_used_discount_code(session, organization_id, codigo.id)
        if not validar_codigo_vigente(codigo, tipo, usos, ahora):
            logger.info(
                "Presupuesto rechazado: código %r no vigente para el tipo %s del evento %s "
                "(usos=%s, max_uses=%s, valid_from=%s, valid_until=%s, ticket_type_id=%s)",
                code_normalizado,
                tipo.id,
                event_id,
                usos,
                codigo.max_uses,
                codigo.valid_from,
                codigo.valid_until,
                codigo.ticket_type_id,
            )
            raise ValidationDomainError(MENSAJE_CODIGO_NO_VALIDO)

        discount_type = codigo.discount_type
        discount_value = codigo.discount_value

    total = calcular_precio_final(tipo.price_cents, discount_type, discount_value)
    return PresupuestoDeCompra(
        price_cents=tipo.price_cents,
        discount_cents=tipo.price_cents - total,
        total_cents=total,
        currency=tipo.currency,
    )
