"""Helpers de los tests del servidor MCP: llamadas JSON-RPC directas a `/mcp`
como las haría cualquier cliente. El fixture `cliente_mcp` vive en
`conftest.py`."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient

EVENTS = "/api/v1/events"
CONEXIONES = "/api/v1/users/me/mcp-connections"
AHORA = datetime.now(UTC).replace(microsecond=0)


async def _rpc(cliente: AsyncClient, clave: str | None, metodo: str, params: dict | None = None):  # type: ignore[no-untyped-def]
    cabeceras = {"Accept": "application/json, text/event-stream"}
    if clave:
        cabeceras["Authorization"] = f"Bearer {clave}"
    return await cliente.post(
        "/mcp",
        headers=cabeceras,
        json={"jsonrpc": "2.0", "id": 1, "method": metodo, "params": params or {}},
    )


async def _herramienta(cliente: AsyncClient, clave: str, nombre: str, **argumentos) -> dict:  # type: ignore[no-untyped-def]
    respuesta = await _rpc(cliente, clave, "tools/call", {"name": nombre, "arguments": argumentos})
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()["result"]


def _datos(resultado: dict):  # type: ignore[no-untyped-def]
    """Contenido de una respuesta correcta. Toda respuesta de herramienta que
    pasa por aquí se comprueba además contra datos personales: ningún correo."""
    assert not resultado.get("isError"), resultado
    assert "@" not in json.dumps(resultado), resultado
    estructurado = resultado.get("structuredContent")
    if estructurado is not None:
        return estructurado.get("result", estructurado)
    return json.loads(resultado["content"][0]["text"])


async def _evento(cliente: AsyncClient, cabeceras: dict[str, str], slug: str) -> dict:
    creado = await cliente.post(
        EVENTS,
        headers=cabeceras,
        json={
            "slug": slug,
            "title": f"Evento {slug}",
            "starts_at": (AHORA + timedelta(days=10)).isoformat(),
            "ends_at": (AHORA + timedelta(days=11)).isoformat(),
            "location_mode": "in_person",
            "capacity": 50,
        },
    )
    assert creado.status_code == 201, creado.text
    return creado.json()


async def _crear_clave(cliente: AsyncClient, cabeceras: dict[str, str], **cuerpo: object) -> dict:
    respuesta = await cliente.post(CONEXIONES, headers=cabeceras, json={"name": "Claude", **cuerpo})
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()
