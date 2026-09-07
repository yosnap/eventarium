"""Roster de eventos y asignación de participantes a sesiones (fase 3 del PRD)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient

from tests.conftest import OrganizacionDePrueba, crear_miembro, iniciar_sesion, iniciar_sesion_como

EVENTS = "/api/v1/events"

AHORA = datetime.now(UTC).replace(microsecond=0)


def _payload_evento(slug: str = "iawic-2026") -> dict:
    return {
        "slug": slug,
        "title": "IA Week in Cascais 2026",
        "starts_at": AHORA.isoformat(),
        "ends_at": (AHORA + timedelta(days=2)).isoformat(),
        "location_mode": "in_person",
    }


async def _crear_evento_con_sesion(
    cliente: AsyncClient, cabeceras: dict[str, str]
) -> tuple[str, dict]:
    evento = (await cliente.post(EVENTS, headers=cabeceras, json=_payload_evento())).json()
    sesion = (
        await cliente.post(
            f"{EVENTS}/{evento['id']}/sessions",
            headers=cabeceras,
            json={
                "session_type": "talk",
                "title": "Charla",
                "starts_at": (AHORA + timedelta(hours=1)).isoformat(),
                "ends_at": (AHORA + timedelta(hours=2)).isoformat(),
            },
        )
    ).json()
    return evento["id"], sesion


async def _anadir_al_roster(
    cliente: AsyncClient, cabeceras: dict[str, str], event_id: str, organization_member_id: str
) -> dict:
    respuesta = await cliente.post(
        f"{EVENTS}/{event_id}/members",
        headers=cabeceras,
        json={"organization_member_id": organization_member_id},
    )
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


async def test_anadir_a_alguien_al_roster_y_asignarlo_a_una_sesion(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    ponente = await crear_miembro(organizacion, "speaker")
    event_id, sesion = await _crear_evento_con_sesion(cliente, cabeceras)

    miembro_evento = await _anadir_al_roster(cliente, cabeceras, event_id, str(ponente.member_id))
    assert miembro_evento["user_id"] == str(ponente.user_id)

    asignacion = await cliente.put(
        f"{EVENTS}/{event_id}/sessions/{sesion['id']}/participants",
        headers=cabeceras,
        json={
            "expected_updated_at": sesion["updated_at"],
            "participants": [{"event_member_id": miembro_evento["id"], "role_key": "speaker"}],
        },
    )
    assert asignacion.status_code == 200, asignacion.text
    participantes = asignacion.json()
    assert len(participantes) == 1
    assert participantes[0]["role_key"] == "speaker"
    assert participantes[0]["user_id"] == str(ponente.user_id)


async def test_la_misma_persona_puede_tener_dos_roles_en_la_misma_sesion(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    ponente = await crear_miembro(organizacion, "speaker")
    event_id, sesion = await _crear_evento_con_sesion(cliente, cabeceras)
    miembro_evento = await _anadir_al_roster(cliente, cabeceras, event_id, str(ponente.member_id))

    respuesta = await cliente.put(
        f"{EVENTS}/{event_id}/sessions/{sesion['id']}/participants",
        headers=cabeceras,
        json={
            "expected_updated_at": sesion["updated_at"],
            "participants": [
                {"event_member_id": miembro_evento["id"], "role_key": "speaker"},
                {"event_member_id": miembro_evento["id"], "role_key": "moderator"},
            ],
        },
    )
    assert respuesta.status_code == 200, respuesta.text
    roles = sorted(p["role_key"] for p in respuesta.json())
    assert roles == ["moderator", "speaker"]


async def test_asignar_a_alguien_fuera_del_roster_falla_con_422(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    event_id, sesion = await _crear_evento_con_sesion(cliente, cabeceras)

    respuesta = await cliente.put(
        f"{EVENTS}/{event_id}/sessions/{sesion['id']}/participants",
        headers=cabeceras,
        json={
            "expected_updated_at": sesion["updated_at"],
            "participants": [
                {"event_member_id": "00000000-0000-0000-0000-000000000000", "role_key": "speaker"}
            ],
        },
    )
    assert respuesta.status_code == 422


async def test_quitar_del_roster_con_participaciones_activas_da_409(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    ponente = await crear_miembro(organizacion, "speaker")
    event_id, sesion = await _crear_evento_con_sesion(cliente, cabeceras)
    miembro_evento = await _anadir_al_roster(cliente, cabeceras, event_id, str(ponente.member_id))
    await cliente.put(
        f"{EVENTS}/{event_id}/sessions/{sesion['id']}/participants",
        headers=cabeceras,
        json={
            "expected_updated_at": sesion["updated_at"],
            "participants": [{"event_member_id": miembro_evento["id"], "role_key": "speaker"}],
        },
    )

    respuesta = await cliente.delete(
        f"{EVENTS}/{event_id}/members/{miembro_evento['id']}", headers=cabeceras
    )
    assert respuesta.status_code == 409


async def test_quitar_del_roster_sin_participaciones_funciona(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    ponente = await crear_miembro(organizacion, "speaker")
    event_id, _ = await _crear_evento_con_sesion(cliente, cabeceras)
    miembro_evento = await _anadir_al_roster(cliente, cabeceras, event_id, str(ponente.member_id))

    respuesta = await cliente.delete(
        f"{EVENTS}/{event_id}/members/{miembro_evento['id']}", headers=cabeceras
    )
    assert respuesta.status_code == 204

    listado = await cliente.get(f"{EVENTS}/{event_id}/members", headers=cabeceras)
    assert listado.json() == []


async def test_anadir_dos_veces_a_la_misma_persona_da_409(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    ponente = await crear_miembro(organizacion, "speaker")
    event_id, _ = await _crear_evento_con_sesion(cliente, cabeceras)
    await _anadir_al_roster(cliente, cabeceras, event_id, str(ponente.member_id))

    repetido = await cliente.post(
        f"{EVENTS}/{event_id}/members",
        headers=cabeceras,
        json={"organization_member_id": str(ponente.member_id)},
    )
    assert repetido.status_code == 409


async def test_dos_guardados_concurrentes_de_participantes_el_segundo_da_409(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    ponente = await crear_miembro(organizacion, "speaker")
    event_id, sesion = await _crear_evento_con_sesion(cliente, cabeceras)
    miembro_evento = await _anadir_al_roster(cliente, cabeceras, event_id, str(ponente.member_id))

    payload = {
        "expected_updated_at": sesion["updated_at"],
        "participants": [{"event_member_id": miembro_evento["id"], "role_key": "speaker"}],
    }
    primero = await cliente.put(
        f"{EVENTS}/{event_id}/sessions/{sesion['id']}/participants", headers=cabeceras, json=payload
    )
    assert primero.status_code == 200

    # El segundo guardado sigue mandando el `updated_at` que tenía cargado antes
    # del primer guardado: ya no coincide con el actual, así que debe chocar.
    segundo = await cliente.put(
        f"{EVENTS}/{event_id}/sessions/{sesion['id']}/participants", headers=cabeceras, json=payload
    )
    assert segundo.status_code == 409


async def test_sin_events_write_no_se_puede_anadir_al_roster(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras_owner = await iniciar_sesion(cliente, organizacion)
    ponente = await crear_miembro(organizacion, "speaker")
    event_id, _ = await _crear_evento_con_sesion(cliente, cabeceras_owner)

    _, cabeceras_attendee = await iniciar_sesion_como(cliente, organizacion, "attendee")
    respuesta = await cliente.post(
        f"{EVENTS}/{event_id}/members",
        headers=cabeceras_attendee,
        json={"organization_member_id": str(ponente.member_id)},
    )
    assert respuesta.status_code == 403
