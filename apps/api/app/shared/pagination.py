"""Paginación por desplazamiento, común a todos los módulos."""

from __future__ import annotations

from typing import Annotated

from fastapi import Query
from pydantic import BaseModel, Field


class PageParams(BaseModel):
    """Parámetros de paginación de una petición."""

    limit: Annotated[int, Field(ge=1, le=100)] = 20
    offset: Annotated[int, Field(ge=0)] = 0


def page_params(
    limit: Annotated[int, Query(ge=1, le=100, description="Elementos por página")] = 20,
    offset: Annotated[int, Query(ge=0, description="Elementos omitidos")] = 0,
) -> PageParams:
    """Dependencia de FastAPI para inyectar la paginación."""
    return PageParams(limit=limit, offset=offset)


class Page[T](BaseModel):
    """Página de resultados."""

    items: list[T]
    total: int
    limit: int
    offset: int
