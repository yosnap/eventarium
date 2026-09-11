"""Acceso a los datos de plataforma.

Los endpoints públicos (`tenant/router.py`, `legal/router.py`) preguntan aquí
con la sesión de la petición (`app_user`, que solo tiene `SELECT` sobre estas
tablas). La escritura vive en `modules/admin`, con la sesión de mantenimiento:
no hay función de escritura que un módulo ajeno pueda reutilizar por descuido.
"""

from __future__ import annotations

import uuid
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.platform.models import (
    NOMBRE_PLATAFORMA,
    PlatformBranding,
    PlatformDomain,
    PlatformLegalPage,
)
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
    return fila if fila is not None else PlatformBranding(name=NOMBRE_PLATAFORMA)


async def get_platform_legal_page(session: AsyncSession, kind: str) -> PlatformLegalPage | None:
    """Texto editado de una página legal de plataforma, o `None` si no hay."""
    return cast(
        "PlatformLegalPage | None",
        await session.scalar(select(PlatformLegalPage).where(PlatformLegalPage.kind == kind)),
    )


async def get_platform_domains(session: AsyncSession) -> list[PlatformDomain]:
    """Todos los hosts de plataforma, ordenados."""
    filas = await session.scalars(select(PlatformDomain).order_by(PlatformDomain.host))
    return list(filas.all())


async def get_platform_domain(session: AsyncSession, host: str) -> PlatformDomain | None:
    """Un host de plataforma por su nombre exacto (ya normalizado)."""
    return cast(
        "PlatformDomain | None",
        await session.scalar(select(PlatformDomain).where(PlatformDomain.host == host)),
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
