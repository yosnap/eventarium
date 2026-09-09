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
from app.modules.theme_templates import repository as theme_templates_repository
from app.modules.theme_templates.schemas import ThemeTemplateCatalogItem
from app.shared.errors import NotFoundError, ValidationDomainError
from app.shared.pagination import Page, PageParams, page_params

router = APIRouter(prefix="/organizations", tags=["organizaciones"])


def _branding_response(branding: OrganizationBranding | None) -> BrandingAdminResponse:
    almacen = get_storage()
    if branding is None:
        return BrandingAdminResponse(template_key="classic", social_links=[])
    return BrandingAdminResponse(
        template_key=branding.template_key,
        theme_template_id=str(branding.theme_template_id) if branding.theme_template_id else None,
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
    theme_template_id: uuid.UUID | None = None
    if datos.theme_template_id is not None:
        try:
            theme_template_id = uuid.UUID(datos.theme_template_id)
        except ValueError as exc:
            raise ValidationDomainError(
                f"«{datos.theme_template_id}» no es un identificador válido de plantilla."
            ) from exc
        plantilla = await theme_templates_repository.get_theme_template(session, theme_template_id)
        if plantilla is None:
            raise ValidationDomainError(
                f"No existe ninguna plantilla de tema con el id «{datos.theme_template_id}»."
            )

    branding = await repository.get_branding(session, usuario.organization_id)
    if branding is None:
        branding = OrganizationBranding(organization_id=usuario.organization_id)
        session.add(branding)

    branding.template_key = datos.template_key
    branding.theme_template_id = theme_template_id
    branding.social_links = [enlace.model_dump() for enlace in datos.social_links]
    branding.organizer_blurb = datos.organizer_blurb
    await session.flush()
    return _branding_response(branding)


@router.get(
    "/me/theme-templates",
    summary="Catálogo de plantillas de tema disponibles",
    description=(
        "Los tokens hacen falta para pintar la muestra de cada plantilla en el "
        "selector de la galería del editor de branding."
    ),
    response_model=list[ThemeTemplateCatalogItem],
    dependencies=[require_permission(Permission.ORGANIZATIONS_READ)],
)
async def list_theme_templates_catalog(
    _: CurrentUserDep, session: DbDep
) -> list[ThemeTemplateCatalogItem]:
    plantillas = await theme_templates_repository.list_theme_templates(session)
    return [
        ThemeTemplateCatalogItem(
            id=str(plantilla.id), key=plantilla.key, name=plantilla.name, tokens=plantilla.tokens
        )
        for plantilla in plantillas
    ]


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
                first_name=persona.first_name,
                last_name=persona.last_name,
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
        first_name=datos.first_name,
        last_name=datos.last_name,
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
        first_name=persona.first_name,
        last_name=persona.last_name,
        role_id=str(rol.id),
        role_key=rol.key,
        profile_data=registro.profile_data,
    )
