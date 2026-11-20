"""Acceso a los datos de plataforma.

Los endpoints públicos (`tenant/router.py`, `legal/router.py`) preguntan aquí
con la sesión de la petición (`app_user`, que solo tiene `SELECT` sobre estas
tablas). La escritura vive en `modules/admin`, con la sesión de mantenimiento:
no hay función de escritura que un módulo ajeno pueda reutilizar por descuido.
"""

from __future__ import annotations

import uuid
from typing import cast

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.locale import LOCALES
from app.modules.platform.models import NOMBRE_PLATAFORMA, PlatformBranding, PlatformLegalPage
from app.modules.theme_templates.models import ThemeTemplate


async def get_platform_branding(session: AsyncSession) -> PlatformBranding:
    """La fila única de identidad de plataforma, o una sin persistir si falta.

    Si la fila no existe (instalación con el esquema pero sin la semilla), se
    devuelve un objeto en memoria con el nombre por defecto: el endpoint
    público tiene que responder 200 igualmente, no 500 por una semilla que
    falta. No se hace `INSERT` desde aquí a propósito — `app_user` no tiene
    permiso de escritura sobre esta tabla.
    """
    fila = await session.scalar(select(PlatformBranding).limit(1))
    if fila is not None:
        return fila
    # Los `default` del modelo solo se aplican al insertar: aquí se fijan a mano.
    return PlatformBranding(
        name=NOMBRE_PLATAFORMA,
        social_links=[],
        enabled_locales=list(LOCALES),
        language_switcher_visible=True,
    )


async def versiones_legales_traducidas(
    session: AsyncSession,
) -> dict[tuple[str, str], PlatformLegalPage]:
    """Las versiones de las páginas legales en otros idiomas, por (página, idioma)."""
    filas = await session.scalars(
        select(PlatformLegalPage).where(PlatformLegalPage.locale != "es-ES")
    )
    return {(fila.kind, fila.locale): fila for fila in filas}


async def reiniciar_errores_de_traduccion_legal(session: AsyncSession) -> None:
    """Quita la espera tras errores de las versiones de la IA."""
    await session.execute(
        update(PlatformLegalPage)
        .where(PlatformLegalPage.origin == "ia")
        .values(error_count=0, retry_after=None)
    )


async def paginas_legales_editadas(session: AsyncSession) -> set[str]:
    """Páginas cuyo español se ha editado (no es la plantilla)."""
    filas = await session.scalars(
        select(PlatformLegalPage.kind).where(
            PlatformLegalPage.locale == "es-ES",
            PlatformLegalPage.content.is_not(None),
            PlatformLegalPage.content != "",
        )
    )
    return set(filas)


async def get_platform_legal_page(
    session: AsyncSession, kind: str, locale: str = "es-ES"
) -> PlatformLegalPage | None:
    """Texto editado de una página legal de plataforma en `locale`, o `None` si no hay."""
    return cast(
        "PlatformLegalPage | None",
        await session.scalar(
            select(PlatformLegalPage).where(
                PlatformLegalPage.kind == kind, PlatformLegalPage.locale == locale
            )
        ),
    )


async def get_platform_theme(
    session: AsyncSession, template_id: uuid.UUID | None
) -> ThemeTemplate | None:
    """Plantilla de tema del chrome de plataforma.

    La elegida si la identidad tiene una; si no (o si el `id` apunta a una
    plantilla borrada), la marcada `is_default` del catálogo. Misma convención
    que resuelve el branding de organización en `tenant/router.py`.
    """
    if template_id is not None:
        plantilla = await session.get(ThemeTemplate, template_id)
        if plantilla is not None:
            return plantilla
    return cast(
        "ThemeTemplate | None",
        await session.scalar(select(ThemeTemplate).where(ThemeTemplate.is_default.is_(True))),
    )
