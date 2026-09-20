"""Endpoints de la biblioteca de medios de una organización.

`POST .../media` acepta multipart (fichero) o JSON (`{url}`) según el
`Content-Type` — dispatch manual sobre `Request`, porque FastAPI no ofrece
un decorador que declare ambos contratos sobre la misma ruta.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile

from app.core.deps import CurrentUserDep, DbDep, PermissionsDep
from app.core.storage import get_storage
from app.modules.media import service
from app.modules.media.models import Media, MediaFolder
from app.modules.media.schemas import (
    MediaCropRequest,
    MediaFolderCreate,
    MediaFolderResponse,
    MediaResponse,
    MediaUpdateRequest,
)
from app.shared.errors import ValidationDomainError
from app.shared.pagination import Page, PageParams, page_params

router = APIRouter(prefix="/organizations/me/media", tags=["biblioteca de medios"])


def _media_response(fila: Media) -> MediaResponse:
    return MediaResponse(
        id=str(fila.id),
        kind=fila.kind,
        url=get_storage().public_url(fila.object_key),
        filename=fila.filename,
        mime_type=fila.mime_type,
        size=fila.size,
        width=fila.width,
        height=fila.height,
        alt=fila.alt,
        folder_id=str(fila.folder_id) if fila.folder_id else None,
        uploaded_by_user_id=str(fila.uploaded_by_user_id),
        created_at=fila.created_at,
    )


def _folder_response(fila: MediaFolder) -> MediaFolderResponse:
    return MediaFolderResponse(id=str(fila.id), name=fila.name, slug=fila.slug)


@router.post("", summary="Subir una imagen a la biblioteca", response_model=MediaResponse)
async def subir(
    request: Request,
    usuario: CurrentUserDep,
    session: DbDep,
    permisos: PermissionsDep,
    kind: Annotated[str | None, Form()] = None,
    fichero: Annotated[UploadFile | None, File()] = None,
) -> MediaResponse:
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("application/json"):
        cuerpo = await request.json()
        kind_json = cuerpo.get("kind")
        url = cuerpo.get("url")
        if not kind_json or not url:
            raise ValidationDomainError("Faltan «kind» o «url».")
        fila = await service.subir_desde_url(
            session,
            organization_id=usuario.organization_id,
            kind=kind_json,
            uploaded_by_user_id=usuario.id,
            permisos=permisos,
            url=url,
        )
    else:
        if not kind or fichero is None:
            raise ValidationDomainError("Faltan «kind» o el fichero.")
        contenido = await fichero.read()
        fila = await service.subir_desde_fichero(
            session,
            organization_id=usuario.organization_id,
            kind=kind,
            uploaded_by_user_id=usuario.id,
            permisos=permisos,
            contenido=contenido,
            filename=fichero.filename or "imagen",
        )
    return _media_response(fila)


@router.get("", summary="Listar la biblioteca de medios", response_model=Page[MediaResponse])
async def listar(
    usuario: CurrentUserDep,
    session: DbDep,
    permisos: PermissionsDep,
    kind: str,
    pagina: Annotated[PageParams, Depends(page_params)],
    search: str | None = Query(default=None),
    folder_id: str | None = Query(default=None),
) -> Page[MediaResponse]:
    filas, total = await service.listar(
        session,
        organization_id=usuario.organization_id,
        kind=kind,
        user_id=usuario.id,
        permisos=permisos,
        search=search,
        folder_id=uuid.UUID(folder_id) if folder_id else None,
        limit=pagina.limit,
        offset=pagina.offset,
    )
    return Page(
        items=[_media_response(f) for f in filas],
        total=total,
        limit=pagina.limit,
        offset=pagina.offset,
    )


@router.delete("/{media_id}", summary="Enviar una imagen a la papelera", status_code=204)
async def borrar(
    media_id: str, usuario: CurrentUserDep, session: DbDep, permisos: PermissionsDep
) -> None:
    await service.borrar(
        session,
        media_id=uuid.UUID(media_id),
        organization_id=usuario.organization_id,
        user_id=usuario.id,
        permisos=permisos,
    )


@router.post(
    "/{media_id}/restore", summary="Restaurar de la papelera", response_model=MediaResponse
)
async def restaurar(
    media_id: str, usuario: CurrentUserDep, session: DbDep, permisos: PermissionsDep
) -> MediaResponse:
    fila = await service.restaurar(
        session,
        media_id=uuid.UUID(media_id),
        organization_id=usuario.organization_id,
        user_id=usuario.id,
        permisos=permisos,
    )
    return _media_response(fila)


@router.patch(
    "/{media_id}/crop", summary="Recortar (crea una imagen nueva)", response_model=MediaResponse
)
async def recortar(
    media_id: str,
    cuerpo: MediaCropRequest,
    usuario: CurrentUserDep,
    session: DbDep,
    permisos: PermissionsDep,
) -> MediaResponse:
    fila = await service.recortar(
        session,
        media_id=uuid.UUID(media_id),
        organization_id=usuario.organization_id,
        uploaded_by_user_id=usuario.id,
        permisos=permisos,
        x=cuerpo.x,
        y=cuerpo.y,
        width=cuerpo.width,
        height=cuerpo.height,
    )
    return _media_response(fila)


@router.patch("/{media_id}", summary="Editar alt/carpeta", response_model=MediaResponse)
async def actualizar(
    media_id: str,
    cuerpo: MediaUpdateRequest,
    usuario: CurrentUserDep,
    session: DbDep,
    permisos: PermissionsDep,
) -> MediaResponse:
    campos_enviados = cuerpo.model_fields_set
    fila = await service.actualizar_metadatos(
        session,
        media_id=uuid.UUID(media_id),
        organization_id=usuario.organization_id,
        user_id=usuario.id,
        permisos=permisos,
        alt=cuerpo.alt,
        folder_id=uuid.UUID(cuerpo.folder_id) if cuerpo.folder_id else None,
        alt_incluido="alt" in campos_enviados,
        folder_id_incluido="folder_id" in campos_enviados,
    )
    return _media_response(fila)


folders_router = APIRouter(prefix="/organizations/me/media-folders", tags=["biblioteca de medios"])


@folders_router.post("", summary="Crear una carpeta", response_model=MediaFolderResponse)
async def crear_carpeta(
    cuerpo: MediaFolderCreate, usuario: CurrentUserDep, session: DbDep, permisos: PermissionsDep
) -> MediaFolderResponse:
    carpeta = await service.crear_carpeta(
        session,
        organization_id=usuario.organization_id,
        name=cuerpo.name,
        slug=cuerpo.slug,
        kind=cuerpo.kind,
        permisos=permisos,
    )
    return _folder_response(carpeta)


@folders_router.get("", summary="Listar carpetas", response_model=list[MediaFolderResponse])
async def listar_carpetas(usuario: CurrentUserDep, session: DbDep) -> list[MediaFolderResponse]:
    carpetas = await service.listar_carpetas(session, organization_id=usuario.organization_id)
    return [_folder_response(c) for c in carpetas]
