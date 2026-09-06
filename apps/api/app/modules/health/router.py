"""Comprobación de estado de las dependencias críticas."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Response, status
from pydantic import BaseModel
from sqlalchemy import text

from app.core.database import SessionApp
from app.core.redis_client import redis_healthy
from app.core.storage import get_storage

router = APIRouter(prefix="/health", tags=["salud"])

Estado = Literal["ok", "error"]


class HealthResponse(BaseModel):
    """Estado de cada dependencia."""

    database: Estado
    storage: Estado
    redis: Estado


async def _database_ok() -> bool:
    try:
        async with SessionApp() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


@router.get(
    "",
    summary="Estado del servicio",
    description="Comprueba base de datos, almacenamiento de objetos y Redis.",
    response_model=HealthResponse,
)
async def health(response: Response) -> HealthResponse:
    resultado = HealthResponse(
        database="ok" if await _database_ok() else "error",
        storage="ok" if await get_storage().healthcheck() else "error",
        redis="ok" if await redis_healthy() else "error",
    )
    if "error" in resultado.model_dump().values():
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return resultado
