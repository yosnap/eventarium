"""`POST /organizations/me/media` — subida por fichero y por URL, con el
SSRF comprobado a nivel de endpoint (no solo la función unitaria de
`app/modules/media/ssrf.py`, que ya tiene su propia suite)."""

from __future__ import annotations

import base64
import io
import socket
from unittest.mock import AsyncMock, patch

import httpx
from httpx import AsyncClient
from PIL import Image

from app.core.permissions import Permission
from tests.conftest import (
    OrganizacionDePrueba,
    crear_rol,
    crear_usuario_con_rol,
    iniciar_sesion,
    iniciar_sesion_con,
)

MEDIA = "/api/v1/organizations/me/media"

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def _png_grande(ancho: int, alto: int) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (ancho, alto), color=(10, 20, 30)).save(buffer, format="PNG")
    return buffer.getvalue()


async def test_subir_por_fichero_crea_una_fila_en_la_biblioteca(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    respuesta = await cliente.post(
        MEDIA,
        headers=cabeceras,
        data={"kind": "branding"},
        files={"fichero": ("logo.png", PNG, "image/png")},
    )
    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["kind"] == "branding"
    assert cuerpo["url"]


async def test_subir_sin_el_permiso_del_kind_da_403(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    await crear_rol(organizacion, key="solo-eventos", permisos=[Permission.EVENTS_WRITE])
    correo, contrasena = await crear_usuario_con_rol(organizacion, "solo-eventos")
    _, cabeceras = await iniciar_sesion_con(cliente, organizacion, correo, contrasena)

    respuesta = await cliente.post(
        MEDIA,
        headers=cabeceras,
        data={"kind": "branding"},
        files={"fichero": ("logo.png", PNG, "image/png")},
    )
    assert respuesta.status_code == 403, respuesta.text


_HOST_DE_PRUEBA = "ejemplo-de-prueba.invalid"
_GETADDRINFO_REAL = socket.getaddrinfo


def _resolucion_dns_publica_falsa(host: str, *args: object, **kwargs: object) -> list[tuple]:
    """Sustituye `socket.getaddrinfo` SOLO para `_HOST_DE_PRUEBA` — es un
    patch sobre el módulo `socket` global (`ssrf.py` hace `import socket`,
    no una copia), así que debe reenviar cualquier otro host (el almacén
    local en `localhost`, p. ej.) a la función real o rompe subidas que no
    tienen nada que ver con esta prueba. Un host de prueba resuelve a una IP
    pública genuina — los rangos TEST-NET (203.0.113.0/24 y similares)
    cuentan como `is_private` en el propio módulo `ipaddress`, así que no
    sirven aquí."""
    if host == _HOST_DE_PRUEBA:
        return [(2, 1, 6, "", ("93.184.216.34", 0))]
    return _GETADDRINFO_REAL(host, *args, **kwargs)


async def test_subir_por_url_descarga_y_reprocesa_sin_guardar_la_url_externa(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    respuesta_falsa = httpx.Response(200, content=PNG, request=httpx.Request("GET", "https://x"))

    with (
        patch("app.modules.media.ssrf.socket.getaddrinfo", new=_resolucion_dns_publica_falsa),
        patch("httpx.AsyncClient.get", new=AsyncMock(return_value=respuesta_falsa)),
    ):
        respuesta = await cliente.post(
            MEDIA,
            headers=cabeceras,
            json={"kind": "branding", "url": "https://ejemplo-de-prueba.invalid/logo.png"},
        )
    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert "ejemplo-de-prueba.invalid" not in cuerpo["url"]


async def test_subir_por_url_rechaza_una_redireccion_sin_seguirla(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    redireccion = httpx.Response(
        302,
        headers={"location": "https://otro-sitio.invalid/logo.png"},
        request=httpx.Request("GET", "https://x"),
    )

    with (
        patch("app.modules.media.ssrf.socket.getaddrinfo", new=_resolucion_dns_publica_falsa),
        patch("httpx.AsyncClient.get", new=AsyncMock(return_value=redireccion)),
    ):
        respuesta = await cliente.post(
            MEDIA,
            headers=cabeceras,
            json={"kind": "branding", "url": "https://ejemplo-de-prueba.invalid/logo.png"},
        )
    assert respuesta.status_code == 422, respuesta.text


async def test_subir_por_url_a_una_ip_privada_se_rechaza_sin_llegar_a_la_red(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    with patch("httpx.AsyncClient.get", new=AsyncMock()) as descarga:
        respuesta = await cliente.post(
            MEDIA,
            headers=cabeceras,
            json={"kind": "branding", "url": "https://169.254.169.254/latest/meta-data"},
        )
    assert respuesta.status_code == 422, respuesta.text
    descarga.assert_not_called()


async def test_un_logo_de_branding_se_procesa_con_el_perfil_logo(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    """Regresión: `KIND_A_PERFIL` — sin él, toda subida usaba el perfil por
    defecto de la firma (`"default"`, 1920×1920) sin importar el `kind`, y un
    logo ocupaba y pesaba como una portada."""
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    respuesta = await cliente.post(
        MEDIA,
        headers=cabeceras,
        data={"kind": "branding"},
        files={"fichero": ("logo.png", _png_grande(2000, 2000), "image/png")},
    )
    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["width"] <= 800
    assert cuerpo["height"] <= 800


async def test_una_portada_de_evento_se_procesa_con_el_perfil_default(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    respuesta = await cliente.post(
        MEDIA,
        headers=cabeceras,
        data={"kind": "events"},
        files={"fichero": ("portada.png", _png_grande(2000, 1000), "image/png")},
    )
    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["width"] == 1920
