"""Acceso a datos de `theme_templates`.

Sin filtro por organización: es una tabla de instalación, común a toda la
plataforma.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.theme_templates.models import ThemeTemplate


async def list_theme_templates(session: AsyncSession) -> list[ThemeTemplate]:
    resultado = await session.scalars(select(ThemeTemplate).order_by(ThemeTemplate.name))
    return list(resultado)


async def get_theme_template(session: AsyncSession, template_id: uuid.UUID) -> ThemeTemplate | None:
    return await session.get(ThemeTemplate, template_id)


async def get_theme_template_by_key(session: AsyncSession, key: str) -> ThemeTemplate | None:
    return await session.scalar(select(ThemeTemplate).where(ThemeTemplate.key == key))


async def get_default_theme_template(session: AsyncSession) -> ThemeTemplate | None:
    return await session.scalar(select(ThemeTemplate).where(ThemeTemplate.is_default.is_(True)))


async def clear_default(session: AsyncSession, *, except_id: uuid.UUID | None = None) -> None:
    """Desmarca cualquier plantilla que sea `is_default`, salvo `except_id`.

    Se usa antes de marcar una plantilla nueva como por defecto, en la misma
    transacción, para que como mucho una fila lo sea (índice único parcial de
    la migración como red de seguridad final).
    """
    consulta = update(ThemeTemplate).where(ThemeTemplate.is_default.is_(True))
    if except_id is not None:
        consulta = consulta.where(ThemeTemplate.id != except_id)
    await session.execute(consulta.values(is_default=False))
