"""Endpoints de niveles de patrocinio (organización) y patrocinadores (evento).

Dos routers en el mismo fichero, mismo criterio que separar `sponsor_tiers` de
`sponsors` en `models.py`: los niveles son de la organización actual
(`/organizations/me/...`, mismo prefijo que `branding`/`members` en
`organizations/router.py`, no `/organizations/{id}/...` — esta API nunca
identifica la organización por un `{id}` en la ruta, la resuelve del usuario
autenticado); los patrocinadores cuelgan de un evento concreto
(`/events/{event_id}/sponsors`, mismo patrón que `/events/{event_id}/sessions`
en `events/router.py`).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, UploadFile, status

from app.core.deps import CurrentUserDep, DbDep, require_permission
from app.core.permissions import Permission
from app.core.storage import build_object_key, get_storage, validate_upload
from app.modules.events import repository as events_repository
from app.modules.events.models import Event
from app.modules.sponsors import repository, service
from app.modules.sponsors.models import Sponsor, SponsorTier
from app.modules.sponsors.schemas import (
    SponsorCreate,
    SponsorResponse,
    SponsorTierCreate,
    SponsorTierResponse,
    SponsorTierUpdate,
    SponsorUpdate,
)
from app.shared.errors import NotFoundError
from app.shared.pagination import Page, PageParams, page_params

router_tiers = APIRouter(prefix="/organizations/me/sponsor-tiers", tags=["patrocinio"])
router_sponsors = APIRouter(prefix="/events/{event_id}/sponsors", tags=["patrocinio"])


def _tier_response(nivel: SponsorTier) -> SponsorTierResponse:
    return SponsorTierResponse(
        id=str(nivel.id),
        name=nivel.name,
        display_order=nivel.display_order,
        logo_size=nivel.logo_size,  # type: ignore[arg-type]
        benefits=nivel.benefits,
    )


def _sponsor_response(patrocinador: Sponsor) -> SponsorResponse:
    almacen = get_storage()
    return SponsorResponse(
        id=str(patrocinador.id),
        tier_id=str(patrocinador.tier_id),
        name=patrocinador.name,
        logo_url=almacen.public_url(patrocinador.logo_object_key)
        if patrocinador.logo_object_key
        else None,
        website=patrocinador.website,
        contribution_type=patrocinador.contribution_type,  # type: ignore[arg-type]
        contribution_amount=patrocinador.contribution_amount,
        contribution_description=patrocinador.contribution_description,
    )


@router_tiers.get(
    "",
    summary="Listar niveles de patrocinio",
    response_model=Page[SponsorTierResponse],
    dependencies=[require_permission(Permission.SPONSORS_READ)],
)
async def list_sponsor_tiers(
    usuario: CurrentUserDep,
    session: DbDep,
    paginacion: Annotated[PageParams, Depends(page_params)],
) -> Page[SponsorTierResponse]:
    consulta = repository.sponsor_tiers_query(usuario.organization_id)
    total = len((await session.execute(consulta)).all())
    filas = (
        await session.execute(consulta.limit(paginacion.limit).offset(paginacion.offset))
    ).scalars()
    return Page[SponsorTierResponse](
        items=[_tier_response(nivel) for nivel in filas],
        total=total,
        limit=paginacion.limit,
        offset=paginacion.offset,
    )


@router_tiers.post(
    "",
    summary="Crear un nivel de patrocinio",
    status_code=status.HTTP_201_CREATED,
    response_model=SponsorTierResponse,
    dependencies=[require_permission(Permission.SPONSORS_WRITE)],
)
async def create_sponsor_tier(
    datos: SponsorTierCreate, usuario: CurrentUserDep, session: DbDep
) -> SponsorTierResponse:
    nivel = await service.create_tier(
        session, organization_id=usuario.organization_id, datos=datos.model_dump()
    )
    return _tier_response(nivel)


@router_tiers.patch(
    "/{tier_id}",
    summary="Actualizar un nivel de patrocinio",
    description=(
        "También reordena: para mover un nivel, actualiza `display_order` de los "
        "niveles afectados con peticiones sucesivas."
    ),
    response_model=SponsorTierResponse,
    dependencies=[require_permission(Permission.SPONSORS_WRITE)],
)
async def update_sponsor_tier(
    datos: SponsorTierUpdate, usuario: CurrentUserDep, session: DbDep, tier_id: str
) -> SponsorTierResponse:
    nivel = await service.update_tier(
        session,
        organization_id=usuario.organization_id,
        tier_id=uuid.UUID(tier_id),
        datos=datos.model_dump(exclude_unset=True),
    )
    return _tier_response(nivel)


@router_tiers.delete(
    "/{tier_id}",
    summary="Borrar un nivel de patrocinio",
    description="Falla con 409 si el nivel tiene patrocinadores asignados.",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[require_permission(Permission.SPONSORS_WRITE)],
)
async def delete_sponsor_tier(usuario: CurrentUserDep, session: DbDep, tier_id: str) -> None:
    await service.delete_tier(
        session, organization_id=usuario.organization_id, tier_id=uuid.UUID(tier_id)
    )


async def _obtener_evento_o_404(session: DbDep, usuario: CurrentUserDep, event_id: str) -> Event:
    evento = await events_repository.get_event(session, usuario.organization_id, uuid.UUID(event_id))
    if evento is None:
        raise NotFoundError("El evento no existe.")
    return evento


@router_sponsors.get(
    "",
    summary="Listar los patrocinadores de un evento",
    response_model=list[SponsorResponse],
    dependencies=[require_permission(Permission.SPONSORS_READ)],
)
async def list_sponsors(
    evento: Annotated[Event, Depends(_obtener_evento_o_404)], session: DbDep
) -> list[SponsorResponse]:
    consulta = repository.sponsors_query(evento.organization_id, evento.id)
    filas = (await session.execute(consulta)).scalars()
    return [_sponsor_response(patrocinador) for patrocinador in filas]


@router_sponsors.post(
    "",
    summary="Añadir un patrocinador a un evento",
    status_code=status.HTTP_201_CREATED,
    response_model=SponsorResponse,
    dependencies=[require_permission(Permission.SPONSORS_WRITE)],
)
async def create_sponsor(
    datos: SponsorCreate,
    evento: Annotated[Event, Depends(_obtener_evento_o_404)],
    session: DbDep,
) -> SponsorResponse:
    valores = datos.model_dump()
    valores["tier_id"] = uuid.UUID(valores["tier_id"])
    patrocinador = await service.create_sponsor(
        session, organization_id=evento.organization_id, event_id=evento.id, datos=valores
    )
    return _sponsor_response(patrocinador)


@router_sponsors.patch(
    "/{sponsor_id}",
    summary="Actualizar un patrocinador",
    response_model=SponsorResponse,
    dependencies=[require_permission(Permission.SPONSORS_WRITE)],
)
async def update_sponsor(
    datos: SponsorUpdate,
    evento: Annotated[Event, Depends(_obtener_evento_o_404)],
    session: DbDep,
    sponsor_id: str,
) -> SponsorResponse:
    valores = datos.model_dump(exclude_unset=True)
    if "tier_id" in valores:
        valores["tier_id"] = uuid.UUID(valores["tier_id"])
    patrocinador = await service.update_sponsor(
        session,
        organization_id=evento.organization_id,
        event_id=evento.id,
        sponsor_id=uuid.UUID(sponsor_id),
        datos=valores,
    )
    return _sponsor_response(patrocinador)


@router_sponsors.delete(
    "/{sponsor_id}",
    summary="Quitar un patrocinador de un evento",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[require_permission(Permission.SPONSORS_WRITE)],
)
async def delete_sponsor(
    evento: Annotated[Event, Depends(_obtener_evento_o_404)],
    session: DbDep,
    background_tasks: BackgroundTasks,
    sponsor_id: str,
) -> None:
    clave_logo = await service.delete_sponsor(
        session,
        organization_id=evento.organization_id,
        event_id=evento.id,
        sponsor_id=uuid.UUID(sponsor_id),
    )
    # Igual que `events/router.py:upload_cover`: el borrado del objeto se difiere
    # a después de que la respuesta salga (y por tanto tras el commit real de la
    # transacción), para no dejar la fila borrada con un objeto huérfano si el
    # commit fallara antes de llegar aquí.
    if clave_logo:
        background_tasks.add_task(get_storage().delete_object, clave_logo)


@router_sponsors.put(
    "/{sponsor_id}/logo",
    summary="Subir el logotipo de un patrocinador",
    description="Acepta PNG, JPEG o WebP de hasta 5 MB. El tipo se comprueba por contenido.",
    response_model=SponsorResponse,
    dependencies=[require_permission(Permission.SPONSORS_WRITE)],
)
async def upload_sponsor_logo(
    evento: Annotated[Event, Depends(_obtener_evento_o_404)],
    session: DbDep,
    background_tasks: BackgroundTasks,
    sponsor_id: str,
    fichero: Annotated[UploadFile, File(description="Logotipo del patrocinador")],
) -> SponsorResponse:
    patrocinador = await repository.get_sponsor(
        session, evento.organization_id, evento.id, uuid.UUID(sponsor_id)
    )
    if patrocinador is None:
        raise NotFoundError("Ese patrocinador no existe.")

    contenido = await fichero.read()
    mime, extension = validate_upload(contenido)

    almacen = get_storage()
    clave = build_object_key(
        evento.organization_id, f"sponsors/{evento.id}/{patrocinador.id}", extension
    )
    await almacen.put_object(clave, contenido, mime)

    anterior = patrocinador.logo_object_key
    patrocinador.logo_object_key = clave
    await session.flush()

    if anterior and anterior != clave:
        background_tasks.add_task(almacen.delete_object, anterior)

    return _sponsor_response(patrocinador)
