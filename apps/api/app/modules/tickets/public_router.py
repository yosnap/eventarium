"""`/mi-entrada`: ver de nuevo el QR de una entrada (fase 4 del PRD, fase 4 de trabajo).

Mismo patrón que `registrations/public_router.py`: sin autenticación, contexto
RLS fijado por host vía `OrganizationDep`/`DbDep`. Reutiliza el token de
autocancelación ya existente — no genera uno nuevo — así que solo necesita
`peek_token`, nunca `consume_token`.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Response

from app.core.deps import DbDep
from app.core.ratelimit import MI_ENTRADA_POR_IP, limit_per_ip
from app.modules.tickets import service
from app.modules.tickets.schemas import MyTicketResponse

router = APIRouter(prefix="/public", tags=["entradas"])


@router.get(
    "/registrations/my-ticket",
    summary="Consultar el estado de una entrada por su token de autocancelación",
    response_model=MyTicketResponse,
    dependencies=[limit_per_ip("mi-entrada", MI_ENTRADA_POR_IP)],
)
async def get_my_ticket(session: DbDep, token: Annotated[str, Query()]) -> MyTicketResponse:
    info = await service.get_my_ticket_info(session, token=token)
    return MyTicketResponse(status=info.status, full_name=info.full_name, has_qr=info.tiene_qr)


@router.get(
    "/registrations/my-ticket/qr",
    summary="Imagen PNG del QR de una entrada",
    dependencies=[limit_per_ip("mi-entrada-qr", MI_ENTRADA_POR_IP)],
)
async def get_my_ticket_qr(session: DbDep, token: Annotated[str, Query()]) -> Response:
    imagen = await service.get_my_ticket_qr_png(session, token=token)
    return Response(content=imagen, media_type="image/png")
