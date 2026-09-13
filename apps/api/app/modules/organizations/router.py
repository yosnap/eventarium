"""Endpoints de la organización actual (la resuelta por host)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUserDep, DbDep, PermissionsDep, require_permission
from app.core.permissions import Permission
from app.core.storage import build_object_key, get_storage, validate_upload
from app.core.tasks import send_invitation_email
from app.modules.organizations import (
    invitations_service,
    members_service,
    metrics_service,
    repository,
)
from app.modules.organizations.invitations_models import OrganizationInvitation
from app.modules.organizations.metrics_schemas import MetricasDeOrganizacionOut
from app.modules.organizations.models import OrganizationBranding, OrganizationMember
from app.modules.organizations.schemas import (
    BrandingAdminResponse,
    BrandingUpdate,
    InvitationCreate,
    InvitationCreateResponse,
    InvitationResponse,
    MemberCreate,
    MemberResponse,
    MemberRoleOut,
    OrganizationResponse,
    OrganizationUpdate,
)
from app.modules.roles.models import Role
from app.modules.theme_templates import repository as theme_templates_repository
from app.modules.theme_templates.schemas import ThemeTemplateCatalogItem
from app.modules.users.models import User
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
    "/me/metrics",
    summary="Métricas del escritorio de la organización",
    description=(
        "Compone en una llamada la tabla de eventos con sus cifras, los totales "
        "de la organización, su estructura y el estado de la cuenta de Stripe. "
        "Los bloques para los que quien pide no tiene permiso **se omiten**, no "
        "se esconden en la interfaz: el escritorio junta recursos con permisos "
        "propios y no todos los miembros pueden verlos todos."
    ),
    response_model=MetricasDeOrganizacionOut,
)
async def get_my_metrics(
    usuario: CurrentUserDep, session: DbDep, permisos: PermissionsDep
) -> MetricasDeOrganizacionOut:
    return await metrics_service.metricas_de_la_organizacion(
        session, usuario.organization_id, permisos
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


def _member_response_from_rows(
    persona: User, filas: list[tuple[OrganizationMember, Role]]
) -> MemberResponse:
    return MemberResponse(
        user_id=str(persona.id),
        email=persona.email,
        first_name=persona.first_name,
        last_name=persona.last_name,
        roles=[
            MemberRoleOut(
                id=str(miembro.id), role_id=str(rol.id), role_key=rol.key, role_name=rol.name
            )
            for miembro, rol in filas
        ],
        profile_data=repository.best_profile_data(filas),
    )


@router.get(
    "/me/members",
    summary="Miembros de la organización",
    description=(
        "Una fila por persona, con todos sus roles — no una fila por membresía "
        "(fase 4 del plan de invitaciones): quien tiene dos roles aparecía dos "
        "veces, sin nada que dijera que eran la misma persona."
    ),
    response_model=Page[MemberResponse],
    dependencies=[require_permission(Permission.MEMBERS_READ)],
)
async def list_members(
    usuario: CurrentUserDep,
    session: DbDep,
    paginacion: Annotated[PageParams, Depends(page_params)],
) -> Page[MemberResponse]:
    agrupado = await repository.list_members_grouped(
        session, usuario.organization_id, limit=paginacion.limit, offset=paginacion.offset
    )
    return Page[MemberResponse](
        items=[_member_response_from_rows(persona, filas) for persona, filas in agrupado],
        total=await repository.count_members_grouped(session, usuario.organization_id),
        limit=paginacion.limit,
        offset=paginacion.offset,
    )


async def _member_response_for_user(
    session: AsyncSession, organization_id: uuid.UUID, user_id: uuid.UUID
) -> MemberResponse:
    persona = await session.get(User, user_id)
    if persona is None:  # pragma: no cover - garantizado por la FK de OrganizationMember
        raise NotFoundError("Esa persona ya no existe.")
    filas = await repository.member_roles_for_user(session, organization_id, user_id)
    return _member_response_from_rows(persona, filas)


@router.post(
    "/me/members",
    summary="Añadir un miembro, o un rol más a quien ya está",
    description=(
        "Si el correo ya pertenece a alguien de la organización, esto le añade "
        "el rol nuevo sin duplicarla — es el camino para «hazlo también "
        "ponente». La respuesta trae a la persona con todos sus roles."
    ),
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
    return await _member_response_for_user(session, usuario.organization_id, miembro.user_id)


@router.delete(
    "/me/members/{organization_member_id}",
    summary="Quitar un rol de una persona",
    description=(
        "Quita esa membresía concreta, no a la persona. Si es su último rol en "
        "la organización, rechaza con 409 — decisión del usuario: para dejarla "
        "sin permisos hay que sacarla de la organización, no vaciarle los roles."
    ),
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[require_permission(Permission.MEMBERS_WRITE)],
)
async def remove_member_role(
    organization_member_id: str,
    usuario: CurrentUserDep,
    session: DbDep,
    permisos: PermissionsDep,
) -> None:
    await members_service.remove_member_role(
        session,
        organization_id=usuario.organization_id,
        actor_id=usuario.id,
        actor_permissions=permisos,
        organization_member_id=uuid.UUID(organization_member_id),
    )


def _invitation_response(invitacion: OrganizationInvitation, role_key: str) -> InvitationResponse:
    return InvitationResponse(
        id=str(invitacion.id),
        email=invitacion.email,
        role_id=str(invitacion.role_id),
        role_key=role_key,
        event_id=str(invitacion.event_id) if invitacion.event_id else None,
        estado=invitations_service.estado_efectivo(invitacion),
        expires_at=invitacion.expires_at,
        created_at=invitacion.created_at,
    )


async def _invitation_response_por_id(
    session: AsyncSession, organization_id: uuid.UUID, invitation_id: uuid.UUID
) -> InvitationResponse:
    consulta = repository.invitations_query(organization_id).where(
        OrganizationInvitation.id == invitation_id
    )
    invitacion, rol = (await session.execute(consulta)).one()
    return _invitation_response(invitacion, rol.key)


async def _encolar_correo_de_invitacion(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    invitacion: OrganizationInvitation,
    token: str,
) -> None:
    """Fase 2: el correo dice «te han invitado», nunca «recupera tu contraseña»."""
    organizacion = await repository.get_organization(session, organization_id)
    rol = await session.get(Role, invitacion.role_id)
    if organizacion is None or rol is None:  # pragma: no cover - garantizado por las FK
        return
    await send_invitation_email.kiq(
        invitacion.email, token, str(organization_id), organizacion.name, rol.name
    )


@router.get(
    "/me/invitations",
    summary="Invitaciones pendientes de la organización",
    description=(
        "El estado se calcula al leer: una fila «pendiente» con `expires_at` "
        "pasado se muestra «caducada» sin reescribir la fila."
    ),
    response_model=list[InvitationResponse],
    dependencies=[require_permission(Permission.INVITATIONS_MANAGE)],
)
async def list_invitations(usuario: CurrentUserDep, session: DbDep) -> list[InvitationResponse]:
    filas = (
        await session.execute(repository.invitations_query(usuario.organization_id))
    ).all()
    return [_invitation_response(invitacion, rol.key) for invitacion, rol in filas]


@router.post(
    "/me/invitations",
    summary="Invitar a alguien al equipo",
    description=(
        "Si el correo ya tiene cuenta, se le añade directamente y no se emite "
        "ningún token (regla que cierra el secuestro de cuenta). Si no, se crea "
        "la invitación y una cuenta sin contraseña."
    ),
    status_code=status.HTTP_201_CREATED,
    response_model=InvitationCreateResponse,
    dependencies=[require_permission(Permission.INVITATIONS_MANAGE)],
)
async def create_invitation(
    datos: InvitationCreate,
    usuario: CurrentUserDep,
    session: DbDep,
    permisos: PermissionsDep,
) -> InvitationCreateResponse:
    resultado = await invitations_service.create_invitation(
        session,
        organization_id=usuario.organization_id,
        actor_id=usuario.id,
        actor_permissions=permisos,
        email=str(datos.email),
        role_id=uuid.UUID(datos.role_id),
    )
    if resultado.member is not None:
        return InvitationCreateResponse(
            status="added",
            member=await _member_response_for_user(
                session, usuario.organization_id, resultado.member.user_id
            ),
        )
    if resultado.invitation is None or resultado.token is None:  # pragma: no cover - exhaustivo
        raise RuntimeError("create_invitation no ha devuelto ni miembro ni invitación con token.")
    await _encolar_correo_de_invitacion(
        session,
        organization_id=usuario.organization_id,
        invitacion=resultado.invitation,
        token=resultado.token,
    )
    return InvitationCreateResponse(
        status="invited",
        invitation=await _invitation_response_por_id(
            session, usuario.organization_id, resultado.invitation.id
        ),
    )


@router.delete(
    "/me/invitations/{invitation_id}",
    summary="Revocar una invitación pendiente",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[require_permission(Permission.INVITATIONS_MANAGE)],
)
async def revoke_invitation(
    invitation_id: str, usuario: CurrentUserDep, session: DbDep
) -> None:
    await invitations_service.revoke_invitation(
        session, organization_id=usuario.organization_id, invitation_id=uuid.UUID(invitation_id)
    )


@router.post(
    "/me/invitations/{invitation_id}/resend",
    summary="Reenviar una invitación pendiente",
    description="Emite un token nuevo, alarga la caducidad e invalida el enlace anterior.",
    response_model=InvitationResponse,
    dependencies=[require_permission(Permission.INVITATIONS_MANAGE)],
)
async def resend_invitation(
    invitation_id: str, usuario: CurrentUserDep, session: DbDep
) -> InvitationResponse:
    invitacion, token = await invitations_service.resend_invitation(
        session, organization_id=usuario.organization_id, invitation_id=uuid.UUID(invitation_id)
    )
    await _encolar_correo_de_invitacion(
        session, organization_id=usuario.organization_id, invitacion=invitacion, token=token
    )
    return await _invitation_response_por_id(session, usuario.organization_id, invitacion.id)
