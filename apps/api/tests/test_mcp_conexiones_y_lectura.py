"""Servidor MCP: conexiones por clave de API y herramientas de solo lectura.

El `cliente` de `conftest` no ejecuta el `lifespan`, y el gestor de sesiones
del MCP solo funciona dentro de él: `cliente_mcp` monta una app nueva con su
propio servidor MCP en marcha. Las llamadas son JSON-RPC directas a `/mcp`,
como las haría cualquier cliente.
"""

from __future__ import annotations

import inspect
import json
import uuid

from httpx import AsyncClient
from sqlalchemy import delete, select

from app.core.database import SessionMaintenance
from app.modules.mcp import herramientas_lectura, server
from app.modules.mcp import service as mcp_service
from app.modules.roles.models import RolePermission
from app.modules.users.models import User
from tests.conftest import OrganizacionDePrueba, crear_miembro, iniciar_sesion, iniciar_sesion_con
from tests.mcp_test_helpers import CONEXIONES, _crear_clave, _datos, _evento, _herramienta, _rpc


class TestClaves:
    async def test_la_clave_se_enseña_una_sola_vez(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        creada = await _crear_clave(cliente, cabeceras)
        listado = await cliente.get(CONEXIONES, headers=cabeceras)

        assert creada["api_key"].startswith("evtm_")
        assert creada["mcp_url"].endswith("/mcp")
        assert creada["connection"]["scopes"] == ["eventos:leer", "inscripciones:cifras"]
        assert creada["api_key"] not in listado.text
        assert listado.json()[0]["key_prefix"] == creada["api_key"][:12]

    async def test_un_organizador_sin_el_permiso_no_puede_conectar(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        miembro = await crear_miembro(organizacion, "organizer")
        _, cabeceras = await iniciar_sesion_con(
            cliente, organizacion, miembro.email, miembro.password
        )

        respuesta = await cliente.post(CONEXIONES, headers=cabeceras, json={"name": "Claude"})

        assert respuesta.status_code == 403

    async def test_no_se_puede_limitar_a_eventos_de_otra_organizacion(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        respuesta = await cliente.post(
            CONEXIONES, headers=cabeceras, json={"name": "Claude", "event_ids": [str(uuid.uuid4())]}
        )
        assert respuesta.status_code == 422


class TestAutenticacion:
    async def test_sin_clave_responde_401_con_los_metadatos_del_recurso(
        self, cliente_mcp: AsyncClient
    ) -> None:
        respuesta = await _rpc(cliente_mcp, None, "tools/list")
        metadatos = await cliente_mcp.get("/.well-known/oauth-protected-resource/mcp")

        assert respuesta.status_code == 401
        assert "resource_metadata=" in respuesta.headers["www-authenticate"]
        assert metadatos.json()["resource"].endswith("/mcp")

    async def test_revocar_la_conexion_corta_la_siguiente_llamada(
        self, cliente: AsyncClient, cliente_mcp: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        creada = await _crear_clave(cliente, cabeceras)
        antes = await _rpc(cliente_mcp, creada["api_key"], "tools/list")

        await cliente.delete(f"{CONEXIONES}/{creada['connection']['id']}", headers=cabeceras)
        despues = await _rpc(cliente_mcp, creada["api_key"], "tools/list")

        assert antes.status_code == 200
        assert {h["name"] for h in antes.json()["result"]["tools"]} >= {
            "listar_eventos",
            "ver_evento",
            "cifras_de_inscripcion",
        }
        assert despues.status_code == 401

    async def test_perder_el_permiso_o_la_cuenta_corta_la_conexion(
        self, cliente: AsyncClient, cliente_mcp: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        clave = (await _crear_clave(cliente, cabeceras))["api_key"]

        async with SessionMaintenance() as session:
            await session.execute(
                delete(RolePermission).where(
                    RolePermission.role_id == organizacion.owner_role_id,
                    RolePermission.permission == "mcp:connect",
                )
            )
            await session.commit()
        sin_permiso = await _rpc(cliente_mcp, clave, "tools/list")

        assert sin_permiso.status_code == 401

    async def test_cambiar_la_contraseña_revoca_las_conexiones(
        self, cliente: AsyncClient, cliente_mcp: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        clave = (await _crear_clave(cliente, cabeceras))["api_key"]

        async with SessionMaintenance() as session:
            await mcp_service.revocar_todas_de_persona(session, organizacion.owner_id)
            await session.commit()

        assert (await _rpc(cliente_mcp, clave, "tools/list")).status_code == 401

    async def test_una_cuenta_desactivada_no_entra(
        self, cliente: AsyncClient, cliente_mcp: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        clave = (await _crear_clave(cliente, cabeceras))["api_key"]

        async with SessionMaintenance() as session:
            usuario = await session.scalar(select(User).where(User.id == organizacion.owner_id))
            usuario.is_active = False
            await session.commit()

        assert (await _rpc(cliente_mcp, clave, "tools/list")).status_code == 401


class TestHerramientasDeLectura:
    async def test_una_conexion_limitada_solo_ve_sus_eventos(
        self, cliente: AsyncClient, cliente_mcp: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        permitido = await _evento(cliente, cabeceras, "mcp-permitido")
        ajeno = await _evento(cliente, cabeceras, "mcp-ajeno")
        clave = (await _crear_clave(cliente, cabeceras, event_ids=[permitido["id"]]))["api_key"]

        listado = _datos(await _herramienta(cliente_mcp, clave, "listar_eventos"))
        fuera = await _herramienta(cliente_mcp, clave, "ver_evento", event_id=ajeno["id"])

        assert [e["slug"] for e in listado] == ["mcp-permitido"]
        assert fuera["isError"] is True
        assert "no existe" in json.dumps(fuera, ensure_ascii=False)

    async def test_ver_evento_y_cifras_no_llevan_datos_personales(
        self, cliente: AsyncClient, cliente_mcp: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _evento(cliente, cabeceras, "mcp-sin-datos")
        clave = (await _crear_clave(cliente, cabeceras))["api_key"]

        detalle = _datos(
            await _herramienta(cliente_mcp, clave, "ver_evento", event_id=evento["id"])
        )
        cifras = _datos(
            await _herramienta(cliente_mcp, clave, "cifras_de_inscripcion", event_id=evento["id"])
        )

        assert detalle["enlace_panel"].endswith(f"/dashboard/events/{evento['id']}")
        assert cifras["aforo"] == 50 and cifras["plazas_libres"] == 50
        for respuesta in (detalle, cifras):
            texto = json.dumps(respuesta)
            assert "@" not in texto and "email" not in texto and "phone" not in texto

    async def test_sin_el_ambito_la_herramienta_se_niega(
        self, cliente: AsyncClient, cliente_mcp: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _evento(cliente, cabeceras, "mcp-sin-ambito")
        clave = (await _crear_clave(cliente, cabeceras, scopes=["eventos:leer"]))["api_key"]

        resultado = await _herramienta(
            cliente_mcp, clave, "cifras_de_inscripcion", event_id=evento["id"]
        )

        assert resultado["isError"] is True


def test_todas_las_herramientas_pasan_por_preparar() -> None:
    """Contrato: toda herramienta empieza aplicando el contexto y el límite
    por conexión. Una herramienta nueva que se lo salte falla aquí."""
    servidor = server.crear_servidor()
    herramientas = servidor._tool_manager.list_tools()  # noqa: SLF001
    assert herramientas
    for herramienta in herramientas:
        fuente = inspect.getsource(herramienta.fn)
        assert "await preparar()" in fuente, herramienta.name
    assert herramientas_lectura.preparar
