"""Pantalla pública de aceptación de invitaciones (fase 2 del plan de invitaciones).

Mismo patrón que `registrations/public_router.py`/`events/public_router.py`:
sin autenticación, contexto RLS fijado por host vía `OrganizationDep`/`PublicDbDep`.
El enlace del correo apunta al dominio propio de la organización
(`base_url_de_organizacion`, usado en `send_invitation_email`), así que la
petición a `/public/invitations/{token}` llega de vuelta con el `Host`
correcto y resuelve la misma organización sin necesidad de pasarla en la URL.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.core.deps import OrganizationDep, PublicDbDep
from app.core.ratelimit import INVITACION_ACEPTAR_POR_IP, INVITACION_CONSULTA_POR_IP, limit_per_ip
from app.modules.organizations import invitations_service
from app.modules.organizations.invitations_service import InvitationTokenState
from app.modules.organizations.schemas import (
    InvitationAcceptRequest,
    InvitationAcceptResponse,
    InvitationPublicResponse,
    InvitationTokenErrorResponse,
)
from app.shared.errors import NotFoundError

router = APIRouter(prefix="/public/invitations", tags=["invitaciones"])


@router.get(
    "/{token}",
    summary="Consultar una invitación por su token",
    description=(
        "Respuesta mínima: nombre de la organización y rol propuesto. Nunca la "
        "lista de miembros ni ningún otro dato de negocio."
    ),
    responses={404: {"model": InvitationTokenErrorResponse}},
    response_model=InvitationPublicResponse,
    dependencies=[limit_per_ip("invitacion-consulta", INVITACION_CONSULTA_POR_IP)],
)
async def get_invitation(
    token: str, _organizacion: OrganizationDep, session: PublicDbDep
) -> InvitationPublicResponse:
    resuelto = await invitations_service.resolve_invitation_token(session, token)
    if resuelto.state != InvitationTokenState.VALIDA:
        raise NotFoundError(invitations_service.mensaje_de_estado(resuelto.state))
    return InvitationPublicResponse(
        organization_name=resuelto.organization_name or "",
        role_name=resuelto.role_name or "",
        account_has_password=resuelto.account_has_password,
    )


@router.post(
    "/{token}/accept",
    summary="Aceptar una invitación",
    description=(
        "Fija nombre y contraseña de la cuenta invitada y crea la membresía. "
        "Idempotente: aceptar dos veces no duplica nada."
    ),
    responses={
        404: {"model": InvitationTokenErrorResponse},
        409: {"model": InvitationTokenErrorResponse},
    },
    response_model=InvitationAcceptResponse,
    dependencies=[limit_per_ip("invitacion-aceptar", INVITACION_ACEPTAR_POR_IP)],
)
async def accept_invitation(
    token: str,
    datos: InvitationAcceptRequest,
    organizacion: OrganizationDep,
    session: PublicDbDep,
) -> InvitationAcceptResponse:
    await invitations_service.accept_invitation(
        session,
        token=token,
        first_name=datos.first_name,
        last_name=datos.last_name,
        password=datos.password,
    )
    return InvitationAcceptResponse(organization_slug=organizacion.slug)
