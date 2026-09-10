"""Sedes múltiples de un evento: CRUD, geocodificación y su restricción de borrado."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

from httpx import AsyncClient

from tests.conftest import OrganizacionDePrueba, iniciar_sesion

EVENTS = "/api/v1/events"

AHORA = datetime.now(UTC).replace(microsecond=0)


def _payload_evento(slug: str = "multisede-2026", **overrides: object) -> dict:
    payload: dict = {
        "slug": slug,
        "title": "Evento multisede",
        "starts_at": AHORA.isoformat(),
        "ends_at": (AHORA + timedelta(days=2)).isoformat(),
        "location_mode": "in_person",
    }
    payload.update(overrides)
    return payload


async def _crear_evento(
    cliente: AsyncClient, cabeceras: dict[str, str], **overrides: object
) -> dict:
    respuesta = await cliente.post(EVENTS, headers=cabeceras, json=_payload_evento(**overrides))
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


async def test_crear_listar_editar_y_borrar_una_sede(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_evento(cliente, cabeceras)

    with patch(
        "app.modules.events.service.geocode_address",
        new=AsyncMock(return_value=(39.4699, -0.3763)),
    ):
        alta = await cliente.post(
            f"{EVENTS}/{evento['id']}/venues",
            headers=cabeceras,
            json={"name": "Las Naves", "address": "Calle Juan Verdeguer 16, Valencia"},
        )
    assert alta.status_code == 201, alta.text
    sede = alta.json()
    assert sede["name"] == "Las Naves"
    assert sede["latitude"] == 39.4699
    assert sede["longitude"] == -0.3763
    assert sede["geocoded_at"] is not None

    listado = await cliente.get(f"{EVENTS}/{evento['id']}/venues", headers=cabeceras)
    assert listado.status_code == 200
    assert [s["id"] for s in listado.json()] == [sede["id"]]

    edicion = await cliente.patch(
        f"{EVENTS}/{evento['id']}/venues/{sede['id']}",
        headers=cabeceras,
        json={"capacity": 250},
    )
    assert edicion.status_code == 200
    assert edicion.json()["capacity"] == 250
    # La dirección no cambió: las coordenadas ya geocodificadas se conservan.
    assert edicion.json()["latitude"] == 39.4699

    borrado = await cliente.delete(
        f"{EVENTS}/{evento['id']}/venues/{sede['id']}", headers=cabeceras
    )
    assert borrado.status_code == 204

    listado_vacio = await cliente.get(f"{EVENTS}/{evento['id']}/venues", headers=cabeceras)
    assert listado_vacio.json() == []


async def test_geocodificacion_fallida_no_bloquea_crear_la_sede(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_evento(cliente, cabeceras)

    with patch(
        "app.modules.events.service.geocode_address", new=AsyncMock(return_value=None)
    ):
        respuesta = await cliente.post(
            f"{EVENTS}/{evento['id']}/venues",
            headers=cabeceras,
            json={
                "name": "Sede sin geocodificar",
                "address": "Dirección inventada, en ninguna parte",
            },
        )
    assert respuesta.status_code == 201, respuesta.text
    sede = respuesta.json()
    assert sede["latitude"] is None
    assert sede["longitude"] is None
    assert sede["geocoded_at"] is None


async def test_una_sede_sin_direccion_no_geocodifica(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_evento(cliente, cabeceras)

    with patch(
        "app.modules.events.service.geocode_address", new=AsyncMock(return_value=(1.0, 2.0))
    ) as mock_geocode:
        respuesta = await cliente.post(
            f"{EVENTS}/{evento['id']}/venues",
            headers=cabeceras,
            json={"name": "Sede sin dirección"},
        )
    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json()["latitude"] is None
    mock_geocode.assert_not_called()


async def test_no_se_puede_borrar_una_sede_con_sesiones_asociadas(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_evento(cliente, cabeceras)

    alta_sede = await cliente.post(
        f"{EVENTS}/{evento['id']}/venues", headers=cabeceras, json={"name": "Sala Principal"}
    )
    sede_id = alta_sede.json()["id"]

    # La sesión no expone `venue_id` en su schema de escritura (tanda 1 solo
    # añade el campo al modelo para que el admin de la tanda 2 lo use); se
    # asigna directamente en base de datos para comprobar la restricción.
    from sqlalchemy import text as sql_text

    from app.core.database import SessionMaintenance

    alta_sesion = await cliente.post(
        f"{EVENTS}/{evento['id']}/sessions",
        headers=cabeceras,
        json={
            "session_type": "talk",
            "title": "Charla en la sala",
            "starts_at": (AHORA + timedelta(hours=1)).isoformat(),
            "ends_at": (AHORA + timedelta(hours=2)).isoformat(),
        },
    )
    session_id = alta_sesion.json()["id"]

    async with SessionMaintenance() as db:
        await db.execute(
            sql_text("UPDATE event_sessions SET venue_id = :venue_id WHERE id = :session_id"),
            {"venue_id": sede_id, "session_id": session_id},
        )
        await db.commit()

    borrado = await cliente.delete(
        f"{EVENTS}/{evento['id']}/venues/{sede_id}", headers=cabeceras
    )
    assert borrado.status_code == 409


async def test_evento_geocodifica_su_direccion_simple(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    with patch(
        "app.modules.events.service.geocode_address",
        new=AsyncMock(return_value=(40.4168, -3.7038)),
    ):
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        respuesta = await cliente.post(
            EVENTS,
            headers=cabeceras,
            json=_payload_evento(
                slug="evento-con-direccion",
                location_address="Puerta del Sol, Madrid",
            ),
        )
    assert respuesta.status_code == 201, respuesta.text
    evento = respuesta.json()
    assert evento["latitude"] == 40.4168
    assert evento["longitude"] == -3.7038


async def test_evento_online_no_geocodifica_aunque_haya_direccion(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    with patch(
        "app.modules.events.service.geocode_address", new=AsyncMock(return_value=(1.0, 2.0))
    ) as mock_geocode:
        respuesta = await cliente.post(
            EVENTS,
            headers=cabeceras,
            json=_payload_evento(
                slug="evento-online",
                location_mode="online",
                location_address="Dirección irrelevante",
            ),
        )
    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json()["latitude"] is None
    mock_geocode.assert_not_called()


async def test_editar_la_direccion_regeocodifica_solo_si_cambia(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    with patch(
        "app.modules.events.service.geocode_address",
        new=AsyncMock(return_value=(41.3851, 2.1734)),
    ):
        evento = await _crear_evento(
            cliente, cabeceras, slug="evento-editable", location_address="Barcelona, España"
        )

    with patch(
        "app.modules.events.service.geocode_address", new=AsyncMock(return_value=(1.0, 1.0))
    ) as mock_geocode:
        sin_cambios = await cliente.patch(
            f"{EVENTS}/{evento['id']}", headers=cabeceras, json={"title": "Otro título"}
        )
    assert sin_cambios.status_code == 200
    mock_geocode.assert_not_called()
    assert sin_cambios.json()["latitude"] == 41.3851

    with patch(
        "app.modules.events.service.geocode_address",
        new=AsyncMock(return_value=(48.8566, 2.3522)),
    ) as mock_geocode:
        con_cambios = await cliente.patch(
            f"{EVENTS}/{evento['id']}",
            headers=cabeceras,
            json={"location_address": "París, Francia"},
        )
    assert con_cambios.status_code == 200
    mock_geocode.assert_called_once()
    assert con_cambios.json()["latitude"] == 48.8566


async def test_nominatim_respeta_el_espaciado_minimo_entre_llamadas(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    """No golpea la red real: valida el espaciado del `asyncio.Lock` de
    `geocoding.py` en aislamiento, parcheando la llamada HTTP subyacente."""
    from app.modules.events import geocoding

    geocoding._ultima_llamada = 0.0

    class _RespuestaFalsa:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> list[dict]:
            return [{"lat": "1.0", "lon": "2.0"}]

    async def _get_falso(*args: object, **kwargs: object) -> _RespuestaFalsa:
        return _RespuestaFalsa()

    with patch("httpx.AsyncClient.get", new=_get_falso):
        inicio = time.monotonic()
        resultado_1 = await geocoding.geocode_address("Dirección 1")
        resultado_2 = await geocoding.geocode_address("Dirección 2")
        transcurrido = time.monotonic() - inicio

    assert resultado_1 == (1.0, 2.0)
    assert resultado_2 == (1.0, 2.0)
    assert transcurrido >= geocoding.INTERVALO_MINIMO_SEGUNDOS


async def test_geocode_address_falla_abierto_ante_error_http() -> None:
    import httpx

    from app.modules.events import geocoding

    geocoding._ultima_llamada = 0.0

    async def _get_con_error(*args: object, **kwargs: object) -> None:
        raise httpx.ConnectTimeout("timeout simulado")

    with patch("httpx.AsyncClient.get", new=_get_con_error):
        resultado = await geocoding.geocode_address("Dirección que falla")

    assert resultado is None


async def test_geocode_address_ignora_direccion_vacia() -> None:
    from app.modules.events import geocoding

    assert await geocoding.geocode_address("   ") is None
