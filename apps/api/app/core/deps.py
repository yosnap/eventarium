"""Dependencias transversales de FastAPI.

Cadena de una petición autenticada:

    get_session → get_current_organization → get_db → get_current_user → require_permission

`get_db` es el **único** punto donde se fija el contexto de RLS. Ningún router abre
sesiones por su cuenta ni usa el motor de mantenimiento.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import SessionApp, SessionMaintenance, set_organization_context
from app.core.permissions import Permission
from app.core.security import AccessTokenClaims, decode_access_token
from app.core.tenant import ResolvedOrganization, resolve_organization
from app.shared.errors import (
    AuthenticationError,
    NotFoundError,
    PermissionDeniedError,
)


async def get_session() -> AsyncIterator[AsyncSession]:
    """Sesión con el rol de la API y una transacción abierta, sin contexto todavía."""
    async with SessionApp() as session:
        async with session.begin():
            yield session


async def get_current_organization(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ResolvedOrganization:
    """Organización resuelta por host. 404 si el host no está registrado."""
    organizacion = await resolve_organization(session, request)
    if not organizacion.is_active:
        raise NotFoundError("La organización no está activa.")
    request.state.organization = organizacion
    return organizacion


async def get_db(
    session: Annotated[AsyncSession, Depends(get_session)],
    organizacion: Annotated[ResolvedOrganization, Depends(get_current_organization)],
) -> AsyncSession:
    """Sesión con el contexto RLS de la organización ya fijado."""
    await set_organization_context(session, organizacion.id)
    return session


async def get_maintenance_db() -> AsyncIterator[AsyncSession]:
    """Sesión con el rol `app_maintainer` (BYPASSRLS).

    Solo puede usarla `app.modules.admin`. La regla se verifica en CI con un test
    estático que falla si esta dependencia aparece en cualquier otro módulo.
    """
    async with SessionMaintenance() as session:
        async with session.begin():
            yield session


def _extraer_token(request: Request) -> str:
    cabecera = request.headers.get("authorization", "")
    esquema, _, token = cabecera.partition(" ")
    if esquema.lower() != "bearer" or not token:
        raise AuthenticationError("Falta la cabecera Authorization: Bearer.")
    return token.strip()


async def get_token_claims(request: Request) -> AccessTokenClaims:
    """Contenido verificado del access token, sin tocar la base de datos."""
    return decode_access_token(_extraer_token(request))


class CurrentUser:
    """Usuario autenticado en el contexto de la organización de la petición."""

    __slots__ = ("id", "email", "first_name", "last_name", "is_superadmin", "organization_id")

    def __init__(
        self,
        *,
        id: uuid.UUID,
        email: str,
        first_name: str | None,
        last_name: str | None,
        is_superadmin: bool,
        organization_id: uuid.UUID,
    ) -> None:
        self.id = id
        self.email = email
        self.first_name = first_name
        self.last_name = last_name
        self.is_superadmin = is_superadmin
        self.organization_id = organization_id


async def get_current_user(
    claims: Annotated[AccessTokenClaims, Depends(get_token_claims)],
    organizacion: Annotated[ResolvedOrganization, Depends(get_current_organization)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> CurrentUser:
    """Carga el usuario del token.

    Un token emitido para otra organización no vale en este host aunque la firma sea
    válida: sin esta comprobación bastaría con cambiar el `Host` para llevarse una
    sesión de una organización a otra.
    """
    if claims.organization_id != organizacion.id:
        raise PermissionDeniedError("El token no pertenece a esta organización.")

    # `users` también tiene RLS: hay que declarar quién pregunta antes de leer.
    await set_organization_context(session, organizacion.id, claims.user_id)

    fila = (
        await session.execute(
            text(
                "SELECT id, email, first_name, last_name, is_superadmin, is_active "
                "FROM users WHERE id = :id"
            ),
            {"id": claims.user_id},
        )
    ).first()
    if fila is None or not fila[5]:
        raise AuthenticationError("El usuario ya no existe o está desactivado.")

    return CurrentUser(
        id=fila[0],
        email=fila[1],
        first_name=fila[2],
        last_name=fila[3],
        is_superadmin=fila[4],
        organization_id=organizacion.id,
    )


async def get_user_permissions(session: AsyncSession, usuario: CurrentUser) -> set[Permission]:
    """Permisos efectivos del usuario en la organización de la petición."""
    filas = await session.execute(
        text(
            "SELECT DISTINCT rp.permission "
            "FROM organization_members m "
            "JOIN role_permissions rp ON rp.role_id = m.role_id "
            "WHERE m.user_id = :user_id AND m.organization_id = :org_id"
        ),
        {"user_id": usuario.id, "org_id": usuario.organization_id},
    )
    permisos: set[Permission] = set()
    for (valor,) in filas:
        try:
            permisos.add(Permission(valor))
        except ValueError:
            # Un permiso retirado del catálogo se ignora en lugar de romper la sesión.
            continue
    return permisos


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
DbDep = Annotated[AsyncSession, Depends(get_db)]


async def current_permissions(usuario: CurrentUserDep, session: DbDep) -> set[Permission]:
    """Dependencia con los permisos efectivos del usuario."""
    return await get_user_permissions(session, usuario)


PermissionsDep = Annotated[set[Permission], Depends(current_permissions)]


def require_permission(*requeridos: Permission):  # type: ignore[no-untyped-def]
    """Exige que el usuario tenga **todos** los permisos indicados."""

    async def dependencia(permisos: PermissionsDep) -> set[Permission]:
        faltan = {p for p in requeridos if p not in permisos}
        if faltan:
            raise PermissionDeniedError(
                "No tienes permiso para esta operación.",
                extra={"required": sorted(p.value for p in faltan)},
            )
        return permisos

    return Depends(dependencia)


async def require_superadmin(
    claims: Annotated[AccessTokenClaims, Depends(get_token_claims)],
    session: Annotated[AsyncSession, Depends(get_maintenance_db)],
) -> CurrentUser:
    """Superadmin de la instalación.

    Los endpoints de administración son globales, así que no exigen organización en
    el token. `is_superadmin` se comprueba **en base de datos** en cada petición: un
    token antiguo no puede conservar el privilegio si se revocó.
    """
    fila = (
        await session.execute(
            text(
                "SELECT id, email, first_name, last_name, is_superadmin, is_active "
                "FROM users WHERE id = :id"
            ),
            {"id": claims.user_id},
        )
    ).first()
    if fila is None or not fila[5]:
        raise AuthenticationError("El usuario ya no existe o está desactivado.")
    if not fila[4]:
        raise PermissionDeniedError("Se requieren privilegios de superadministrador.")
    return CurrentUser(
        id=fila[0],
        email=fila[1],
        first_name=fila[2],
        last_name=fila[3],
        is_superadmin=True,
        organization_id=claims.organization_id or uuid.UUID(int=0),
    )
