"""Traducciones en el panel: editor por entidad, guardado manual, revisión,
permisos, aislamiento y los idiomas de la organización y del evento."""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy import update

from app.core.database import SessionMaintenance
from app.modules.platform.models import PlatformBranding
from tests.conftest import OrganizacionDePrueba, crear_miembro, iniciar_sesion, iniciar_sesion_con
from tests.test_events_public import EVENTOS_DE_ACME, EVENTS, _crear_evento, _publicar

ORGANIZACION = "/api/v1/organizations/me"
EN = {"locale": "en-US"}
INGLES = {"Accept-Language": "en-US"}


def _url(tipo: str, entity_id: str) -> str:
    return f"/api/v1/translations/{tipo}/{entity_id}"


async def _bilingue(cliente: AsyncClient, organizacion: OrganizacionDePrueba) -> tuple[dict, dict]:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    activado = await cliente.patch(
        ORGANIZACION, headers=cabeceras, json={"content_locales": ["es-ES", "en-US"]}
    )
    assert activado.status_code == 200, activado.text
    assert activado.json()["content_locales"] == ["es-ES", "en-US"]
    evento = await _crear_evento(
        cliente, cabeceras, slug="panel-bilingue", title="Jornada", tags=["ia"]
    )
    return cabeceras, evento


async def test_editar_la_version_en_ingles_y_verla_en_la_web(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    cabeceras, evento = await _bilingue(cliente, organizacion)

    editor = (await cliente.get(_url("event", evento["id"]), headers=cabeceras, params=EN)).json()
    assert editor["locales"] == ["es-ES", "en-US"]
    assert editor["source_locale"] == "es-ES"
    por_campo = {(i["entity_type"], i["field"]): i for i in editor["items"]}
    assert por_campo[("event", "title")]["status"] == "pendiente"
    assert ("tag", "ia") in por_campo

    guardado = await cliente.put(
        _url("event", evento["id"]),
        headers=cabeceras,
        params=EN,
        json={
            "items": [
                {
                    "entity_type": "event",
                    "entity_id": evento["id"],
                    "field": "title",
                    "value": "Day",
                },
                {
                    "entity_type": "tag",
                    "entity_id": por_campo[("tag", "ia")]["entity_id"],
                    "field": "ia",
                    "value": "ai",
                },
            ]
        },
    )
    assert guardado.status_code == 200, guardado.text
    titulo = next(i for i in guardado.json()["items"] if i["field"] == "title")
    assert titulo["status"] == "al_dia"
    assert titulo["origin"] == "manual"

    await _publicar(cliente, cabeceras, evento["id"])
    ficha = (await cliente.get(f"{EVENTOS_DE_ACME}/panel-bilingue", headers=INGLES)).json()
    assert ficha["title"] == "Day"
    assert ficha["tag_labels"] == {"ia": "ai"}

    resumen = (
        await cliente.get(f"/api/v1/translations/events/{evento['id']}/summary", headers=cabeceras)
    ).json()
    assert resumen["locales"][0]["locale"] == "en-US"
    assert resumen["locales"][0]["up_to_date"] == 2


async def test_cambiar_el_original_la_desactualiza_y_revisarla_la_fija(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    cabeceras, evento = await _bilingue(cliente, organizacion)
    item = {"entity_type": "event", "entity_id": evento["id"], "field": "title"}
    await cliente.put(
        _url("event", evento["id"]),
        headers=cabeceras,
        params=EN,
        json={"items": [{**item, "value": "Day"}]},
    )
    await cliente.patch(f"{EVENTS}/{evento['id']}", headers=cabeceras, json={"title": "Jornada 2"})

    editor = (await cliente.get(_url("event", evento["id"]), headers=cabeceras, params=EN)).json()
    titulo = next(i for i in editor["items"] if i["field"] == "title")
    assert titulo["status"] == "desactualizada"
    assert titulo["value"] == "Day"

    revisada = await cliente.post(
        f"{_url('event', evento['id'])}/review", headers=cabeceras, params=EN, json=item
    )
    assert revisada.status_code == 200, revisada.text
    titulo = next(i for i in revisada.json()["items"] if i["field"] == "title")
    assert (titulo["status"], titulo["origin"]) == ("al_dia", "revisada")

    borrada = await cliente.put(
        _url("event", evento["id"]),
        headers=cabeceras,
        params=EN,
        json={"items": [{**item, "value": ""}]},
    )
    titulo = next(i for i in borrada.json()["items"] if i["field"] == "title")
    assert titulo["status"] == "pendiente"


async def test_otra_organizacion_no_abre_ni_traduce_el_evento(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    otra_organizacion: OrganizacionDePrueba,
) -> None:
    _, evento = await _bilingue(cliente, organizacion)
    _, cabeceras_rival = await iniciar_sesion(cliente, otra_organizacion)

    leer = await cliente.get(_url("event", evento["id"]), headers=cabeceras_rival, params=EN)
    escribir = await cliente.put(
        _url("event", evento["id"]),
        headers=cabeceras_rival,
        params=EN,
        json={"items": []},
    )
    assert leer.status_code == 404
    assert escribir.status_code == 404


async def test_sin_permiso_de_edicion_no_se_traduce(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, evento = await _bilingue(cliente, organizacion)
    ponente = await crear_miembro(organizacion, "speaker")
    _, cabeceras = await iniciar_sesion_con(cliente, organizacion, ponente.email, ponente.password)

    respuesta = await cliente.put(
        _url("event", evento["id"]),
        headers=cabeceras,
        params=EN,
        json={
            "items": [
                {"entity_type": "event", "entity_id": evento["id"], "field": "title", "value": "X"}
            ]
        },
    )
    assert respuesta.status_code == 403


async def test_no_se_guarda_un_campo_ajeno_a_la_entidad(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    cabeceras, evento = await _bilingue(cliente, organizacion)

    respuesta = await cliente.put(
        _url("event", evento["id"]),
        headers=cabeceras,
        params=EN,
        json={
            "items": [
                {"entity_type": "event", "entity_id": evento["id"], "field": "slug", "value": "x"}
            ]
        },
    )
    assert respuesta.status_code == 422


async def test_idiomas_de_la_organizacion_y_del_evento_se_validan(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    cabeceras, evento = await _bilingue(cliente, organizacion)

    sin_origen = await cliente.patch(
        ORGANIZACION, headers=cabeceras, json={"content_locales": ["en-US"]}
    )
    assert sin_origen.status_code == 422
    en_ingles = await cliente.patch(
        f"{EVENTS}/{evento['id']}", headers=cabeceras, json={"source_locale": "en-US"}
    )
    assert en_ingles.status_code == 200, en_ingles.text
    assert en_ingles.json()["source_locale"] == "en-US"

    # No se quita un idioma en que está escrito un evento: el error lo nombra.
    bloqueado = await cliente.patch(
        ORGANIZACION, headers=cabeceras, json={"content_locales": ["es-ES"]}
    )
    assert bloqueado.status_code == 422
    assert "Jornada" in bloqueado.json()["detail"]

    await cliente.patch(
        f"{EVENTS}/{evento['id']}", headers=cabeceras, json={"source_locale": "es-ES"}
    )
    solo_espanol = await cliente.patch(
        ORGANIZACION, headers=cabeceras, json={"content_locales": ["es-ES"]}
    )
    assert solo_espanol.status_code == 200
    no_publica = await cliente.patch(
        f"{EVENTS}/{evento['id']}", headers=cabeceras, json={"source_locale": "en-US"}
    )
    assert no_publica.status_code == 422


async def test_un_idioma_que_la_plataforma_desactiva_no_bloquea_guardar(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    cabeceras, _ = await _bilingue(cliente, organizacion)
    async with SessionMaintenance() as session, session.begin():
        await session.execute(update(PlatformBranding).values(enabled_locales=["es-ES"]))

    guardado = await cliente.patch(
        ORGANIZACION,
        headers=cabeceras,
        json={"name": "Otro nombre", "content_locales": ["es-ES", "en-US"]},
    )
    assert guardado.status_code == 200, guardado.text


async def test_revisar_contra_un_original_que_ya_cambio_da_conflicto(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    cabeceras, evento = await _bilingue(cliente, organizacion)
    item = {"entity_type": "event", "entity_id": evento["id"], "field": "title"}
    await cliente.put(
        _url("event", evento["id"]),
        headers=cabeceras,
        params=EN,
        json={"items": [{**item, "value": "Day"}]},
    )

    respuesta = await cliente.post(
        f"{_url('event', evento['id'])}/review",
        headers=cabeceras,
        params=EN,
        json={**item, "original": "Un texto que ya no es el original"},
    )
    assert respuesta.status_code == 409


async def test_las_etiquetas_se_traducen_desde_la_organizacion(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    cabeceras, _ = await _bilingue(cliente, organizacion)

    editor = (
        await cliente.get(_url("organization", str(organizacion.id)), headers=cabeceras, params=EN)
    ).json()
    assert ("tag", "ia") in {(i["entity_type"], i["field"]) for i in editor["items"]}


async def test_el_titular_traduce_su_propia_ficha(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    await _bilingue(cliente, organizacion)
    ponente = await crear_miembro(organizacion, "speaker")
    _, cabeceras = await iniciar_sesion_con(cliente, organizacion, ponente.email, ponente.password)
    await cliente.patch(
        f"{ORGANIZACION}/members/{ponente.member_id}/profile",
        headers=cabeceras,
        json={"profile_data": {"bio": "Investigadora"}},
    )

    guardado = await cliente.put(
        _url("member_profile", str(ponente.member_id)),
        headers=cabeceras,
        params=EN,
        json={
            "items": [
                {
                    "entity_type": "member_profile",
                    "entity_id": str(ponente.member_id),
                    "field": "bio",
                    "value": "Researcher",
                }
            ]
        },
    )
    assert guardado.status_code == 200, guardado.text
    assert guardado.json()["items"][0]["status"] == "al_dia"
