"""Lógica de la biblioteca de medios: subida, asignación, listado, papelera,
recorte. Compartida entre el router de organización (RLS) y el de
plataforma (sesión de mantenimiento) — solo cambia qué modelo/sesión se
pasa, la lógica de negocio es la misma.
"""

from __future__ import annotations

import io
import uuid
from datetime import UTC, datetime
from typing import Literal

import httpx
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import Permission
from app.core.storage import build_object_key, get_storage, validate_upload
from app.modules.events.models import Event
from app.modules.media.models import Media, MediaFolder
from app.modules.media.processing import MEDIA_LIBRARY_IMAGE_MIMES, procesar_imagen
from app.modules.media.ssrf import validar_url_publica_segura
from app.modules.organizations.models import OrganizationBranding
from app.modules.sponsors.models import Sponsor
from app.shared.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationDomainError,
)

#: Catálogo cerrado, fijo en código — no en BD (ver `Media.kind`). Claves en
#: `str` plano, no `Literal`: el valor viene siempre de una petición HTTP o
#: de una fila ya persistida, nunca de un literal en el propio código, así
#: que un `Literal` solo complicaría las firmas sin aportar seguridad real.
KIND_A_PERMISO: dict[str, Permission] = {
    "branding": Permission.BRANDING_WRITE,
    "events": Permission.EVENTS_WRITE,
    "sponsors": Permission.SPONSORS_WRITE,
}

#: Perfil de procesado por `kind` (ver `processing._PERFILES`): `branding` y
#: `sponsors` son logotipos (pequeños, 800×800 basta); `events` es una
#: portada (más grande, se queda en el máximo genérico). Nadie más define
#: `perfil` — antes de esto, todas las subidas de la biblioteca usaban el
#: valor por defecto de la firma (`"default"`), así que un logo ocupaba y
#: pesaba como una portada.
KIND_A_PERFIL: dict[str, Literal["logo", "default"]] = {
    "branding": "logo",
    "events": "default",
    "sponsors": "logo",
}

_TAMANO_MAXIMO_DESCARGA_URL = 5 * 1024 * 1024
_TIMEOUT_DESCARGA_URL = 10.0


def _requerir_permiso_del_kind(kind: str, permisos: set[Permission]) -> Permission:
    permiso = KIND_A_PERMISO.get(kind)
    if permiso is None:
        raise ValidationDomainError(f"Tipo de medio no admitido: {kind}.")
    if permiso not in permisos:
        raise PermissionDeniedError(
            "No tienes permiso para esta operación.", extra={"required": permiso.value}
        )
    return permiso


def _requerir_propiedad_o_permiso(
    fila: Media, *, user_id: uuid.UUID, permisos: set[Permission]
) -> None:
    """Quien sube un medio, o quien tiene el permiso de escritura de SU
    `kind`, puede gestionarlo (borrar/restaurar/recortar/editar metadatos).

    Antes solo `borrar()` comprobaba esto — `restaurar()`, `recortar()` y
    `actualizar_metadatos()` no comprobaban ni permiso ni propiedad, así que
    cualquier miembro autenticado de la organización (sin importar su rol)
    podía sacar de la papelera, recortar o editar el `alt`/carpeta de
    CUALQUIER medio ajeno — incluido uno de un `kind` que ni siquiera podría
    listar (hallazgo de code-review)."""
    permiso = KIND_A_PERMISO.get(fila.kind)
    puede_gestionar = fila.uploaded_by_user_id == user_id or (
        permiso is not None and permiso in permisos
    )
    if not puede_gestionar:
        raise PermissionDeniedError("No tienes permiso para gestionar este medio.")


async def _crear_fila(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    kind: str,
    uploaded_by_user_id: uuid.UUID,
    folder_id: uuid.UUID | None,
    contenido: bytes,
    mime: str,
    filename: str,
    perfil: Literal["logo", "default"],
) -> Media:
    procesada = procesar_imagen(contenido, mime, perfil)
    extension = MEDIA_LIBRARY_IMAGE_MIMES[procesada.mime_type]
    clave = build_object_key(organization_id, f"media/{kind}", extension)
    await get_storage().put_object(clave, procesada.contenido, procesada.mime_type)

    fila = Media(
        organization_id=organization_id,
        kind=kind,
        uploaded_by_user_id=uploaded_by_user_id,
        folder_id=folder_id,
        object_key=clave,
        filename=filename,
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
    organization_id: uuid.UUID,
    kind: str,
    uploaded_by_user_id: uuid.UUID,
    permisos: set[Permission],
    contenido: bytes,
    filename: str,
    folder_id: uuid.UUID | None = None,
) -> Media:
    _requerir_permiso_del_kind(kind, permisos)
    mime, _extension = validate_upload(contenido, allowed_mimes=MEDIA_LIBRARY_IMAGE_MIMES)
    return await _crear_fila(
        session,
        organization_id=organization_id,
        kind=kind,
        uploaded_by_user_id=uploaded_by_user_id,
        folder_id=folder_id,
        contenido=contenido,
        mime=mime,
        filename=filename,
        perfil=KIND_A_PERFIL.get(kind, "default"),
    )


async def subir_desde_url(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    kind: str,
    uploaded_by_user_id: uuid.UUID,
    permisos: set[Permission],
    url: str,
    folder_id: uuid.UUID | None = None,
) -> Media:
    """Descarga la URL en el servidor y la trata como cualquier subida —
    nunca se guarda la URL externa tal cual."""
    _requerir_permiso_del_kind(kind, permisos)
    url_segura = validar_url_publica_segura(url)

    async with httpx.AsyncClient(follow_redirects=False, timeout=_TIMEOUT_DESCARGA_URL) as cliente:
        try:
            respuesta = await cliente.get(url_segura)
        except httpx.HTTPError as error:
            raise ValidationDomainError("No se ha podido descargar la URL.") from error

    if respuesta.status_code >= 300:
        # Incluye 3xx: sin seguir redirecciones, cualquier salto se rechaza
        # sin más (hallazgo de red-team — nunca revalidar un host "final").
        raise ValidationDomainError("La URL no se ha podido descargar (redirección o error).")

    contenido = respuesta.content
    if len(contenido) > _TAMANO_MAXIMO_DESCARGA_URL:
        raise ValidationDomainError("El fichero descargado supera el tamaño máximo permitido.")

    filename = url_segura.rsplit("/", 1)[-1].split("?", 1)[0] or "imagen"
    mime, _extension = validate_upload(contenido, allowed_mimes=MEDIA_LIBRARY_IMAGE_MIMES)
    return await _crear_fila(
        session,
        organization_id=organization_id,
        kind=kind,
        uploaded_by_user_id=uploaded_by_user_id,
        folder_id=folder_id,
        contenido=contenido,
        mime=mime,
        filename=filename,
        perfil=KIND_A_PERFIL.get(kind, "default"),
    )


async def obtener_visible(
    session: AsyncSession,
    *,
    media_id: uuid.UUID,
    organization_id: uuid.UUID,
    kind: str | None,
    user_id: uuid.UUID,
    permisos: set[Permission],
) -> Media:
    """Resuelve un medio para asignarlo a un campo: debe existir, no estar
    en la papelera, ser del `kind` esperado (si se indica), y ser visible
    para quien lo pide (lo subió, o tiene el permiso de escritura de ese
    `kind`) — RLS ya garantiza que es de la organización activa."""
    fila = await session.get(Media, media_id)
    if fila is None or fila.deleted_at is not None or fila.organization_id != organization_id:
        raise NotFoundError("Ese medio no existe.")
    if kind is not None and fila.kind != kind:
        raise ValidationDomainError(f"Ese medio no es de tipo «{kind}».")
    permiso_del_kind = KIND_A_PERMISO.get(fila.kind)
    puede_ver = fila.uploaded_by_user_id == user_id or (
        permiso_del_kind is not None and permiso_del_kind in permisos
    )
    if not puede_ver:
        raise NotFoundError("Ese medio no existe.")
    return fila


async def listar(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    kind: str,
    user_id: uuid.UUID,
    permisos: set[Permission],
    search: str | None,
    folder_id: uuid.UUID | None,
    limit: int,
    offset: int,
) -> tuple[list[Media], int]:
    permiso_del_kind = KIND_A_PERMISO.get(kind)
    if permiso_del_kind is None:
        raise ValidationDomainError(f"Tipo de medio no admitido: {kind}.")
    ve_toda_la_organizacion = permiso_del_kind in permisos
    condiciones = [
        Media.organization_id == organization_id,
        Media.kind == kind,
        Media.deleted_at.is_(None),
    ]
    if not ve_toda_la_organizacion:
        condiciones.append(Media.uploaded_by_user_id == user_id)
    if folder_id is not None:
        condiciones.append(Media.folder_id == folder_id)
    if search:
        condiciones.append(Media.filename.ilike(f"%{search}%"))

    base = select(Media).where(*condiciones)
    total = (await session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    filas = (
        (await session.execute(base.order_by(Media.created_at.desc()).limit(limit).offset(offset)))
        .scalars()
        .all()
    )
    return list(filas), total


async def _referencias_activas(session: AsyncSession, media_id: uuid.UUID) -> list[dict[str, str]]:
    """Comprueba las 3 columnas de dominio que pueden apuntar a este medio —
    reutilizada tanto por `borrar` como por la regla de reemplazo de cada
    endpoint consumidor (hallazgo de red-team: hay que mirar las 3, no solo
    el campo que se está tocando)."""
    referencias: list[dict[str, str]] = []

    branding = (
        await session.execute(
            select(OrganizationBranding).where(OrganizationBranding.logo_media_id == media_id)
        )
    ).scalar_one_or_none()
    if branding is not None:
        referencias.append({"tipo": "branding", "id": str(branding.organization_id)})

    # Eventos y patrocinadores, a diferencia de `OrganizationBranding` (una
    # fila por organización), pueden ser varios reutilizando el MISMO
    # `media_id` — justo el caso de uso de una biblioteca "reutilizable".
    # `scalar_one_or_none()` lanzaría `MultipleResultsFound` con dos
    # coincidencias (500 en vez de 409, hallazgo de code-review): hace falta
    # `.scalars().all()` y listar todas, no solo la primera.
    eventos = (
        (await session.execute(select(Event).where(Event.cover_media_id == media_id)))
        .scalars()
        .all()
    )
    for evento in eventos:
        referencias.append({"tipo": "evento", "id": str(evento.id), "nombre": evento.title})

    patrocinadores = (
        (await session.execute(select(Sponsor).where(Sponsor.logo_media_id == media_id)))
        .scalars()
        .all()
    )
    for patrocinador in patrocinadores:
        referencias.append(
            {"tipo": "patrocinador", "id": str(patrocinador.id), "nombre": patrocinador.name}
        )

    return referencias


async def borrar(
    session: AsyncSession,
    *,
    media_id: uuid.UUID,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    permisos: set[Permission],
) -> None:
    fila = await session.get(Media, media_id)
    if fila is None or fila.organization_id != organization_id or fila.deleted_at is not None:
        raise NotFoundError("Ese medio no existe.")
    _requerir_propiedad_o_permiso(fila, user_id=user_id, permisos=permisos)

    referencias = await _referencias_activas(session, media_id)
    if referencias:
        raise ConflictError(
            "Este medio está en uso y no se puede borrar.", extra={"used_by": referencias}
        )

    fila.deleted_at = datetime.now(UTC)
    await session.flush()


async def restaurar(
    session: AsyncSession,
    *,
    media_id: uuid.UUID,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    permisos: set[Permission],
) -> Media:
    fila = await session.get(Media, media_id)
    if fila is None or fila.organization_id != organization_id:
        raise NotFoundError("Ese medio no existe.")
    _requerir_propiedad_o_permiso(fila, user_id=user_id, permisos=permisos)
    fila.deleted_at = None
    await session.flush()
    return fila


async def recortar(
    session: AsyncSession,
    *,
    media_id: uuid.UUID,
    organization_id: uuid.UUID,
    uploaded_by_user_id: uuid.UUID,
    permisos: set[Permission],
    x: float,
    y: float,
    width: float,
    height: float,
) -> Media:
    """Crea una fila NUEVA con clave nueva — nunca muta el objeto existente
    (hallazgo de red-team: la caché pública es `immutable`, y dos personas
    recortando el mismo ítem compartido se pisarían sin esto)."""
    original = await session.get(Media, media_id)
    if (
        original is None
        or original.organization_id != organization_id
        or original.deleted_at is not None
    ):
        raise NotFoundError("Ese medio no existe.")
    _requerir_propiedad_o_permiso(original, user_id=uploaded_by_user_id, permisos=permisos)

    contenido, _mime = await get_storage().get_object(original.object_key)
    with Image.open(io.BytesIO(contenido)) as imagen:
        ancho, alto = imagen.size
        caja = (
            int(x * ancho),
            int(y * alto),
            int((x + width) * ancho),
            int((y + height) * alto),
        )
        recortada = imagen.convert("RGB").crop(caja)
        salida = io.BytesIO()
        recortada.save(salida, format="WEBP", quality=85)
        contenido_final = salida.getvalue()
        ancho_final, alto_final = recortada.size

    clave = build_object_key(organization_id, f"media/{original.kind}", "webp")
    await get_storage().put_object(clave, contenido_final, "image/webp")

    nueva = Media(
        organization_id=organization_id,
        kind=original.kind,
        uploaded_by_user_id=uploaded_by_user_id,
        folder_id=original.folder_id,
        object_key=clave,
        filename=original.filename,
        mime_type="image/webp",
        size=len(contenido_final),
        width=ancho_final,
        height=alto_final,
    )
    session.add(nueva)
    await session.flush()
    return nueva


async def actualizar_metadatos(
    session: AsyncSession,
    *,
    media_id: uuid.UUID,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    permisos: set[Permission],
    alt: str | None,
    folder_id: uuid.UUID | None,
    alt_incluido: bool,
    folder_id_incluido: bool,
) -> Media:
    """`alt_incluido`/`folder_id_incluido` distinguen "no venía en la
    petición" de "venía como `null`" — es un PATCH, no un PUT: enviar solo
    `folder_id` no debe borrar el `alt` ya guardado (hallazgo de
    code-review; antes se asignaban los dos incondicionalmente)."""
    fila = await session.get(Media, media_id)
    if fila is None or fila.organization_id != organization_id:
        raise NotFoundError("Ese medio no existe.")
    _requerir_propiedad_o_permiso(fila, user_id=user_id, permisos=permisos)
    if alt_incluido:
        fila.alt = alt
    if folder_id_incluido:
        fila.folder_id = folder_id
    await session.flush()
    return fila


async def crear_carpeta(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    name: str,
    slug: str,
    kind: str,
    permisos: set[Permission],
) -> MediaFolder:
    _requerir_permiso_del_kind(kind, permisos)
    carpeta = MediaFolder(organization_id=organization_id, name=name, slug=slug)
    session.add(carpeta)
    await session.flush()
    return carpeta


async def listar_carpetas(
    session: AsyncSession, *, organization_id: uuid.UUID
) -> list[MediaFolder]:
    filas = (
        (
            await session.execute(
                select(MediaFolder).where(MediaFolder.organization_id == organization_id)
            )
        )
        .scalars()
        .all()
    )
    return list(filas)
