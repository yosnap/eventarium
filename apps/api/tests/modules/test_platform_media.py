"""Biblioteca de medios de plataforma (`/admin/platform/media*`) — subida por
fichero y por URL, con el mismo dispatch manual por `Content-Type` que
`POST /organizations/me/media` (Fase 2)."""

from __future__ import annotations

import base64
import io
from unittest.mock import AsyncMock, patch

import httpx
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import update

from app.core.database import SessionMaintenance
from app.modules.users.models import User
from tests.conftest import OrganizacionDePrueba, iniciar_sesion

PLATFORM_MEDIA = "/api/v1/admin/platform/media"

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


async def _hacer_superadmin(email: str) -> None:
    async with SessionMaintenance() as session:
        await session.execute(update(User).where(User.email == email).values(is_superadmin=True))
        await session.commit()


async def _superadmin_headers(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> dict[str, str]:
    await _hacer_superadmin(organizacion.owner_email)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    return cabeceras


async def test_subir_por_fichero_a_la_biblioteca_de_plataforma(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    cabeceras = await _superadmin_headers(cliente, organizacion)
    respuesta = await cliente.post(
        PLATFORM_MEDIA, headers=cabeceras, files={"fichero": ("logo.png", PNG, "image/png")}
    )
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["kind"] == "platform"


async def test_subir_por_url_a_la_biblioteca_de_plataforma(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    cabeceras = await _superadmin_headers(cliente, organizacion)
    respuesta_falsa = httpx.Response(200, content=PNG, request=httpx.Request("GET", "https://x"))

    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=respuesta_falsa)):
        respuesta = await cliente.post(
            PLATFORM_MEDIA, headers=cabeceras, json={"url": "https://169.254.169.254/x"}
        )
    # La IP de metadata se rechaza antes de llegar al mock — confirma que la
    # rama JSON reutiliza `validar_url_publica_segura`, no solo la de fichero.
    assert respuesta.status_code == 422, respuesta.text


async def test_listar_y_borrar_en_la_biblioteca_de_plataforma(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    cabeceras = await _superadmin_headers(cliente, organizacion)
    subido = await cliente.post(
        PLATFORM_MEDIA, headers=cabeceras, files={"fichero": ("logo.png", PNG, "image/png")}
    )
    assert subido.status_code == 200, subido.text
    media_id = subido.json()["id"]

    listado = await cliente.get(PLATFORM_MEDIA, headers=cabeceras)
    assert listado.status_code == 200, listado.text
    assert any(item["id"] == media_id for item in listado.json()["items"])

    borrado = await cliente.delete(f"{PLATFORM_MEDIA}/{media_id}", headers=cabeceras)
    assert borrado.status_code == 204, borrado.text


async def test_la_biblioteca_de_plataforma_procesa_siempre_con_el_perfil_logo(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    cabeceras = await _superadmin_headers(cliente, organizacion)
    buffer = io.BytesIO()
    Image.new("RGB", (2000, 2000), color=(10, 20, 30)).save(buffer, format="PNG")

    respuesta = await cliente.post(
        PLATFORM_MEDIA,
        headers=cabeceras,
        files={"fichero": ("logo.png", buffer.getvalue(), "image/png")},
    )
    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["width"] <= 800
    assert cuerpo["height"] <= 800
