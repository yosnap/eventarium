"""Endpoints de eventos y agenda de la organización actual."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUserDep, DbDep, PermissionsDep, require_permission
from app.core.permissions import Permission
from app.core.ratelimit import PEDIR_BIO_POR_IP, limit_per_ip
from app.core.storage import build_object_key, get_storage, validate_upload
from app.core.tasks import send_invitation_email, send_speaker_bio_request_email
from app.modules.events import repository, service, speakers_repository
from app.modules.events.models import Event, EventMember, EventSession, EventVenue
from app.modules.events.schemas import (
    EventCreate,
    EventInvitationCreate,
    EventMemberCreate,
    EventMemberResponse,
    EventResponse,
    EventSessionCreate,
    EventSessionResponse,
    EventSessionUpdate,
    EventSpeakersViewOut,
    EventStatus,
    EventUpdate,
    EventVenueCreate,
    EventVenueResponse,
    EventVenueUpdate,
    SessionParticipantResponse,
    SessionParticipantsUpdate,
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
from app.shared.pagination import Page, PageParams, page_params

router = APIRouter(prefix="/events", tags=["eventos"])


def _event_response(evento: Event) -> EventResponse:
    almacen = get_storage()
    return EventResponse(
        id=str(evento.id),
        slug=evento.slug,
        title=evento.title,
        summary=evento.summary,
        description=evento.description,
        cover_url=almacen.public_url(evento.cover_object_key) if evento.cover_object_key else None,
        status=evento.status,  # type: ignore[arg-type]
        visibility=evento.visibility,  # type: ignore[arg-type]
        timezone=evento.timezone,
        starts_at=evento.starts_at,
        ends_at=evento.ends_at,
        location_mode=evento.location_mode,  # type: ignore[arg-type]
        location_name=evento.location_name,
        location_address=evento.location_address,
        city=evento.city,
        online_url=evento.online_url,
        capacity=evento.capacity,
        registration_mode=evento.registration_mode,  # type: ignore[arg-type]
        registration_opens_at=evento.registration_opens_at,
        email_verification_required=evento.email_verification_required,
        payment_checkout_window_minutes=evento.payment_checkout_window_minutes,
        latitude=float(evento.latitude) if evento.latitude is not None else None,
        longitude=float(evento.longitude) if evento.longitude is not None else None,
        contingency_fund_percent=evento.contingency_fund_percent,
        budget_approved_at=evento.budget_approved_at,
        contingency_fund_cents=evento.contingency_fund_cents,
        accounting_currency=evento.accounting_currency,
        theme_template_id=(str(evento.theme_template_id) if evento.theme_template_id else None),
        theme_overrides=evento.theme_overrides,
    )


def _venue_response(sede: EventVenue) -> EventVenueResponse:
    return EventVenueResponse(
        id=str(sede.id),
        name=sede.name,
        address=sede.address,
        capacity=sede.capacity,
        display_order=sede.display_order,
        latitude=float(sede.latitude) if sede.latitude is not None else None,
        longitude=float(sede.longitude) if sede.longitude is not None else None,
        geocoded_at=sede.geocoded_at,
    )


def _session_response(sesion: EventSession) -> EventSessionResponse:
    return EventSessionResponse(
        id=str(sesion.id),
        session_type=sesion.session_type,  # type: ignore[arg-type]
        title=sesion.title,
        description=sesion.description,
        starts_at=sesion.starts_at,
        ends_at=sesion.ends_at,
        room=sesion.room,
        video_platform=sesion.video_platform,  # type: ignore[arg-type]
        video_url=sesion.video_url,
        materials=sesion.materials,
        sort_order=sesion.sort_order,
        venue_id=str(sesion.venue_id) if sesion.venue_id is not None else None,
        updated_at=sesion.updated_at,
    )


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


def _session_participant_response(fila: Any) -> SessionParticipantResponse:
    participante, miembro, miembro_org, persona = fila
    return SessionParticipantResponse(
        id=str(participante.id),
        event_member_id=str(miembro.id),
        user_id=str(persona.id),
        email=persona.email,
        first_name=persona.first_name,
        last_name=persona.last_name,
        role_key=participante.role_key,
        sort_order=participante.sort_order,
    )


async def _obtener_evento_o_404(session: DbDep, usuario: CurrentUserDep, event_id: str) -> Event:
    evento = await repository.get_event(session, usuario.organization_id, uuid.UUID(event_id))
    if evento is None:
        raise NotFoundError("El evento no existe.")
    return evento


@router.get(
    "",
    summary="Listar eventos",
    response_model=Page[EventResponse],
    dependencies=[require_permission(Permission.EVENTS_READ)],
)
async def list_events(
    usuario: CurrentUserDep,
    session: DbDep,
    paginacion: Annotated[PageParams, Depends(page_params)],
    estado: Annotated[EventStatus | None, Query(alias="status")] = None,
) -> Page[EventResponse]:
    consulta = repository.events_query(usuario.organization_id, status=estado)
    total = len((await session.execute(consulta)).all())
    filas = (
        await session.execute(consulta.limit(paginacion.limit).offset(paginacion.offset))
    ).scalars()
    return Page[EventResponse](
        items=[_event_response(evento) for evento in filas],
        total=total,
        limit=paginacion.limit,
        offset=paginacion.offset,
    )


@router.post(
    "",
    summary="Crear un evento",
    status_code=status.HTTP_201_CREATED,
    response_model=EventResponse,
    dependencies=[require_permission(Permission.EVENTS_WRITE)],
)
async def create_event(
    datos: EventCreate, usuario: CurrentUserDep, session: DbDep
) -> EventResponse:
    evento = await service.create_event(
        session, organization_id=usuario.organization_id, datos=datos.model_dump()
    )
    return _event_response(evento)


@router.get(
    "/{event_id}",
    summary="Ver un evento",
    response_model=EventResponse,
    dependencies=[require_permission(Permission.EVENTS_READ)],
)
async def get_event(evento: Annotated[Event, Depends(_obtener_evento_o_404)]) -> EventResponse:
    return _event_response(evento)


@router.patch(
    "/{event_id}",
    summary="Actualizar un evento",
    response_model=EventResponse,
    dependencies=[require_permission(Permission.EVENTS_WRITE)],
)
async def update_event(
    datos: EventUpdate, usuario: CurrentUserDep, session: DbDep, event_id: str
) -> EventResponse:
    evento = await service.update_event(
        session,
        organization_id=usuario.organization_id,
        event_id=uuid.UUID(event_id),
        datos=datos.model_dump(exclude_unset=True),
    )
    return _event_response(evento)


@router.put(
    "/{event_id}/cover",
    summary="Subir la portada del evento",
    description="Acepta PNG, JPEG o WebP de hasta 5 MB. El tipo se comprueba por contenido.",
    response_model=EventResponse,
    dependencies=[require_permission(Permission.EVENTS_WRITE)],
)
async def upload_cover(
    evento: Annotated[Event, Depends(_obtener_evento_o_404)],
    session: DbDep,
    background_tasks: BackgroundTasks,
    fichero: Annotated[UploadFile, File(description="Imagen de portada")],
) -> EventResponse:
    contenido = await fichero.read()
    mime, extension = validate_upload(contenido)

    almacen = get_storage()
    clave = build_object_key(evento.organization_id, f"events/{evento.id}/cover", extension)
    await almacen.put_object(clave, contenido, mime)

    anterior = evento.cover_object_key
    evento.cover_object_key = clave
    await session.flush()

    # El objeto anterior se borra en un `BackgroundTask`, que Starlette ejecuta
    # tras enviar la respuesta — y por tanto tras el `commit` real de la
    # transacción (que ocurre al salir de la dependencia `get_db`, antes de que
    # exista una `Response` a la que enganchar la tarea). Si el `commit` fallara,
    # nunca se llega a construir la respuesta y esta tarea nunca se ejecuta: el
    # objeto anterior no se borra si la fila no queda actualizada. Borrarlo justo
    # tras el `flush()` (como hacía `branding/logo`) dejaría la fila apuntando a
    # un objeto ya inexistente ante cualquier fallo posterior en la misma
    # transacción — más grave aquí, porque esta portada alimenta `og:image` en
    # una página pública indexada.
    if anterior and anterior != clave:
        background_tasks.add_task(almacen.delete_object, anterior)

    return _event_response(evento)


@router.get(
    "/{event_id}/sessions",
    summary="Listar la agenda de un evento",
    response_model=list[EventSessionResponse],
    dependencies=[require_permission(Permission.EVENTS_READ)],
)
async def list_sessions(
    evento: Annotated[Event, Depends(_obtener_evento_o_404)], session: DbDep
) -> list[EventSessionResponse]:
    consulta = repository.sessions_query(evento.organization_id, evento.id)
    filas = (await session.execute(consulta)).scalars()
    return [_session_response(sesion) for sesion in filas]


@router.post(
    "/{event_id}/sessions",
    summary="Añadir una sesión a la agenda",
    status_code=status.HTTP_201_CREATED,
    response_model=EventSessionResponse,
    dependencies=[require_permission(Permission.EVENTS_WRITE)],
)
async def create_session(
    datos: EventSessionCreate,
    evento: Annotated[Event, Depends(_obtener_evento_o_404)],
    usuario: CurrentUserDep,
    session: DbDep,
) -> EventSessionResponse:
    sesion = await service.create_session(
        session,
        organization_id=usuario.organization_id,
        event_id=evento.id,
        datos=datos.model_dump(),
    )
    return _session_response(sesion)


@router.patch(
    "/{event_id}/sessions/{session_id}",
    summary="Actualizar una sesión de la agenda",
    response_model=EventSessionResponse,
    dependencies=[require_permission(Permission.EVENTS_WRITE)],
)
async def update_session(
    datos: EventSessionUpdate,
    evento: Annotated[Event, Depends(_obtener_evento_o_404)],
    usuario: CurrentUserDep,
    session: DbDep,
    session_id: str,
) -> EventSessionResponse:
    sesion = await service.update_session(
        session,
        organization_id=usuario.organization_id,
        event_id=evento.id,
        session_id=uuid.UUID(session_id),
        datos=datos.model_dump(exclude_unset=True),
    )
    return _session_response(sesion)


@router.delete(
    "/{event_id}/sessions/{session_id}",
    summary="Quitar una sesión de la agenda",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[require_permission(Permission.EVENTS_WRITE)],
)
async def delete_session(
    evento: Annotated[Event, Depends(_obtener_evento_o_404)],
    usuario: CurrentUserDep,
    session: DbDep,
    session_id: str,
) -> None:
    await service.delete_session(
        session,
        organization_id=usuario.organization_id,
        event_id=evento.id,
        session_id=uuid.UUID(session_id),
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
    evento: Annotated[Event, Depends(_obtener_evento_o_404)], session: DbDep
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
        items.append(
            SpeakerRowOut(
                organization_member_id=str(miembro_org.id),
                user_id=str(persona.id),
                email=persona.email,
                first_name=persona.first_name,
                last_name=persona.last_name,
                titular=titular.strip() if isinstance(titular, str) and titular.strip() else None,
                sesiones=[
                    SpeakerSessionOut(id=str(id_sesion), titulo=titulo, starts_at=empieza)
                    for id_sesion, titulo, empieza in sesiones.get(miembro.id, [])
                ],
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
    evento: Annotated[Event, Depends(_obtener_evento_o_404)],
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
    evento: Annotated[Event, Depends(_obtener_evento_o_404)],
    session: DbDep,
    organization_member_id: str,
) -> None:
    correo = await speakers_repository.obtener_email_de_miembro_del_evento(
        session,
        organization_id=evento.organization_id,
        event_id=evento.id,
        organization_member_id=uuid.UUID(organization_member_id),
    )
    if correo is None:
        raise NotFoundError("La persona no está en el roster de este evento.")
    await send_speaker_bio_request_email.kiq(correo, str(evento.organization_id), evento.title)


@router.get(
    "/{event_id}/members",
    summary="Listar el roster de un evento",
    response_model=list[EventMemberResponse],
    dependencies=[require_permission(Permission.EVENTS_READ)],
)
async def list_event_members(
    evento: Annotated[Event, Depends(_obtener_evento_o_404)], session: DbDep
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
    evento: Annotated[Event, Depends(_obtener_evento_o_404)],
    usuario: CurrentUserDep,
    session: DbDep,
) -> EventMemberResponse:
    miembro = await service.add_event_member(
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
    evento: Annotated[Event, Depends(_obtener_evento_o_404)],
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
    evento: Annotated[Event, Depends(_obtener_evento_o_404)],
    usuario: CurrentUserDep,
    session: DbDep,
    event_member_id: str,
) -> None:
    await service.remove_event_member(
        session,
        organization_id=usuario.organization_id,
        event_id=evento.id,
        event_member_id=uuid.UUID(event_member_id),
    )


@router.get(
    "/{event_id}/sessions/{session_id}/participants",
    summary="Listar los participantes de una sesión",
    response_model=list[SessionParticipantResponse],
    dependencies=[require_permission(Permission.EVENTS_READ)],
)
async def list_session_participants(
    evento: Annotated[Event, Depends(_obtener_evento_o_404)],
    session: DbDep,
    session_id: str,
) -> list[SessionParticipantResponse]:
    sesion = await repository.get_event_session(
        session, evento.organization_id, evento.id, uuid.UUID(session_id)
    )
    if sesion is None:
        raise NotFoundError("La sesión no existe.")
    consulta = repository.session_participants_query(evento.organization_id, sesion.id)
    filas = (await session.execute(consulta)).all()
    return [_session_participant_response(fila) for fila in filas]


@router.get(
    "/{event_id}/venues",
    summary="Listar las sedes de un evento",
    response_model=list[EventVenueResponse],
    dependencies=[require_permission(Permission.EVENTS_READ)],
)
async def list_venues(
    evento: Annotated[Event, Depends(_obtener_evento_o_404)], session: DbDep
) -> list[EventVenueResponse]:
    consulta = repository.venues_query(evento.organization_id, evento.id)
    filas = (await session.execute(consulta)).scalars()
    return [_venue_response(sede) for sede in filas]


@router.post(
    "/{event_id}/venues",
    summary="Añadir una sede a un evento",
    status_code=status.HTTP_201_CREATED,
    response_model=EventVenueResponse,
    dependencies=[require_permission(Permission.EVENTS_WRITE)],
)
async def create_venue(
    datos: EventVenueCreate,
    evento: Annotated[Event, Depends(_obtener_evento_o_404)],
    usuario: CurrentUserDep,
    session: DbDep,
) -> EventVenueResponse:
    sede = await service.create_venue(
        session,
        organization_id=usuario.organization_id,
        event_id=evento.id,
        datos=datos.model_dump(),
    )
    return _venue_response(sede)


@router.patch(
    "/{event_id}/venues/{venue_id}",
    summary="Actualizar una sede",
    response_model=EventVenueResponse,
    dependencies=[require_permission(Permission.EVENTS_WRITE)],
)
async def update_venue(
    datos: EventVenueUpdate,
    evento: Annotated[Event, Depends(_obtener_evento_o_404)],
    usuario: CurrentUserDep,
    session: DbDep,
    venue_id: str,
) -> EventVenueResponse:
    sede = await service.update_venue(
        session,
        organization_id=usuario.organization_id,
        event_id=evento.id,
        venue_id=uuid.UUID(venue_id),
        datos=datos.model_dump(exclude_unset=True),
    )
    return _venue_response(sede)


@router.delete(
    "/{event_id}/venues/{venue_id}",
    summary="Quitar una sede de un evento",
    description=(
        "Falla con 409 si alguna sesión de la agenda tiene esta sede asignada — "
        "hay que reasignarla o quitarla primero de esas sesiones."
    ),
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[require_permission(Permission.EVENTS_WRITE)],
)
async def delete_venue(
    evento: Annotated[Event, Depends(_obtener_evento_o_404)],
    usuario: CurrentUserDep,
    session: DbDep,
    venue_id: str,
) -> None:
    await service.delete_venue(
        session,
        organization_id=usuario.organization_id,
        event_id=evento.id,
        venue_id=uuid.UUID(venue_id),
    )


@router.put(
    "/{event_id}/sessions/{session_id}/participants",
    summary="Reemplazar los participantes de una sesión",
    description=(
        "Reemplaza la lista completa en una sola petición. Lleva control de "
        "concurrencia optimista: `expected_updated_at` debe coincidir con el "
        "`updated_at` actual de la sesión, si no la petición falla con 409."
    ),
    response_model=list[SessionParticipantResponse],
    dependencies=[require_permission(Permission.EVENTS_WRITE)],
)
async def replace_session_participants(
    datos: SessionParticipantsUpdate,
    evento: Annotated[Event, Depends(_obtener_evento_o_404)],
    usuario: CurrentUserDep,
    session: DbDep,
    session_id: str,
) -> list[SessionParticipantResponse]:
    sesion = await service.replace_session_participants(
        session,
        organization_id=usuario.organization_id,
        event_id=evento.id,
        session_id=uuid.UUID(session_id),
        expected_updated_at=datos.expected_updated_at,
        entries=[
            {"event_member_id": uuid.UUID(p.event_member_id), "role_key": p.role_key}
            for p in datos.participants
        ],
    )
    consulta = repository.session_participants_query(evento.organization_id, sesion.id)
    filas = (await session.execute(consulta)).all()
    return [_session_participant_response(fila) for fila in filas]
