"""Resolución de la identidad y las páginas legales de plataforma.

Aquí vive la lógica que comparten los dos lados: el endpoint público
(`tenant/router.py`, `legal/router.py`) y los endpoints de administración
(`modules/admin`). La lectura va por el repositorio con la sesión que reciba;
la escritura la hace `modules/admin` con la sesión de mantenimiento.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.storage import get_storage
from app.modules.platform import repository
from app.modules.platform.models import PLATFORM_LEGAL_PAGE_KINDS, PlatformBranding
from app.modules.platform.schemas import (
    PlatformBrandingResponse,
    PlatformLegalPageItem,
    PlatformLegalPagesResponse,
    ThemeResolved,
)
from app.modules.platform.templates import resolve_platform_legal_page

#: Mapea la clave pública de página con el nombre del campo en el schema de
#: actualización.
_CAMPOS_DE_PAGINA: dict[str, str] = {
    "aviso-legal": "legal_notice_content",
    "privacidad": "privacy_policy_content",
    "cookies": "cookies_policy_content",
    "condiciones-de-inscripcion": "registration_terms_content",
}

#: Clave pública → nombre del atributo en `PlatformLegalPagesResponse`.
ATRIBUTO_DE_PAGINA: dict[str, str] = {
    "aviso-legal": "legal_notice",
    "privacidad": "privacy_policy",
    "cookies": "cookies_policy",
    "condiciones-de-inscripcion": "registration_terms",
}


async def branding_publico(session: AsyncSession) -> PlatformBrandingResponse:
    """Identidad de plataforma resuelta para el endpoint público.

    El logo y el favicon se sirven por la URL pública del almacén (mismo
    tratamiento que los de organización: son imágenes de marca, no datos
    sensibles). La plantilla de tema se resuelve desde `theme_templates` con la
    convención de siempre: la elegida, o la marcada `is_default`.
    """
    branding = await repository.get_platform_branding(session)
    almacen = get_storage()

    tema = await repository.get_platform_theme(session, branding.theme_template_id)

    return PlatformBrandingResponse(
        name=branding.name,
        logo_url=almacen.public_url(branding.logo_object_key) if branding.logo_object_key else None,
        favicon_url=(
            almacen.public_url(branding.favicon_object_key) if branding.favicon_object_key else None
        ),
        social_links=list(branding.social_links or []),
        theme_template_id=str(branding.theme_template_id) if branding.theme_template_id else None,
        theme=(
            ThemeResolved(id=str(tema.id), key=tema.key, name=tema.name, tokens=tema.tokens)
            if tema is not None
            else None
        ),
    )


def _sitio_de_la_instalacion() -> str:
    """El único sitio que opera la plataforma, para los textos legales.

    Sin dominio por organización, ya no hay una lista de hosts registrados
    (`platform_domains`, retirada en la fase 6 del plan de organización sin
    dominio) — una instalación es siempre un único dominio público.
    """
    return get_settings().web_base_url.split("://", 1)[-1]


async def legal_pages_publicas(session: AsyncSession) -> PlatformLegalPagesResponse:
    """Las cuatro páginas legales de plataforma, con su contenido efectivo."""
    branding: PlatformBranding = await repository.get_platform_branding(session)
    sitio = _sitio_de_la_instalacion()

    items: dict[str, PlatformLegalPageItem] = {}
    for clave in PLATFORM_LEGAL_PAGE_KINDS:
        fila = await repository.get_platform_legal_page(session, clave)
        contenido_editado = fila.content if fila is not None else None
        items[ATRIBUTO_DE_PAGINA[clave]] = PlatformLegalPageItem(
            content=resolve_platform_legal_page(branding, sitio, clave, contenido_editado),
            is_custom=bool(contenido_editado),
        )

    return PlatformLegalPagesResponse(**items)


def campo_de_pagina(clave: str) -> str:
    """Nombre del campo de `PlatformLegalPagesUpdate` para una clave pública."""
    return _CAMPOS_DE_PAGINA[clave]
