"""Endpoints del usuario autenticado."""

from __future__ import annotations

from fastapi import APIRouter, status
from sqlalchemy import delete, select, text

from app.core.deps import CurrentUserDep, DbDep, PermissionsDep
from app.core.permissions import Permission
from app.modules.auth import service as auth_service
from app.modules.organizations.repository import user_role_keys
from app.modules.users.models import UserSocialLink
from app.modules.users.schemas import (
    ChangeEmailConfirmRequest,
    ChangeEmailRequest,
    ChangePasswordRequest,
    CurrentUserResponse,
    OrganizationMembershipResponse,
    SocialLinkResponse,
    SocialLinkUpdate,
    UserMeUpdate,
)
from app.shared.errors import DomainError

router = APIRouter(prefix="/users", tags=["usuarios"])


@router.get(
    "/me",
    summary="Usuario autenticado",
    description="Devuelve el usuario, sus roles y sus permisos en la organización actual.",
    response_model=CurrentUserResponse,
)
async def get_me(
    usuario: CurrentUserDep, session: DbDep, permisos: PermissionsDep
) -> CurrentUserResponse:
    claves = await user_role_keys(session, usuario.organization_id, usuario.id)
    return CurrentUserResponse(
        id=str(usuario.id),
        email=usuario.email,
        first_name=usuario.first_name,
        last_name=usuario.last_name,
        is_superadmin=usuario.is_superadmin,
        organization_id=str(usuario.organization_id),
        roles=sorted(claves),
        permissions=sorted(Permission(p) for p in permisos),
    )


@router.patch(
    "/me",
    summary="Modificar el usuario autenticado",
    description="Nombre y locale. El correo tiene su propio flujo, con confirmación.",
    response_model=CurrentUserResponse,
)
async def update_me(
    datos: UserMeUpdate, usuario: CurrentUserDep, session: DbDep, permisos: PermissionsDep
) -> CurrentUserResponse:
    cambios = datos.model_dump(exclude_unset=True)
    if cambios:
        asignaciones = ", ".join(f"{campo} = :{campo}" for campo in cambios)
        await session.execute(
            text(f"UPDATE users SET {asignaciones} WHERE id = :id"),  # noqa: S608 - claves fijas
            {**cambios, "id": usuario.id},
        )
        # `usuario` viene del token decodificado antes de este cambio: `get_me`
        # tomaría los valores viejos si se le pasara tal cual.
        for campo, valor in cambios.items():
            setattr(usuario, campo, valor)
    return await get_me(usuario, session, permisos)


@router.post(
    "/me/change-email",
    summary="Solicitar un cambio de correo",
    description=(
        "Exige la contraseña actual. Avisa al correo actual y envía la confirmación "
        "al correo nuevo; el cambio no se aplica hasta confirmarlo."
    ),
    status_code=status.HTTP_202_ACCEPTED,
)
async def change_email(
    datos: ChangeEmailRequest, usuario: CurrentUserDep, session: DbDep
) -> dict[str, str]:
    await auth_service.change_email_request(
        session,
        user_id=usuario.id,
        current_email=usuario.email,
        new_email=str(datos.new_email),
        password=datos.password,
    )
    return {"message": "Revisa el correo nuevo para confirmar el cambio."}


@router.post(
    "/me/change-email/confirm",
    summary="Confirmar un cambio de correo",
    description=(
        "Consume el token recibido en el correo nuevo, aplica el cambio y revoca las "
        "demás sesiones. No exige estar autenticado: el token prueba la propiedad del "
        "correo nuevo."
    ),
)
async def change_email_confirm(datos: ChangeEmailConfirmRequest, session: DbDep) -> dict[str, str]:
    await auth_service.change_email_confirm(session, token=datos.token)
    return {"message": "Correo actualizado correctamente."}


@router.post(
    "/me/change-password",
    summary="Cambiar la contraseña",
    description="Exige la actual y revoca las demás sesiones, salvo la actual.",
)
async def change_password(
    datos: ChangePasswordRequest, usuario: CurrentUserDep, session: DbDep
) -> dict[str, str]:
    await auth_service.change_password(
        session,
        user_id=usuario.id,
        current_password=datos.current_password,
        new_password=datos.new_password,
        keep_family=usuario.refresh_family,
    )
    return {"message": "Contraseña actualizada correctamente."}


@router.get(
    "/me/social-links",
    summary="Enlaces sociales del perfil",
    response_model=list[SocialLinkResponse],
)
async def list_social_links(usuario: CurrentUserDep, session: DbDep) -> list[SocialLinkResponse]:
    filas = await session.scalars(
        select(UserSocialLink)
        .where(UserSocialLink.user_id == usuario.id)
        .order_by(UserSocialLink.kind)
    )
    return [SocialLinkResponse.model_validate(fila) for fila in filas]


@router.put(
    "/me/social-links/{kind}",
    summary="Crear o actualizar un enlace social",
    response_model=SocialLinkResponse,
)
async def upsert_social_link(
    kind: str, datos: SocialLinkUpdate, usuario: CurrentUserDep, session: DbDep
) -> SocialLinkResponse:
    if len(kind) > 40:
        raise DomainError("El tipo de enlace es demasiado largo.")
    enlace = await session.scalar(
        select(UserSocialLink).where(
            UserSocialLink.user_id == usuario.id, UserSocialLink.kind == kind
        )
    )
    if enlace is None:
        enlace = UserSocialLink(user_id=usuario.id, kind=kind, url=datos.url)
        session.add(enlace)
    else:
        enlace.url = datos.url
    await session.flush()
    return SocialLinkResponse.model_validate(enlace)


@router.delete(
    "/me/social-links/{kind}",
    summary="Eliminar un enlace social",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_social_link(kind: str, usuario: CurrentUserDep, session: DbDep) -> None:
    await session.execute(
        delete(UserSocialLink).where(
            UserSocialLink.user_id == usuario.id, UserSocialLink.kind == kind
        )
    )


@router.get(
    "/me/organizations",
    summary="Organizaciones a las que pertenece la persona",
    description="Para el selector de organización del panel, cuando pertenece a más de una.",
    response_model=list[OrganizationMembershipResponse],
)
async def list_my_organizations(
    usuario: CurrentUserDep, session: DbDep
) -> list[OrganizationMembershipResponse]:
    filas = await session.execute(
        text("SELECT organization_id, slug, name, host FROM app_user_organizations(:id)"),
        {"id": usuario.id},
    )
    return [
        OrganizationMembershipResponse(
            organization_id=str(fila[0]), slug=fila[1], name=fila[2], host=fila[3]
        )
        for fila in filas
    ]
