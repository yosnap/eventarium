"""`GET /ai/catalog` y `GET /admin/ai-usage`, que alimentan los dos paneles.

El catálogo es el que valida el `PUT`, serializado: si alguien añadiera un
proveedor a `proveedores.py` sin tocar nada más, el desplegable lo vería.
El uso agregado es la única consulta de uso que cruza organizaciones, y solo
la puede pedir el admin.
"""

from __future__ import annotations

from decimal import Decimal

from httpx import AsyncClient

from app.modules.ai_gateway import client as ai_client
from app.modules.ai_gateway import repository
from app.modules.ai_gateway.proveedores import PROVEEDORES
from tests.ai_gateway_test_helpers import (
    ProveedorSimulado,
    cabeceras_de_superadmin,
    configurar_plataforma,
)
from tests.conftest import OrganizacionDePrueba, iniciar_sesion

CATALOGO = "/api/v1/ai/catalog"
USO_DE_PLATAFORMA = "/api/v1/admin/ai-usage"

MENSAJES = [{"role": "user", "content": "hola"}]


async def test_el_catalogo_sale_entero_del_modulo_de_proveedores(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    respuesta = await cliente.get(CATALOGO, headers=cabeceras)

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    # Mismas claves y mismo orden que el catálogo cerrado: una sola lista.
    assert [entrada["clave"] for entrada in cuerpo] == list(PROVEEDORES)
    por_clave = {entrada["clave"]: entrada for entrada in cuerpo}
    nan = por_clave["nan_builders"]
    assert nan["api_base_fijo"] == "https://api.nan.builders/v1"
    assert nan["api_base_editable"] is False
    assert nan["coste_auditable"] is False
    assert [modelo["clave"] for modelo in nan["modelos"]] == [
        modelo.clave for modelo in PROVEEDORES["nan_builders"].modelos
    ]
    # La marca de visión viaja por modelo: es lo que el panel no puede inventar.
    assert por_clave["openai"]["modelos"][0]["vision"] is True
    assert nan["modelos"][0]["vision"] is False
    # `custom` es el único con modelo escrito a mano y dirección editable.
    assert por_clave["custom"]["modelos_abiertos"] is True
    assert por_clave["custom"]["api_base_editable"] is True


async def test_el_catalogo_exige_sesion(cliente: AsyncClient) -> None:
    respuesta = await cliente.get(CATALOGO)

    assert respuesta.status_code == 401


async def test_el_uso_agregado_suma_el_gasto_de_la_instalacion(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    cifrado: str,
    proveedor_simulado: ProveedorSimulado,
    dns_publico: None,
) -> None:
    await configurar_plataforma(techo_usd=Decimal("25"))
    await ai_client.completar(
        organization_id=organizacion.id, use_case="accounting_ocr", messages=MENSAJES
    )
    cabeceras = await cabeceras_de_superadmin(cliente, organizacion)

    respuesta = await cliente.get(USO_DE_PLATAFORMA, headers=cabeceras)

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["periodo"] == repository.periodo_actual()
    assert cuerpo["llamadas"] == 1
    assert cuerpo["llamadas_fallidas"] == 0
    assert Decimal(cuerpo["monthly_ceiling_usd"]) == Decimal("25")
    # `nan_builders` está fuera del mapa de precios: el total es orientativo.
    assert cuerpo["gasto_auditable"] is False
    assert cuerpo["ultimos"][0]["organization_id"] == str(organizacion.id)


async def test_el_uso_agregado_es_solo_del_admin(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    respuesta = await cliente.get(USO_DE_PLATAFORMA, headers=cabeceras)

    assert respuesta.status_code == 403
