"""Vista agregada de ponentes del evento (panel de organizador)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.core.database import SessionApp, set_organization_context
from app.core.tasks import send_speaker_bio_request_email
from app.modules.organizations.models import OrganizationMember
from tests.conftest import OrganizacionDePrueba, crear_miembro, iniciar_sesion

EVENTS = "/api/v1/events"

AHORA = datetime.now(UTC).replace(microsecond=0)
CLAVES_FICHA = ("bio", "titular", "empresa", "curriculum", "web", "contacto")


def _payload_evento(slug: str) -> dict:
    return {
        "slug": slug,
        "title": f"Evento {slug}",
        "starts_at": AHORA.isoformat(),
        "ends_at": (AHORA + timedelta(days=2)).isoformat(),
        "location_mode": "in_person",
    }


async def _crear_evento(
    cliente: AsyncClient, cabeceras: dict[str, str], slug: str, n_sesiones: int = 0
) -> dict:
    evento = (await cliente.post(EVENTS, headers=cabeceras, json=_payload_evento(slug))).json()
    for n in range(n_sesiones):
        await cliente.post(
            f"{EVENTS}/{evento['id']}/sessions",
            headers=cabeceras,
            json={
                "session_type": "talk",
                "title": f"Sesión {n} de {slug}",
                "starts_at": (AHORA + timedelta(hours=n + 1)).isoformat(),
                "ends_at": (AHORA + timedelta(hours=n + 2)).isoformat(),
            },
        )
    return evento


async def _añadir_al_roster(
    cliente: AsyncClient, cabeceras: dict[str, str], evento_id: str, member_id: str
) -> str:
    respuesta = await cliente.post(
        f"{EVENTS}/{evento_id}/members",
        headers=cabeceras,
        json={"organization_member_id": member_id},
    )
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()["id"]


async def _asignar_sesion(
    cliente: AsyncClient,
    cabeceras: dict[str, str],
    evento_id: str,
    sesion_id: str,
    sesion_updated_at: str,
    miembro_evento_id: str,
) -> None:
    respuesta = await cliente.put(
        f"{EVENTS}/{evento_id}/sessions/{sesion_id}/participants",
        headers=cabeceras,
        json={
            "expected_updated_at": sesion_updated_at,
            "participants": [{"event_member_id": miembro_evento_id, "role_key": "speaker"}],
        },
    )
    assert respuesta.status_code == 200, respuesta.text


@pytest.fixture
def _pedir_bio_mockeado():
    with patch.object(send_speaker_bio_request_email, "kiq", new_callable=AsyncMock) as mock:
        yield mock


async def test_vista_agregada_con_ficha_sesion_y_ediciones(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    ponente = await crear_miembro(organizacion, "speaker")
    # Ficha a medias: bio y titular rellenas, lo demás vacío o ausente.
    async with SessionApp() as session:
        async with session.begin():
            await set_organization_context(session, organizacion.id)
            fila = await session.get(OrganizationMember, ponente.member_id)
            assert fila is not None
            fila.profile_data = {"bio": "Bio del ponente", "titular": " Titular profesional "}

    evento = await _crear_evento(cliente, cabeceras, "panel-ponentes", n_sesiones=2)
    sesiones = (await cliente.get(f"{EVENTS}/{evento['id']}/sessions", headers=cabeceras)).json()
    miembro_evento = await _añadir_al_roster(
        cliente, cabeceras, evento["id"], str(ponente.member_id)
    )
    await _asignar_sesion(
        cliente,
        cabeceras,
        evento["id"],
        sesiones[0]["id"],
        sesiones[0]["updated_at"],
        miembro_evento,
    )

    respuesta = await cliente.get(f"{EVENTS}/{evento['id']}/speakers", headers=cabeceras)
    assert respuesta.status_code == 200, respuesta.text
    vista = respuesta.json()

    assert vista["total_sesiones"] == 2
    assert len(vista["items"]) == 1
    fila = vista["items"][0]
    assert fila["email"] == ponente.email
    assert fila["titular"] == "Titular profesional"
    assert [sesion["titulo"] for sesion in fila["sesiones"]] == [sesiones[0]["title"]]
    assert fila["completitud"]["rellenas"] == 2
    assert fila["completitud"]["total"] == len(CLAVES_FICHA)
    assert fila["completitud"]["porcentaje"] == round(2 / len(CLAVES_FICHA) * 100)
    assert set(fila["completitud"]["faltantes"]) == set(CLAVES_FICHA) - {"bio", "titular"}
    assert fila["ediciones"] == 1
    assert fila["public_slug"] is None


async def test_ponente_sin_ficha_ni_sesion_sale_incompleto(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    ponente = await crear_miembro(organizacion, "speaker")
    evento = await _crear_evento(cliente, cabeceras, "sin-ficha")
    await _añadir_al_roster(cliente, cabeceras, evento["id"], str(ponente.member_id))

    respuesta = await cliente.get(f"{EVENTS}/{evento['id']}/speakers", headers=cabeceras)
    assert respuesta.status_code == 200, respuesta.text
    fila = respuesta.json()["items"][0]

    assert fila["sesiones"] == []
    assert fila["completitud"]["porcentaje"] == 0
    assert fila["completitud"]["faltantes"] == list(CLAVES_FICHA)
    assert fila["ediciones"] == 1


async def test_repetir_edicion_cuenta_eventos_de_la_organizacion(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    ponente = await crear_miembro(organizacion, "speaker")
    primera = await _crear_evento(cliente, cabeceras, "edicion-uno")
    segunda = await _crear_evento(cliente, cabeceras, "edicion-dos")
    await _añadir_al_roster(cliente, cabeceras, primera["id"], str(ponente.member_id))
    await _añadir_al_roster(cliente, cabeceras, segunda["id"], str(ponente.member_id))

    respuesta = await cliente.get(f"{EVENTS}/{segunda['id']}/speakers", headers=cabeceras)
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["items"][0]["ediciones"] == 2


async def test_el_ponente_de_otra_organizacion_no_aparece(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    otra_organizacion: OrganizacionDePrueba,
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    propio = await crear_miembro(organizacion, "speaker")
    ajeno = await crear_miembro(otra_organizacion, "speaker")
    evento = await _crear_evento(cliente, cabeceras, "aislamiento-ponentes")
    await _añadir_al_roster(cliente, cabeceras, evento["id"], str(propio.member_id))
    # Intentar colar la membresía de la otra organización en el roster propio
    # no puede funcionar: la FK compuesta la bloquea y la vista tampoco la ve.
    respuesta_ajena = await cliente.post(
        f"{EVENTS}/{evento['id']}/members",
        headers=cabeceras,
        json={"organization_member_id": str(ajeno.member_id)},
    )
    assert respuesta_ajena.status_code in (404, 422), respuesta_ajena.text

    vista = await cliente.get(f"{EVENTS}/{evento['id']}/speakers", headers=cabeceras)
    assert vista.status_code == 200, vista.text
    emails = [fila["email"] for fila in vista.json()["items"]]
    assert ajeno.email not in emails


async def test_historial_para_el_dialogo_sin_filtro_de_publicacion(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    ponente = await crear_miembro(organizacion, "speaker")
    evento = await _crear_evento(cliente, cabeceras, "con-historial", n_sesiones=1)
    sesiones = (await cliente.get(f"{EVENTS}/{evento['id']}/sessions", headers=cabeceras)).json()
    miembro_evento = await _añadir_al_roster(
        cliente, cabeceras, evento["id"], str(ponente.member_id)
    )
    await _asignar_sesion(
        cliente,
        cabeceras,
        evento["id"],
        sesiones[0]["id"],
        sesiones[0]["updated_at"],
        miembro_evento,
    )

    respuesta = await cliente.get(
        f"{EVENTS}/{evento['id']}/speakers/{ponente.user_id}/historial", headers=cabeceras
    )
    assert respuesta.status_code == 200, respuesta.text
    historial = respuesta.json()
    assert len(historial) == 1
    assert historial[0]["evento_titulo"] == evento["title"]
    assert historial[0]["rol"] == "speaker"


async def test_pedir_bio_encola_correo_y_valida_roster(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, _pedir_bio_mockeado: AsyncMock
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    ponente = await crear_miembro(organizacion, "speaker")
    evento = await _crear_evento(cliente, cabeceras, "pedir-bio")
    await _añadir_al_roster(cliente, cabeceras, evento["id"], str(ponente.member_id))

    respuesta = await cliente.post(
        f"{EVENTS}/{evento['id']}/speakers/{ponente.member_id}/pedir-bio",
        headers=cabeceras,
    )
    assert respuesta.status_code == 204, respuesta.text
    _pedir_bio_mockeado.assert_awaited_once()
    destino, organization_id, event_name = _pedir_bio_mockeado.await_args.args
    assert destino == ponente.email
    assert organization_id == str(organizacion.id)
    assert event_name == evento["title"]


async def test_pedir_bio_a_alieno_da_404(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, _pedir_bio_mockeado: AsyncMock
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_evento(cliente, cabeceras, "pedir-bio-ajeno")

    respuesta = await cliente.post(
        f"{EVENTS}/{evento['id']}/speakers/{uuid4()}/pedir-bio",
        headers=cabeceras,
    )
    assert respuesta.status_code == 404, respuesta.text
    _pedir_bio_mockeado.assert_not_awaited()


async def test_pedir_bio_a_alguien_que_no_es_ponente_da_404(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, _pedir_bio_mockeado: AsyncMock
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    voluntario = await crear_miembro(organizacion, "volunteer")
    evento = await _crear_evento(cliente, cabeceras, "pedir-bio-no-ponente")
    await _añadir_al_roster(cliente, cabeceras, evento["id"], str(voluntario.member_id))

    respuesta = await cliente.post(
        f"{EVENTS}/{evento['id']}/speakers/{voluntario.member_id}/pedir-bio",
        headers=cabeceras,
    )
    assert respuesta.status_code == 404, respuesta.text
    _pedir_bio_mockeado.assert_not_awaited()
