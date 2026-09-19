"""Papelera (`DELETE`/`restore`) y recorte (`PATCH .../crop`) de la biblioteca
de medios. El borrado comprueba referencias en las 3 tablas de dominio antes
de aceptar; el recorte crea siempre una fila nueva, nunca muta la original."""

from __future__ import annotations

import base64

from httpx import AsyncClient

from tests.conftest import OrganizacionDePrueba, iniciar_sesion

MEDIA = "/api/v1/organizations/me/media"
BRANDING_LOGO = "/api/v1/organizations/me/branding/logo"

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


async def _subir(cliente: AsyncClient, cabeceras: dict[str, str], kind: str) -> dict:
    respuesta = await cliente.post(
        MEDIA,
        headers=cabeceras,
        data={"kind": kind},
        files={"fichero": ("i.png", PNG, "image/png")},
    )
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


async def test_borrar_una_imagen_no_usada_la_envia_a_la_papelera(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    subido = await _subir(cliente, cabeceras, "branding")

    borrado = await cliente.delete(f"{MEDIA}/{subido['id']}", headers=cabeceras)
    assert borrado.status_code == 204, borrado.text

    listado = await cliente.get(f"{MEDIA}?kind=branding", headers=cabeceras)
    assert listado.json()["total"] == 0


async def test_borrar_una_imagen_en_uso_da_409_con_el_recurso_que_la_usa(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    subido = await _subir(cliente, cabeceras, "branding")
    asignado = await cliente.put(BRANDING_LOGO, headers=cabeceras, json={"media_id": subido["id"]})
    assert asignado.status_code == 200, asignado.text

    borrado = await cliente.delete(f"{MEDIA}/{subido['id']}", headers=cabeceras)
    assert borrado.status_code == 409, borrado.text
    cuerpo = borrado.json()
    assert cuerpo["used_by"][0]["tipo"] == "branding"


async def test_restaurar_una_imagen_de_la_papelera(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    subido = await _subir(cliente, cabeceras, "branding")
    await cliente.delete(f"{MEDIA}/{subido['id']}", headers=cabeceras)

    restaurado = await cliente.post(f"{MEDIA}/{subido['id']}/restore", headers=cabeceras)
    assert restaurado.status_code == 200, restaurado.text

    listado = await cliente.get(f"{MEDIA}?kind=branding", headers=cabeceras)
    assert listado.json()["total"] == 1


async def test_recortar_crea_una_fila_nueva_y_no_toca_la_original(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    subido = await _subir(cliente, cabeceras, "branding")

    recortado = await cliente.patch(
        f"{MEDIA}/{subido['id']}/crop",
        headers=cabeceras,
        json={"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0},
    )
    assert recortado.status_code == 200, recortado.text
    assert recortado.json()["id"] != subido["id"]

    listado = await cliente.get(f"{MEDIA}?kind=branding", headers=cabeceras)
    ids = {f["id"] for f in listado.json()["items"]}
    assert {subido["id"], recortado.json()["id"]} <= ids


async def test_editar_metadatos_de_una_imagen(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    subido = await _subir(cliente, cabeceras, "branding")

    editado = await cliente.patch(
        f"{MEDIA}/{subido['id']}", headers=cabeceras, json={"alt": "Logotipo de la organización"}
    )
    assert editado.status_code == 200, editado.text
    assert editado.json()["alt"] == "Logotipo de la organización"
