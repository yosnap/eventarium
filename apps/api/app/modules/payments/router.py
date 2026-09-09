"""Endpoints de conexión Stripe Connect, tipos de entrada y códigos de descuento.

`/organizations/{organization_id}/stripe...`, no `/organizations/me/...`
(patrón de `organizations/router.py`/`sponsors/router.py`): el Success
Criteria de aislamiento exige que un organizador de la organización A reciba
404 al pedir el `{organization_id}` de B, así que el identificador tiene que
viajar en la ruta para poder probarlo. `_organizacion_propia` es quien cierra
ese hueco: nunca se confía en el `{organization_id}` de la URL por sí solo,
se exige que coincida con el de la sesión autenticada.

Fase 3 de trabajo: dos routers adicionales en el mismo fichero, mismo patrón
que `sponsors/router.py` (niveles/patrocinadores) — `router_ticket_types` y
`router_discount_codes` cuelgan de `/events/{event_id}/...`, resuelto por
`usuario.organization_id` igual que `registrations/router.py`.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.config import get_settings
from app.core.deps import CurrentUserDep, DbDep, require_permission
from app.core.permissions import Permission
from app.core.ratelimit import STRIPE_SYNC_POR_IP, limit_per_ip
from app.modules.events import repository as events_repository
from app.modules.events.models import Event
from app.modules.payments import refunds_service, repository, service
from app.modules.payments.models import (
    EventDiscountCode,
    EventTicketType,
    OrganizationStripeAccount,
)
from app.modules.payments.refunds_service import PaymentOut
from app.modules.payments.schemas import (
    DiscountCodeCreate,
    DiscountCodeResponse,
    DiscountCodeUpdate,
    PaymentListItem,
    PaymentRefundOut,
    RefundAcceptedResponse,
    RefundRequest,
    StripeAccountResponse,
    StripeOnboardingResponse,
    TicketTypeCreate,
    TicketTypeResponse,
    TicketTypeUpdate,
    estado_no_conectado,
)
from app.shared.errors import NotFoundError, ServiceUnavailableError

router = APIRouter(prefix="/organizations/{organization_id}/stripe", tags=["pagos"])
router_ticket_types = APIRouter(prefix="/events/{event_id}/ticket-types", tags=["pagos"])
router_discount_codes = APIRouter(prefix="/events/{event_id}/discount-codes", tags=["pagos"])
router_payments = APIRouter(prefix="/events/{event_id}/payments", tags=["pagos"])


def _organizacion_propia(organization_id: str, usuario: CurrentUserDep) -> uuid.UUID:
    """Exige que el `{organization_id}` de la ruta sea el de la sesión.

    Un usuario solo pertenece a una organización por sesión (`CurrentUser`,
    fijado por el `Host`), así que cualquier otro valor es, por definición,
    de otra organización: se responde 404 (no 403) para no confirmar ni
    siquiera que ese identificador exista.
    """
    try:
        id_de_la_ruta = uuid.UUID(organization_id)
    except ValueError as exc:
        raise NotFoundError("Esa organización no existe.") from exc
    if id_de_la_ruta != usuario.organization_id:
        raise NotFoundError("Esa organización no existe.")
    return id_de_la_ruta


OrganizationIdDep = Annotated[uuid.UUID, Depends(_organizacion_propia)]


def _exigir_pagos_habilitados() -> None:
    if not get_settings().payments_enabled:
        raise ServiceUnavailableError(
            "Los pagos no están configurados en esta instalación. Contacta con quien "
            "administra la plataforma."
        )


def _account_response(cuenta: OrganizationStripeAccount | None) -> StripeAccountResponse:
    if cuenta is None:
        return estado_no_conectado()
    return StripeAccountResponse(
        connected=True,
        charges_enabled=cuenta.charges_enabled,
        payouts_enabled=cuenta.payouts_enabled,
        details_submitted=cuenta.details_submitted,
        connected_at=cuenta.connected_at,
        deauthorized_at=cuenta.deauthorized_at,
        last_synced_at=cuenta.last_synced_at,
    )


@router.post(
    "/onboarding",
    summary="Iniciar (o reiniciar) el onboarding de Stripe Connect",
    description=(
        "Crea una cuenta Standard si no hay ninguna activa (o si la única fila está "
        "desautorizada) y devuelve la URL de un solo uso del Account Link. Nunca crea "
        "una segunda cuenta activa."
    ),
    response_model=StripeOnboardingResponse,
    dependencies=[
        require_permission(Permission.PAYMENTS_WRITE),
        Depends(_exigir_pagos_habilitados),
    ],
)
async def start_onboarding(
    organization_id: OrganizationIdDep, session: DbDep
) -> StripeOnboardingResponse:
    url = await service.iniciar_onboarding(session, organization_id=organization_id)
    return StripeOnboardingResponse(onboarding_url=url)


@router.get(
    "",
    summary="Estado persistido de la conexión con Stripe",
    description="Lee únicamente lo persistido: nunca llama a Stripe.",
    response_model=StripeAccountResponse,
    dependencies=[
        require_permission(Permission.PAYMENTS_READ),
        Depends(_exigir_pagos_habilitados),
    ],
)
async def get_stripe_status(
    organization_id: OrganizationIdDep, session: DbDep
) -> StripeAccountResponse:
    cuenta = await service.obtener_estado(session, organization_id=organization_id)
    return _account_response(cuenta)


@router.post(
    "/sync",
    summary="Sincronizar el estado con el `Account` real de Stripe",
    description=(
        "Única ruta del panel que provoca una llamada de red a Stripe por petición: "
        "el frontend la invoca al volver del onboarding y desde el botón manual."
    ),
    response_model=StripeAccountResponse,
    dependencies=[
        require_permission(Permission.PAYMENTS_WRITE),
        Depends(_exigir_pagos_habilitados),
        limit_per_ip("stripe-sync", STRIPE_SYNC_POR_IP),
    ],
)
async def sync_stripe_status(
    organization_id: OrganizationIdDep, session: DbDep
) -> StripeAccountResponse:
    cuenta = await service.sincronizar_estado(session, organization_id=organization_id)
    return _account_response(cuenta)


# --- Tipos de entrada ---------------------------------------------------------


async def _obtener_evento_o_404(usuario: CurrentUserDep, session: DbDep, event_id: str) -> Event:
    evento = await events_repository.get_event(
        session, usuario.organization_id, uuid.UUID(event_id)
    )
    if evento is None:
        raise NotFoundError("El evento no existe.")
    return evento


def _ticket_type_response(tipo: EventTicketType) -> TicketTypeResponse:
    return TicketTypeResponse(
        id=str(tipo.id),
        name=tipo.name,
        description=tipo.description,
        price_cents=tipo.price_cents,
        currency=tipo.currency,
        max_quantity=tipo.max_quantity,
        sales_start_at=tipo.sales_start_at,
        sales_end_at=tipo.sales_end_at,
        sort_order=tipo.sort_order,
        is_active=tipo.is_active,
    )


@router_ticket_types.get(
    "",
    summary="Listar los tipos de entrada de un evento",
    response_model=list[TicketTypeResponse],
    dependencies=[require_permission(Permission.PAYMENTS_READ)],
)
async def list_ticket_types(
    evento: Annotated[Event, Depends(_obtener_evento_o_404)], session: DbDep
) -> list[TicketTypeResponse]:
    tipos = await service.list_ticket_types(
        session, organization_id=evento.organization_id, event_id=evento.id
    )
    return [_ticket_type_response(tipo) for tipo in tipos]


@router_ticket_types.post(
    "",
    summary="Crear un tipo de entrada",
    status_code=201,
    response_model=TicketTypeResponse,
    dependencies=[require_permission(Permission.PAYMENTS_WRITE)],
)
async def create_ticket_type(
    datos: TicketTypeCreate,
    evento: Annotated[Event, Depends(_obtener_evento_o_404)],
    session: DbDep,
) -> TicketTypeResponse:
    tipo = await service.create_ticket_type(
        session,
        organization_id=evento.organization_id,
        event_id=evento.id,
        datos=datos.model_dump(),
    )
    return _ticket_type_response(tipo)


@router_ticket_types.patch(
    "/{ticket_type_id}",
    summary="Editar un tipo de entrada",
    description=(
        "Reordenar es un caso particular de edición: el panel envía el nuevo "
        "`sort_order` de cada tipo afectado con peticiones sucesivas, mismo "
        "patrón que `sponsor_tiers`."
    ),
    response_model=TicketTypeResponse,
    dependencies=[require_permission(Permission.PAYMENTS_WRITE)],
)
async def update_ticket_type(
    datos: TicketTypeUpdate,
    evento: Annotated[Event, Depends(_obtener_evento_o_404)],
    session: DbDep,
    ticket_type_id: str,
) -> TicketTypeResponse:
    tipo = await service.update_ticket_type(
        session,
        organization_id=evento.organization_id,
        event_id=evento.id,
        ticket_type_id=uuid.UUID(ticket_type_id),
        datos=datos.model_dump(exclude_unset=True),
    )
    return _ticket_type_response(tipo)


@router_ticket_types.delete(
    "/{ticket_type_id}",
    summary="Borrar un tipo de entrada",
    description=(
        "Falla con 409 si tiene códigos de descuento o pagos asociados; "
        "desactívalo (`is_active = false`) en su lugar."
    ),
    status_code=204,
    dependencies=[require_permission(Permission.PAYMENTS_WRITE)],
)
async def delete_ticket_type(
    evento: Annotated[Event, Depends(_obtener_evento_o_404)],
    session: DbDep,
    ticket_type_id: str,
) -> None:
    await service.delete_ticket_type(
        session,
        organization_id=evento.organization_id,
        event_id=evento.id,
        ticket_type_id=uuid.UUID(ticket_type_id),
    )


# --- Códigos de descuento -------------------------------------------------


def _discount_code_response(codigo: EventDiscountCode, used_count: int) -> DiscountCodeResponse:
    return DiscountCodeResponse(
        id=str(codigo.id),
        code=codigo.code,
        discount_type=codigo.discount_type,  # type: ignore[arg-type]
        discount_value=codigo.discount_value,
        max_uses=codigo.max_uses,
        valid_from=codigo.valid_from,
        valid_until=codigo.valid_until,
        ticket_type_id=str(codigo.ticket_type_id) if codigo.ticket_type_id else None,
        used_count=used_count,
    )


@router_discount_codes.get(
    "",
    summary="Listar los códigos de descuento de un evento",
    description="`used_count` es siempre derivado de los pagos, nunca un contador guardado.",
    response_model=list[DiscountCodeResponse],
    dependencies=[require_permission(Permission.PAYMENTS_READ)],
)
async def list_discount_codes(
    evento: Annotated[Event, Depends(_obtener_evento_o_404)], session: DbDep
) -> list[DiscountCodeResponse]:
    codigos = await service.list_discount_codes(
        session, organization_id=evento.organization_id, event_id=evento.id
    )
    return [_discount_code_response(codigo, usos) for codigo, usos in codigos]


@router_discount_codes.post(
    "",
    summary="Crear un código de descuento",
    status_code=201,
    response_model=DiscountCodeResponse,
    dependencies=[require_permission(Permission.PAYMENTS_WRITE)],
)
async def create_discount_code(
    datos: DiscountCodeCreate,
    evento: Annotated[Event, Depends(_obtener_evento_o_404)],
    session: DbDep,
) -> DiscountCodeResponse:
    valores = datos.model_dump()
    if valores.get("ticket_type_id") is not None:
        valores["ticket_type_id"] = uuid.UUID(valores["ticket_type_id"])
    codigo = await service.create_discount_code(
        session, organization_id=evento.organization_id, event_id=evento.id, datos=valores
    )
    return _discount_code_response(codigo, 0)


@router_discount_codes.patch(
    "/{discount_code_id}",
    summary="Editar un código de descuento",
    response_model=DiscountCodeResponse,
    dependencies=[require_permission(Permission.PAYMENTS_WRITE)],
)
async def update_discount_code(
    datos: DiscountCodeUpdate,
    evento: Annotated[Event, Depends(_obtener_evento_o_404)],
    session: DbDep,
    discount_code_id: str,
) -> DiscountCodeResponse:
    valores = datos.model_dump(exclude_unset=True)
    if valores.get("ticket_type_id") is not None:
        valores["ticket_type_id"] = uuid.UUID(valores["ticket_type_id"])
    codigo = await service.update_discount_code(
        session,
        organization_id=evento.organization_id,
        event_id=evento.id,
        discount_code_id=uuid.UUID(discount_code_id),
        datos=valores,
    )
    usos = await repository.count_used_discount_code(session, evento.organization_id, codigo.id)
    return _discount_code_response(codigo, usos)


@router_discount_codes.delete(
    "/{discount_code_id}",
    summary="Borrar un código de descuento",
    description="Falla con 409 si el código tiene pagos asociados.",
    status_code=204,
    dependencies=[require_permission(Permission.PAYMENTS_WRITE)],
)
async def delete_discount_code(
    evento: Annotated[Event, Depends(_obtener_evento_o_404)],
    session: DbDep,
    discount_code_id: str,
) -> None:
    await service.delete_discount_code(
        session,
        organization_id=evento.organization_id,
        event_id=evento.id,
        discount_code_id=uuid.UUID(discount_code_id),
    )


# --- Pagos y reembolsos (fase 6 del PRD, fase 5 de trabajo) ------------------


def _refund_response(refund: refunds_service.RefundOut) -> PaymentRefundOut:
    return PaymentRefundOut(
        id=str(refund.id),
        amount_cents=refund.amount_cents,
        reason=refund.reason,  # type: ignore[arg-type]
        revoke_ticket=refund.revoke_ticket,
        status=refund.status,  # type: ignore[arg-type]
        error=refund.error,
        attempts=refund.attempts,
    )


def _payment_list_item(pago_out: PaymentOut) -> PaymentListItem:
    pago = pago_out.payment
    return PaymentListItem(
        id=str(pago.id),
        registration_id=str(pago.registration_id) if pago.registration_id else None,
        email=pago_out.email,
        ticket_type_name=pago_out.ticket_type_name,
        status=pago.status,  # type: ignore[arg-type]
        amount_cents=pago.amount_cents,
        discount_cents=pago.discount_cents,
        currency=pago.currency,
        refunded_cents=pago.refunded_cents,
        paid_at=pago.paid_at,
        no_auto_refund_reason=pago_out.no_auto_refund_reason,  # type: ignore[arg-type]
        refunds=[_refund_response(fila) for fila in pago_out.refunds],
    )


@router_payments.get(
    "",
    summary="Listar los pagos de un evento",
    description=(
        "Estado, importes y reembolsos en curso de cada pago, con el motivo de «sin "
        "reembolso automático» cuando aplica — siempre derivado, nunca una columna guardada."
    ),
    response_model=list[PaymentListItem],
    dependencies=[require_permission(Permission.PAYMENTS_READ)],
)
async def list_payments(
    evento: Annotated[Event, Depends(_obtener_evento_o_404)], session: DbDep
) -> list[PaymentListItem]:
    pagos = await refunds_service.listar_pagos_del_evento(
        session, organization_id=evento.organization_id, event_id=evento.id
    )
    return [_payment_list_item(pago) for pago in pagos]


@router_payments.post(
    "/{payment_id}/refund",
    summary="Reembolsar un pago, total o parcialmente",
    description=(
        "Escribe la intención en el mismo outbox que el reembolso automático de una "
        "cancelación: nunca llama a Stripe en esta petición, así que un importe superior "
        "al pendiente falla con 409 antes de cualquier llamada de red. Un reembolso total "
        "revoca siempre la entrada, ignorando `revoke_ticket`; uno parcial no revoca salvo "
        "que se pida explícitamente."
    ),
    status_code=202,
    response_model=RefundAcceptedResponse,
    dependencies=[require_permission(Permission.PAYMENTS_WRITE)],
)
async def refund_payment(
    datos: RefundRequest,
    evento: Annotated[Event, Depends(_obtener_evento_o_404)],
    session: DbDep,
    payment_id: str,
) -> RefundAcceptedResponse:
    reembolso = await refunds_service.solicitar_reembolso_manual(
        session,
        organization_id=evento.organization_id,
        payment_id=uuid.UUID(payment_id),
        amount_cents=datos.amount_cents,
        revoke_ticket=datos.revoke_ticket,
    )

    from app.core.tasks import process_refunds_task

    await process_refunds_task.kiq()
    return RefundAcceptedResponse(refund_id=str(reembolso.id))
