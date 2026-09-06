"""Endpoints de la organización actual (la resuelta por host)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile, status

from app.core.deps import CurrentUserDep, DbDep, PermissionsDep, require_permission
from app.core.permissions import Permission
from app.core.storage import build_object_key, get_storage, validate_upload
from app.modules.organizations import members_service, repository
from app.modules.organizations.models import OrganizationBranding, OrganizationMember
from app.modules.organizations.schemas import (
    BrandingAdminResponse,
    BrandingUpdate,
    MemberCreate,
    MemberResponse,
    OrganizationResponse,
    OrganizationUpdate,
)
from app.shared.errors import NotFoundError
from app.shared.pagination import Page, PageParams, page_params

router = APIRouter(prefix="/organizations", tags=["organizaciones"])


def _branding_response(branding: OrganizationBranding | None) -> BrandingAdminResponse:
    almacen = get_storage()
    if branding is None:
        return BrandingAdminResponse(template_key="classic", colors={}, fonts={}, social_links=[])
    return BrandingAdminResponse(
        template_key=branding.template_key,
        colors=branding.colors,
        fonts=branding.fonts,
        social_links=branding.social_links,
        organizer_blurb=branding.organizer_blurb,
        logo_url=almacen.public_url(branding.logo_object_key) if branding.logo_object_key else None,
        favicon_url=almacen.public_url(branding.favicon_object_key)
        if branding.favicon_object_key
        else None,
    )


@router.get(
    "/me",
    summary="Datos de la organización actual",
    response_model=OrganizationResponse,
    dependencies=[require_permission(Permission.ORGANIZATIONS_READ)],
)
async def get_me(usuario: CurrentUserDep, session: DbDep) -> OrganizationResponse:
    organizacion = await repository.get_organization(session, usuario.organization_id)
    if organizacion is None:
        raise NotFoundError("La organización no existe.")
    return OrganizationResponse(
        id=str(organizacion.id),
        slug=organizacion.slug,
        name=organizacion.name,
        legal_name=organizacion.legal_name,
        description=organizacion.description,
        website=organizacion.website,
        contact_email=organizacion.contact_email,
        is_active=organizacion.is_active,
    )


@router.patch(
    "/me",
    summary="Actualizar la organización actual",
    response_model=OrganizationResponse,
    dependencies=[require_permission(Permission.ORGANIZATIONS_WRITE)],
)
async def update_me(
    datos: OrganizationUpdate, usuario: CurrentUserDep, session: DbDep
) -> OrganizationResponse:
    organizacion = await repository.get_organization(session, usuario.organization_id)
    if organizacion is None:
        raise NotFoundError("La organización no existe.")
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(organizacion, campo, valor)
    await session.flush()
    return await get_me(usuario, session)


@router.get(
    "/me/branding",
    summary="Identidad visual de la organización",
    response_model=BrandingAdminResponse,
    dependencies=[require_permission(Permission.ORGANIZATIONS_READ)],
)
async def get_branding(usuario: CurrentUserDep, session: DbDep) -> BrandingAdminResponse:
    return _branding_response(await repository.get_branding(session, usuario.organization_id))


@router.put(
    "/me/branding",
    summary="Actualizar la identidad visual",
    response_model=BrandingAdminResponse,
    dependencies=[require_permission(Permission.BRANDING_WRITE)],
)
async def update_branding(
    datos: BrandingUpdate, usuario: CurrentUserDep, session: DbDep
) -> BrandingAdminResponse:
    branding = await repository.get_branding(session, usuario.organization_id)
    if branding is None:
        branding = OrganizationBranding(organization_id=usuario.organization_id)
        session.add(branding)

    branding.template_key = datos.template_key
    branding.colors = dict(datos.colors)
    branding.fonts = dict(datos.fonts)
    branding.social_links = [enlace.model_dump() for enlace in datos.social_links]
    branding.organizer_blurb = datos.organizer_blurb
    await session.flush()
    return _branding_response(branding)


@router.put(
    "/me/branding/logo",
    summary="Subir el logotipo",
    description="Acepta PNG, JPEG o WebP de hasta 5 MB. El tipo se comprueba por contenido.",
    response_model=BrandingAdminResponse,
    dependencies=[require_permission(Permission.BRANDING_WRITE)],
)
async def upload_logo(
    usuario: CurrentUserDep,
    session: DbDep,
    fichero: Annotated[UploadFile, File(description="Imagen del logotipo")],
) -> BrandingAdminResponse:
    contenido = await fichero.read()
    mime, extension = validate_upload(contenido)

    almacen = get_storage()
    clave = build_object_key(usuario.organization_id, "branding/logo", extension)
    await almacen.put_object(clave, contenido, mime)

    branding = await repository.get_branding(session, usuario.organization_id)
    if branding is None:
        branding = OrganizationBranding(organization_id=usuario.organization_id)
        session.add(branding)
    anterior = branding.logo_object_key
    branding.logo_object_key = clave
    await session.flush()

    if anterior and anterior != clave:
        await almacen.delete_object(anterior)
    return _branding_response(branding)


@router.get(
    "/me/members",
    summary="Miembros de la organización",
    response_model=Page[MemberResponse],
    dependencies=[require_permission(Permission.MEMBERS_READ)],
)
async def list_members(
    usuario: CurrentUserDep,
    session: DbDep,
    paginacion: Annotated[PageParams, Depends(page_params)],
) -> Page[MemberResponse]:
    consulta = (
        repository.members_query(usuario.organization_id)
        .limit(paginacion.limit)
        .offset(paginacion.offset)
    )
    filas = (await session.execute(consulta)).all()
    return Page[MemberResponse](
        items=[
            MemberResponse(
                id=str(miembro.id),
                user_id=str(persona.id),
                email=persona.email,
                full_name=persona.full_name,
                role_id=str(rol.id),
                role_key=rol.key,
                profile_data=miembro.profile_data,
            )
            for miembro, persona, rol in filas
        ],
        total=await repository.count_members(session, usuario.organization_id),
        limit=paginacion.limit,
        offset=paginacion.offset,
    )


@router.post(
    "/me/members",
    summary="Añadir un miembro",
    status_code=status.HTTP_201_CREATED,
    response_model=MemberResponse,
    dependencies=[require_permission(Permission.MEMBERS_WRITE)],
)
async def create_member(
    datos: MemberCreate,
    usuario: CurrentUserDep,
    session: DbDep,
    permisos: PermissionsDep,
) -> MemberResponse:
    miembro = await members_service.add_member(
        session,
        organization_id=usuario.organization_id,
        actor_id=usuario.id,
        actor_permissions=permisos,
        email=str(datos.email),
        full_name=datos.full_name,
        role_id=uuid.UUID(datos.role_id),
        profile_data=datos.profile_data,
    )
    consulta = repository.members_query(usuario.organization_id).where(
        OrganizationMember.id == miembro.id
    )
    fila = (await session.execute(consulta)).one()
    registro, persona, rol = fila
    return MemberResponse(
        id=str(registro.id),
        user_id=str(persona.id),
        email=persona.email,
        full_name=persona.full_name,
        role_id=str(rol.id),
        role_key=rol.key,
        profile_data=registro.profile_data,
    )
