"""Endpoints de escaneo y check-in de entradas (fase 4 del PRD, fase 2 de trabajo).

Mismo patrón que `registrations/router.py`: la organización se resuelve de
`usuario.organization_id` (nunca de la URL), sesión autenticada con permiso —
sin *rate limiting* específico, a diferencia de los endpoints públicos de la
fase 3 (no-funcional del plan).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.deps import CurrentUserDep, DbDep, require_permission
from app.core.permissions import Permission
from app.modules.events import repository as events_repository
from app.modules.events.models import Event
from app.modules.registrations.models import EventRegistration
from app.modules.tickets import repository, scanning
from app.modules.tickets.models import EventTicket
from app.modules.tickets.schemas import (
    ScanBatchRequest,
    ScanRequest,
    TicketDetail,
    TicketScanResultOut,
    TicketSearchItem,
)
from app.shared.errors import NotFoundError

router = APIRouter(prefix="/events/{event_id}", tags=["entradas"])


async def _obtener_evento_o_404(usuario: CurrentUserDep, session: DbDep, event_id: str) -> Event:
    evento = await events_repository.get_event(
        session, usuario.organization_id, uuid.UUID(event_id)
    )
    if evento is None:
        raise NotFoundError("El evento no existe.")
    return evento


def _resultado_out(resultado: scanning.ResultadoEscaneo) -> TicketScanResultOut:
    ticket: EventTicket | None = resultado.ticket
    inscripcion: EventRegistration | None = resultado.registration
    return TicketScanResultOut(
        client_scan_id=resultado.client_scan_id,
        result=resultado.result,
        ticket_id=str(ticket.id) if ticket is not None else None,
        registration_id=str(ticket.registration_id) if ticket is not None else None,
        full_name=inscripcion.full_name if inscripcion is not None else None,
        email=inscripcion.email if inscripcion is not None else None,
        used_at=ticket.used_at if ticket is not None else None,
        used_by_event_member_id=(
            str(ticket.used_by_event_member_id)
            if ticket is not None and ticket.used_by_event_member_id is not None
            else None
        ),
    )


@router.post(
    "/tickets/scan",
    summary="Escanear el QR de una entrada",
    response_model=TicketScanResultOut,
    dependencies=[require_permission(Permission.TICKETS_WRITE)],
)
async def scan_ticket(
    datos: ScanRequest,
    evento: Annotated[Event, Depends(_obtener_evento_o_404)],
    usuario: CurrentUserDep,
    session: DbDep,
) -> TicketScanResultOut:
    miembro = await scanning.resolver_event_member_del_usuario(
        session, organization_id=evento.organization_id, event_id=evento.id, user_id=usuario.id
    )
    resultado = await scanning.procesar_escaneo(
        session,
        organization_id=evento.organization_id,
        event_id=evento.id,
        token=datos.token,
        client_scan_id=datos.client_scan_id,
        client_scanned_at=datos.client_scanned_at,
        device_label=datos.device_label,
        scanner_event_member_id=miembro.id,
    )
    return _resultado_out(resultado)


@router.post(
    "/tickets/scan/batch",
    summary="Sincronizar varios escaneos encolados sin conexión",
    response_model=list[TicketScanResultOut],
    dependencies=[require_permission(Permission.TICKETS_WRITE)],
)
async def scan_tickets_batch(
    datos: ScanBatchRequest,
    evento: Annotated[Event, Depends(_obtener_evento_o_404)],
    usuario: CurrentUserDep,
    session: DbDep,
) -> list[TicketScanResultOut]:
    miembro = await scanning.resolver_event_member_del_usuario(
        session, organization_id=evento.organization_id, event_id=evento.id, user_id=usuario.id
    )
    resultados = await scanning.procesar_escaneos_en_lote(
        session,
        organization_id=evento.organization_id,
        event_id=evento.id,
        escaneos=datos.scans,
        scanner_event_member_id=miembro.id,
    )
    return [_resultado_out(resultado) for resultado in resultados]


@router.post(
    "/tickets/{ticket_id}/check-in-manual",
    summary="Marcar el uso de una entrada desde la búsqueda manual",
    response_model=TicketScanResultOut,
    dependencies=[require_permission(Permission.TICKETS_WRITE)],
)
async def check_in_manual(
    ticket_id: str,
    evento: Annotated[Event, Depends(_obtener_evento_o_404)],
    usuario: CurrentUserDep,
    session: DbDep,
) -> TicketScanResultOut:
    miembro = await scanning.resolver_event_member_del_usuario(
        session, organization_id=evento.organization_id, event_id=evento.id, user_id=usuario.id
    )
    resultado = await scanning.procesar_check_in_manual(
        session,
        organization_id=evento.organization_id,
        event_id=evento.id,
        ticket_id=uuid.UUID(ticket_id),
        scanner_event_member_id=miembro.id,
    )
    return _resultado_out(resultado)


@router.get(
    "/tickets/search",
    summary="Buscar una inscripción confirmada por nombre o email",
    response_model=list[TicketSearchItem],
    dependencies=[require_permission(Permission.TICKETS_WRITE)],
)
async def search_tickets(
    evento: Annotated[Event, Depends(_obtener_evento_o_404)],
    session: DbDep,
    q: Annotated[str, Query(min_length=1)],
) -> list[TicketSearchItem]:
    filas = await repository.search_confirmed_tickets(session, evento.organization_id, evento.id, q)
    return [
        TicketSearchItem(
            ticket_id=str(ticket.id),
            registration_id=str(inscripcion.id),
            full_name=inscripcion.full_name,
            email=inscripcion.email,
            used_at=ticket.used_at,
        )
        for ticket, inscripcion in filas
    ]


@router.get(
    "/tickets/{registration_id}",
    summary="Detalle de la entrada de una inscripción",
    response_model=TicketDetail,
    dependencies=[require_permission(Permission.TICKETS_READ)],
)
async def get_ticket_detail(
    registration_id: str,
    evento: Annotated[Event, Depends(_obtener_evento_o_404)],
    session: DbDep,
) -> TicketDetail:
    fila = await repository.get_ticket_with_registration(
        session, evento.organization_id, evento.id, uuid.UUID(registration_id)
    )
    if fila is None:
        raise NotFoundError("Esta inscripción no tiene ninguna entrada emitida.")
    ticket, inscripcion = fila
    return TicketDetail(
        id=str(ticket.id),
        registration_id=str(inscripcion.id),
        event_id=str(ticket.event_id),
        issued_at=ticket.issued_at,
        used_at=ticket.used_at,
        used_by_event_member_id=(
            str(ticket.used_by_event_member_id)
            if ticket.used_by_event_member_id is not None
            else None
        ),
        revoked_at=ticket.revoked_at,
        full_name=inscripcion.full_name,
        email=inscripcion.email,
        status=inscripcion.status,
    )
