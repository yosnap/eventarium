"""Aceptación de las políticas del organizador en la inscripción: página
pública, comprobación en los caminos gratuito y de pago (incluida la
reactivación de una compra abandonada) y detalle en el panel."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.database import SessionMaintenance
from app.core.ratelimit import PUBLICO_POR_IP
from app.modules.events.models import Event
from app.modules.payments.models import EventPayment
from app.modules.registrations.models import EventRegistration, EventRegistrationConsent
from tests.conftest import OrganizacionDePrueba, iniciar_sesion
from tests.payments_test_helpers import (
    FakeStripeClient,
    _preparar_evento_de_pago,
    _sesion_creada,
    _url_checkout,
)

AHORA = datetime.now(UTC).replace(microsecond=0)
ORGANIZACION = "/api/v1/organizations/me/policies"


def _publicas(slug: str) -> str:
    return f"/api/v1/public/events/{slug}/policies"


def _inscripcion(slug: str) -> str:
    return f"/api/v1/public/events/{slug}/registrations"


def _payload(email: str = "asistente@example.com", **extra: object) -> dict:
    payload: dict[str, object] = {
        "email": email,
        "full_name": "Asistente de Prueba",
        "answers": [],
        "data_processing_accepted": True,
        "turnstile_token": "token-de-prueba",
    }
    payload.update(extra)
    return payload


async def _crear_evento(
    organizacion: OrganizacionDePrueba,
    slug: str,
    *,
    status: str = "published",
    visibility: str = "public",
) -> uuid.UUID:
    async with SessionMaintenance() as session:
        evento = Event(
            organization_id=organizacion.id,
            slug=slug,
            title=f"Evento {slug}",
            status=status,
            visibility=visibility,
            starts_at=AHORA + timedelta(days=5),
            ends_at=AHORA + timedelta(days=6),
            location_mode="online",
            email_verification_required=False,
        )
        session.add(evento)
        await session.commit()
        return evento.id


async def _escribir(cliente: AsyncClient, cabeceras: dict[str, str], kind: str, texto: str) -> None:
    respuesta = await cliente.put(
        f"{ORGANIZACION}/{kind}", json={"content": texto}, headers=cabeceras
    )
    assert respuesta.status_code == 200, respuesta.text


async def _ids_vigentes(cliente: AsyncClient, slug: str) -> list[str]:
    respuesta = await cliente.get(_publicas(slug))
    assert respuesta.status_code == 200, respuesta.text
    return [politica["version_id"] for politica in respuesta.json()["policies"]]


async def _consentimiento(email: str) -> EventRegistrationConsent | None:
    async with SessionMaintenance() as session:
        return await session.scalar(
            select(EventRegistrationConsent)
            .join(
                EventRegistration, EventRegistration.id == EventRegistrationConsent.registration_id
            )
            .where(EventRegistration.email == email)
        )


# --- Página pública -----------------------------------------------------------


async def test_la_pagina_publica_devuelve_los_textos_vigentes_en_orden(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    await _crear_evento(organizacion, "con-textos")
    await _escribir(cliente, cabeceras, "privacidad", "Privacidad")
    await _escribir(cliente, cabeceras, "condiciones", "Condiciones")

    respuesta = await cliente.get(_publicas("con-textos"))
    assert respuesta.status_code == 200, respuesta.text
    datos = respuesta.json()
    assert datos["organization_name"] == "Organización acme"
    assert [p["kind"] for p in datos["policies"]] == ["condiciones", "privacidad"]


async def test_sin_textos_la_pagina_publica_devuelve_lista_vacia(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    await _crear_evento(organizacion, "sin-textos")
    respuesta = await cliente.get(_publicas("sin-textos"))
    assert respuesta.status_code == 200
    assert respuesta.json()["policies"] == []


@pytest.mark.parametrize(
    ("status", "visibility"),
    [("draft", "public"), ("published", "hidden"), ("published", "private")],
)
async def test_la_pagina_publica_no_revela_eventos_no_publicables(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, status: str, visibility: str
) -> None:
    await _crear_evento(organizacion, "no-publicable", status=status, visibility=visibility)
    respuesta = await cliente.get(_publicas("no-publicable"))
    assert respuesta.status_code == 404


async def test_la_pagina_publica_tiene_limite_por_ip(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    await _crear_evento(organizacion, "limite")
    for _ in range(PUBLICO_POR_IP):
        assert (await cliente.get(_publicas("limite"))).status_code == 200
    assert (await cliente.get(_publicas("limite"))).status_code == 429


# --- Inscripción gratuita -----------------------------------------------------


async def test_sin_textos_no_se_exige_aceptacion(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    await _crear_evento(organizacion, "libre")
    respuesta = await cliente.post(_inscripcion("libre"), json=_payload())
    assert respuesta.status_code == 202, respuesta.text
    consentimiento = await _consentimiento("asistente@example.com")
    assert consentimiento is not None
    assert consentimiento.organizer_policies_accepted_at is None
    assert consentimiento.accepted_policy_version_ids == []


async def test_con_textos_la_aceptacion_guarda_fecha_y_versiones(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    await _crear_evento(organizacion, "acepta")
    await _escribir(cliente, cabeceras, "condiciones", "Condiciones")
    await _escribir(cliente, cabeceras, "reembolsos", "Reembolsos")
    ids = await _ids_vigentes(cliente, "acepta")

    respuesta = await cliente.post(
        _inscripcion("acepta"), json=_payload(accepted_policy_version_ids=ids)
    )
    assert respuesta.status_code == 202, respuesta.text
    consentimiento = await _consentimiento("asistente@example.com")
    assert consentimiento is not None
    assert consentimiento.organizer_policies_accepted_at is not None
    assert sorted(map(str, consentimiento.accepted_policy_version_ids)) == sorted(ids)

    # Editar después no cambia lo que consta aceptado.
    await _escribir(cliente, cabeceras, "condiciones", "Condiciones nuevas")
    despues = await _consentimiento("asistente@example.com")
    assert despues is not None
    assert sorted(map(str, despues.accepted_policy_version_ids)) == sorted(ids)


@pytest.mark.parametrize(
    "ids",
    [
        pytest.param("vacia", id="lista-vacia"),
        pytest.param("antigua", id="version-antigua"),
        pytest.param("inventada", id="id-inventado"),
    ],
)
async def test_una_aceptacion_que_no_cuadra_da_409_politicas_cambiadas(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, ids: str
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    await _crear_evento(organizacion, "no-cuadra")
    await _escribir(cliente, cabeceras, "condiciones", "Primera")
    antiguos = await _ids_vigentes(cliente, "no-cuadra")
    await _escribir(cliente, cabeceras, "condiciones", "Segunda")
    enviados = {"vacia": [], "antigua": antiguos, "inventada": [str(uuid.uuid4())]}[ids]

    respuesta = await cliente.post(
        _inscripcion("no-cuadra"), json=_payload(accepted_policy_version_ids=enviados)
    )
    assert respuesta.status_code == 409, respuesta.text
    assert respuesta.json()["code"] == "politicas_cambiadas"
    assert await _consentimiento("asistente@example.com") is None


async def test_ids_de_otra_organizacion_no_valen(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    otra_organizacion: OrganizacionDePrueba,
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    _, ajenas = await iniciar_sesion(cliente, otra_organizacion)
    await _crear_evento(organizacion, "propio")
    await _crear_evento(otra_organizacion, "ajeno")
    await _escribir(cliente, cabeceras, "condiciones", "Nuestras")
    await _escribir(cliente, ajenas, "condiciones", "Suyas")
    ajenos = await _ids_vigentes(cliente, "ajeno")

    respuesta = await cliente.post(
        _inscripcion("propio"), json=_payload(accepted_policy_version_ids=ajenos)
    )
    assert respuesta.status_code == 409
    assert respuesta.json()["code"] == "politicas_cambiadas"


async def test_la_respuesta_no_revela_si_el_email_ya_estaba_inscrito(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    """La comprobación va antes de buscar el email: un correo ya inscrito y
    uno nuevo reciben exactamente la misma respuesta."""
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    await _crear_evento(organizacion, "enumeracion")
    await _escribir(cliente, cabeceras, "condiciones", "Condiciones")
    ids = await _ids_vigentes(cliente, "enumeracion")
    alta = await cliente.post(
        _inscripcion("enumeracion"),
        json=_payload("ya@example.com", accepted_policy_version_ids=ids),
    )
    assert alta.status_code == 202, alta.text

    existente = await cliente.post(_inscripcion("enumeracion"), json=_payload("ya@example.com"))
    nuevo = await cliente.post(_inscripcion("enumeracion"), json=_payload("nuevo@example.com"))
    assert existente.status_code == nuevo.status_code == 409
    assert existente.json()["code"] == nuevo.json()["code"] == "politicas_cambiadas"


# --- Camino de pago -----------------------------------------------------------


async def test_el_checkout_exige_la_aceptacion(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    monkeypatch: pytest.MonkeyPatch,
    fake: FakeStripeClient,
) -> None:
    evento, tipo = await _preparar_evento_de_pago(cliente, organizacion, monkeypatch, "pago-pol")
    fake.v1.checkout.sessions.create_async.return_value = _sesion_creada()
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    await _escribir(cliente, cabeceras, "reembolsos", "Sin reembolsos")
    payload = _payload("compra@example.com", ticket_type_id=tipo["id"])

    sin_aceptar = await cliente.post(_url_checkout(evento["slug"]), json=payload)
    assert sin_aceptar.status_code == 409
    assert sin_aceptar.json()["code"] == "politicas_cambiadas"

    ids = await _ids_vigentes(cliente, evento["slug"])
    aceptando = await cliente.post(
        _url_checkout(evento["slug"]), json={**payload, "accepted_policy_version_ids": ids}
    )
    assert aceptando.status_code == 200, aceptando.text
    consentimiento = await _consentimiento("compra@example.com")
    assert consentimiento is not None
    assert [str(i) for i in consentimiento.accepted_policy_version_ids] == ids


async def test_reactivar_una_compra_abandonada_guarda_la_aceptacion_nueva(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    monkeypatch: pytest.MonkeyPatch,
    fake: FakeStripeClient,
) -> None:
    """Quien abandona una compra y vuelve cuando los textos han cambiado tiene
    que aceptar los nuevos, y lo que consta aceptado es lo de ahora."""
    evento, tipo = await _preparar_evento_de_pago(cliente, organizacion, monkeypatch, "reactiva")
    fake.v1.checkout.sessions.create_async.return_value = _sesion_creada()
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    await _escribir(cliente, cabeceras, "reembolsos", "Versión 1")
    primeros = await _ids_vigentes(cliente, evento["slug"])
    payload = _payload("vuelve@example.com", ticket_type_id=tipo["id"])
    primera = await cliente.post(
        _url_checkout(evento["slug"]), json={**payload, "accepted_policy_version_ids": primeros}
    )
    assert primera.status_code == 200, primera.text

    async with SessionMaintenance() as session:
        registro = await session.scalar(
            select(EventRegistration).where(EventRegistration.email == "vuelve@example.com")
        )
        assert registro is not None
        pago = await session.scalar(
            select(EventPayment).where(EventPayment.registration_id == registro.id)
        )
        assert pago is not None
        registro.status = "cancelled"
        pago.status = "pending"
        await session.commit()

    await _escribir(cliente, cabeceras, "reembolsos", "Versión 2")
    fake.v1.checkout.sessions.create_async.return_value = _sesion_creada("cs_test_2")
    con_los_viejos = await cliente.post(
        _url_checkout(evento["slug"]), json={**payload, "accepted_policy_version_ids": primeros}
    )
    assert con_los_viejos.status_code == 409

    nuevos = await _ids_vigentes(cliente, evento["slug"])
    reactivada = await cliente.post(
        _url_checkout(evento["slug"]), json={**payload, "accepted_policy_version_ids": nuevos}
    )
    assert reactivada.status_code == 200, reactivada.text
    consentimiento = await _consentimiento("vuelve@example.com")
    assert consentimiento is not None
    assert [str(i) for i in consentimiento.accepted_policy_version_ids] == nuevos


# --- Panel --------------------------------------------------------------------


async def test_el_detalle_de_inscripcion_muestra_las_versiones_aceptadas(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    event_id = await _crear_evento(organizacion, "detalle")
    await _escribir(cliente, cabeceras, "otras", "Otras condiciones")
    ids = await _ids_vigentes(cliente, "detalle")
    await cliente.post(_inscripcion("detalle"), json=_payload(accepted_policy_version_ids=ids))

    async with SessionMaintenance() as session:
        registration_id = await session.scalar(
            select(EventRegistration.id).where(EventRegistration.email == "asistente@example.com")
        )
    respuesta = await cliente.get(
        f"/api/v1/events/{event_id}/registrations/{registration_id}", headers=cabeceras
    )
    assert respuesta.status_code == 200, respuesta.text
    consentimiento = respuesta.json()["consent"]
    assert consentimiento["organizer_policies_accepted_at"] is not None
    assert consentimiento["accepted_policies"] == [
        {"version_id": ids[0], "kind": "otras", "version": 1}
    ]


async def test_demasiados_ids_se_rechazan_antes_de_nada(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    await _crear_evento(organizacion, "abuso")
    ids = [str(uuid.uuid4()) for _ in range(11)]
    respuesta = await cliente.post(
        _inscripcion("abuso"), json=_payload(accepted_policy_version_ids=ids)
    )
    assert respuesta.status_code == 422


async def test_recorrido_completo_organizacion_evento_e_inscripcion(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    """La organización escribe sus textos, el evento sustituye los reembolsos,
    la página pública muestra la mezcla, y un cambio a mitad obliga a
    reaceptar con los textos nuevos."""
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    event_id = await _crear_evento(organizacion, "recorrido")
    await _escribir(cliente, cabeceras, "condiciones", "Condiciones de la organización")
    await _escribir(cliente, cabeceras, "reembolsos", "Reembolsos de la organización")
    propio = await cliente.put(
        f"/api/v1/events/{event_id}/policies/reembolsos",
        json={"content": "Reembolsos de este evento"},
        headers=cabeceras,
    )
    assert propio.status_code == 200, propio.text

    publicas = (await cliente.get(_publicas("recorrido"))).json()["policies"]
    assert [(p["kind"], p["content"]) for p in publicas] == [
        ("condiciones", "Condiciones de la organización"),
        ("reembolsos", "Reembolsos de este evento"),
    ]
    vistos = [p["version_id"] for p in publicas]

    # La organización cambia sus condiciones mientras alguien rellena el formulario.
    await _escribir(cliente, cabeceras, "condiciones", "Condiciones nuevas")
    tarde = await cliente.post(
        _inscripcion("recorrido"), json=_payload(accepted_policy_version_ids=vistos)
    )
    assert tarde.status_code == 409
    assert tarde.json()["code"] == "politicas_cambiadas"

    nuevos = await _ids_vigentes(cliente, "recorrido")
    assert nuevos != vistos
    reaceptada = await cliente.post(
        _inscripcion("recorrido"), json=_payload(accepted_policy_version_ids=nuevos)
    )
    assert reaceptada.status_code == 202, reaceptada.text
    consentimiento = await _consentimiento("asistente@example.com")
    assert consentimiento is not None
    assert sorted(map(str, consentimiento.accepted_policy_version_ids)) == sorted(nuevos)


async def test_un_409_de_politicas_no_gasta_el_token_antibots(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    monkeypatch: pytest.MonkeyPatch,
    fake: FakeStripeClient,
) -> None:
    """El token de Turnstile es de un solo uso: si las condiciones no cuadran,
    se responde 409 antes de validarlo, para que el formulario pueda reenviar
    con el mismo token tras volver a aceptar."""
    from app.modules.payments import public_router as pagos_router
    from app.modules.registrations import public_router as inscripciones_router

    validaciones: list[str] = []

    async def turnstile_espia(_request: object, token: str) -> None:
        validaciones.append(token)

    monkeypatch.setattr(inscripciones_router, "require_turnstile", turnstile_espia)
    monkeypatch.setattr(pagos_router, "require_turnstile", turnstile_espia)

    evento, tipo = await _preparar_evento_de_pago(cliente, organizacion, monkeypatch, "token-pago")
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    await _crear_evento(organizacion, "token-gratis")
    await _escribir(cliente, cabeceras, "condiciones", "Condiciones")

    gratis = await cliente.post(_inscripcion("token-gratis"), json=_payload())
    compra = await cliente.post(
        _url_checkout(evento["slug"]),
        json=_payload("compra@example.com", ticket_type_id=tipo["id"]),
    )
    assert gratis.status_code == compra.status_code == 409
    assert validaciones == []


async def test_reactivar_sin_textos_conserva_la_aceptacion_anterior(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    monkeypatch: pytest.MonkeyPatch,
    fake: FakeStripeClient,
) -> None:
    evento, tipo = await _preparar_evento_de_pago(cliente, organizacion, monkeypatch, "retira")
    fake.v1.checkout.sessions.create_async.return_value = _sesion_creada()
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    await _escribir(cliente, cabeceras, "reembolsos", "Versión 1")
    aceptados = await _ids_vigentes(cliente, evento["slug"])
    payload = _payload("retira@example.com", ticket_type_id=tipo["id"])
    primera = await cliente.post(
        _url_checkout(evento["slug"]), json={**payload, "accepted_policy_version_ids": aceptados}
    )
    assert primera.status_code == 200, primera.text

    async with SessionMaintenance() as session:
        registro = await session.scalar(
            select(EventRegistration).where(EventRegistration.email == "retira@example.com")
        )
        assert registro is not None
        pago = await session.scalar(
            select(EventPayment).where(EventPayment.registration_id == registro.id)
        )
        assert pago is not None
        registro.status = "cancelled"
        pago.status = "pending"
        await session.commit()

    await _escribir(cliente, cabeceras, "reembolsos", "")  # el organizador lo retira
    fake.v1.checkout.sessions.create_async.return_value = _sesion_creada("cs_test_2")
    reactivada = await cliente.post(_url_checkout(evento["slug"]), json=payload)
    assert reactivada.status_code == 200, reactivada.text
    consentimiento = await _consentimiento("retira@example.com")
    assert consentimiento is not None
    assert [str(i) for i in consentimiento.accepted_policy_version_ids] == aceptados
    assert consentimiento.organizer_policies_accepted_at is not None
