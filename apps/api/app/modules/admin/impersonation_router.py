"""Endpoints de impersonación: entrar y salir de una sesión de suplantación.

Personal de plataforma (`superadmin` o el rol aditivo `soporte`, plan
`260916-0810-usuarios-y-permisos-plataforma`) entra a la cuenta de una
persona para **ver** lo que ella ve. La sesión es de solo lectura (la
bloquea una dependencia global de `main.py`) y caduca antes que una normal.

Qué NO puede hacer un token de impersonación, y dónde está cada barrera:

- **Escribir**: dependencia global `bloquear_escritura_si_impersona`.
- **Usar los endpoints de administración**: `require_superadmin`/
  `require_platform_staff` rechazan cualquier token con `impersonated_by` —
  el claim `sa` no basta como defensa, porque ese gate mira la fila de
  `users` del suplantado.
- **Seguir vivo tras salir**: la clave de sesión en Redis se borra al salir y
  `get_token_claims` la consulta en cada petición.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import registrar_auditoria
from app.core.deps import (
    CurrentUser,
    get_maintenance_db,
    get_token_claims,
    require_platform_staff,
)
from app.core.ratelimit import IMPERSONATION_POR_IP, limit_per_ip
from app.core.security import (
    AccessTokenClaims,
    create_access_token,
    decode_access_token,
    verify_password,
)
from app.core.tasks import send_impersonation_notice
from app.modules.admin import impersonation
from app.modules.admin.schemas import (
    ImpersonableMember,
    ImpersonationRequest,
    ImpersonationResponse,
)
from app.modules.organizations.models import Organization, OrganizationMember
from app.modules.roles.models import Role
from app.modules.users.models import User
from app.shared.errors import AuthenticationError, NotFoundError, PermissionDeniedError
from app.shared.identifiers import new_uuid7

router = APIRouter(prefix="/admin", tags=["administración"])

MaintenanceDb = Annotated[AsyncSession, Depends(get_maintenance_db)]
PlatformStaff = Annotated[CurrentUser, Depends(require_platform_staff)]
TokenClaims = Annotated[AccessTokenClaims, Depends(get_token_claims)]

#: Vida de una sesión de impersonación. Más corta que un access token normal:
#: durante una suplantación el token da acceso a los datos de otra persona.
_TTL_MINUTOS = 15


@router.post(
    "/impersonate",
    summary="Entrar a la cuenta de un usuario (solo lectura)",
    description=(
        "Abre una sesión de suplantación sobre `user_id` en la organización "
        "indicada. Exige la contraseña del administrador y un motivo, y queda "
        "registrada en la auditoría. La sesión es de solo lectura."
    ),
    status_code=status.HTTP_201_CREATED,
    response_model=ImpersonationResponse,
    dependencies=[limit_per_ip("impersonate", IMPERSONATION_POR_IP)],
)
async def impersonate(
    datos: ImpersonationRequest,
    actor: PlatformStaff,
    session: MaintenanceDb,
) -> ImpersonationResponse:
    # Reautenticación: la misma exigencia que las operaciones RGPD, que son
    # menos sensibles que esta.
    admin = await session.get(User, actor.id)
    if admin is None or not verify_password(datos.password, admin.password_hash):
        raise AuthenticationError("La contraseña no es correcta.")

    objetivo = await session.get(User, datos.user_id)
    if objetivo is None or not objetivo.is_active:
        raise NotFoundError("El usuario no existe o está desactivado.")

    # Nunca suplantar a otro miembro del personal de plataforma (superadmin o
    # soporte): sería una vía para operar con sus privilegios sin su
    # contraseña.
    if objetivo.is_superadmin or objetivo.platform_role is not None:
        raise PermissionDeniedError("No se puede suplantar a personal de la plataforma.")

    # El usuario tiene que ser **miembro** de esa organización: el token fija la
    # organización del suplantado, y suplantarlo en una a la que no pertenece no
    # reproduciría lo que él ve.
    miembro = await session.scalar(
        select(OrganizationMember).where(
            OrganizationMember.user_id == objetivo.id,
            OrganizationMember.organization_id == datos.organization_id,
        )
    )
    if miembro is None:
        raise NotFoundError("El usuario no pertenece a esa organización.")

    segundos = _TTL_MINUTOS * 60
    session_id = new_uuid7().hex

    token = create_access_token(
        objetivo.id,
        datos.organization_id,
        is_superadmin=False,
        impersonated_by=actor.id,
        ttl_minutes=_TTL_MINUTOS,
    )
    # El `jti` es la clave de la sesión en Redis (lo que permite revocarla al
    # salir); el `session_id` es el valor que se guarda en la auditoría y
    # empareja la entrada con la salida.
    claims = decode_access_token(token)
    await impersonation.abrir_sesion(
        jti=claims.jti, admin_id=actor.id, session_id=session_id, segundos=segundos
    )

    await registrar_auditoria(
        session,
        actor_user_id=actor.id,
        organization_id=datos.organization_id,
        action="impersonation.started",
        entity_type="user",
        entity_id=str(objetivo.id),
        detail={"reason": datos.reason, "expires_in": segundos},
        subject_user_id=objetivo.id,
        session_id=session_id,
    )

    # Aviso a la persona suplantada. Se envía como tarea de fondo (no en el
    # camino de la respuesta): que el correo falle no puede impedir que el
    # administrador entre, y el acceso ya queda registrado en la auditoría en
    # cualquier caso. Es su única vía de enterarse: el registro de auditoría no
    # está a su alcance.
    organizacion = await session.get(Organization, datos.organization_id)
    await send_impersonation_notice.kiq(
        objetivo.email,
        reason=datos.reason,
        minutos=_TTL_MINUTOS,
        organizacion=organizacion.name if organizacion else "la plataforma",
    )

    return ImpersonationResponse(
        access_token=token,
        session_id=session_id,
        impersonated_user_id=str(objetivo.id),
        organization_id=str(datos.organization_id),
        expires_in=segundos,
    )


@router.post(
    "/impersonate/stop",
    summary="Salir de la sesión de suplantación",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[limit_per_ip("impersonate-stop", IMPERSONATION_POR_IP)],
)
async def stop_impersonating(
    claims: TokenClaims,
    session: MaintenanceDb,
) -> None:
    """Revoca la sesión **en el servidor**, no solo en el cliente.

    Se llama con el token de impersonación (no con el del administrador): el
    `jti` de ese token es la clave que hay que borrar de Redis.
    """
    if claims.impersonated_by is None:
        raise PermissionDeniedError("Esta sesión no es de suplantación.")

    # Se lee el id de sesión **antes** de borrar la clave: es lo que permite
    # que esta fila y la de entrada se puedan emparejar en la auditoría.
    datos_sesion = await impersonation.datos_de_sesion(claims.jti)
    await impersonation.cerrar_sesion(claims.jti)

    await registrar_auditoria(
        session,
        actor_user_id=claims.impersonated_by,
        organization_id=claims.organization_id,
        action="impersonation.stopped",
        entity_type="user",
        entity_id=str(claims.user_id),
        detail=None,
        subject_user_id=claims.user_id,
        session_id=datos_sesion.get("sesion") if datos_sesion else None,
    )


def _enmascarar_email(email: str) -> str:
    """`ana@ejemplo.com` → `a***@ejemplo.com`.

    El panel de plataforma necesita distinguir personas, no leer su correo: esta
    lista no es para contactarlas. Enmascararlo reduce lo que se expone si el
    token de un administrador se filtra.
    """
    usuario, _, dominio = email.partition("@")
    if not usuario:
        return email
    return f"{usuario[0]}***@{dominio}" if dominio else f"{usuario[0]}***"


@router.get(
    "/organizations/{organization_id}/members",
    summary="Miembros de una organización, para elegir a quién suplantar",
    response_model=list[ImpersonableMember],
)
async def list_impersonable_members(
    organization_id: uuid.UUID,
    _: PlatformStaff,
    session: MaintenanceDb,
) -> list[ImpersonableMember]:
    filas = (
        await session.execute(
            select(User, Role.key)
            .join(OrganizationMember, OrganizationMember.user_id == User.id)
            .join(Role, Role.id == OrganizationMember.role_id)
            .where(OrganizationMember.organization_id == organization_id)
            .order_by(User.first_name, User.email)
        )
    ).all()

    return [
        ImpersonableMember(
            user_id=str(usuario.id),
            nombre=f"{usuario.first_name or ''} {usuario.last_name or ''}".strip() or usuario.email,
            email_enmascarado=_enmascarar_email(usuario.email),
            role_key=rol_key,
            suplantable=not usuario.is_superadmin
            and usuario.platform_role is None
            and usuario.is_active,
        )
        for usuario, rol_key in filas
    ]
