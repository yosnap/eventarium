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

from fastapi import APIRouter, Body, Depends, File, UploadFile
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import registrar_auditoria
from app.core.deps import CurrentUser, get_maintenance_db, require_superadmin
from app.core.storage import build_platform_object_key, get_storage, validate_upload
from app.core.tenant import normalize_host
from app.modules.platform import repository as platform_repository
from app.modules.platform import service as platform_service
from app.modules.platform.models import PlatformDomain, PlatformLegalPage
from app.modules.platform.schemas import (
    PlatformBrandingResponse,
    PlatformBrandingUpdate,
    PlatformDomainOut,
    PlatformDomainsUpdate,
    PlatformLegalPagesResponse,
    PlatformLegalPagesUpdate,
)
from app.modules.theme_templates import repository as theme_templates_repository
from app.shared.errors import ValidationDomainError

router = APIRouter(prefix="/admin", tags=["administración"])

MaintenanceDb = Annotated[AsyncSession, Depends(get_maintenance_db)]
Superadmin = Annotated[CurrentUser, Depends(require_superadmin)]

#: Clave pública de página legal → campo de `PlatformLegalPagesUpdate`.
_CAMPOS_DE_PAGINA: dict[str, str] = {
    "aviso-legal": "legal_notice_content",
    "privacidad": "privacy_policy_content",
    "cookies": "cookies_policy_content",
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
    session: AsyncSession,
    *,
    actor_user_id: uuid.UUID,
    fichero: UploadFile,
    campo: str,
    kind: str,
    action: str,
) -> PlatformBrandingResponse:
    """Sube logo o favicon de plataforma y actualiza la identidad.

    Mismo contrato que la subida de marca de una organización: se valida por
    bytes reales (`validate_upload`), se guarda con clave construida en el
    servidor y se borra la anterior para no dejar objetos huérfanos.
    """
    contenido = await fichero.read()
    mime, extension = validate_upload(contenido)

    almacen = get_storage()
    clave = build_platform_object_key(kind, extension)
    await almacen.put_object(clave, contenido, mime)

    branding = await platform_repository.get_platform_branding(session)
    anterior: str | None = getattr(branding, campo)
    setattr(branding, campo, clave)
    session.add(branding)
    await session.flush()

    if anterior and anterior != clave:
        await almacen.delete_object(anterior)

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
    summary="Subir el logotipo de la plataforma",
    description="Acepta PNG, JPEG o WebP de hasta 5 MB. El tipo se comprueba por contenido.",
    response_model=PlatformBrandingResponse,
)
async def upload_platform_logo(
    superadmin: Superadmin,
    session: MaintenanceDb,
    fichero: Annotated[UploadFile, File(description="Imagen del logotipo")],
) -> PlatformBrandingResponse:
    return await _subir_imagen_de_marca(
        session,
        actor_user_id=superadmin.id,
        fichero=fichero,
        campo="logo_object_key",
        kind="branding/logo",
        action="platform_identity.logo_updated",
    )


@router.put(
    "/identity/favicon",
    summary="Subir el favicon de la plataforma",
    description="Mismas reglas que el logotipo.",
    response_model=PlatformBrandingResponse,
)
async def upload_platform_favicon(
    superadmin: Superadmin,
    session: MaintenanceDb,
    fichero: Annotated[UploadFile, File(description="Imagen del favicon")],
) -> PlatformBrandingResponse:
    return await _subir_imagen_de_marca(
        session,
        actor_user_id=superadmin.id,
        fichero=fichero,
        campo="favicon_object_key",
        kind="branding/favicon",
        action="platform_identity.favicon_updated",
    )


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


@router.get(
    "/platform-domains",
    summary="Hosts de la web de la plataforma",
    response_model=list[PlatformDomainOut],
)
async def list_platform_domains(_: Superadmin, session: MaintenanceDb) -> list[PlatformDomainOut]:
    dominios = await platform_repository.get_platform_domains(session)
    return [PlatformDomainOut(id=str(d.id), host=d.host) for d in dominios]


@router.put(
    "/platform-domains",
    summary="Reemplazar los hosts de la web de la plataforma",
    description=(
        "Sustituye la lista completa. Un host de plataforma se comprueba antes "
        "que los de organización, así que deja de resolverse como organización."
    ),
    response_model=list[PlatformDomainOut],
)
async def replace_platform_domains(
    datos: Annotated[PlatformDomainsUpdate, Body()],
    superadmin: Superadmin,
    session: MaintenanceDb,
) -> list[PlatformDomainOut]:
    limpios = sorted({normalize_host(host) for host in datos.hosts if normalize_host(host)})

    await session.execute(delete(PlatformDomain))
    for host in limpios:
        session.add(PlatformDomain(host=host))
    await session.flush()

    await registrar_auditoria(
        session,
        actor_user_id=superadmin.id,
        organization_id=None,
        action="platform_domains.replaced",
        entity_type="platform_domain",
        entity_id=None,
        detail={"hosts": limpios},
    )

    dominios = await platform_repository.get_platform_domains(session)
    return [PlatformDomainOut(id=str(d.id), host=d.host) for d in dominios]
