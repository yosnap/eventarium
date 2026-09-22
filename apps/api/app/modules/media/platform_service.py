"""Lógica de la biblioteca de medios de plataforma — mismas operaciones que
`service.py`, pero sin `kind`/`organization_id`/`permisos`: un único contexto
(la identidad de la instalación), gestionado por `app/modules/admin` con la
sesión de mantenimiento. El gateo de acceso (superadmin) ya lo hace la
dependencia `require_superadmin` en el router; este módulo no repite ese
control.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal

import httpx
from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.storage import build_platform_object_key, get_storage, validate_upload
from app.modules.media.models import PlatformMedia, PlatformMediaFolder
from app.modules.media.processing import MEDIA_LIBRARY_IMAGE_MIMES, procesar_imagen
from app.modules.media.ssrf import validar_url_publica_segura
from app.modules.platform.models import PlatformBranding
from app.shared.errors import ConflictError, NotFoundError, ValidationDomainError

_TAMANO_MAXIMO_DESCARGA_URL = 5 * 1024 * 1024
_TIMEOUT_DESCARGA_URL = 10.0


async def _crear_fila(
    session: AsyncSession,
    *,
    uploaded_by_user_id: uuid.UUID,
    folder_id: uuid.UUID | None,
    contenido: bytes,
    mime: str,
    filename: str,
    perfil: Literal["logo", "default"],
) -> PlatformMedia:
    procesada = procesar_imagen(contenido, mime, perfil)
    extension = MEDIA_LIBRARY_IMAGE_MIMES[procesada.mime_type]
    clave = build_platform_object_key("media", extension)
    await get_storage().put_object(clave, procesada.contenido, procesada.mime_type)

    fila = PlatformMedia(
        uploaded_by_user_id=uploaded_by_user_id,
        folder_id=folder_id,
        object_key=clave,
        # Ver el mismo comentario en `service._crear_fila`: `filename` es
        # `String(255)`, y sin recortarlo aquí un nombre importado por URL
        # demasiado largo revienta el INSERT con un 500 tras haber subido
        # ya el objeto al almacenamiento.
        filename=filename[:255],
        mime_type=procesada.mime_type,
        size=len(procesada.contenido),
        width=procesada.width,
        height=procesada.height,
    )
    session.add(fila)
    await session.flush()
    return fila


async def subir_desde_fichero(
    session: AsyncSession,
    *,
    uploaded_by_user_id: uuid.UUID,
    contenido: bytes,
    filename: str,
    folder_id: uuid.UUID | None = None,
) -> PlatformMedia:
    mime, _extension = validate_upload(contenido, allowed_mimes=MEDIA_LIBRARY_IMAGE_MIMES)
    return await _crear_fila(
        session,
        uploaded_by_user_id=uploaded_by_user_id,
        folder_id=folder_id,
        contenido=contenido,
        mime=mime,
        filename=filename,
        # Único contexto: logo/favicon de la instalación — ambos son iconos
        # pequeños, igual que `KIND_A_PERFIL["branding"]` en `service.py`.
        perfil="logo",
    )


async def subir_desde_url(
    session: AsyncSession,
    *,
    uploaded_by_user_id: uuid.UUID,
    url: str,
    folder_id: uuid.UUID | None = None,
) -> PlatformMedia:
    """Descarga la URL en el servidor y la trata como cualquier subida —
    nunca se guarda la URL externa tal cual (mismo criterio que
    `service.subir_desde_url`)."""
    url_segura = validar_url_publica_segura(url)

    async with httpx.AsyncClient(follow_redirects=False, timeout=_TIMEOUT_DESCARGA_URL) as cliente:
        try:
            respuesta = await cliente.get(url_segura)
        except httpx.HTTPError as error:
            raise ValidationDomainError("No se ha podido descargar la URL.") from error

    if respuesta.status_code >= 300:
        raise ValidationDomainError("La URL no se ha podido descargar (redirección o error).")

    contenido = respuesta.content
    if len(contenido) > _TAMANO_MAXIMO_DESCARGA_URL:
        raise ValidationDomainError("El fichero descargado supera el tamaño máximo permitido.")

    filename = url_segura.rsplit("/", 1)[-1].split("?", 1)[0] or "imagen"
    mime, _extension = validate_upload(contenido, allowed_mimes=MEDIA_LIBRARY_IMAGE_MIMES)
    return await _crear_fila(
        session,
        uploaded_by_user_id=uploaded_by_user_id,
        folder_id=folder_id,
        contenido=contenido,
        mime=mime,
        filename=filename,
        perfil="logo",
    )


async def obtener_visible(session: AsyncSession, *, media_id: uuid.UUID) -> PlatformMedia:
    fila = await session.get(PlatformMedia, media_id)
    if fila is None or fila.deleted_at is not None:
        raise NotFoundError("Ese medio no existe.")
    return fila


async def listar(
    session: AsyncSession,
    *,
    search: str | None,
    folder_id: uuid.UUID | None,
    limit: int,
    offset: int,
) -> tuple[list[PlatformMedia], int]:
    condiciones: list[ColumnElement[bool]] = [PlatformMedia.deleted_at.is_(None)]
    if folder_id is not None:
        condiciones.append(PlatformMedia.folder_id == folder_id)
    if search:
        condiciones.append(PlatformMedia.filename.ilike(f"%{search}%"))

    base = select(PlatformMedia).where(*condiciones)
    total = (await session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    filas = (
        (
            await session.execute(
                base.order_by(PlatformMedia.created_at.desc()).limit(limit).offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return list(filas), total


async def _referencias_activas(session: AsyncSession, media_id: uuid.UUID) -> list[dict[str, str]]:
    """Comprueba las 2 columnas de `platform_branding` que pueden apuntar a
    este medio — mismo criterio que `service._referencias_activas` para la
    biblioteca de organización."""
    referencias: list[dict[str, str]] = []
    branding = (
        await session.execute(
            select(PlatformBranding).where(
                (PlatformBranding.logo_media_id == media_id)
                | (PlatformBranding.favicon_media_id == media_id)
            )
        )
    ).scalar_one_or_none()
    if branding is not None:
        campo = "logo" if branding.logo_media_id == media_id else "favicon"
        referencias.append(
            {"tipo": f"identidad_de_plataforma_{campo}", "id": str(branding.singleton)}
        )
    return referencias


async def borrar(session: AsyncSession, *, media_id: uuid.UUID) -> None:
    fila = await session.get(PlatformMedia, media_id)
    if fila is None or fila.deleted_at is not None:
        raise NotFoundError("Ese medio no existe.")

    referencias = await _referencias_activas(session, media_id)
    if referencias:
        raise ConflictError(
            "Este medio está en uso y no se puede borrar.", extra={"used_by": referencias}
        )

    fila.deleted_at = datetime.now(UTC)
    await session.flush()


async def restaurar(session: AsyncSession, *, media_id: uuid.UUID) -> PlatformMedia:
    fila = await session.get(PlatformMedia, media_id)
    if fila is None:
        raise NotFoundError("Ese medio no existe.")
    fila.deleted_at = None
    await session.flush()
    return fila


async def actualizar_metadatos(
    session: AsyncSession,
    *,
    media_id: uuid.UUID,
    alt: str | None,
    folder_id: uuid.UUID | None,
    filename: str | None,
    alt_incluido: bool,
    folder_id_incluido: bool,
    filename_incluido: bool,
) -> PlatformMedia:
    """`alt_incluido`/`folder_id_incluido`/`filename_incluido`: ver el
    mismo parámetro en `service.actualizar_metadatos` — es un PATCH, no
    debe borrar el campo que no venía en la petición."""
    fila = await session.get(PlatformMedia, media_id)
    if fila is None:
        raise NotFoundError("Ese medio no existe.")
    if alt_incluido:
        fila.alt = alt
    if folder_id_incluido:
        fila.folder_id = folder_id
    if filename_incluido:
        nombre = (filename or "").strip()
        if not nombre:
            raise ValidationDomainError("El nombre no puede estar vacío.")
        fila.filename = nombre
    await session.flush()
    return fila


async def sobrescribir_contenido(
    session: AsyncSession, *, media_id: uuid.UUID, contenido: bytes
) -> PlatformMedia:
    """Ver `service.sobrescribir_contenido` — mismo criterio (MISMA
    `object_key`, la URL no cambia), sin `organization_id`/permisos porque
    el gateo de acceso (superadmin) ya lo hace `require_superadmin`."""
    fila = await session.get(PlatformMedia, media_id)
    if fila is None or fila.deleted_at is not None:
        raise NotFoundError("Ese medio no existe.")

    mime, _extension = validate_upload(contenido, allowed_mimes=MEDIA_LIBRARY_IMAGE_MIMES)
    procesada = procesar_imagen(contenido, mime, "logo")
    await get_storage().put_object(fila.object_key, procesada.contenido, procesada.mime_type)

    fila.mime_type = procesada.mime_type
    fila.size = len(procesada.contenido)
    fila.width = procesada.width
    fila.height = procesada.height
    # Ver el mismo comentario en `service.sobrescribir_contenido`: `onupdate`
    # no se dispara si las 4 columnas de arriba no cambian de valor de
    # verdad, y sin `updated_at` fresco la URL versionada queda idéntica.
    fila.updated_at = datetime.now(UTC)
    await session.flush()
    return fila


async def crear_carpeta(session: AsyncSession, *, name: str, slug: str) -> PlatformMediaFolder:
    carpeta = PlatformMediaFolder(name=name, slug=slug)
    session.add(carpeta)
    await session.flush()
    return carpeta


async def listar_carpetas(session: AsyncSession) -> list[PlatformMediaFolder]:
    filas = (await session.execute(select(PlatformMediaFolder))).scalars().all()
    return list(filas)
