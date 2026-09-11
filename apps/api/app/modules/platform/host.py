"""Resolución del host: ¿plataforma u organización?

Antes de preguntar por la organización, `resolve_host` mira `platform_domains`.
La garantía fail-closed de `resolve_organization` no cambia: un host de
organización **no registrado** sigue sin resolver. La diferencia es que ahora un
host puede ser de plataforma, y eso permite servir la web de la instalación
(identidad y páginas legales) sin organización asociada — cosa que antes era
imposible, porque cualquier host sin organización daba 404.

La resolución de la organización **delega en `resolve_organization`** en vez de
repetir su consulta: esa función conoce matices que una copia perdería (el
atajo de desarrollo por cabecera/slug, y en qué casos lanza 404). Duplicar la
lógica fue justo el origen de una regresión: los endpoints públicos empezaron a
fallar en desarrollo con un host sin dominio registrado.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.core.tenant import ResolvedOrganization, extract_host, normalize_host, resolve_organization
from app.modules.platform import repository as platform_repository


@dataclass(frozen=True, slots=True)
class ResolvedHost:
    """Resultado de resolver el host de una petición."""

    kind: Literal["platform", "organization"]
    """`platform` en un host de la web de la instalación; cualquier otro, `organization`."""
    organization: ResolvedOrganization | None
    """Presente solo si el host resuelve a una organización registrada."""


async def resolve_host(session: AsyncSession, request: Request) -> ResolvedHost:
    """Clasifica el host de la petición.

    Un host que no resuelve a ninguna organización **no lanza aquí**: devuelve
    `organization=None` y deja que cada endpoint decida. Los que puedan servirse
    sin organización (la identidad y las legales de plataforma) lo hacen; los que
    la exijan siguen fallando con 404, conservando el comportamiento de siempre.
    """
    host = extract_host(request)

    # `platform_domains` es una tabla de instalación con solo `SELECT` para el
    # rol de la API, así que esta consulta es segura sin contexto RLS.
    if host and await platform_repository.get_platform_domain(session, normalize_host(host)):
        return ResolvedHost(kind="platform", organization=None)

    organizacion = await resolve_organization(request, session, required=False)
    return ResolvedHost(kind="organization", organization=organizacion)
