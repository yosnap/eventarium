"""Punto de entrada de la API."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.redis_client import close_redis
from app.core.storage import get_storage
from app.modules.admin.router import router as admin_router
from app.modules.auth.router import router as auth_router
from app.modules.events.public_router import router as events_public_router
from app.modules.events.router import router as events_router
from app.modules.health.router import router as health_router
from app.modules.organizations.router import router as organizations_router
from app.modules.organizations.self_service import router as organizations_self_service_router
from app.modules.registrations.public_router import router as registrations_public_router
from app.modules.registrations.router import router as registrations_router
from app.modules.roles.router import router as roles_router
from app.modules.tenant.router import router as tenant_router
from app.modules.tickets.public_router import router as tickets_public_router
from app.modules.tickets.router import router as tickets_router
from app.modules.users.router import router as users_router
from app.shared.errors import register_exception_handlers

API_PREFIX = "/api/v1"

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Prepara y libera los recursos compartidos."""
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)

    await get_storage().ensure_bucket()
    logger.info("API lista en entorno %s", settings.app_env)
    try:
        yield
    finally:
        await close_redis()


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

    api = APIRouter(prefix=API_PREFIX)
    api.include_router(health_router)
    api.include_router(auth_router)
    api.include_router(tenant_router)
    api.include_router(organizations_self_service_router)
    api.include_router(organizations_router)
    api.include_router(users_router)
    api.include_router(roles_router)
    api.include_router(admin_router)
    api.include_router(events_router)
    api.include_router(events_public_router)
    api.include_router(registrations_router)
    api.include_router(registrations_public_router)
    api.include_router(tickets_router)
    api.include_router(tickets_public_router)
    app.include_router(api)

    return app


app = create_app()
