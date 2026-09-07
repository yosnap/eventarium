"""Historial de un ponente entre ediciones (`speakers_repository`, fase 3 del PRD)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient

from app.core.database import SessionApp, set_organization_context
from app.modules.events import speakers_repository
from tests.conftest import OrganizacionDePrueba, crear_miembro, iniciar_sesion

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


async def _crear_evento_publicado_con_ponente(
    cliente: AsyncClient,
    cabeceras: dict[str, str],
    slug: str,
    organization_member_id: str,
    *,
    visibility: str = "public",
) -> None:
    evento = (await cliente.post(EVENTS, headers=cabeceras, json=_payload_evento(slug))).json()
    sesion = (
        await cliente.post(
            f"{EVENTS}/{evento['id']}/sessions",
            headers=cabeceras,
            json={
                "session_type": "talk",
                "title": f"Charla de {slug}",
                "starts_at": (AHORA + timedelta(hours=1)).isoformat(),
                "ends_at": (AHORA + timedelta(hours=2)).isoformat(),
            },
        )
    ).json()
    miembro_evento = (
        await cliente.post(
            f"{EVENTS}/{evento['id']}/members",
            headers=cabeceras,
            json={"organization_member_id": organization_member_id},
        )
    ).json()
    await cliente.put(
        f"{EVENTS}/{evento['id']}/sessions/{sesion['id']}/participants",
        headers=cabeceras,
        json={
            "expected_updated_at": sesion["updated_at"],
            "participants": [{"event_member_id": miembro_evento["id"], "role_key": "speaker"}],
        },
    )
    await cliente.patch(
        f"{EVENTS}/{evento['id']}",
        headers=cabeceras,
        json={"status": "published", "visibility": visibility},
    )


async def test_el_historial_incluye_ediciones_published_y_public(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    ponente = await crear_miembro(organizacion, "speaker")
    await _crear_evento_publicado_con_ponente(
        cliente, cabeceras, "edicion-2025", str(ponente.member_id), visibility="public"
    )

    async with SessionApp() as session:
        async with session.begin():
            await set_organization_context(session, organizacion.id, ponente.user_id)
            historial = await speakers_repository.get_speaker_history(
                session, organizacion.id, ponente.user_id, only_published_public=True
            )

    assert len(historial) == 1


async def test_el_historial_excluye_published_private_y_published_hidden(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    ponente = await crear_miembro(organizacion, "speaker")
    await _crear_evento_publicado_con_ponente(
        cliente, cabeceras, "edicion-privada", str(ponente.member_id), visibility="private"
    )
    await _crear_evento_publicado_con_ponente(
        cliente, cabeceras, "edicion-oculta", str(ponente.member_id), visibility="hidden"
    )
    await _crear_evento_publicado_con_ponente(
        cliente, cabeceras, "edicion-publica", str(ponente.member_id), visibility="public"
    )

    async with SessionApp() as session:
        async with session.begin():
            await set_organization_context(session, organizacion.id, ponente.user_id)
            historial = await speakers_repository.get_speaker_history(
                session, organizacion.id, ponente.user_id, only_published_public=True
            )

    assert len(historial) == 1
    _, _, evento = historial[0]
    assert evento.slug == "edicion-publica"


async def test_sin_el_filtro_de_visibilidad_se_ve_todo(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    ponente = await crear_miembro(organizacion, "speaker")
    await _crear_evento_publicado_con_ponente(
        cliente, cabeceras, "edicion-privada-2", str(ponente.member_id), visibility="private"
    )

    async with SessionApp() as session:
        async with session.begin():
            await set_organization_context(session, organizacion.id, ponente.user_id)
            historial = await speakers_repository.get_speaker_history(
                session, organizacion.id, ponente.user_id, only_published_public=False
            )

    assert len(historial) == 1
