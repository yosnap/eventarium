"""Resolución de la organización a partir del host de la petición.

Regla: **fail-closed**. Si el host no coincide exactamente con un dominio registrado
se responde 404 antes de tocar ninguna otra tabla. Un `Host` no verificado nunca
puede seleccionar una organización distinta de la suya.
"""

from __future__ import annotations

import ipaddress
import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.core.config import get_settings
from app.core.database import maintenance_session
from app.shared.errors import NotFoundError

# Cabecera de conveniencia, aceptada solo con APP_ENV=development.
DEV_ORGANIZATION_HEADER = "x-organization-slug"


@dataclass(frozen=True, slots=True)
class ResolvedOrganization:
    """Organización resuelta por host, con lo mínimo para autorizar la petición."""

    id: uuid.UUID
    slug: str
    is_active: bool


def is_trusted_proxy(ip: str | None) -> bool:
    """Indica si la IP de origen pertenece a una red de proxy de confianza."""
    if not ip:
        return False
    try:
        direccion = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(direccion in red for red in get_settings().trusted_proxy_networks)


def normalize_host(host: str) -> str:
    """Minúsculas y sin puerto. `EJEMPLO.com:8080` → `ejemplo.com`."""
    limpio = host.strip().lower()
    if limpio.startswith("["):  # IPv6 literal: [::1]:8080
        cierre = limpio.find("]")
        if cierre != -1:
            return limpio[: cierre + 1]
    if ":" in limpio:
        limpio = limpio.rsplit(":", 1)[0]
    return limpio


def extract_host(request: Request) -> str:
    """Host efectivo de la petición.

    `X-Forwarded-Host` solo se acepta si la conexión viene de un proxy de confianza;
    en otro caso cualquier cliente podría suplantar la organización.
    """
    cliente = request.client.host if request.client else None
    if is_trusted_proxy(cliente):
        reenviado = request.headers.get("x-forwarded-host")
        if reenviado:
            # Un proxy mal configurado puede encadenar varios valores.
            return normalize_host(reenviado.split(",")[0])
    return normalize_host(request.headers.get("host", ""))


async def resolve_organization(session: AsyncSession, request: Request) -> ResolvedOrganization:
    """Resuelve la organización de la petición o lanza 404.

    Esta lectura es el único punto que ocurre necesariamente *antes* de conocer la
    organización, así que no puede depender del contexto RLS. En lugar de dar
    `BYPASSRLS` al rol de la API se usa `app_resolve_organization`, una función
    `SECURITY DEFINER` (creada en la migración de políticas) que devuelve solo
    `id`, `slug` e `is_active` para un host exacto: el bypass queda acotado a esta
    consulta concreta y auditable, en vez de a todo el rol.
    """
    settings = get_settings()
    host = extract_host(request)

    if host:
        fila = (
            await session.execute(
                text("SELECT id, slug, is_active FROM app_resolve_organization(:host)"),
                {"host": host},
            )
        ).first()
        if fila is not None:
            return ResolvedOrganization(id=fila[0], slug=fila[1], is_active=fila[2])

    # Atajo de conveniencia para desarrollo, nunca disponible en test ni producción.
    if settings.is_development:
        slug = request.headers.get(DEV_ORGANIZATION_HEADER) or (
            settings.default_organization_slug or None
        )
        if slug:
            fila = (
                await session.execute(
                    text("SELECT id, slug, is_active FROM app_resolve_organization_by_slug(:slug)"),
                    {"slug": slug},
                )
            ).first()
            if fila is not None:
                return ResolvedOrganization(id=fila[0], slug=fila[1], is_active=fila[2])

    raise NotFoundError(f"No hay ninguna organización asociada al host «{host}».")


async def base_url_de_organizacion(organization_id: uuid.UUID) -> str:
    """URL pública de la organización, por su dominio primario.

    Extraída de `core/tasks.py` (fase 6 del PRD, fase 2 de trabajo): un correo
    o una redirección de Stripe (`return_url`/`refresh_url`) que llega a
    alguien sin sesión ni contexto de organización tiene que apuntar al
    dominio propio de esa organización — la instalación resuelve el tenant por
    `Host`, así que un enlace al dominio equivocado no encontraría el recurso
    al volver. Usa `maintenance_session` porque quien llama (una tarea de
    fondo o el propio endpoint de onboarding, antes de que exista contexto de
    organización) no siempre tiene una petición HTTP de la que resolverla.
    """
    settings = get_settings()
    async with maintenance_session() as session:
        host = await session.scalar(
            text(
                "SELECT host FROM organization_domains "
                "WHERE organization_id = :id ORDER BY is_primary DESC LIMIT 1"
            ),
            {"id": organization_id},
        )
    if not host:
        return settings.web_base_url
    esquema = "https" if settings.app_env == "production" else "http"
    return f"{esquema}://{host}"
