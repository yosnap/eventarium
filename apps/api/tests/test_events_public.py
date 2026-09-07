"""Endpoints públicos de eventos, sesiones y ponentes (fase 4 del PRD)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient

from app.core.ratelimit import PUBLICO_POR_IP
from tests.conftest import OrganizacionDePrueba, crear_miembro, iniciar_sesion, iniciar_sesion_con

PUBLIC_EVENTS = "/api/v1/public/events"
PUBLIC_SPEAKERS = "/api/v1/public/speakers"
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


async def _crear_evento(
    cliente: AsyncClient, cabeceras: dict[str, str], **overrides: object
) -> dict:
    slug = overrides.pop("slug", "iawic-2026")
    respuesta = await cliente.post(
        EVENTS, headers=cabeceras, json=_payload_evento(slug, **overrides)
    )
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


async def _publicar(
    cliente: AsyncClient, cabeceras: dict[str, str], event_id: str, *, visibility: str = "public"
) -> None:
    respuesta = await cliente.patch(
        f"{EVENTS}/{event_id}",
        headers=cabeceras,
        json={"status": "published", "visibility": visibility},
    )
    assert respuesta.status_code == 200, respuesta.text


async def test_el_listado_publico_solo_incluye_published_public(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    borrador = await _crear_evento(cliente, cabeceras, slug="borrador")
    oculto = await _crear_evento(cliente, cabeceras, slug="oculto")
    await _publicar(cliente, cabeceras, oculto["id"], visibility="hidden")
    publico = await _crear_evento(cliente, cabeceras, slug="publico")
    await _publicar(cliente, cabeceras, publico["id"], visibility="public")

    listado = await cliente.get(PUBLIC_EVENTS, headers={"Host": organizacion.host})
    assert listado.status_code == 200
    slugs = [e["slug"] for e in listado.json()]
    assert slugs == ["publico"]
    assert borrador["slug"] not in slugs


async def test_el_detalle_de_un_evento_no_publico_da_404_uniforme(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    cabeceras_publicas = {"Host": organizacion.host}

    await _crear_evento(cliente, cabeceras, slug="en-borrador")
    oculto = await _crear_evento(cliente, cabeceras, slug="oculto-2")
    await _publicar(cliente, cabeceras, oculto["id"], visibility="hidden")
    privado = await _crear_evento(cliente, cabeceras, slug="privado-2")
    await _publicar(cliente, cabeceras, privado["id"], visibility="private")

    for slug in ("en-borrador", "oculto-2", "privado-2", "no-existe"):
        respuesta = await cliente.get(f"{PUBLIC_EVENTS}/{slug}", headers=cabeceras_publicas)
        assert respuesta.status_code == 404
        assert respuesta.json()["detail"] == "El evento no existe."


async def test_el_detalle_incluye_agenda_y_participantes_sin_correo(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    ponente = await crear_miembro(organizacion, "speaker")
    evento = await _crear_evento(cliente, cabeceras, slug="con-agenda")
    sesion = (
        await cliente.post(
            f"{EVENTS}/{evento['id']}/sessions",
            headers=cabeceras,
            json={
                "session_type": "talk",
                "title": "Charla estrella",
                "starts_at": (AHORA + timedelta(hours=1)).isoformat(),
                "ends_at": (AHORA + timedelta(hours=2)).isoformat(),
            },
        )
    ).json()
    miembro_evento = (
        await cliente.post(
            f"{EVENTS}/{evento['id']}/members",
            headers=cabeceras,
            json={"organization_member_id": str(ponente.member_id)},
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
    await _publicar(cliente, cabeceras, evento["id"])

    detalle = await cliente.get(f"{PUBLIC_EVENTS}/con-agenda", headers={"Host": organizacion.host})
    assert detalle.status_code == 200
    cuerpo = detalle.json()
    assert len(cuerpo["sessions"]) == 1
    participante = cuerpo["sessions"][0]["participants"][0]
    assert participante["role_key"] == "speaker"
    assert participante["public_slug"] is None
    assert "email" not in participante


async def test_una_sesion_de_evento_no_publicado_da_404_aunque_se_conozca_el_id(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_evento(cliente, cabeceras, slug="sin-publicar")
    sesion = (
        await cliente.post(
            f"{EVENTS}/{evento['id']}/sessions",
            headers=cabeceras,
            json={
                "session_type": "talk",
                "title": "Charla oculta",
                "starts_at": (AHORA + timedelta(hours=1)).isoformat(),
                "ends_at": (AHORA + timedelta(hours=2)).isoformat(),
            },
        )
    ).json()

    respuesta = await cliente.get(
        f"{PUBLIC_EVENTS}/sin-publicar/sessions/{sesion['id']}",
        headers={"Host": organizacion.host},
    )
    assert respuesta.status_code == 404


async def test_una_sesion_publicada_se_ve_anidada_bajo_su_evento(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_evento(cliente, cabeceras, slug="con-sesion-publica")
    sesion = (
        await cliente.post(
            f"{EVENTS}/{evento['id']}/sessions",
            headers=cabeceras,
            json={
                "session_type": "talk",
                "title": "Charla visible",
                "starts_at": (AHORA + timedelta(hours=1)).isoformat(),
                "ends_at": (AHORA + timedelta(hours=2)).isoformat(),
            },
        )
    ).json()
    await _publicar(cliente, cabeceras, evento["id"])

    respuesta = await cliente.get(
        f"{PUBLIC_EVENTS}/con-sesion-publica/sessions/{sesion['id']}",
        headers={"Host": organizacion.host},
    )
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["event_slug"] == "con-sesion-publica"
    assert cuerpo["title"] == "Charla visible"


async def test_un_ponente_sin_perfil_publico_da_404(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    respuesta = await cliente.get(
        f"{PUBLIC_SPEAKERS}/no-existe", headers={"Host": organizacion.host}
    )
    assert respuesta.status_code == 404


async def test_el_perfil_publico_de_un_ponente_expone_la_lista_blanca_y_el_historial(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras_admin = await iniciar_sesion(cliente, organizacion)
    ponente = await crear_miembro(organizacion, "speaker")

    _, cabeceras_ponente = await iniciar_sesion_con(
        cliente, organizacion, ponente.email, ponente.password
    )
    await cliente.patch(
        "/api/v1/users/me/public-profile",
        headers=cabeceras_ponente,
        json={
            "public_slug": "la-gran-ponente",
            "source_organization_member_id": str(ponente.member_id),
        },
    )

    evento = await _crear_evento(cliente, cabeceras_admin, slug="con-ponente-publico")
    sesion = (
        await cliente.post(
            f"{EVENTS}/{evento['id']}/sessions",
            headers=cabeceras_admin,
            json={
                "session_type": "talk",
                "title": "Su charla",
                "starts_at": (AHORA + timedelta(hours=1)).isoformat(),
                "ends_at": (AHORA + timedelta(hours=2)).isoformat(),
            },
        )
    ).json()
    miembro_evento = (
        await cliente.post(
            f"{EVENTS}/{evento['id']}/members",
            headers=cabeceras_admin,
            json={"organization_member_id": str(ponente.member_id)},
        )
    ).json()
    await cliente.put(
        f"{EVENTS}/{evento['id']}/sessions/{sesion['id']}/participants",
        headers=cabeceras_admin,
        json={
            "expected_updated_at": sesion["updated_at"],
            "participants": [{"event_member_id": miembro_evento["id"], "role_key": "speaker"}],
        },
    )
    await _publicar(cliente, cabeceras_admin, evento["id"])

    perfil = await cliente.get(
        f"{PUBLIC_SPEAKERS}/la-gran-ponente", headers={"Host": organizacion.host}
    )
    assert perfil.status_code == 200
    cuerpo = perfil.json()
    assert cuerpo["public_slug"] == "la-gran-ponente"
    assert set(cuerpo["fields"].keys()) <= {
        "bio",
        "titular",
        "empresa",
        "curriculum",
        "web",
        "contacto",
    }
    assert len(cuerpo["history"]) == 1
    assert cuerpo["history"][0]["event_slug"] == "con-ponente-publico"

    # La agenda pública del evento enlaza al perfil recién activado.
    detalle = await cliente.get(
        f"{PUBLIC_EVENTS}/con-ponente-publico", headers={"Host": organizacion.host}
    )
    assert detalle.json()["sessions"][0]["participants"][0]["public_slug"] == "la-gran-ponente"


async def test_dos_organizaciones_no_ven_los_eventos_ni_ponentes_de_la_otra(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    otra_organizacion: OrganizacionDePrueba,
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_evento(cliente, cabeceras, slug="evento-de-acme")
    await _publicar(cliente, cabeceras, evento["id"])

    listado_rival = await cliente.get(PUBLIC_EVENTS, headers={"Host": otra_organizacion.host})
    assert listado_rival.json() == []

    detalle_rival = await cliente.get(
        f"{PUBLIC_EVENTS}/evento-de-acme", headers={"Host": otra_organizacion.host}
    )
    assert detalle_rival.status_code == 404


async def test_el_listado_publico_tiene_limite_de_peticiones_por_ip(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    cabeceras = {"Host": organizacion.host}
    for _ in range(PUBLICO_POR_IP):
        respuesta = await cliente.get(PUBLIC_EVENTS, headers=cabeceras)
        assert respuesta.status_code == 200

    bloqueada = await cliente.get(PUBLIC_EVENTS, headers=cabeceras)
    assert bloqueada.status_code == 429
