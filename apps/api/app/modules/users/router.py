"""Endpoints del usuario autenticado."""

from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, status
from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError

from app.core.deps import CurrentUserDep, DbDep, PermissionsDep
from app.core.permissions import Permission
from app.modules.auth import service as auth_service
from app.modules.events.models import SpeakerPublicProfile
from app.modules.organizations.models import OrganizationMember
from app.modules.organizations.repository import user_role_keys
from app.modules.organizations.schemas import SLUG_PATTERN
from app.modules.roles.models import Role
from app.modules.users.models import UserSocialLink
from app.modules.users.schemas import (
    PUBLIC_PROFILE_FIELDS,
    ChangeEmailConfirmRequest,
    ChangeEmailRequest,
    ChangePasswordRequest,
    CheckPublicSlugResponse,
    CurrentUserResponse,
    EligibleMembershipResponse,
    OrganizationMembershipResponse,
    PublicProfileResponse,
    PublicProfileStateResponse,
    PublicProfileUpdate,
    SocialLinkResponse,
    SocialLinkUpdate,
    UserMeUpdate,
)
from app.shared.errors import ConflictError, DomainError, ValidationDomainError

router = APIRouter(prefix="/users", tags=["usuarios"])

_SLUG_RE = re.compile(SLUG_PATTERN)


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


async def _membresias_publicables(
    session: DbDep, organization_id: uuid.UUID, user_id: uuid.UUID
) -> list[EligibleMembershipResponse]:
    """Membresías propias en esta organización cuyo rol declara al menos un
    campo de la lista blanca — las únicas desde las que tiene sentido activar
    el perfil público."""
    filas = (
        await session.execute(
            select(OrganizationMember, Role)
            .join(Role, Role.id == OrganizationMember.role_id)
            .where(
                OrganizationMember.organization_id == organization_id,
                OrganizationMember.user_id == user_id,
            )
        )
    ).all()
    elegibles: list[EligibleMembershipResponse] = []
    for miembro, rol in filas:
        claves = {campo.key for campo in rol.profile_fields}
        if claves & set(PUBLIC_PROFILE_FIELDS):
            elegibles.append(
                EligibleMembershipResponse(
                    organization_member_id=str(miembro.id), role_key=rol.key, role_name=rol.name
                )
            )
    return elegibles


@router.get(
    "/me/public-profile",
    summary="Estado del perfil público propio",
    response_model=PublicProfileStateResponse,
)
async def get_public_profile(usuario: CurrentUserDep, session: DbDep) -> PublicProfileStateResponse:
    perfil = await session.scalar(
        select(SpeakerPublicProfile).where(
            SpeakerPublicProfile.organization_id == usuario.organization_id,
            SpeakerPublicProfile.user_id == usuario.id,
        )
    )
    return PublicProfileStateResponse(
        profile=PublicProfileResponse(
            active=perfil is not None,
            public_slug=perfil.public_slug if perfil else None,
            source_organization_member_id=(
                str(perfil.source_organization_member_id) if perfil else None
            ),
        ),
        eligible_memberships=await _membresias_publicables(
            session, usuario.organization_id, usuario.id
        ),
    )


@router.patch(
    "/me/public-profile",
    summary="Activar, cambiar o desactivar el perfil público propio",
    description=(
        "Autoservicio puro: nadie más que la propia persona puede activar o "
        "desactivar su perfil público, sin permiso especial más allá de estar "
        "autenticado. `public_slug: null` desactiva el perfil."
    ),
    response_model=PublicProfileStateResponse,
)
async def update_public_profile(
    datos: PublicProfileUpdate, usuario: CurrentUserDep, session: DbDep
) -> PublicProfileStateResponse:
    perfil = await session.scalar(
        select(SpeakerPublicProfile).where(
            SpeakerPublicProfile.organization_id == usuario.organization_id,
            SpeakerPublicProfile.user_id == usuario.id,
        )
    )

    if datos.public_slug is None:
        if perfil is not None:
            await session.delete(perfil)
            await session.flush()
        return await get_public_profile(usuario, session)

    if datos.source_organization_member_id is None:  # pragma: no cover - ya lo valida el esquema
        raise ValidationDomainError("Falta indicar de qué membresía tomar la biografía.")

    miembro = await session.scalar(
        select(OrganizationMember).where(
            OrganizationMember.id == uuid.UUID(datos.source_organization_member_id),
            OrganizationMember.organization_id == usuario.organization_id,
        )
    )
    if miembro is None or miembro.user_id != usuario.id:
        raise ValidationDomainError("Esa membresía no te pertenece.")

    rol = await session.get(Role, miembro.role_id)
    claves = {campo.key for campo in rol.profile_fields} if rol else set()
    if not (claves & set(PUBLIC_PROFILE_FIELDS)):
        raise ValidationDomainError("El rol de esa membresía no declara ningún campo publicable.")

    slug_limpio = datos.public_slug.strip().lower()
    if perfil is None:
        perfil = SpeakerPublicProfile(
            organization_id=usuario.organization_id,
            user_id=usuario.id,
            public_slug=slug_limpio,
            source_organization_member_id=miembro.id,
        )
        session.add(perfil)
    else:
        perfil.public_slug = slug_limpio
        perfil.source_organization_member_id = miembro.id

    try:
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError(f"El identificador «{slug_limpio}» ya está en uso.") from exc

    return await get_public_profile(usuario, session)


@router.get(
    "/me/public-profile/check-slug",
    summary="Comprobar disponibilidad de un identificador de ponente",
    description=(
        "Ayuda de UX en vivo, mismo espíritu que el `check-slug` de organizaciones "
        "pero sin `SECURITY DEFINER`: quien pregunta ya tiene contexto de "
        "organización (autenticado), así que una consulta normal bajo RLS basta."
    ),
    response_model=CheckPublicSlugResponse,
)
async def check_public_slug(
    slug: str, usuario: CurrentUserDep, session: DbDep
) -> CheckPublicSlugResponse:
    slug_limpio = slug.strip().lower()
    if not _SLUG_RE.fullmatch(slug_limpio):
        return CheckPublicSlugResponse(available=False)
    existente = await session.scalar(
        select(SpeakerPublicProfile.id).where(
            SpeakerPublicProfile.organization_id == usuario.organization_id,
            SpeakerPublicProfile.public_slug == slug_limpio,
        )
    )
    return CheckPublicSlugResponse(available=existente is None)


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
