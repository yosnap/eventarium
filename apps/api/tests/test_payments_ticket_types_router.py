"""Panel de organizador: CRUD de tipos de entrada (fase 6 del PRD, fase 3 de
trabajo). Mismo patrón que `test_registrations_organizer.py`: cliente HTTP
real, `Host` para resolver la organización.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient

from tests.conftest import OrganizacionDePrueba, iniciar_sesion

EVENTS = "/api/v1/events"
AHORA = datetime.now(UTC).replace(microsecond=0)


def _payload_evento(slug: str, **overrides: object) -> dict:
    payload = {
        "slug": slug,
        "title": f"Evento {slug}",
        "starts_at": AHORA.isoformat(),
        "ends_at": (AHORA + timedelta(days=2)).isoformat(),
        "location_mode": "in_person",
    }
    payload.update(overrides)
    return payload


async def _crear_evento(cliente: AsyncClient, cabeceras: dict[str, str], slug: str) -> dict:
    creacion = await cliente.post(EVENTS, headers=cabeceras, json=_payload_evento(slug))
    assert creacion.status_code == 201, creacion.text
    return creacion.json()


def _url_tipos(event_id: str, sufijo: str = "") -> str:
    return f"{EVENTS}/{event_id}/ticket-types{sufijo}"


async def test_crear_reordenar_y_listar_tipos_de_entrada(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_evento(cliente, cabeceras, "evento-tipos")

    creados = []
    for nombre, precio in (("General", 1000), ("VIP", 5000), ("Estudiante", 500)):
        respuesta = await cliente.post(
            _url_tipos(evento["id"]),
            headers=cabeceras,
            json={"name": nombre, "price_cents": precio, "max_quantity": 10, "sort_order": 0},
        )
        assert respuesta.status_code == 201, respuesta.text
        creados.append(respuesta.json())

    # Reordena: el último pasa a ser el primero.
    await cliente.patch(
        _url_tipos(evento["id"], f"/{creados[2]['id']}"),
        headers=cabeceras,
        json={"sort_order": -1},
    )

    listado = await cliente.get(_url_tipos(evento["id"]), headers=cabeceras)
    assert listado.status_code == 200, listado.text
    nombres = [tipo["name"] for tipo in listado.json()]
    assert nombres[0] == "Estudiante"


async def test_tipo_fuera_de_ventana_de_venta_se_puede_crear_pero_marcarse_inactivo(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_evento(cliente, cabeceras, "evento-ventana")

    creado = await cliente.post(
        _url_tipos(evento["id"]),
        headers=cabeceras,
        json={
            "name": "Early bird",
            "price_cents": 1000,
            "sales_start_at": (AHORA - timedelta(days=10)).isoformat(),
            "sales_end_at": (AHORA - timedelta(days=1)).isoformat(),
        },
    )
    assert creado.status_code == 201, creado.text

    desactivado = await cliente.patch(
        _url_tipos(evento["id"], f"/{creado.json()['id']}"),
        headers=cabeceras,
        json={"is_active": False},
    )
    assert desactivado.status_code == 200
    assert desactivado.json()["is_active"] is False


async def test_borrar_tipo_de_entrada_sin_dependencias_funciona(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_evento(cliente, cabeceras, "evento-borrado")

    creado = await cliente.post(
        _url_tipos(evento["id"]), headers=cabeceras, json={"name": "General", "price_cents": 1000}
    )
    assert creado.status_code == 201

    borrado = await cliente.delete(
        _url_tipos(evento["id"], f"/{creado.json()['id']}"), headers=cabeceras
    )
    assert borrado.status_code == 204

    listado = await cliente.get(_url_tipos(evento["id"]), headers=cabeceras)
    assert listado.json() == []


async def test_borrar_tipo_de_entrada_con_codigo_asociado_devuelve_409_no_500(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_evento(cliente, cabeceras, "evento-409")

    tipo = await cliente.post(
        _url_tipos(evento["id"]), headers=cabeceras, json={"name": "General", "price_cents": 1000}
    )
    tipo_id = tipo.json()["id"]

    codigo = await cliente.post(
        f"{EVENTS}/{evento['id']}/discount-codes",
        headers=cabeceras,
        json={
            "code": "PROMO10",
            "discount_type": "percentage",
            "discount_value": 10,
            "ticket_type_id": tipo_id,
        },
    )
    assert codigo.status_code == 201, codigo.text

    borrado = await cliente.delete(_url_tipos(evento["id"], f"/{tipo_id}"), headers=cabeceras)
    assert borrado.status_code == 409

    desactivado = await cliente.patch(
        _url_tipos(evento["id"], f"/{tipo_id}"), headers=cabeceras, json={"is_active": False}
    )
    assert desactivado.status_code == 200


async def test_una_organizacion_no_puede_gestionar_tipos_de_entrada_de_otra(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    otra_organizacion: OrganizacionDePrueba,
) -> None:
    _, cabeceras_a = await iniciar_sesion(cliente, organizacion)
    _, cabeceras_b = await iniciar_sesion(cliente, otra_organizacion)
    evento_b = await _crear_evento(cliente, cabeceras_b, "evento-de-b")

    respuesta = await cliente.get(_url_tipos(evento_b["id"]), headers=cabeceras_a)
    assert respuesta.status_code == 404

    creacion_cruzada = await cliente.post(
        _url_tipos(evento_b["id"]),
        headers=cabeceras_a,
        json={"name": "Intruso", "price_cents": 100},
    )
    assert creacion_cruzada.status_code == 404
