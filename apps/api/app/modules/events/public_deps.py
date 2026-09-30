"""Dependencia compartida de los routers públicos que cuelgan de un evento.

Cada ruta existe en dos formas: la anidada `/public/organizations/{org_slug}/events/{slug}/…`
y la plana anterior `/public/events/{slug}/…`. Decide la presencia de `org_slug`
en los parámetros de ruta, no un parámetro opcional: un opcional también se
aceptaría como *query* en la ruta plana y permitiría saltarse la resolución
por enlaces antiguos con `?org_slug=…`.

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
            parametros["slug"],
            org_slug=parametros.get("org_slug"),
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
    """Registra un mismo manejador en la ruta anidada y en la plana anterior.

    La plana queda marcada como obsoleta y se retira en una versión posterior;
    mientras tanto solo resuelve por enlaces antiguos (ver `service`). Cada
    forma tiene su propio contador de límite por IP: un ataque contra la ruta
    obsoleta no agota el presupuesto de la nueva.
    """
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
        router.add_api_route(
            f"/events/{{slug}}{sufijo}",
            funcion,
            methods=[metodo.upper()],
            dependencies=[limit_per_ip(f"{nombre_limite}-antiguo", veces)],
            openapi_extra={"parameters": [_parametro_de_ruta("slug")]},
            deprecated=True,
            **kwargs,
        )
        return funcion

    return decorar
