"""MCP: categoría y etiquetas al crear y editar eventos, y filtros al listarlos.

Mismo montaje que `test_mcp_escritura.py`: llamadas JSON-RPC directas a `/mcp`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient

from tests.conftest import OrganizacionDePrueba
from tests.mcp_test_helpers import _crear_clave, _datos, _herramienta
from tests.test_events_categorias import _crear_categoria, _superadmin

AHORA = datetime.now(UTC).replace(microsecond=0)
AMBITOS = ["eventos:leer", "eventos:editar"]


async def _crear(cliente_mcp: AsyncClient, clave: str, slug: str, **extra: object) -> dict:
    return await _herramienta(
        cliente_mcp,
        clave,
        "crear_evento",
        slug=slug,
        titulo=f"Evento {slug}",
        inicio=(AHORA + timedelta(days=5)).isoformat(),
        fin=(AHORA + timedelta(days=6)).isoformat(),
        **extra,
    )


async def _preparar(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> tuple[str, dict[str, str]]:
    cabeceras = await _superadmin(cliente, organizacion)
    clave = (await _crear_clave(cliente, cabeceras, scopes=AMBITOS))["api_key"]
    return clave, cabeceras


async def test_crear_y_editar_con_categoria_y_etiquetas(
    cliente: AsyncClient, cliente_mcp: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    clave, cabeceras = await _preparar(cliente, organizacion)
    await _crear_categoria(cliente, cabeceras, "taller")
    await _crear_categoria(cliente, cabeceras, "charla")

    creado = _datos(
        await _crear(
            cliente_mcp, clave, "con-categoria", categoria="taller", etiquetas=["IA", "ia"]
        )
    )
    assert creado["categoria"] == "taller"
    assert creado["etiquetas"] == ["ia"]

    # Sin `categoria` ni `etiquetas`, no se toca nada.
    sin_tocar = _datos(
        await _herramienta(
            cliente_mcp, clave, "editar_evento", event_id=creado["id"], titulo="Otro título"
        )
    )
    assert (sin_tocar["categoria"], sin_tocar["etiquetas"]) == ("taller", ["ia"])

    cambiada = _datos(
        await _herramienta(
            cliente_mcp,
            clave,
            "editar_evento",
            event_id=creado["id"],
            categoria="charla",
            etiquetas=["datos", "python"],
        )
    )
    assert (cambiada["categoria"], cambiada["etiquetas"]) == ("charla", ["datos", "python"])

    quitada = _datos(
        await _herramienta(
            cliente_mcp, clave, "editar_evento", event_id=creado["id"], categoria="", etiquetas=[]
        )
    )
    assert (quitada["categoria"], quitada["etiquetas"]) == (None, [])


async def test_rechaza_categoria_inactiva_inexistente_y_etiquetas_invalidas(
    cliente: AsyncClient, cliente_mcp: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    clave, cabeceras = await _preparar(cliente, organizacion)
    await _crear_categoria(cliente, cabeceras, "vieja", is_active=False)
    await _crear_categoria(cliente, cabeceras, "taller")
    evento = _datos(await _crear(cliente_mcp, clave, "rechazos"))

    for categoria in ("vieja", "no-existe"):
        assert (await _crear(cliente_mcp, clave, f"x-{categoria}", categoria=categoria))[
            "isError"
        ] is True
        assert (
            await _herramienta(
                cliente_mcp, clave, "editar_evento", event_id=evento["id"], categoria=categoria
            )
        )["isError"] is True
    for etiquetas in (["#ia"], ["a"], ["uno", "dos", "tres", "cuatro", "cinco", "seis"]):
        assert (
            await _herramienta(
                cliente_mcp, clave, "editar_evento", event_id=evento["id"], etiquetas=etiquetas
            )
        )["isError"] is True

    # Ninguno de los rechazos dejó cambios.
    sigue = _datos(await _herramienta(cliente_mcp, clave, "ver_evento", event_id=evento["id"]))
    assert (sigue["categoria"], sigue["etiquetas"]) == (None, [])


async def test_categoria_que_se_desactiva_se_conserva_al_editar_otros_datos(
    cliente: AsyncClient, cliente_mcp: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    clave, cabeceras = await _preparar(cliente, organizacion)
    categoria = await _crear_categoria(cliente, cabeceras, "taller")
    evento = _datos(await _crear(cliente_mcp, clave, "conserva", categoria="taller"))
    desactivada = await cliente.patch(
        f"/api/v1/admin/event-categories/{categoria['id']}",
        headers=cabeceras,
        json={"is_active": False},
    )
    assert desactivada.status_code == 200, desactivada.text

    editado = _datos(
        await _herramienta(
            cliente_mcp, clave, "editar_evento", event_id=evento["id"], titulo="Sigue con ella"
        )
    )
    assert editado["categoria"] == "taller"
    # Y `listar_categorias` ya no la ofrece para asignar.
    assert _datos(await _herramienta(cliente_mcp, clave, "listar_categorias")) == []


async def test_listar_categorias_y_filtros_de_listar_eventos(
    cliente: AsyncClient, cliente_mcp: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    clave, cabeceras = await _preparar(cliente, organizacion)
    await _crear_categoria(cliente, cabeceras, "taller", display_order=2)
    await _crear_categoria(cliente, cabeceras, "charla", display_order=1)
    await _crear(cliente_mcp, clave, "ev-a", categoria="taller", etiquetas=["ia", "datos"])
    await _crear(cliente_mcp, clave, "ev-b", categoria="charla", etiquetas=["ia"])
    await _crear(cliente_mcp, clave, "ev-c")

    categorias = _datos(await _herramienta(cliente_mcp, clave, "listar_categorias"))
    assert [c["slug"] for c in categorias] == ["charla", "taller"]

    async def slugs(**filtros: object) -> set[str]:
        resultado = await _herramienta(cliente_mcp, clave, "listar_eventos", **filtros)
        return {e["slug"] for e in _datos(resultado)}

    assert await slugs() == {"ev-a", "ev-b", "ev-c"}
    assert await slugs(categoria="taller") == {"ev-a"}
    assert await slugs(etiquetas=["ia"]) == {"ev-a", "ev-b"}
    assert await slugs(etiquetas=["ia", "datos"]) == {"ev-a"}
    assert await slugs(categoria="charla", etiquetas=["datos"]) == set()

    demasiadas = await _herramienta(
        cliente_mcp, clave, "listar_eventos", etiquetas=["uno", "dos", "tres", "cuatro"]
    )
    assert demasiadas["isError"] is True

    for desconocida in ("no-existe", "taller-viejo"):
        error = await _herramienta(cliente_mcp, clave, "listar_eventos", categoria=desconocida)
        assert error["isError"] is True
