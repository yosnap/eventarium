"""Presupuesto público de compra (fase 6 del PRD, fase 3 de trabajo).

Mismo patrón que `test_registrations_public.py`: cliente HTTP real, `Host`
para resolver la organización. El presupuesto nunca reserva cupo ni consume
un uso de código — se comprueba pidiendo muchos presupuestos y verificando
que `used_count` sigue en 0.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient

from app.core.database import SessionApp, SessionMaintenance, set_organization_context
from app.core.ratelimit import CHECKOUT_QUOTE_POR_IP
from app.modules.payments import service as payments_service
from app.modules.payments.models import EventPayment
from tests.conftest import OrganizacionDePrueba, iniciar_sesion

EVENTS = "/api/v1/events"
AHORA = datetime.now(UTC).replace(microsecond=0)


def _payload_evento(slug: str) -> dict:
    # `registration_mode` se deja en `free` (valor por defecto): publicar un
    # evento `paid` exige una cuenta de Stripe conectada y verificada
    # (`events/service.py:_asegurar_venta_posible`), fuera del alcance de esta
    # fase de trabajo. Los tipos de entrada, códigos y el presupuesto no
    # dependen de `registration_mode` a nivel de API — esa condición solo
    # gobierna la visibilidad de las pantallas del panel.
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


async def _crear_codigo(cliente: AsyncClient, cabeceras: dict[str, str], event_id: str, **datos):
    payload = {"code": "DESCUENTO", "discount_type": "percentage", "discount_value": 20}
    payload.update(datos)
    creado = await cliente.post(
        f"{EVENTS}/{event_id}/discount-codes", headers=cabeceras, json=payload
    )
    assert creado.status_code == 201, creado.text
    return creado.json()


def _url_quote(slug: str) -> str:
    return f"/api/v1/public/events/{slug}/checkout/quote"


async def test_presupuesto_sin_codigo_devuelve_el_precio_de_lista(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_publicar_evento(cliente, cabeceras, "evento-quote-simple")
    tipo = await _crear_tipo(cliente, cabeceras, evento["id"])

    respuesta = await cliente.post(
        _url_quote(evento["slug"]),
        headers={"Host": organizacion.host},
        json={"ticket_type_id": tipo["id"], "turnstile_token": "token-de-prueba"},
    )
    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["price_cents"] == 1000
    assert cuerpo["discount_cents"] == 0
    assert cuerpo["total_cents"] == 1000
    assert cuerpo["currency"] == "eur"


async def test_presupuesto_con_codigo_valido_aplica_el_descuento(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_publicar_evento(cliente, cabeceras, "evento-quote-descuento")
    tipo = await _crear_tipo(cliente, cabeceras, evento["id"])
    await _crear_codigo(cliente, cabeceras, evento["id"])

    respuesta = await cliente.post(
        _url_quote(evento["slug"]),
        headers={"Host": organizacion.host},
        json={
            "ticket_type_id": tipo["id"],
            "code": "descuento",
            "turnstile_token": "token-de-prueba",
        },
    )
    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["discount_cents"] == 200
    assert cuerpo["total_cents"] == 800


async def test_tipo_fuera_de_ventana_de_venta_rechaza_el_presupuesto(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_publicar_evento(cliente, cabeceras, "evento-quote-ventana")
    tipo = await _crear_tipo(
        cliente,
        cabeceras,
        evento["id"],
        sales_start_at=(AHORA - timedelta(days=10)).isoformat(),
        sales_end_at=(AHORA - timedelta(days=1)).isoformat(),
    )

    respuesta = await cliente.post(
        _url_quote(evento["slug"]),
        headers={"Host": organizacion.host},
        json={"ticket_type_id": tipo["id"], "turnstile_token": "token-de-prueba"},
    )
    assert respuesta.status_code == 422


async def test_codigo_agotado_caducado_inexistente_y_de_otro_tipo_dan_el_mismo_mensaje(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_publicar_evento(cliente, cabeceras, "evento-quote-mensaje-unico")
    tipo = await _crear_tipo(cliente, cabeceras, evento["id"])
    otro_tipo = await _crear_tipo(cliente, cabeceras, evento["id"], name="VIP", price_cents=5000)

    codigo_agotado = await _crear_codigo(
        cliente, cabeceras, evento["id"], code="AGOTADO", max_uses=1
    )
    codigo_caducado = await _crear_codigo(
        cliente,
        cabeceras,
        evento["id"],
        code="CADUCADO",
        valid_until=(AHORA - timedelta(days=1)).isoformat(),
    )
    codigo_de_otro_tipo = await _crear_codigo(
        cliente,
        cabeceras,
        evento["id"],
        code="OTROTIPO",
        ticket_type_id=otro_tipo["id"],
    )

    async def _presupuesto(code: str, tipo_id: str) -> dict:
        respuesta = await cliente.post(
            _url_quote(evento["slug"]),
            headers={"Host": organizacion.host},
            json={"ticket_type_id": tipo_id, "code": code, "turnstile_token": "token-de-prueba"},
        )
        assert respuesta.status_code == 422
        return respuesta.json()

    # Consume el único uso permitido antes de comprobar que ya está agotado:
    # un presupuesto **no** consume usos, así que se agota con un pago real.
    async with SessionMaintenance() as session:
        session.add(
            EventPayment(
                organization_id=organizacion.id,
                event_id=uuid.UUID(evento["id"]),
                stripe_account_id="acct_prueba",
                ticket_type_id=uuid.UUID(tipo["id"]),
                discount_code_id=uuid.UUID(codigo_agotado["id"]),
                amount_cents=1000,
                currency="eur",
                status="paid",
            )
        )
        await session.commit()

    mensajes = {
        (await _presupuesto(codigo_agotado["code"], tipo["id"]))["detail"],
        (await _presupuesto(codigo_caducado["code"], tipo["id"]))["detail"],
        (await _presupuesto("INEXISTENTE", tipo["id"]))["detail"],
        (await _presupuesto(codigo_de_otro_tipo["code"], tipo["id"]))["detail"],
    }
    assert mensajes == {"Este código no es válido para esta entrada."}


async def test_50_presupuestos_sobre_un_codigo_de_un_uso_no_lo_consumen(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    """50 presupuestos superan `CHECKOUT_QUOTE_POR_IP` (30/min): se llama al
    servicio directamente, sin pasar por el límite de peticiones HTTP, que ya
    tiene su propio test dedicado más abajo. Lo que se comprueba aquí es que
    un presupuesto nunca escribe en `event_payments`."""
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_publicar_evento(cliente, cabeceras, "evento-quote-no-consume")
    tipo = await _crear_tipo(cliente, cabeceras, evento["id"])
    codigo = await _crear_codigo(cliente, cabeceras, evento["id"], code="LIMITADO", max_uses=1)

    async with SessionApp() as session:
        async with session.begin():
            await set_organization_context(session, organizacion.id)
            for _ in range(50):
                presupuesto = await payments_service.calcular_presupuesto(
                    session,
                    organization_id=organizacion.id,
                    event_id=uuid.UUID(evento["id"]),
                    ticket_type_id=uuid.UUID(tipo["id"]),
                    code="limitado",
                )
                assert presupuesto.total_cents == 800

    listado = await cliente.get(f"{EVENTS}/{evento['id']}/discount-codes", headers=cabeceras)
    encontrado = next(c for c in listado.json() if c["id"] == codigo["id"])
    assert encontrado["used_count"] == 0


async def test_el_presupuesto_tiene_limite_de_peticiones_por_ip(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_publicar_evento(cliente, cabeceras, "evento-quote-limite")
    tipo = await _crear_tipo(cliente, cabeceras, evento["id"])

    payload = {"ticket_type_id": tipo["id"], "turnstile_token": "token-de-prueba"}
    for _ in range(CHECKOUT_QUOTE_POR_IP):
        respuesta = await cliente.post(
            _url_quote(evento["slug"]), headers={"Host": organizacion.host}, json=payload
        )
        assert respuesta.status_code == 200

    bloqueada = await cliente.post(
        _url_quote(evento["slug"]), headers={"Host": organizacion.host}, json=payload
    )
    assert bloqueada.status_code == 429
