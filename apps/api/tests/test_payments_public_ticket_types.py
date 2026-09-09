"""Listado público de tipos de entrada vendibles ahora mismo (fase 6 del PRD,
fase 4 de trabajo).

Añadido junto al frontend del paso de compra: el presupuesto público
(`checkout/quote`, fase 3 de trabajo) exige un `ticket_type_id` que el
formulario tiene que conocer de antemano, y no existía ningún endpoint
público que listara los tipos de un evento — solo el del panel, protegido
por `PAYMENTS_READ`. Mismo patrón de test que
`test_payments_checkout_quote_public.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient

from tests.conftest import OrganizacionDePrueba, iniciar_sesion

EVENTS = "/api/v1/events"
AHORA = datetime.now(UTC).replace(microsecond=0)


def _payload_evento(slug: str) -> dict:
    return {
        "slug": slug,
        "title": f"Evento {slug}",
        "starts_at": AHORA.isoformat(),
        "ends_at": (AHORA + timedelta(days=2)).isoformat(),
        "location_mode": "in_person",
    }


async def _crear_publicar_evento(
    cliente: AsyncClient, cabeceras: dict[str, str], slug: str
) -> dict:
    creacion = await cliente.post(EVENTS, headers=cabeceras, json=_payload_evento(slug))
    assert creacion.status_code == 201, creacion.text
    evento = creacion.json()
    publicacion = await cliente.patch(
        f"{EVENTS}/{evento['id']}",
        headers=cabeceras,
        json={"status": "published", "visibility": "public"},
    )
    assert publicacion.status_code == 200, publicacion.text
    return publicacion.json()


async def _crear_tipo(cliente: AsyncClient, cabeceras: dict[str, str], event_id: str, **datos):
    payload = {"name": "General", "price_cents": 1000}
    payload.update(datos)
    creado = await cliente.post(
        f"{EVENTS}/{event_id}/ticket-types", headers=cabeceras, json=payload
    )
    assert creado.status_code == 201, creado.text
    return creado.json()


def _url(slug: str) -> str:
    return f"/api/v1/public/events/{slug}/ticket-types"


async def test_lista_los_tipos_activos_y_en_ventana_con_su_precio(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_publicar_evento(cliente, cabeceras, "evento-tipos-publicos")
    tipo = await _crear_tipo(cliente, cabeceras, evento["id"], name="VIP", price_cents=5000)

    respuesta = await cliente.get(_url(evento["slug"]), headers={"Host": organizacion.host})
    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert len(cuerpo) == 1
    assert cuerpo[0]["id"] == tipo["id"]
    assert cuerpo[0]["name"] == "VIP"
    assert cuerpo[0]["price_cents"] == 5000
    assert cuerpo[0]["currency"] == "eur"


async def test_un_tipo_inactivo_no_se_lista(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_publicar_evento(cliente, cabeceras, "evento-tipos-inactivo")
    await _crear_tipo(cliente, cabeceras, evento["id"], is_active=False)

    respuesta = await cliente.get(_url(evento["slug"]), headers={"Host": organizacion.host})
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json() == []


async def test_un_tipo_fuera_de_su_ventana_de_venta_no_se_lista(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_publicar_evento(cliente, cabeceras, "evento-tipos-fuera-de-ventana")
    await _crear_tipo(
        cliente,
        cabeceras,
        evento["id"],
        sales_end_at=(AHORA - timedelta(hours=1)).isoformat(),
    )

    respuesta = await cliente.get(_url(evento["slug"]), headers={"Host": organizacion.host})
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json() == []


async def test_un_evento_inexistente_devuelve_404(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    respuesta = await cliente.get(_url("no-existe"), headers={"Host": organizacion.host})
    assert respuesta.status_code == 404, respuesta.text
