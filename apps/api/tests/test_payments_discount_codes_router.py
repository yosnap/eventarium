"""Panel de organizador: CRUD de códigos de descuento (fase 6 del PRD, fase 3
de trabajo). El `used_count` de la respuesta es siempre derivado de
`event_payments`, nunca un contador guardado — ver `models.py:EventDiscountCode`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient

from app.core.database import SessionMaintenance
from app.modules.payments.models import EventPayment
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


async def _crear_evento(cliente: AsyncClient, cabeceras: dict[str, str], slug: str) -> dict:
    creacion = await cliente.post(EVENTS, headers=cabeceras, json=_payload_evento(slug))
    assert creacion.status_code == 201, creacion.text
    return creacion.json()


async def _crear_tipo(cliente: AsyncClient, cabeceras: dict[str, str], event_id: str) -> dict:
    creado = await cliente.post(
        f"{EVENTS}/{event_id}/ticket-types",
        headers=cabeceras,
        json={"name": "General", "price_cents": 1000},
    )
    assert creado.status_code == 201, creado.text
    return creado.json()


def _url_codigos(event_id: str, sufijo: str = "") -> str:
    return f"{EVENTS}/{event_id}/discount-codes{sufijo}"


async def test_codigo_se_normaliza_a_mayusculas_al_guardar(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_evento(cliente, cabeceras, "evento-mayusculas")

    creado = await cliente.post(
        _url_codigos(evento["id"]),
        headers=cabeceras,
        json={"code": "verano2026", "discount_type": "percentage", "discount_value": 20},
    )
    assert creado.status_code == 201, creado.text
    assert creado.json()["code"] == "VERANO2026"


async def test_rechaza_porcentaje_fuera_de_rango_y_fijo_no_positivo(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_evento(cliente, cabeceras, "evento-rangos")

    porcentaje_invalido = await cliente.post(
        _url_codigos(evento["id"]),
        headers=cabeceras,
        json={"code": "P1", "discount_type": "percentage", "discount_value": 150},
    )
    assert porcentaje_invalido.status_code == 422

    fijo_invalido = await cliente.post(
        _url_codigos(evento["id"]),
        headers=cabeceras,
        json={"code": "F1", "discount_type": "fixed_amount", "discount_value": 0},
    )
    assert fijo_invalido.status_code == 422


async def test_no_se_puede_duplicar_un_codigo_en_el_mismo_evento(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_evento(cliente, cabeceras, "evento-duplicado")

    payload = {"code": "UNICO", "discount_type": "percentage", "discount_value": 10}
    primero = await cliente.post(_url_codigos(evento["id"]), headers=cabeceras, json=payload)
    assert primero.status_code == 201

    segundo = await cliente.post(
        _url_codigos(evento["id"]),
        headers=cabeceras,
        json={"code": "unico", "discount_type": "percentage", "discount_value": 5},
    )
    assert segundo.status_code == 409


async def test_no_se_puede_crear_un_codigo_con_tipo_de_entrada_de_otro_evento(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento_a = await _crear_evento(cliente, cabeceras, "evento-a-tipo")
    evento_b = await _crear_evento(cliente, cabeceras, "evento-b-tipo")
    tipo_de_b = await _crear_tipo(cliente, cabeceras, evento_b["id"])

    respuesta = await cliente.post(
        _url_codigos(evento_a["id"]),
        headers=cabeceras,
        json={
            "code": "CRUZADO",
            "discount_type": "percentage",
            "discount_value": 10,
            "ticket_type_id": tipo_de_b["id"],
        },
    )
    assert respuesta.status_code == 422


async def test_used_count_es_derivado_y_no_una_columna(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_evento(cliente, cabeceras, "evento-used-count")
    tipo = await _crear_tipo(cliente, cabeceras, evento["id"])

    codigo = await cliente.post(
        _url_codigos(evento["id"]),
        headers=cabeceras,
        json={"code": "DERIVADO", "discount_type": "percentage", "discount_value": 10},
    )
    codigo_id = codigo.json()["id"]
    assert codigo.json()["used_count"] == 0

    async with SessionMaintenance() as session:
        pago = EventPayment(
            organization_id=organizacion.id,
            event_id=uuid.UUID(evento["id"]),
            stripe_account_id="acct_prueba",
            ticket_type_id=uuid.UUID(tipo["id"]),
            discount_code_id=uuid.UUID(codigo_id),
            amount_cents=900,
            currency="eur",
            status="paid",
        )
        session.add(pago)
        await session.commit()
        pago_id = pago.id

    listado = await cliente.get(_url_codigos(evento["id"]), headers=cabeceras)
    assert listado.status_code == 200, listado.text
    encontrado = next(c for c in listado.json() if c["id"] == codigo_id)
    assert encontrado["used_count"] == 1

    # Un pago `expired` deja de contar sin que nadie lo decremente.
    async with SessionMaintenance() as session:
        pago_en_bd = await session.get(EventPayment, pago_id)
        assert pago_en_bd is not None
        pago_en_bd.status = "expired"
        await session.commit()

    listado_tras_expirar = await cliente.get(_url_codigos(evento["id"]), headers=cabeceras)
    encontrado_tras_expirar = next(c for c in listado_tras_expirar.json() if c["id"] == codigo_id)
    assert encontrado_tras_expirar["used_count"] == 0


async def test_borrar_codigo_con_pago_asociado_devuelve_409(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_evento(cliente, cabeceras, "evento-codigo-409")
    tipo = await _crear_tipo(cliente, cabeceras, evento["id"])

    codigo = await cliente.post(
        _url_codigos(evento["id"]),
        headers=cabeceras,
        json={"code": "CONPAGO", "discount_type": "percentage", "discount_value": 10},
    )
    codigo_id = codigo.json()["id"]

    async with SessionMaintenance() as session:
        session.add(
            EventPayment(
                organization_id=organizacion.id,
                event_id=uuid.UUID(evento["id"]),
                stripe_account_id="acct_prueba",
                ticket_type_id=uuid.UUID(tipo["id"]),
                discount_code_id=uuid.UUID(codigo_id),
                amount_cents=900,
                currency="eur",
                status="paid",
            )
        )
        await session.commit()

    borrado = await cliente.delete(_url_codigos(evento["id"], f"/{codigo_id}"), headers=cabeceras)
    assert borrado.status_code == 409
