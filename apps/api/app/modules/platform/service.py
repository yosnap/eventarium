"""Resolución de la identidad y las páginas legales de plataforma.

Aquí vive la lógica que comparten los dos lados: el endpoint público
(`tenant/router.py`, `legal/router.py`) y los endpoints de administración
(`modules/admin`). La lectura va por el repositorio con la sesión que reciba;
la escritura la hace `modules/admin` con la sesión de mantenimiento.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.locale import DEFAULT_LOCALE, LOCALES, Locale
from app.core.storage import get_storage, public_url_versionada
from app.modules.media.models import PlatformMedia
from app.modules.platform import repository
from app.modules.platform.models import (
    PLATFORM_LEGAL_PAGE_KINDS,
    PlatformBranding,
    PlatformLegalPage,
)
from app.modules.platform.schemas import (
    PlatformBrandingResponse,
    PlatformLegalPageItem,
    PlatformLegalPagesResponse,
    PlatformLegalTranslation,
    ThemeResolved,
)
from app.modules.platform.templates import resolve_platform_legal_page
from app.modules.translations.campos import huella

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

    logo_url: str | None
    if branding.logo_media_id is not None:
        media = await session.get(PlatformMedia, branding.logo_media_id)
        logo_url = public_url_versionada(media.object_key, media.updated_at) if media else None
    elif branding.logo_object_key:
        logo_url = almacen.public_url(branding.logo_object_key)
    else:
        logo_url = None

    favicon_url: str | None
    if branding.favicon_media_id is not None:
        media = await session.get(PlatformMedia, branding.favicon_media_id)
        favicon_url = public_url_versionada(media.object_key, media.updated_at) if media else None
    else:
        favicon_url = (
            almacen.public_url(branding.favicon_object_key) if branding.favicon_object_key else None
        )

    return PlatformBrandingResponse(
        name=branding.name,
        logo_url=logo_url,
        favicon_url=favicon_url,
        social_links=list(branding.social_links or []),
        theme_template_id=str(branding.theme_template_id) if branding.theme_template_id else None,
        enabled_locales=[
            locale for locale in LOCALES if locale in (branding.enabled_locales or [])
        ],
        language_switcher_visible=branding.language_switcher_visible,
        theme=(
            ThemeResolved(
                id=str(tema.id),
                key=tema.key,
                name=tema.name,
                tokens=tema.tokens,
                default_mode=tema.default_mode,
            )
            if tema is not None
            else None
        ),
    )


def sitio_de_la_instalacion() -> str:
    """El único sitio que opera la plataforma, para los textos legales.

    Sin dominio por organización, ya no hay una lista de hosts registrados
    (`platform_domains`, retirada en la fase 6 del plan de organización sin
    dominio) — una instalación es siempre un único dominio público.
    """
    return get_settings().web_base_url.split("://", 1)[-1]


#: Versiones traducidas que escribió o revisó el superadmin: la IA no las toca.
ORIGENES_A_MANO = ("manual", "revisada")


async def espanoles_efectivos(session: AsyncSession) -> dict[str, str]:
    """Por página, el texto español que se sirve (editado o plantilla)."""
    branding: PlatformBranding = await repository.get_platform_branding(session)
    sitio = sitio_de_la_instalacion()
    resultado: dict[str, str] = {}
    for clave in PLATFORM_LEGAL_PAGE_KINDS:
        fila = await repository.get_platform_legal_page(session, clave)
        editado = fila.content if fila is not None else None
        resultado[clave] = resolve_platform_legal_page(branding, sitio, clave, editado)
    return resultado


def estado_de_version(fila: PlatformLegalPage | None, firma: str) -> str | None:
    """Estado de una versión traducida respecto al español actual (`firma` es su
    huella), o `None` si no hay. Solo `al_dia` se sirve."""
    if fila is None or (fila.origin is None and fila.status is None):
        return None
    if fila.content and fila.source_hash == firma and fila.status == "al_dia":
        return "al_dia"
    if fila.origin in ORIGENES_A_MANO:
        return "desactualizada" if fila.content else "pendiente"
    if fila.status in ("en_curso", "error"):
        return fila.status
    return "pendiente"


async def legal_pages_publicas(
    session: AsyncSession, locale: Locale = DEFAULT_LOCALE
) -> PlatformLegalPagesResponse:
    """Las cuatro páginas legales de plataforma en `locale`, con su contenido efectivo.

    La española cae a la plantilla por defecto si no se ha editado. En otro idioma
    se sirve la versión traducida solo si está al día con el español efectivo; si
    no hay o está desfasada, se sirve la española y `served_locale` lo indica. La
    traducida por IA sin revisar sale marcada (`machine_translated`) y no se anuncia
    a los buscadores (`available_locales` solo lleva las escritas o revisadas a mano).
    """
    espanoles = await espanoles_efectivos(session)
    traducidas = await repository.versiones_legales_traducidas(session)
    editadas = await repository.paginas_legales_editadas(session)

    items: dict[str, PlatformLegalPageItem] = {}
    for clave in PLATFORM_LEGAL_PAGE_KINDS:
        firma = huella(espanoles[clave])
        al_dia = {
            idioma: fila
            for (pagina, idioma), fila in traducidas.items()
            if pagina == clave and estado_de_version(fila, firma) == "al_dia"
        }
        disponibles: list[Locale] = [
            idioma
            for idioma in LOCALES
            if idioma == DEFAULT_LOCALE
            or (idioma in al_dia and al_dia[idioma].origin in ORIGENES_A_MANO)
        ]
        version = traducidas.get((clave, locale)) if locale != DEFAULT_LOCALE else None
        traduccion = (
            PlatformLegalTranslation(
                content=version.content,
                origin=version.origin,
                status=estado_de_version(version, firma),
            )
            if version is not None and estado_de_version(version, firma) is not None
            else None
        )
        servida = al_dia.get(locale)
        if servida is not None and servida.content:
            items[ATRIBUTO_DE_PAGINA[clave]] = PlatformLegalPageItem(
                content=servida.content,
                is_custom=servida.origin in ORIGENES_A_MANO,
                served_locale=locale,
                available_locales=disponibles,
                machine_translated=servida.origin == "ia",
                translation=traduccion,
            )
            continue
        items[ATRIBUTO_DE_PAGINA[clave]] = PlatformLegalPageItem(
            content=espanoles[clave],
            is_custom=clave in editadas and locale == DEFAULT_LOCALE,
            served_locale=DEFAULT_LOCALE,
            available_locales=disponibles,
            translation=traduccion,
        )

    return PlatformLegalPagesResponse(**items)


def clave_de_atributo(atributo: str) -> str:
    """Clave de página (`aviso-legal`…) de un atributo de la respuesta (`legal_notice`…)."""
    return next(clave for clave, valor in ATRIBUTO_DE_PAGINA.items() if valor == atributo)


def campo_de_pagina(clave: str) -> str:
    """Nombre del campo de `PlatformLegalPagesUpdate` para una clave pública."""
    return _CAMPOS_DE_PAGINA[clave]
