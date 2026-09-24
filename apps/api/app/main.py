"""Punto de entrada de la API."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import get_settings
from app.core.deps import bloquear_escritura_si_impersona
from app.core.ratelimit import consumir_mcp_por_ip
from app.core.redis_client import close_redis
from app.core.storage import get_storage
from app.modules.accounting.drafts_router import router as accounting_drafts_router
from app.modules.accounting.router import router as accounting_router
from app.modules.admin.ai_router import router as admin_ai_router
from app.modules.admin.analytics_router import router as admin_analytics_router
from app.modules.admin.ga4_client import close_ga4
from app.modules.admin.impersonation_router import router as admin_impersonation_router
from app.modules.admin.platform_router import router as admin_platform_router
from app.modules.admin.router import router as admin_router
from app.modules.admin.users_router import router as admin_users_router
from app.modules.ai_gateway.router import catalogo_router as ai_catalog_router
from app.modules.ai_gateway.router import router as ai_gateway_router
from app.modules.auth.router import router as auth_router
from app.modules.events.cancel_router import router as events_cancel_router
from app.modules.events.public_router import router as events_public_router
from app.modules.events.router import router as events_router
from app.modules.health.router import router as health_router
from app.modules.legal.router import router_cookie_consent as cookie_consent_router
from app.modules.legal.router import router_public as legal_public_router
from app.modules.mcp.oauth.consentimiento import router as mcp_consentimiento_router
from app.modules.mcp.router import router as mcp_router
from app.modules.mcp.router import router_organizacion as mcp_organizacion_router
from app.modules.mcp.server import crear_app as crear_app_mcp
from app.modules.mcp.server import (
    crear_app_oauth,
    metadatos_del_recurso,
    metadatos_del_servidor_de_autorizacion,
)
from app.modules.mcp.server import crear_servidor as crear_servidor_mcp
from app.modules.media.router import folders_router as media_folders_router
from app.modules.media.router import router as media_router
from app.modules.metrics.router import router as metrics_router
from app.modules.organizations.invitations_public_router import (
    router as invitations_public_router,
)
from app.modules.organizations.router import router as organizations_router
from app.modules.organizations.self_service import router as organizations_self_service_router
from app.modules.payments.public_router import router as payments_public_router
from app.modules.payments.router import router as payments_router
from app.modules.payments.router import router_discount_codes as payments_discount_codes_router
from app.modules.payments.router import router_payments as payments_payments_router
from app.modules.payments.router import router_ticket_types as payments_ticket_types_router
from app.modules.payments.webhooks import router as payments_webhooks_router
from app.modules.policies.public_router import router as policies_public_router
from app.modules.policies.router import router_evento as policies_event_router
from app.modules.policies.router import router_organizacion as policies_organization_router
from app.modules.registrations.public_router import router as registrations_public_router
from app.modules.registrations.router import router as registrations_router
from app.modules.roles.router import router as roles_router
from app.modules.sponsors.router import router_sponsors as sponsors_router
from app.modules.sponsors.router import router_tiers as sponsor_tiers_router
from app.modules.tenant.router import router as tenant_router
from app.modules.tickets.public_router import router as tickets_public_router
from app.modules.tickets.router import router as tickets_router
from app.modules.users.router import router as users_router
from app.shared.errors import DomainError, register_exception_handlers

API_PREFIX = "/api/v1"


class _EntradaMcp:
    """Delante del servidor MCP montado, que queda fuera de las dependencias
    de FastAPI:

    - límite por IP **antes** de autenticar (`consumir_mcp_por_ip`), para que
      nadie pueda probar claves sin tope;
    - `/mcp` → `/mcp/`: Starlette respondería con una redirección, y los
      clientes MCP no la siguen en un POST.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        ruta = scope.get("path", "")
        if scope["type"] == "http" and (ruta == "/mcp" or ruta.startswith("/mcp/")):
            try:
                await consumir_mcp_por_ip(Request(scope))
            except DomainError as exc:
                respuesta = JSONResponse(
                    exc.to_problem(ruta),
                    status_code=exc.status_code,
                    media_type="application/problem+json",
                )
                await respuesta(scope, receive, send)
                return
            if ruta == "/mcp":
                scope = {**scope, "path": "/mcp/", "raw_path": b"/mcp/"}
        await self.app(scope, receive, send)


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Prepara y libera los recursos compartidos."""
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)

    await get_storage().ensure_bucket()
    logger.info("API lista en entorno %s", settings.app_env)
    try:
        # El gestor de sesiones del MCP tiene que vivir en el lifespan de la
        # app principal: el de una app montada no se ejecuta.
        async with crear_servidor_mcp().session_manager.run():
            yield
    finally:
        await close_redis()
        await close_ga4()


def create_app() -> FastAPI:
    """Construye la aplicación."""
    settings = get_settings()

    app = FastAPI(
        title="API de la plataforma de eventos IA Week",
        version="0.1.0",
        description=(
            "API multi-organización para el registro y la gestión de eventos. "
            "La organización se resuelve por el host de la petición."
        ),
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url="/docs",
        redoc_url=None,
        lifespan=lifespan,
    )

    # En producción web y API comparten host tras Caddy, así que no hay peticiones
    # entre orígenes y habilitar CORS solo ampliaría la superficie de ataque.
    if settings.is_development and settings.cors_origin_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    register_exception_handlers(app)

    # La dependencia de solo lectura se aplica aquí, al router raíz de la API,
    # y no endpoint a endpoint: una sesión de suplantación no debe poder
    # escribir en ningún sitio, y un endpoint nuevo no puede quedarse fuera por
    # olvido. Es inerte para una sesión normal.
    api = APIRouter(
        prefix=API_PREFIX,
        dependencies=[Depends(bloquear_escritura_si_impersona)],
    )
    api.include_router(health_router)
    api.include_router(auth_router)
    api.include_router(tenant_router)
    api.include_router(organizations_self_service_router)
    api.include_router(organizations_router)
    api.include_router(invitations_public_router)
    api.include_router(users_router)
    api.include_router(roles_router)
    api.include_router(admin_router)
    api.include_router(admin_users_router)
    api.include_router(admin_analytics_router)
    api.include_router(admin_ai_router)
    api.include_router(admin_platform_router)
    api.include_router(admin_impersonation_router)
    api.include_router(events_router)
    api.include_router(events_cancel_router)
    api.include_router(mcp_router)
    api.include_router(mcp_organizacion_router)
    api.include_router(mcp_consentimiento_router)
    api.include_router(events_public_router)
    api.include_router(policies_organization_router)
    api.include_router(policies_event_router)
    api.include_router(policies_public_router)
    api.include_router(registrations_router)
    api.include_router(metrics_router)
    api.include_router(registrations_public_router)
    api.include_router(tickets_router)
    api.include_router(tickets_public_router)
    api.include_router(sponsor_tiers_router)
    api.include_router(sponsors_router)
    api.include_router(media_router)
    api.include_router(media_folders_router)
    api.include_router(payments_router)
    api.include_router(payments_ticket_types_router)
    api.include_router(payments_discount_codes_router)
    api.include_router(payments_payments_router)
    api.include_router(payments_public_router)
    api.include_router(payments_webhooks_router)
    api.include_router(legal_public_router)
    api.include_router(cookie_consent_router)
    api.include_router(accounting_router)
    api.include_router(accounting_drafts_router)
    api.include_router(ai_gateway_router)
    api.include_router(ai_catalog_router)
    app.include_router(api)

    # Servidor MCP (fuera de `/api/v1`: los clientes lo conocen por su URL
    # pública `…/mcp`) y sus metadatos de recurso protegido (RFC 9728), en la
    # raíz y en la ruta específica del recurso, que es donde los busca cada
    # cliente según la versión de la especificación que implemente.
    # `/mcp/oauth` antes que `/mcp`: Starlette monta por orden, y el MCP
    # (montado en `/mcp`) se quedaría con las rutas del servidor de
    # autorización.
    app.mount("/mcp/oauth", crear_app_oauth())
    app.mount("/mcp", crear_app_mcp())

    @app.get("/.well-known/oauth-authorization-server/mcp/oauth", include_in_schema=False)
    async def servidor_de_autorizacion_mcp() -> dict[str, object]:
        return metadatos_del_servidor_de_autorizacion()

    @app.get("/.well-known/oauth-protected-resource", include_in_schema=False)
    @app.get("/.well-known/oauth-protected-resource/mcp", include_in_schema=False)
    async def recurso_protegido_mcp() -> dict[str, object]:
        return metadatos_del_recurso()

    app.add_middleware(_EntradaMcp)

    return app


app = create_app()
