"""Acceso a datos de la configuración de IA y de los interruptores.

Como el resto de repositorios del proyecto, filtra siempre por
`organization_id` de forma explícita: RLS es la red de seguridad, no el
filtro principal.

Las dos tablas de plataforma se **leen** con la sesión que traiga quien
llama —incluida la `SessionApp` de una organización, que tiene `SELECT`
concedido (V-3/V-4)— y solo se **escriben** desde el módulo `admin` con la
sesión de mantenimiento, porque `app_user` tiene revocado el DML sobre ellas
(V-2).
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai_gateway.models import (
    ID_FILA_DE_PLATAFORMA,
    OrganizationAiSettings,
    OrganizationService,
    PlatformAiSettings,
    PlatformService,
)


async def get_platform_settings(session: AsyncSession) -> PlatformAiSettings | None:
    """La fila única de configuración de plataforma, o `None` si no existe."""
    fila: PlatformAiSettings | None = await session.scalar(
        select(PlatformAiSettings).where(PlatformAiSettings.id == ID_FILA_DE_PLATAFORMA)
    )
    return fila


async def get_or_create_platform_settings(session: AsyncSession) -> PlatformAiSettings:
    """La fila única, creándola vacía si todavía no existe.

    Solo la llama el módulo `admin` (sesión de mantenimiento): `app_user`
    no puede insertar en esta tabla.
    """
    fila = await get_platform_settings(session)
    if fila is None:
        fila = PlatformAiSettings(id=ID_FILA_DE_PLATAFORMA)
        session.add(fila)
        await session.flush()
    return fila


async def get_organization_settings(
    session: AsyncSession, organization_id: uuid.UUID
) -> OrganizationAiSettings | None:
    """El override de una organización, o `None` si hereda de plataforma."""
    fila: OrganizationAiSettings | None = await session.scalar(
        select(OrganizationAiSettings).where(
            OrganizationAiSettings.organization_id == organization_id
        )
    )
    return fila


async def delete_organization_settings(session: AsyncSession, organization_id: uuid.UUID) -> bool:
    """Borra el override. Devuelve si había algo que borrar."""
    fila = await get_organization_settings(session, organization_id)
    if fila is None:
        return False
    await session.delete(fila)
    await session.flush()
    return True


async def list_platform_services(session: AsyncSession) -> list[PlatformService]:
    filas = await session.scalars(select(PlatformService).order_by(PlatformService.service_key))
    return list(filas)


async def get_platform_service(session: AsyncSession, service_key: str) -> PlatformService | None:
    fila: PlatformService | None = await session.scalar(
        select(PlatformService).where(PlatformService.service_key == service_key)
    )
    return fila


async def set_platform_service(
    session: AsyncSession, service_key: str, *, enabled: bool
) -> PlatformService:
    """Enciende o apaga un interruptor global (solo el admin)."""
    fila = await get_platform_service(session, service_key)
    if fila is None:
        fila = PlatformService(service_key=service_key, enabled=enabled)
        session.add(fila)
    else:
        fila.enabled = enabled
    await session.flush()
    return fila


async def list_organization_service_overrides(
    session: AsyncSession, organization_id: uuid.UUID
) -> list[OrganizationService]:
    filas = await session.scalars(
        select(OrganizationService)
        .where(OrganizationService.organization_id == organization_id)
        .order_by(OrganizationService.service_key)
    )
    return list(filas)


async def force_organization_service_off(
    session: AsyncSession, organization_id: uuid.UUID, service_key: str
) -> None:
    """Fuerza el servicio a apagado para esa organización (idempotente)."""
    existente = await session.scalar(
        select(OrganizationService).where(
            OrganizationService.organization_id == organization_id,
            OrganizationService.service_key == service_key,
        )
    )
    if existente is None:
        session.add(
            OrganizationService(
                organization_id=organization_id, service_key=service_key, enabled=False
            )
        )
        await session.flush()


async def clear_organization_service_override(
    session: AsyncSession, organization_id: uuid.UUID, service_key: str
) -> None:
    """Vuelve a heredar: borra el override (idempotente).

    No existe «forzar on» (V-7): heredar es la única alternativa a apagado.
    """
    await session.execute(
        delete(OrganizationService).where(
            OrganizationService.organization_id == organization_id,
            OrganizationService.service_key == service_key,
        )
    )
    await session.flush()
