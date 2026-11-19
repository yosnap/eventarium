"""Idioma en el servidor MCP: leer traducido, escribir traducciones a mano y la
herramienta `traducir_evento`."""

from __future__ import annotations

from datetime import timedelta

from httpx import AsyncClient

from tests.conftest import OrganizacionDePrueba, iniciar_sesion
from tests.mcp_test_helpers import AHORA, _crear_clave, _datos, _evento, _herramienta, _rpc

ORGANIZACION = "/api/v1/organizations/me"


async def _bilingue(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, slug: str
) -> tuple[dict[str, str], dict, str]:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    activado = await cliente.patch(
        ORGANIZACION, headers=cabeceras, json={"content_locales": ["es-ES", "en-US"]}
    )
    assert activado.status_code == 200, activado.text
    evento = await _evento(cliente, cabeceras, slug)
    clave = (
        await _crear_clave(
            cliente, cabeceras, scopes=["eventos:leer", "eventos:editar", "patrocinadores:editar"]
        )
    )["api_key"]
    return cabeceras, evento, clave


async def test_editar_en_otro_idioma_guarda_la_traduccion_sin_tocar_el_original(
    cliente: AsyncClient, cliente_mcp: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, evento, clave = await _bilingue(cliente, organizacion, "mcp-idioma-editar")

    editado = _datos(
        await _herramienta(
            cliente_mcp,
            clave,
            "editar_evento",
            event_id=evento["id"],
            titulo="Event in English",
            aforo=80,
            idioma="en",
        )
    )
    # El original no cambia; lo que no es texto, sí.
    assert editado["titulo"] == evento["title"]
    assert editado["aforo"] == 80

    en_ingles = _datos(
        await _herramienta(cliente_mcp, clave, "ver_evento", event_id=evento["id"], idioma="en-US")
    )
    assert en_ingles["titulo"] == "Event in English"
    assert en_ingles["idioma_original"] == "es-ES"
    assert en_ingles["idioma_servido"] == "en-US"
    assert "en-US" in en_ingles["idiomas_al_dia"]

    original = _datos(await _herramienta(cliente_mcp, clave, "ver_evento", event_id=evento["id"]))
    assert original["titulo"] == evento["title"]
    assert original["idioma_servido"] is None

    listado = _datos(await _herramienta(cliente_mcp, clave, "listar_eventos", idioma="en-US"))
    assert {"Event in English"} <= {e["titulo"] for e in listado}


async def test_traducir_solo_textos_de_una_sesion_no_la_cambia(
    cliente: AsyncClient, cliente_mcp: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, evento, clave = await _bilingue(cliente, organizacion, "mcp-idioma-sesion")
    sesion = _datos(
        await _herramienta(
            cliente_mcp,
            clave,
            "anadir_sesion",
            event_id=evento["id"],
            titulo="Apertura",
            inicio=(AHORA + timedelta(days=10, hours=1)).isoformat(),
            fin=(AHORA + timedelta(days=10, hours=2)).isoformat(),
            idioma="es-ES",
        )
    )

    traducida = _datos(
        await _herramienta(
            cliente_mcp,
            clave,
            "editar_sesion",
            event_id=evento["id"],
            session_id=sesion["id"],
            titulo="Opening",
            idioma="en-US",
        )
    )
    assert traducida["titulo"] == "Apertura"

    detalle = _datos(
        await _herramienta(cliente_mcp, clave, "ver_evento", event_id=evento["id"], idioma="en-US")
    )
    assert [s["titulo"] for s in detalle["sesiones"]] == ["Opening"]


async def test_crear_contenido_en_otro_idioma_que_el_original_se_rechaza(
    cliente: AsyncClient, cliente_mcp: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, evento, clave = await _bilingue(cliente, organizacion, "mcp-idioma-crear")

    respuesta = await _rpc(
        cliente_mcp,
        clave,
        "tools/call",
        {
            "name": "anadir_sede",
            "arguments": {"event_id": evento["id"], "nombre": "Main hall", "idioma": "en"},
        },
    )
    resultado = respuesta.json()["result"]
    assert resultado["isError"] is True
    assert "es-ES" in resultado["content"][0]["text"]

    desconocido = await _herramienta(
        cliente_mcp, clave, "ver_evento", event_id=evento["id"], idioma="klingon"
    )
    assert desconocido["isError"] is True


async def test_crear_evento_con_idioma_lo_escribe_en_ese_idioma(
    cliente: AsyncClient, cliente_mcp: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, _, clave = await _bilingue(cliente, organizacion, "mcp-idioma-base")

    creado = _datos(
        await _herramienta(
            cliente_mcp,
            clave,
            "crear_evento",
            slug="mcp-en-ingles",
            titulo="Written in English",
            inicio=(AHORA + timedelta(days=5)).isoformat(),
            fin=(AHORA + timedelta(days=6)).isoformat(),
            idioma="en-US",
        )
    )
    assert creado["idioma_original"] == "en-US"


async def test_traducir_evento_da_el_estado_y_sin_clave_propia_no_lanza(
    cliente: AsyncClient, cliente_mcp: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, evento, clave = await _bilingue(cliente, organizacion, "mcp-idioma-estado")
    await _herramienta(
        cliente_mcp, clave, "editar_evento", event_id=evento["id"], titulo="Event", idioma="en"
    )

    estado = _datos(
        await _herramienta(
            cliente_mcp, clave, "traducir_evento", event_id=evento["id"], idioma="en-US"
        )
    )
    assert estado["idioma_original"] == "es-ES"
    assert estado["textos"] >= 1
    assert estado["al_dia"] == 1
    assert estado["en_cola"] is False
    assert estado["traduccion_automatica"] is False

    lanzar = await _herramienta(
        cliente_mcp,
        clave,
        "traducir_evento",
        event_id=evento["id"],
        idioma="en-US",
        accion="lanzar",
    )
    assert lanzar["isError"] is True
    assert "clave" in lanzar["content"][0]["text"]

    al_original = await _herramienta(
        cliente_mcp, clave, "traducir_evento", event_id=evento["id"], idioma="es-ES"
    )
    assert al_original["isError"] is True
