"""MCP entre organizaciones y panel del dueño: conexiones de la organización,
revocación por el dueño e historial desde la auditoría."""

from __future__ import annotations

import json
from datetime import timedelta

from httpx import AsyncClient

from tests.conftest import OrganizacionDePrueba, crear_miembro, iniciar_sesion, iniciar_sesion_con
from tests.mcp_test_helpers import AHORA, CONEXIONES, _crear_clave, _evento, _herramienta, _rpc

DE_LA_ORGANIZACION = "/api/v1/organizations/me/mcp-connections"


async def test_una_clave_no_ve_eventos_de_otra_organizacion(
    cliente: AsyncClient,
    cliente_mcp: AsyncClient,
    organizacion: OrganizacionDePrueba,
    otra_organizacion: OrganizacionDePrueba,
) -> None:
    _, cabeceras_a = await iniciar_sesion(cliente, organizacion)
    _, cabeceras_b = await iniciar_sesion(cliente, otra_organizacion)
    evento_b = await _evento(cliente, cabeceras_b, "evento-de-b")
    clave_a = (await _crear_clave(cliente, cabeceras_a))["api_key"]

    ajeno = await _herramienta(cliente_mcp, clave_a, "ver_evento", event_id=evento_b["id"])
    limitada = await cliente.post(
        CONEXIONES, headers=cabeceras_a, json={"name": "Intrusa", "event_ids": [evento_b["id"]]}
    )
    listado = await _herramienta(cliente_mcp, clave_a, "listar_eventos")

    assert ajeno["isError"] is True
    assert "no existe" in json.dumps(ajeno, ensure_ascii=False)
    assert limitada.status_code == 422
    assert "evento-de-b" not in json.dumps(listado)


async def test_el_dueno_ve_y_revoca_las_conexiones_de_sus_miembros(
    cliente: AsyncClient, cliente_mcp: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras_dueno = await iniciar_sesion(cliente, organizacion)
    miembro = await crear_miembro(organizacion, "organizer")
    # El dueño da `mcp:connect` al rol de organizador desde la API de roles
    # sería lo normal; aquí basta con que el dueño tenga su propia conexión.
    propia = await _crear_clave(cliente, cabeceras_dueno, scopes=["eventos:leer"])

    listado = await cliente.get(DE_LA_ORGANIZACION, headers=cabeceras_dueno)
    revocar = await cliente.delete(
        f"{DE_LA_ORGANIZACION}/{propia['connection']['id']}", headers=cabeceras_dueno
    )
    despues = await _rpc(cliente_mcp, propia["api_key"], "tools/list")
    _, cabeceras_organizador = await iniciar_sesion_con(
        cliente, organizacion, miembro.email, miembro.password
    )
    como_organizador = await cliente.get(DE_LA_ORGANIZACION, headers=cabeceras_organizador)

    assert listado.status_code == 200
    assert listado.json()[0]["user_email"] == organizacion.owner_email
    assert revocar.status_code == 204
    assert despues.status_code == 401
    assert como_organizador.status_code == 403


async def test_el_historial_sale_de_la_auditoria_y_solo_para_quien_toca(
    cliente: AsyncClient,
    cliente_mcp: AsyncClient,
    organizacion: OrganizacionDePrueba,
    otra_organizacion: OrganizacionDePrueba,
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    creada = await _crear_clave(cliente, cabeceras, scopes=["eventos:editar"])
    await _herramienta(
        cliente_mcp,
        creada["api_key"],
        "crear_evento",
        slug="para-el-historial",
        titulo="Historial",
        inicio=(AHORA + timedelta(days=5)).isoformat(),
        fin=(AHORA + timedelta(days=6)).isoformat(),
    )
    id_conexion = creada["connection"]["id"]

    propio = await cliente.get(f"{CONEXIONES}/{id_conexion}/history", headers=cabeceras)
    _, cabeceras_b = await iniciar_sesion(cliente, otra_organizacion)
    ajeno = await cliente.get(f"{DE_LA_ORGANIZACION}/{id_conexion}/history", headers=cabeceras_b)

    assert propio.status_code == 200
    assert [a["action"] for a in propio.json()] == ["mcp.crear_evento"]
    assert "connection_id" not in propio.json()[0]["detail"]
    assert ajeno.status_code == 404
