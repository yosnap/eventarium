"""CRUD de eventos y agenda en el panel (fase 2 del PRD)."""

from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.orm import SessionTransaction

from tests.conftest import OrganizacionDePrueba, iniciar_sesion, iniciar_sesion_como

EVENTS = "/api/v1/events"

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

AHORA = datetime.now(UTC).replace(microsecond=0)


def _payload_evento(slug: str = "iawic-2026") -> dict:
    return {
        "slug": slug,
        "title": "IA Week in Cascais 2026",
        "starts_at": AHORA.isoformat(),
        "ends_at": (AHORA + timedelta(days=2)).isoformat(),
        "location_mode": "in_person",
    }


async def _crear_evento(
    cliente: AsyncClient, cabeceras: dict[str, str], **overrides: object
) -> dict:
    payload = _payload_evento()
    payload.update(overrides)
    respuesta = await cliente.post(EVENTS, headers=cabeceras, json=payload)
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


async def test_crear_editar_y_publicar_un_evento(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    evento = await _crear_evento(cliente, cabeceras)
    assert evento["status"] == "draft"

    edicion = await cliente.patch(
        f"{EVENTS}/{evento['id']}", headers=cabeceras, json={"title": "Nuevo título"}
    )
    assert edicion.status_code == 200
    assert edicion.json()["title"] == "Nuevo título"

    publicado = await cliente.patch(
        f"{EVENTS}/{evento['id']}", headers=cabeceras, json={"status": "published"}
    )
    assert publicado.status_code == 200
    assert publicado.json()["status"] == "published"


async def test_el_slug_es_unico_por_organizacion(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    await _crear_evento(cliente, cabeceras)

    repetido = await cliente.post(EVENTS, headers=cabeceras, json=_payload_evento())
    assert repetido.status_code == 409


async def test_un_evento_archivado_no_puede_volver_a_publicarse(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_evento(cliente, cabeceras)

    archivado = await cliente.patch(
        f"{EVENTS}/{evento['id']}", headers=cabeceras, json={"status": "archived"}
    )
    assert archivado.status_code == 200
    assert archivado.json()["status"] == "archived"

    reabierto = await cliente.patch(
        f"{EVENTS}/{evento['id']}", headers=cabeceras, json={"status": "draft"}
    )
    assert reabierto.status_code == 422


async def test_no_existe_delete_de_evento(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    """Un evento se archiva, no se borra: no hay ruta `DELETE /events/{id}`."""
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_evento(cliente, cabeceras)

    respuesta = await cliente.delete(f"{EVENTS}/{evento['id']}", headers=cabeceras)
    assert respuesta.status_code in (404, 405)


async def test_sin_events_write_no_se_puede_crear(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion_como(cliente, organizacion, "attendee")
    respuesta = await cliente.post(EVENTS, headers=cabeceras, json=_payload_evento())
    assert respuesta.status_code == 403


async def test_sin_events_read_no_se_puede_listar(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion_como(cliente, organizacion, "attendee")
    respuesta = await cliente.get(EVENTS, headers=cabeceras)
    assert respuesta.status_code == 403


async def test_crear_una_sesion_y_listar_la_agenda_ordenada(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_evento(cliente, cabeceras)

    tarde = await cliente.post(
        f"{EVENTS}/{evento['id']}/sessions",
        headers=cabeceras,
        json={
            "session_type": "talk",
            "title": "Charla de la tarde",
            "starts_at": (AHORA + timedelta(hours=6)).isoformat(),
            "ends_at": (AHORA + timedelta(hours=7)).isoformat(),
        },
    )
    assert tarde.status_code == 201

    manana = await cliente.post(
        f"{EVENTS}/{evento['id']}/sessions",
        headers=cabeceras,
        json={
            "session_type": "talk",
            "title": "Charla de la mañana",
            "starts_at": (AHORA + timedelta(hours=1)).isoformat(),
            "ends_at": (AHORA + timedelta(hours=2)).isoformat(),
        },
    )
    assert manana.status_code == 201

    agenda = await cliente.get(f"{EVENTS}/{evento['id']}/sessions", headers=cabeceras)
    assert agenda.status_code == 200
    titulos = [s["title"] for s in agenda.json()]
    assert titulos == ["Charla de la mañana", "Charla de la tarde"]


async def test_una_sesion_fuera_del_rango_del_evento_se_rechaza(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_evento(cliente, cabeceras)

    respuesta = await cliente.post(
        f"{EVENTS}/{evento['id']}/sessions",
        headers=cabeceras,
        json={
            "session_type": "talk",
            "title": "Charla fuera de rango",
            "starts_at": (AHORA + timedelta(days=10)).isoformat(),
            "ends_at": (AHORA + timedelta(days=10, hours=1)).isoformat(),
        },
    )
    assert respuesta.status_code == 422


async def test_video_url_sin_https_se_rechaza(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_evento(cliente, cabeceras)

    respuesta = await cliente.post(
        f"{EVENTS}/{evento['id']}/sessions",
        headers=cabeceras,
        json={
            "session_type": "talk",
            "title": "Charla con vídeo inseguro",
            "starts_at": (AHORA + timedelta(hours=1)).isoformat(),
            "ends_at": (AHORA + timedelta(hours=2)).isoformat(),
            "video_platform": "youtube",
            "video_url": "http://youtube.com/watch?v=abc",
        },
    )
    assert respuesta.status_code == 422


async def test_video_url_de_dominio_ajeno_a_la_plataforma_se_rechaza(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_evento(cliente, cabeceras)

    respuesta = await cliente.post(
        f"{EVENTS}/{evento['id']}/sessions",
        headers=cabeceras,
        json={
            "session_type": "talk",
            "title": "Charla con vídeo de otro dominio",
            "starts_at": (AHORA + timedelta(hours=1)).isoformat(),
            "ends_at": (AHORA + timedelta(hours=2)).isoformat(),
            "video_platform": "youtube",
            "video_url": "https://evil.example.com/video",
        },
    )
    assert respuesta.status_code == 422


async def test_video_url_https_del_dominio_correcto_se_acepta(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_evento(cliente, cabeceras)

    respuesta = await cliente.post(
        f"{EVENTS}/{evento['id']}/sessions",
        headers=cabeceras,
        json={
            "session_type": "talk",
            "title": "Charla con vídeo válido",
            "starts_at": (AHORA + timedelta(hours=1)).isoformat(),
            "ends_at": (AHORA + timedelta(hours=2)).isoformat(),
            "video_platform": "youtube",
            "video_url": "https://youtu.be/abc123",
        },
    )
    assert respuesta.status_code == 201


async def test_un_material_sin_https_se_rechaza(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_evento(cliente, cabeceras)

    respuesta = await cliente.post(
        f"{EVENTS}/{evento['id']}/sessions",
        headers=cabeceras,
        json={
            "session_type": "talk",
            "title": "Charla con material inseguro",
            "starts_at": (AHORA + timedelta(hours=1)).isoformat(),
            "ends_at": (AHORA + timedelta(hours=2)).isoformat(),
            "materials": [{"label": "Diapositivas", "url": "http://ejemplo.com/slides.pdf"}],
        },
    )
    assert respuesta.status_code == 422


async def test_cambiar_solo_la_url_del_video_revalida_contra_la_plataforma_ya_guardada(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    """El `PATCH` puede tocar solo `video_url`: la combinación final (con la
    plataforma ya guardada) se valida en el servicio, no solo campo a campo."""
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_evento(cliente, cabeceras)
    sesion = (
        await cliente.post(
            f"{EVENTS}/{evento['id']}/sessions",
            headers=cabeceras,
            json={
                "session_type": "talk",
                "title": "Charla",
                "starts_at": (AHORA + timedelta(hours=1)).isoformat(),
                "ends_at": (AHORA + timedelta(hours=2)).isoformat(),
                "video_platform": "youtube",
                "video_url": "https://youtu.be/abc123",
            },
        )
    ).json()

    respuesta = await cliente.patch(
        f"{EVENTS}/{evento['id']}/sessions/{sesion['id']}",
        headers=cabeceras,
        json={"video_url": "https://vimeo.com/123456"},
    )
    assert respuesta.status_code == 422


async def test_editar_y_borrar_una_sesion(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_evento(cliente, cabeceras)
    alta = await cliente.post(
        f"{EVENTS}/{evento['id']}/sessions",
        headers=cabeceras,
        json={
            "session_type": "talk",
            "title": "Charla",
            "starts_at": (AHORA + timedelta(hours=1)).isoformat(),
            "ends_at": (AHORA + timedelta(hours=2)).isoformat(),
        },
    )
    sesion_id = alta.json()["id"]

    edicion = await cliente.patch(
        f"{EVENTS}/{evento['id']}/sessions/{sesion_id}",
        headers=cabeceras,
        json={"room": "Sala A"},
    )
    assert edicion.status_code == 200
    assert edicion.json()["room"] == "Sala A"

    borrado = await cliente.delete(
        f"{EVENTS}/{evento['id']}/sessions/{sesion_id}", headers=cabeceras
    )
    assert borrado.status_code == 204

    agenda = await cliente.get(f"{EVENTS}/{evento['id']}/sessions", headers=cabeceras)
    assert agenda.json() == []


async def test_subir_la_portada_devuelve_una_url_publica(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_evento(cliente, cabeceras)

    respuesta = await cliente.put(
        f"{EVENTS}/{evento['id']}/cover",
        headers=cabeceras,
        files={"fichero": ("portada.png", PNG, "image/png")},
    )
    assert respuesta.status_code == 200
    url = respuesta.json()["cover_url"]
    assert url and f"orgs/{organizacion.id}/events/{evento['id']}/cover/" in url


async def test_no_se_borra_la_portada_anterior_si_falla_el_commit(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    """El objeto anterior solo se borra tras el `commit` real de la transacción
    (vía `BackgroundTask`, que Starlette ejecuta después de enviar la respuesta).
    Si la persistencia falla, la petición nunca llega a construir esa respuesta y
    el borrado no llega a programarse — el objeto anterior sigue vivo, no
    huérfano, aunque la fila en base de datos tampoco haya quedado actualizada."""
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_evento(cliente, cabeceras)

    primera = await cliente.put(
        f"{EVENTS}/{evento['id']}/cover",
        headers=cabeceras,
        files={"fichero": ("primera.png", PNG, "image/png")},
    )
    assert primera.status_code == 200
    url_original = primera.json()["cover_url"]

    with (
        patch("app.core.storage.S3StorageProvider.delete_object", new_callable=AsyncMock) as borrar,
        patch.object(
            SessionTransaction, "commit", side_effect=RuntimeError("fallo simulado de commit")
        ),
        pytest.raises(RuntimeError),
    ):
        await cliente.put(
            f"{EVENTS}/{evento['id']}/cover",
            headers=cabeceras,
            files={"fichero": ("segunda.png", PNG, "image/png")},
        )
    borrar.assert_not_called()

    lectura = await cliente.get(f"{EVENTS}/{evento['id']}", headers=cabeceras)
    assert lectura.json()["cover_url"] == url_original
