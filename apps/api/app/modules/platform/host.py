"""Resolución del host: ¿plataforma u organización?

Antes de preguntar por la organización, `resolve_host` mira `platform_domains`.
La garantía fail-closed de `resolve_organization` no cambia: un host de
organización **no registrado** sigue sin resolver. La diferencia es que ahora
un host puede ser de plataforma, y eso permite servir la web de la instalación
(identidad y páginas legales) sin organización asociada — cosa que antes era
imposible, porque cualquier host sin organización daba 404.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import ResolvedOrganization, normalize_host
from app.modules.platform import repository as platform_repository


@dataclass(frozen=True, slots=True)
class ResolvedHost:
    """Resultado de resolver el host de una petición."""

    kind: Literal["platform", "organization"]
    """`platform` en un host de la web de la instalación; cualquier otro, `organization`."""
    organization: ResolvedOrganization | None
    """Presente solo si el host resuelve a una organización registrada."""


async def resolve_host(session: AsyncSession, host: str) -> ResolvedHost:
    """Clasifica un host ya resuelto de la petición.

    Un host no registrado **no lanza aquí**: devuelve `organization=None` y
    deja que cada endpoint decida. Los que puedan servirse sin organización (la
    identidad y las legales de plataforma) lo hacen; los que la exijan siguen
    fallando con 404, conservando el comportamiento de siempre.
    """
    limpio = normalize_host(host)

    # `platform_domains` es una tabla de instalación con solo `SELECT` para el
    # rol de la API, así que esta consulta es segura sin contexto RLS.
    if limpio and await platform_repository.get_platform_domain(session, limpio) is not None:
        return ResolvedHost(kind="platform", organization=None)

    if limpio:
        fila = (
            await session.execute(
                text("SELECT id, slug, is_active FROM app_resolve_organization(:host)"),
                {"host": limpio},
            )
        ).first()
        if fila is not None:
            return ResolvedHost(
                kind="organization",
                organization=ResolvedOrganization(id=fila[0], slug=fila[1], is_active=fila[2]),
            )

    return ResolvedHost(kind="organization", organization=None)
