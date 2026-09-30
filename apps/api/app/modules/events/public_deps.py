"""Dependencia compartida de los routers públicos que cuelgan de un evento.

Cada ruta cuelga de `/public/organizations/{org_slug}/events/{slug}/…`: el
slug de un evento solo es único dentro de su organización.

Como la dependencia lee `request.path_params`, FastAPI no ve esos parámetros
en ninguna firma: `ruta_de_evento` los declara en el contrato OpenAPI para que
el cliente generado los conozca.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from fastapi import APIRouter, Request

from app.core.deps import SessionDep
from app.core.ratelimit import limit_per_ip
from app.modules.events import service
from app.modules.events.models import Event

F = TypeVar("F", bound=Callable[..., Any])


def evento_publico(*, para_mostrar: bool) -> Callable[[Request, SessionDep], Awaitable[Event]]:
    async def dependencia(request: Request, session: SessionDep) -> Event:
        parametros = request.path_params
        return await service.resolve_public_event_by_slug(
            session,
            parametros["org_slug"],
            parametros["slug"],
            para_mostrar=para_mostrar,
        )

    return dependencia


EVENTO_PARA_MOSTRAR = evento_publico(para_mostrar=True)
EVENTO_PARA_INSCRIBIR = evento_publico(para_mostrar=False)


def _parametro_de_ruta(nombre: str) -> dict[str, Any]:
    return {"name": nombre, "in": "path", "required": True, "schema": {"type": "string"}}


def ruta_de_evento(
    router: APIRouter,
    metodo: str,
    sufijo: str,
    *,
    limite: tuple[str, int],
    **kwargs: Any,
) -> Callable[[F], F]:
    """Registra un manejador en la ruta anidada `/organizations/{org_slug}/events/{slug}…`."""
    nombre_limite, veces = limite

    def decorar(funcion: F) -> F:
        router.add_api_route(
            f"/organizations/{{org_slug}}/events/{{slug}}{sufijo}",
            funcion,
            methods=[metodo.upper()],
            dependencies=[limit_per_ip(nombre_limite, veces)],
            openapi_extra={
                "parameters": [_parametro_de_ruta("org_slug"), _parametro_de_ruta("slug")]
            },
            **kwargs,
        )
        return funcion

    return decorar
