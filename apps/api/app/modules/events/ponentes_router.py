"""Endpoints del roster de un evento: ponentes, miembros e invitaciones."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUserDep, DbDep, PermissionsDep, require_permission
from app.core.permissions import Permission
from app.core.ratelimit import PEDIR_BIO_POR_IP, limit_per_ip
from app.core.tasks import send_invitation_email, send_speaker_bio_request_email
from app.modules.events import (
    agenda,
    repository,
    speakers_repository,
)
from app.modules.events.models import (
    Event,
    EventMember,
)
from app.modules.events.router_comun import obtener_evento_o_404
from app.modules.events.schemas import (
    EventInvitationCreate,
    EventMemberCreate,
    EventMemberResponse,
    EventSpeakersViewOut,
    SpeakerCompletitudOut,
    SpeakerHistoryItemOut,
    SpeakerRowOut,
    SpeakerSessionOut,
)
from app.modules.organizations import invitations_service
from app.modules.organizations import repository as organizations_repository
from app.modules.organizations.invitations_models import OrganizationInvitation
from app.modules.organizations.schemas import (
    InvitationCreateResponse,
    InvitationResponse,
    MemberResponse,
    MemberRoleOut,
)
from app.modules.roles.models import Role
from app.modules.roles.system_roles import SPEAKER_KEY
from app.modules.users.models import User
from app.shared.errors import NotFoundError

# Sin prefijo ni etiqueta: los hereda al incluirse en `events.router`.
router = APIRouter()


def _event_member_response(fila: Any) -> EventMemberResponse:
    miembro, miembro_org, persona, rol = fila
    return EventMemberResponse(
        id=str(miembro.id),
        organization_member_id=str(miembro_org.id),
        user_id=str(persona.id),
        email=persona.email,
        first_name=persona.first_name,
        last_name=persona.last_name,
        role_key=rol.key,
    )


def _completitud_de_ficha(profile_data: dict[str, Any]) -> SpeakerCompletitudOut:
    """Porcentaje de claves de la ficha de ponente presentes y no vacías.

    La fórmula es fija (las claves de la plantilla del rol ponente, fijadas
    en el repositorio): sin fields rellenados es 0 %, y el filtro de
    «incompletas» del panel la usa sin excepciones.
    """
    claves = speakers_repository.CLAVES_FICHA_PONENTE
    rellenas = sum(1 for clave in claves if _clave_con_texto(profile_data, clave))
    faltantes = [c for c in claves if not _clave_con_texto(profile_data, c)]
    total = len(claves)
    return SpeakerCompletitudOut(
        porcentaje=round(rellenas / total * 100),
        rellenas=rellenas,
        total=total,
        faltantes=faltantes,
    )


def _clave_con_texto(profile_data: dict[str, Any], clave: str) -> bool:
    valor = profile_data.get(clave)
    return isinstance(valor, str) and bool(valor.strip())


@router.get(
    "/{event_id}/speakers",
    summary="Vista agregada de ponentes del evento",
    description=(
        "Una fila por ponente del roster (rol de ponente en la organización), "
        "con sus sesiones asignadas, el estado de su ficha, cuántos eventos de "
        "la organización acumula y su perfil público si lo activó. Una consulta "
        "por tabla: nada de resolver el historial ponente a ponente."
    ),
    response_model=EventSpeakersViewOut,
    dependencies=[require_permission(Permission.EVENTS_READ)],
)
async def list_event_speakers(
    evento: Annotated[Event, Depends(obtener_evento_o_404)], session: DbDep
) -> EventSpeakersViewOut:
    (
        filas,
        sesiones,
        ediciones,
        slugs,
        total_sesiones,
    ) = await speakers_repository.listar_ponentes_del_evento(
        session, evento.organization_id, evento.id
    )
    items: list[SpeakerRowOut] = []
    for miembro, miembro_org, persona, _rol in filas:
        titular = miembro_org.profile_data.get("titular")
        bio = miembro_org.profile_data.get("bio")
        items.append(
            SpeakerRowOut(
                organization_member_id=str(miembro_org.id),
                event_member_id=str(miembro.id),
                user_id=str(persona.id),
                email=persona.email,
                first_name=persona.first_name,
                last_name=persona.last_name,
                titular=titular.strip() if isinstance(titular, str) and titular.strip() else None,
                bio=bio.strip() if isinstance(bio, str) and bio.strip() else None,
                # Una fila por sesión aunque tenga ahí varios roles.
                sesiones=list(
                    {
                        str(id_sesion): SpeakerSessionOut(
                            id=str(id_sesion), titulo=titulo, starts_at=empieza
                        )
                        for id_sesion, titulo, empieza in sesiones.get(miembro.id, [])
                    }.values()
                ),
                completitud=_completitud_de_ficha(miembro_org.profile_data),
                ediciones=ediciones.get(miembro_org.user_id, 0),
                public_slug=slugs.get(miembro_org.user_id),
            )
        )
    return EventSpeakersViewOut(items=items, total_sesiones=total_sesiones)


@router.get(
    "/{event_id}/speakers/{user_id}/historial",
    summary="Historial de participación de un ponente",
    description=(
        "Solo para el diálogo del panel: eventos de esta organización donde la "
        "persona participó, sin filtro de publicación porque el organizador "
        "ve también borradores."
    ),
    response_model=list[SpeakerHistoryItemOut],
    dependencies=[require_permission(Permission.EVENTS_READ)],
)
async def list_speaker_history(
    evento: Annotated[Event, Depends(obtener_evento_o_404)],
    session: DbDep,
    user_id: str,
) -> list[SpeakerHistoryItemOut]:
    filas = await speakers_repository.get_speaker_history(
        session, evento.organization_id, uuid.UUID(user_id), only_published_public=False
    )
    return [
        SpeakerHistoryItemOut(
            evento_titulo=ev.title,
            rol=participacion.role_key,
            fecha=sesion.starts_at,
        )
        for participacion, sesion, ev in filas
    ]


@router.post(
    "/{event_id}/speakers/{organization_member_id}/pedir-bio",
    summary="Pedir al ponente que complete su ficha",
    description=(
        "Encola un correo al ponente con el enlace a su cuenta, donde rellena "
        "su perfil. La persona debe estar en el roster del evento."
    ),
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[
        require_permission(Permission.EVENTS_WRITE),
        limit_per_ip("pedir-bio", PEDIR_BIO_POR_IP),
    ],
)
async def request_speaker_bio(
    evento: Annotated[Event, Depends(obtener_evento_o_404)],
    session: DbDep,
    organization_member_id: str,
) -> None:
    destinatario = await speakers_repository.obtener_correo_e_idioma_de_ponente(
        session,
        organization_id=evento.organization_id,
        event_id=evento.id,
        organization_member_id=uuid.UUID(organization_member_id),
    )
    if destinatario is None:
        raise NotFoundError("La persona no está en el roster de este evento.")
    correo, idioma = destinatario
    await send_speaker_bio_request_email.kiq(
        correo, str(evento.organization_id), evento.title, locale=idioma
    )


@router.get(
    "/{event_id}/members",
    summary="Listar el roster de un evento",
    response_model=list[EventMemberResponse],
    dependencies=[require_permission(Permission.EVENTS_READ)],
)
async def list_event_members(
    evento: Annotated[Event, Depends(obtener_evento_o_404)], session: DbDep
) -> list[EventMemberResponse]:
    consulta = repository.event_members_query(evento.organization_id, evento.id)
    filas = (await session.execute(consulta)).all()
    return [_event_member_response(fila) for fila in filas]


@router.post(
    "/{event_id}/members",
    summary="Añadir una persona al roster del evento",
    status_code=status.HTTP_201_CREATED,
    response_model=EventMemberResponse,
    dependencies=[require_permission(Permission.EVENTS_WRITE)],
)
async def add_event_member(
    datos: EventMemberCreate,
    evento: Annotated[Event, Depends(obtener_evento_o_404)],
    usuario: CurrentUserDep,
    session: DbDep,
) -> EventMemberResponse:
    miembro = await agenda.add_event_member(
        session,
        organization_id=usuario.organization_id,
        event_id=evento.id,
        organization_member_id=uuid.UUID(datos.organization_member_id),
    )
    consulta = repository.event_members_query(evento.organization_id, evento.id).where(
        EventMember.id == miembro.id
    )
    fila = (await session.execute(consulta)).one()
    return _event_member_response(fila)


async def _speaker_role_id(session: AsyncSession, organization_id: uuid.UUID) -> uuid.UUID:
    """El rol `speaker` de la organización — siempre existe: es un rol de
    sistema, clonado en toda organización (`system_roles.py`)."""
    rol = await session.scalar(
        select(Role).where(Role.organization_id == organization_id, Role.key == SPEAKER_KEY)
    )
    if rol is None:  # pragma: no cover - un rol de sistema no debería faltar
        raise NotFoundError("El rol «speaker» no existe en esta organización.")
    return rol.id


async def _organization_member_response(
    session: AsyncSession, organization_id: uuid.UUID, user_id: uuid.UUID
) -> MemberResponse:
    """Mismo mapeo que `organizations/router.py::_member_response_for_user`
    (fase 4 del plan de invitaciones: una fila por persona, con todos sus
    roles). No se reutiliza esa función privada entre routers, se repite
    localmente — es la misma decisión que ya explica `phase-03` (ningún
    router importa helpers de otro)."""
    persona = await session.get(User, user_id)
    if persona is None:  # pragma: no cover - garantizado por la FK de OrganizationMember
        raise NotFoundError("Esa persona ya no existe.")
    filas = await organizations_repository.member_roles_for_user(session, organization_id, user_id)
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
        profile_data=organizations_repository.best_profile_data(filas),
    )


async def _event_invitation_response(
    session: AsyncSession, organization_id: uuid.UUID, invitation_id: uuid.UUID
) -> InvitationResponse:
    consulta = organizations_repository.invitations_query(organization_id).where(
        OrganizationInvitation.id == invitation_id
    )
    invitacion, rol = (await session.execute(consulta)).one()
    return InvitationResponse(
        id=str(invitacion.id),
        email=invitacion.email,
        role_id=str(invitacion.role_id),
        role_key=rol.key,
        event_id=str(invitacion.event_id) if invitacion.event_id else None,
        estado=invitations_service.estado_efectivo(invitacion),
        expires_at=invitacion.expires_at,
        created_at=invitacion.created_at,
    )


@router.post(
    "/{event_id}/invitations",
    summary="Invitar a un ponente al evento",
    description=(
        "Rol por defecto «speaker»; se puede indicar otro. Si el correo ya "
        "tiene cuenta se añade directamente a la organización y al roster; "
        "si no, se crea la invitación y, al aceptar, la persona queda "
        "en la organización y en el roster del evento en la misma operación."
    ),
    status_code=status.HTTP_201_CREATED,
    response_model=InvitationCreateResponse,
    dependencies=[require_permission(Permission.INVITATIONS_MANAGE)],
)
async def create_event_invitation(
    datos: EventInvitationCreate,
    evento: Annotated[Event, Depends(obtener_evento_o_404)],
    usuario: CurrentUserDep,
    session: DbDep,
    permisos: PermissionsDep,
) -> InvitationCreateResponse:
    role_id = (
        uuid.UUID(datos.role_id)
        if datos.role_id
        else await _speaker_role_id(session, usuario.organization_id)
    )
    resultado = await invitations_service.create_invitation(
        session,
        organization_id=usuario.organization_id,
        actor_id=usuario.id,
        actor_permissions=permisos,
        email=str(datos.email),
        role_id=role_id,
        event_id=evento.id,
    )
    if resultado.member is not None:
        return InvitationCreateResponse(
            status="added",
            member=await _organization_member_response(
                session, usuario.organization_id, resultado.member.user_id
            ),
        )
    if resultado.invitation is None or resultado.token is None:  # pragma: no cover - exhaustivo
        raise RuntimeError("create_invitation no ha devuelto ni miembro ni invitación con token.")

    organizacion = await organizations_repository.get_organization(session, usuario.organization_id)
    rol = await session.get(Role, resultado.invitation.role_id)
    if organizacion is not None and rol is not None:
        await send_invitation_email.kiq(
            resultado.invitation.email,
            resultado.token,
            str(usuario.organization_id),
            organizacion.name,
            rol.name,
            locale=await invitations_service.idioma_de_la_invitacion(resultado.invitation.email),
        )
    return InvitationCreateResponse(
        status="invited",
        invitation=await _event_invitation_response(
            session, usuario.organization_id, resultado.invitation.id
        ),
    )


@router.delete(
    "/{event_id}/members/{event_member_id}",
    summary="Quitar una persona del roster del evento",
    description=(
        "Falla con 409 si la persona tiene participaciones activas en la agenda de "
        "este evento — hay que quitarla primero de las sesiones."
    ),
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[require_permission(Permission.EVENTS_WRITE)],
)
async def remove_event_member(
    evento: Annotated[Event, Depends(obtener_evento_o_404)],
    usuario: CurrentUserDep,
    session: DbDep,
    event_member_id: str,
) -> None:
    await agenda.remove_event_member(
        session,
        organization_id=usuario.organization_id,
        event_id=evento.id,
        event_member_id=uuid.UUID(event_member_id),
    )
