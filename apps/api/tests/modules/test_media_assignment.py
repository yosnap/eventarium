"""Contrato `{media_id}` en los endpoints consumidores existentes (logo de
organización, portada de evento, logo de patrocinador) — fase 2 del plan
`260918-1944-biblioteca-de-medios`. Cubre la regla de reemplazo (no borrar el
objeto anterior cuando ya estaba gestionado por la biblioteca) y el
aislamiento por `kind`/organización al resolver un `media_id`.
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

from httpx import AsyncClient

from app.core.permissions import Permission
from tests.conftest import OrganizacionDePrueba, crear_rol, iniciar_sesion

MEDIA = "/api/v1/organizations/me/media"
BRANDING_LOGO = "/api/v1/organizations/me/branding/logo"
EVENTS = "/api/v1/events"

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

AHORA = datetime.now(UTC).replace(microsecond=0)


async def _subir_a_biblioteca(
    cliente: AsyncClient, cabeceras: dict[str, str], kind: str, nombre: str = "imagen.png"
) -> dict:
    respuesta = await cliente.post(
        MEDIA,
        headers=cabeceras,
        data={"kind": kind},
        files={"fichero": (nombre, PNG, "image/png")},
    )
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


async def _crear_evento(cliente: AsyncClient, cabeceras: dict[str, str], slug: str) -> dict:
    respuesta = await cliente.post(
        EVENTS,
        headers=cabeceras,
        json={
            "slug": slug,
            "title": f"Evento {slug}",
            "starts_at": AHORA.isoformat(),
            "ends_at": (AHORA + timedelta(days=2)).isoformat(),
            "location_mode": "in_person",
        },
    )
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


async def _crear_tier(cliente: AsyncClient, cabeceras: dict[str, str], name: str) -> dict:
    respuesta = await cliente.post(
        "/api/v1/organizations/me/sponsor-tiers",
        headers=cabeceras,
        json={"name": name, "display_order": 1, "logo_size": "large"},
    )
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


async def _crear_patrocinador(
    cliente: AsyncClient, cabeceras: dict[str, str], event_id: str, tier_id: str
) -> dict:
    respuesta = await cliente.post(
        f"{EVENTS}/{event_id}/sponsors",
        headers=cabeceras,
        json={
            "tier_id": tier_id,
            "name": "Patrocinador de prueba",
            "contribution_type": "en_especie",
            "contribution_description": "Espacio en el evento",
        },
    )
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


async def test_asignar_una_imagen_de_biblioteca_al_logo_de_branding(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    subido = await _subir_a_biblioteca(cliente, cabeceras, "branding")

    asignado = await cliente.put(BRANDING_LOGO, headers=cabeceras, json={"media_id": subido["id"]})
    assert asignado.status_code == 200, asignado.text
    assert asignado.json()["logo_url"] == subido["url"]


async def test_reemplazar_el_logo_gestionado_por_la_biblioteca_no_borra_el_objeto_anterior(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    primero = await _subir_a_biblioteca(cliente, cabeceras, "branding", "primero.png")
    segundo = await _subir_a_biblioteca(cliente, cabeceras, "branding", "segundo.png")

    asignado = await cliente.put(BRANDING_LOGO, headers=cabeceras, json={"media_id": primero["id"]})
    assert asignado.status_code == 200, asignado.text

    with patch(
        "app.core.storage.S3StorageProvider.delete_object", new_callable=AsyncMock
    ) as borrar:
        reemplazado = await cliente.put(
            BRANDING_LOGO, headers=cabeceras, json={"media_id": segundo["id"]}
        )
    assert reemplazado.status_code == 200, reemplazado.text
    assert reemplazado.json()["logo_url"] == segundo["url"]
    borrar.assert_not_called()


async def test_reemplazar_un_logo_heredado_por_uno_de_biblioteca_si_borra_el_objeto_anterior(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    """Cuando el logo anterior nunca pasó por la biblioteca (`logo_object_key`
    de siempre, sin `logo_media_id`), reemplazarlo sigue el comportamiento de
    siempre: se borra el objeto huérfano."""
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    heredado = await cliente.put(
        BRANDING_LOGO, headers=cabeceras, files={"fichero": ("legado.png", PNG, "image/png")}
    )
    assert heredado.status_code == 200, heredado.text

    nuevo = await _subir_a_biblioteca(cliente, cabeceras, "branding")
    with patch(
        "app.core.storage.S3StorageProvider.delete_object", new_callable=AsyncMock
    ) as borrar:
        asignado = await cliente.put(
            BRANDING_LOGO, headers=cabeceras, json={"media_id": nuevo["id"]}
        )
    assert asignado.status_code == 200, asignado.text
    borrar.assert_called_once()


async def test_asignar_un_media_de_otro_kind_al_logo_de_branding_falla(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    await crear_rol(
        organizacion,
        key="dueno-total",
        permisos=[Permission.BRANDING_WRITE, Permission.EVENTS_WRITE],
    )
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    de_eventos = await _subir_a_biblioteca(cliente, cabeceras, "events")

    respuesta = await cliente.put(
        BRANDING_LOGO, headers=cabeceras, json={"media_id": de_eventos["id"]}
    )
    assert respuesta.status_code == 422, respuesta.text


async def test_asignar_un_media_de_otra_organizacion_da_404(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    otra_organizacion: OrganizacionDePrueba,
) -> None:
    """RLS ya filtra la fila (`session.get(Media, ...)` no la ve), así que
    `obtener_visible` la trata como inexistente — no una 403 que confirmaría
    que el `media_id` existe en otra organización."""
    _, cabeceras_ajenas = await iniciar_sesion(cliente, otra_organizacion)
    de_otra_organizacion = await _subir_a_biblioteca(cliente, cabeceras_ajenas, "branding")

    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    respuesta = await cliente.put(
        BRANDING_LOGO, headers=cabeceras, json={"media_id": de_otra_organizacion["id"]}
    )
    assert respuesta.status_code == 404, respuesta.text


async def test_asignar_una_imagen_de_biblioteca_a_la_portada_de_un_evento(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_evento(cliente, cabeceras, "con-portada-de-biblioteca")
    subido = await _subir_a_biblioteca(cliente, cabeceras, "events")

    asignado = await cliente.put(
        f"{EVENTS}/{evento['id']}/cover", headers=cabeceras, json={"media_id": subido["id"]}
    )
    assert asignado.status_code == 200, asignado.text
    assert asignado.json()["cover_url"] == subido["url"]


async def test_reemplazar_la_portada_gestionada_por_la_biblioteca_no_borra_el_objeto_anterior(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_evento(cliente, cabeceras, "portada-reemplazada")
    primera = await _subir_a_biblioteca(cliente, cabeceras, "events", "primera.png")
    segunda = await _subir_a_biblioteca(cliente, cabeceras, "events", "segunda.png")

    asignada = await cliente.put(
        f"{EVENTS}/{evento['id']}/cover", headers=cabeceras, json={"media_id": primera["id"]}
    )
    assert asignada.status_code == 200, asignada.text

    with patch(
        "app.core.storage.S3StorageProvider.delete_object", new_callable=AsyncMock
    ) as borrar:
        reemplazada = await cliente.put(
            f"{EVENTS}/{evento['id']}/cover", headers=cabeceras, json={"media_id": segunda["id"]}
        )
    assert reemplazada.status_code == 200, reemplazada.text
    borrar.assert_not_called()


async def test_asignar_una_imagen_de_biblioteca_al_logo_de_un_patrocinador(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_evento(cliente, cabeceras, "con-patrocinador-de-biblioteca")
    nivel = await _crear_tier(cliente, cabeceras, "Oro")
    patrocinador = await _crear_patrocinador(cliente, cabeceras, evento["id"], nivel["id"])
    subido = await _subir_a_biblioteca(cliente, cabeceras, "sponsors")

    asignado = await cliente.put(
        f"{EVENTS}/{evento['id']}/sponsors/{patrocinador['id']}/logo",
        headers=cabeceras,
        json={"media_id": subido["id"]},
    )
    assert asignado.status_code == 200, asignado.text
    assert asignado.json()["logo_url"] == subido["url"]


async def test_reemplazar_el_logo_de_patrocinador_de_biblioteca_no_borra_el_objeto_anterior(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_evento(cliente, cabeceras, "patrocinador-logo-reemplazado")
    nivel = await _crear_tier(cliente, cabeceras, "Plata")
    patrocinador = await _crear_patrocinador(cliente, cabeceras, evento["id"], nivel["id"])
    primero = await _subir_a_biblioteca(cliente, cabeceras, "sponsors", "primero.png")
    segundo = await _subir_a_biblioteca(cliente, cabeceras, "sponsors", "segundo.png")

    asignado = await cliente.put(
        f"{EVENTS}/{evento['id']}/sponsors/{patrocinador['id']}/logo",
        headers=cabeceras,
        json={"media_id": primero["id"]},
    )
    assert asignado.status_code == 200, asignado.text

    with patch(
        "app.core.storage.S3StorageProvider.delete_object", new_callable=AsyncMock
    ) as borrar:
        reemplazado = await cliente.put(
            f"{EVENTS}/{evento['id']}/sponsors/{patrocinador['id']}/logo",
            headers=cabeceras,
            json={"media_id": segundo["id"]},
        )
    assert reemplazado.status_code == 200, reemplazado.text
    borrar.assert_not_called()
