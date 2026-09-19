"""CRUD de carpetas de la biblioteca de medios de organización — el permiso
requerido es el de escritura del `kind` de la carpeta."""

from __future__ import annotations

from httpx import AsyncClient

from app.core.permissions import Permission
from tests.conftest import (
    OrganizacionDePrueba,
    crear_rol,
    crear_usuario_con_rol,
    iniciar_sesion,
    iniciar_sesion_con,
)

MEDIA_FOLDERS = "/api/v1/organizations/me/media-folders"


async def test_crear_y_listar_una_carpeta(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    creada = await cliente.post(
        MEDIA_FOLDERS,
        headers=cabeceras,
        json={"name": "Redes sociales", "slug": "redes-sociales", "kind": "branding"},
    )
    assert creada.status_code == 200, creada.text
    assert creada.json()["name"] == "Redes sociales"

    listado = await cliente.get(MEDIA_FOLDERS, headers=cabeceras)
    assert listado.status_code == 200, listado.text
    assert any(c["slug"] == "redes-sociales" for c in listado.json())


async def test_crear_una_carpeta_sin_el_permiso_del_kind_da_403(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    await crear_rol(organizacion, key="solo-eventos", permisos=[Permission.EVENTS_WRITE])
    correo, contrasena = await crear_usuario_con_rol(organizacion, "solo-eventos")
    _, cabeceras = await iniciar_sesion_con(cliente, organizacion, correo, contrasena)

    respuesta = await cliente.post(
        MEDIA_FOLDERS,
        headers=cabeceras,
        json={"name": "Logotipos", "slug": "logotipos", "kind": "branding"},
    )
    assert respuesta.status_code == 403, respuesta.text


async def test_crear_una_carpeta_con_un_kind_no_admitido_da_422(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    respuesta = await cliente.post(
        MEDIA_FOLDERS,
        headers=cabeceras,
        json={"name": "Lo que sea", "slug": "lo-que-sea", "kind": "lo-que-sea"},
    )
    assert respuesta.status_code == 422, respuesta.text
