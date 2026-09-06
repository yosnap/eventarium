"""Health-check contra las dependencias reales."""

from __future__ import annotations

from httpx import AsyncClient


async def test_health_devuelve_ok_en_las_tres_dependencias(cliente: AsyncClient) -> None:
    respuesta = await cliente.get("/api/v1/health")
    assert respuesta.status_code == 200
    assert respuesta.json() == {"database": "ok", "storage": "ok", "redis": "ok"}
