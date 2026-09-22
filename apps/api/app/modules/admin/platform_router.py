"""Endpoints de superadministración de la identidad de la plataforma.

Vive aparte de `admin/router.py` para no engordar ese fichero (norma del
proyecto: nada por encima de 1000 líneas), pero es parte del **mismo módulo**
`admin` a propósito: es el único autorizado a usar la sesión de mantenimiento
(`get_maintenance_db`, rol `app_maintainer` con `BYPASSRLS`), y la identidad de
la plataforma no pertenece a ninguna organización, así que ninguna sesión con
contexto RLS podría escribirla.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import registrar_auditoria
from app.core.deps import SCOPE_SESION, CurrentUser, get_maintenance_db, require_superadmin
from app.core.storage import build_platform_object_key, get_storage, validate_upload
from app.modules.media import platform_service as platform_media_service
from app.modules.media.models import PlatformMedia, PlatformMediaFolder
from app.modules.media.schemas import (
    MediaFolderResponse,
    MediaResponse,
    MediaUpdateRequest,
    PlatformMediaFolderCreate,
)
from app.modules.platform import repository as platform_repository
from app.modules.platform import service as platform_service
from app.modules.platform.models import PlatformLegalPage
from app.modules.platform.schemas import (
    PlatformBrandingResponse,
    PlatformBrandingUpdate,
    PlatformLegalPagesResponse,
    PlatformLegalPagesUpdate,
)
from app.modules.theme_templates import repository as theme_templates_repository
from app.shared.errors import ValidationDomainError
from app.shared.pagination import Page, PageParams, page_params

router = APIRouter(prefix="/admin", tags=["administración"])

MaintenanceDb = Annotated[AsyncSession, Depends(get_maintenance_db, scope=SCOPE_SESION)]
Superadmin = Annotated[CurrentUser, Depends(require_superadmin)]


def _platform_media_response(fila: PlatformMedia) -> MediaResponse:
    return MediaResponse(
        id=str(fila.id),
        kind="platform",
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


def _platform_folder_response(fila: PlatformMediaFolder) -> MediaFolderResponse:
    return MediaFolderResponse(id=str(fila.id), name=fila.name, slug=fila.slug)


#: Clave pública de página legal → campo de `PlatformLegalPagesUpdate`.
_CAMPOS_DE_PAGINA: dict[str, str] = {
    "aviso-legal": "legal_notice_content",
    "privacidad": "privacy_policy_content",
    "cookies": "cookies_policy_content",
    "condiciones-de-inscripcion": "registration_terms_content",
}


async def _branding(session: AsyncSession) -> PlatformBrandingResponse:
    return await platform_service.branding_publico(session)


@router.get(
    "/identity",
    summary="Identidad de la plataforma",
    description=(
        "Nombre, logotipo, favicon, redes y plantilla del chrome de la web de la "
        "instalación (no de una organización). El endpoint público "
        "`GET /tenant/branding` la sirve en su bloque `platform`."
    ),
    response_model=PlatformBrandingResponse,
)
async def get_platform_identity(_: Superadmin, session: MaintenanceDb) -> PlatformBrandingResponse:
    return await _branding(session)


@router.patch(
    "/identity",
    summary="Editar la identidad de la plataforma",
    description="Un campo ausente no se toca; `social_links` se reemplaza entero cuando viene.",
    response_model=PlatformBrandingResponse,
)
async def update_platform_identity(
    datos: PlatformBrandingUpdate, superadmin: Superadmin, session: MaintenanceDb
) -> PlatformBrandingResponse:
    branding = await platform_repository.get_platform_branding(session)

    if datos.name is not None:
        branding.name = datos.name.strip()

    if datos.social_links is not None:
        branding.social_links = datos.social_links

    if datos.theme_template_id is not None:
        branding.theme_template_id = await _resolver_plantilla(session, datos.theme_template_id)

    session.add(branding)
    await session.flush()

    await registrar_auditoria(
        session,
        actor_user_id=superadmin.id,
        organization_id=None,
        action="platform_identity.updated",
        entity_type="platform_branding",
        entity_id=str(branding.singleton),
        detail={"name": branding.name},
    )
    return await _branding(session)


async def _resolver_plantilla(session: AsyncSession, valor: str) -> uuid.UUID | None:
    """Valida el identificador de plantilla. Cadena vacía = volver a la de defecto."""
    if valor == "":
        return None
    try:
        plantilla_id = uuid.UUID(valor)
    except ValueError as exc:
        raise ValidationDomainError(
            f"«{valor}» no es un identificador de plantilla válido."
        ) from exc
    if await theme_templates_repository.get_theme_template(session, plantilla_id) is None:
        raise ValidationDomainError("La plantilla de tema no existe.")
    return plantilla_id


async def _subir_imagen_de_marca(
    request: Request,
    session: AsyncSession,
    *,
    actor_user_id: uuid.UUID,
    fichero: UploadFile | None,
    campo_object_key: str,
    campo_media_id: str,
    kind: str,
    action: str,
) -> PlatformBrandingResponse:
    """Sube (o asigna desde la biblioteca) el logo o el favicon de plataforma.

    Multipart: sube una imagen nueva, validada por bytes reales
    (`validate_upload`), con clave construida en el servidor. JSON
    `{media_id}`: asigna una imagen ya subida a `platform_media`. Regla de
    reemplazo igual que en organización — si la imagen anterior ya estaba
    gestionada por la biblioteca (`*_media_id` no nulo), su ciclo de vida ya
    no es cosa de este endpoint.
    """
    branding = await platform_repository.get_platform_branding(session)
    anterior_media_id: uuid.UUID | None = getattr(branding, campo_media_id)
    anterior_object_key: str | None = getattr(branding, campo_object_key)
    almacen = get_storage()

    if request.headers.get("content-type", "").startswith("application/json"):
        cuerpo = await request.json()
        media_id = cuerpo.get("media_id")
        if not media_id:
            raise ValidationDomainError("Falta «media_id».")
        media = await platform_media_service.obtener_visible(session, media_id=uuid.UUID(media_id))
        setattr(branding, campo_media_id, media.id)
        setattr(branding, campo_object_key, None)
    else:
        if fichero is None:
            raise ValidationDomainError("Falta el fichero.")
        contenido = await fichero.read()
        mime, extension = validate_upload(contenido)
        clave = build_platform_object_key(kind, extension)
        await almacen.put_object(clave, contenido, mime)
        setattr(branding, campo_media_id, None)
        setattr(branding, campo_object_key, clave)

    session.add(branding)
    await session.flush()

    if (
        anterior_media_id is None
        and anterior_object_key
        and anterior_object_key != getattr(branding, campo_object_key)
    ):
        await almacen.delete_object(anterior_object_key)

    await registrar_auditoria(
        session,
        actor_user_id=actor_user_id,
        organization_id=None,
        action=action,
        entity_type="platform_branding",
        entity_id=str(branding.singleton),
        detail=None,
    )
    return await _branding(session)


@router.put(
    "/identity/logo",
    summary="Subir o asignar el logotipo de la plataforma",
    description=(
        "Multipart (`fichero`): sube una imagen nueva, PNG/JPEG/WebP de hasta "
        "5 MB. JSON (`{media_id}`): asigna una imagen ya subida a la "
        "biblioteca de plataforma."
    ),
    response_model=PlatformBrandingResponse,
)
async def upload_platform_logo(
    request: Request,
    superadmin: Superadmin,
    session: MaintenanceDb,
    fichero: Annotated[UploadFile | None, File(description="Imagen del logotipo")] = None,
) -> PlatformBrandingResponse:
    return await _subir_imagen_de_marca(
        request,
        session,
        actor_user_id=superadmin.id,
        fichero=fichero,
        campo_object_key="logo_object_key",
        campo_media_id="logo_media_id",
        kind="branding/logo",
        action="platform_identity.logo_updated",
    )


@router.put(
    "/identity/favicon",
    summary="Subir o asignar el favicon de la plataforma",
    description="Mismas reglas que el logotipo.",
    response_model=PlatformBrandingResponse,
)
async def upload_platform_favicon(
    request: Request,
    superadmin: Superadmin,
    session: MaintenanceDb,
    fichero: Annotated[UploadFile | None, File(description="Imagen del favicon")] = None,
) -> PlatformBrandingResponse:
    return await _subir_imagen_de_marca(
        request,
        session,
        actor_user_id=superadmin.id,
        fichero=fichero,
        campo_object_key="favicon_object_key",
        campo_media_id="favicon_media_id",
        kind="branding/favicon",
        action="platform_identity.favicon_updated",
    )


@router.post(
    "/platform/media",
    summary="Subir una imagen a la biblioteca de plataforma",
    description=(
        "Multipart (`fichero`): sube una imagen nueva. JSON (`{url}`): la "
        "descarga y reprocesa en el servidor — mismo dispatch manual que "
        "`POST /organizations/me/media` (Fase 2)."
    ),
    response_model=MediaResponse,
)
async def upload_platform_media(
    request: Request,
    superadmin: Superadmin,
    session: MaintenanceDb,
    fichero: Annotated[UploadFile | None, File(description="Imagen")] = None,
) -> MediaResponse:
    if request.headers.get("content-type", "").startswith("application/json"):
        cuerpo = await request.json()
        url = cuerpo.get("url")
        if not url:
            raise ValidationDomainError("Falta «url».")
        fila = await platform_media_service.subir_desde_url(
            session, uploaded_by_user_id=superadmin.id, url=url
        )
        return _platform_media_response(fila)

    if fichero is None:
        raise ValidationDomainError("Falta el fichero.")
    contenido = await fichero.read()
    fila = await platform_media_service.subir_desde_fichero(
        session,
        uploaded_by_user_id=superadmin.id,
        contenido=contenido,
        filename=fichero.filename or "imagen",
    )
    return _platform_media_response(fila)


@router.get(
    "/platform/media",
    summary="Listar la biblioteca de plataforma",
    response_model=Page[MediaResponse],
)
async def list_platform_media(
    superadmin: Superadmin,
    session: MaintenanceDb,
    pagina: Annotated[PageParams, Depends(page_params)],
    search: str | None = Query(default=None),
    folder_id: str | None = Query(default=None),
) -> Page[MediaResponse]:
    filas, total = await platform_media_service.listar(
        session,
        search=search,
        folder_id=uuid.UUID(folder_id) if folder_id else None,
        limit=pagina.limit,
        offset=pagina.offset,
    )
    return Page(
        items=[_platform_media_response(f) for f in filas],
        total=total,
        limit=pagina.limit,
        offset=pagina.offset,
    )


@router.delete("/platform/media/{media_id}", summary="Enviar a la papelera", status_code=204)
async def delete_platform_media(
    media_id: str, superadmin: Superadmin, session: MaintenanceDb
) -> None:
    await platform_media_service.borrar(session, media_id=uuid.UUID(media_id))


@router.post(
    "/platform/media/{media_id}/restore",
    summary="Restaurar de la papelera",
    response_model=MediaResponse,
)
async def restore_platform_media(
    media_id: str, superadmin: Superadmin, session: MaintenanceDb
) -> MediaResponse:
    fila = await platform_media_service.restaurar(session, media_id=uuid.UUID(media_id))
    return _platform_media_response(fila)


@router.patch(
    "/platform/media/{media_id}", summary="Editar nombre/alt/carpeta", response_model=MediaResponse
)
async def update_platform_media(
    media_id: str, cuerpo: MediaUpdateRequest, superadmin: Superadmin, session: MaintenanceDb
) -> MediaResponse:
    campos_enviados = cuerpo.model_fields_set
    fila = await platform_media_service.actualizar_metadatos(
        session,
        media_id=uuid.UUID(media_id),
        alt=cuerpo.alt,
        folder_id=uuid.UUID(cuerpo.folder_id) if cuerpo.folder_id else None,
        filename=cuerpo.filename,
        alt_incluido="alt" in campos_enviados,
        folder_id_incluido="folder_id" in campos_enviados,
        filename_incluido="filename" in campos_enviados,
    )
    return _platform_media_response(fila)


@router.put(
    "/platform/media/{media_id}/contenido",
    summary="Sobrescribir los píxeles de una imagen ya existente",
    response_model=MediaResponse,
)
async def overwrite_platform_media_content(
    media_id: str,
    superadmin: Superadmin,
    session: MaintenanceDb,
    fichero: Annotated[UploadFile, File(description="Imagen")],
) -> MediaResponse:
    contenido = await fichero.read()
    fila = await platform_media_service.sobrescribir_contenido(
        session, media_id=uuid.UUID(media_id), contenido=contenido
    )
    return _platform_media_response(fila)


@router.post(
    "/platform/media-folders", summary="Crear una carpeta", response_model=MediaFolderResponse
)
async def create_platform_media_folder(
    cuerpo: PlatformMediaFolderCreate, superadmin: Superadmin, session: MaintenanceDb
) -> MediaFolderResponse:
    carpeta = await platform_media_service.crear_carpeta(
        session, name=cuerpo.name, slug=cuerpo.slug
    )
    return _platform_folder_response(carpeta)


@router.get(
    "/platform/media-folders",
    summary="Listar carpetas",
    response_model=list[MediaFolderResponse],
)
async def list_platform_media_folders(
    superadmin: Superadmin, session: MaintenanceDb
) -> list[MediaFolderResponse]:
    carpetas = await platform_media_service.listar_carpetas(session)
    return [_platform_folder_response(c) for c in carpetas]


@router.get(
    "/legal-pages",
    summary="Páginas legales de la plataforma",
    response_model=PlatformLegalPagesResponse,
)
async def get_platform_legal_pages(
    _: Superadmin, session: MaintenanceDb
) -> PlatformLegalPagesResponse:
    return await platform_service.legal_pages_publicas(session)


@router.patch(
    "/legal-pages",
    summary="Editar las páginas legales de la plataforma",
    description=(
        "Un campo ausente no se toca; un campo presente con `null` restaura la "
        "plantilla por defecto de esa página."
    ),
    response_model=PlatformLegalPagesResponse,
)
async def update_platform_legal_pages(
    datos: PlatformLegalPagesUpdate, superadmin: Superadmin, session: MaintenanceDb
) -> PlatformLegalPagesResponse:
    cambios = datos.model_dump(exclude_unset=True)

    for clave, campo in _CAMPOS_DE_PAGINA.items():
        if campo not in cambios:
            continue
        valor = cambios[campo]
        limpio = valor.strip() if isinstance(valor, str) else None

        fila = await platform_repository.get_platform_legal_page(session, clave)
        if fila is None:
            # Sin fila y sin contenido: ya estaba en plantilla, no hay nada que
            # restaurar ni que crear (una fila vacía sería lo mismo con ruido).
            if limpio:
                session.add(PlatformLegalPage(kind=clave, content=limpio))
        else:
            fila.content = limpio or None

    await session.flush()

    await registrar_auditoria(
        session,
        actor_user_id=superadmin.id,
        organization_id=None,
        action="platform_legal_pages.updated",
        entity_type="platform_legal_page",
        entity_id=None,
        detail={"campos": sorted(cambios)},
    )
    return await platform_service.legal_pages_publicas(session)
