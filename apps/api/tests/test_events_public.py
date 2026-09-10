"""Endpoints públicos de eventos, sesiones y ponentes (fase 4 del PRD)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient

from app.core.database import SessionMaintenance
from app.core.ratelimit import PUBLICO_POR_IP
from app.modules.events import repository
from app.modules.registrations.models import EventRegistration
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


async def _crear_inscripcion(
    organization_id: uuid.UUID, event_id: uuid.UUID, email: str, **overrides: object
) -> None:
    """Inserta una inscripción directamente en base de datos, saltándose el
    formulario público: los tests de `reserved_count` necesitan estados
    (`pending_payment` con ventana concreta, promoción de lista de espera con
    ventana concreta) que el flujo público no permite fijar a voluntad."""
    async with SessionMaintenance() as session:
        session.add(
            EventRegistration(
                organization_id=organization_id,
                event_id=event_id,
                email=email,
                full_name="Persona de prueba",
                status=overrides.pop("status", "confirmed"),
                **overrides,
            )
        )
        await session.commit()


async def _contar_reservadas(organization_id: uuid.UUID) -> dict[str, int]:
    """`reserved_count` de cada evento publicado de la organización, por slug —
    ejecuta `public_events_with_confirmed_count_query` directamente contra la
    base de datos, igual que hace `list_public_events`."""
    async with SessionMaintenance() as session:
        filas = (
            await session.execute(repository.public_events_with_confirmed_count_query(organization_id))
        ).all()
        return {evento.slug: reservadas for evento, reservadas in filas}


async def test_reserved_count_es_cero_sin_inscripciones(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_evento(cliente, cabeceras, slug="sin-inscripciones")
    await _publicar(cliente, cabeceras, evento["id"])

    conteos = await _contar_reservadas(organizacion.id)
    assert conteos["sin-inscripciones"] == 0


async def test_reserved_count_solo_cuenta_los_estados_que_ocupan_aforo(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_evento(cliente, cabeceras, slug="varios-estados")
    await _publicar(cliente, cabeceras, evento["id"])
    event_id = uuid.UUID(evento["id"])
    organization_id = organizacion.id

    await _crear_inscripcion(organization_id, event_id, "confirmada@example.com", status="confirmed")
    await _crear_inscripcion(
        organization_id, event_id, "pendiente-verificacion@example.com", status="pending_verification"
    )
    await _crear_inscripcion(organization_id, event_id, "rechazada@example.com", status="rejected")
    await _crear_inscripcion(organization_id, event_id, "cancelada@example.com", status="cancelled")
    await _crear_inscripcion(
        organization_id,
        event_id,
        "pago-caducado@example.com",
        status="pending_payment",
        payment_expires_at=AHORA - timedelta(minutes=5),
    )

    conteos = await _contar_reservadas(organizacion.id)
    assert conteos["varios-estados"] == 1


async def test_reserved_count_incluye_pending_payment_dentro_de_ventana(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_evento(cliente, cabeceras, slug="pago-en-curso")
    await _publicar(cliente, cabeceras, evento["id"])
    event_id = uuid.UUID(evento["id"])

    await _crear_inscripcion(
        organizacion.id,
        event_id,
        "comprando@example.com",
        status="pending_payment",
        payment_expires_at=AHORA + timedelta(minutes=10),
    )

    conteos = await _contar_reservadas(organizacion.id)
    assert conteos["pago-en-curso"] == 1


async def test_reserved_count_incluye_promocion_de_lista_de_espera_dentro_de_ventana(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_evento(cliente, cabeceras, slug="promocion-lista-espera")
    await _publicar(cliente, cabeceras, evento["id"])
    event_id = uuid.UUID(evento["id"])

    await _crear_inscripcion(
        organizacion.id,
        event_id,
        "promovida@example.com",
        status="waitlisted",
        waitlist_promoted_at=AHORA,
        waitlist_promotion_expires_at=AHORA + timedelta(hours=1),
    )
    await _crear_inscripcion(
        organizacion.id,
        event_id,
        "promocion-caducada@example.com",
        status="waitlisted",
        waitlist_promoted_at=AHORA - timedelta(hours=2),
        waitlist_promotion_expires_at=AHORA - timedelta(hours=1),
    )
    await _crear_inscripcion(
        organizacion.id, event_id, "en-lista-sin-promover@example.com", status="waitlisted"
    )

    conteos = await _contar_reservadas(organizacion.id)
    assert conteos["promocion-lista-espera"] == 1


async def test_reserved_count_no_mezcla_eventos_distintos(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento_a = await _crear_evento(cliente, cabeceras, slug="evento-a")
    await _publicar(cliente, cabeceras, evento_a["id"])
    evento_b = await _crear_evento(
        cliente,
        cabeceras,
        slug="evento-b",
        starts_at=(AHORA + timedelta(days=5)).isoformat(),
        ends_at=(AHORA + timedelta(days=6)).isoformat(),
    )
    await _publicar(cliente, cabeceras, evento_b["id"])

    await _crear_inscripcion(
        organizacion.id, uuid.UUID(evento_a["id"]), "una@example.com", status="confirmed"
    )
    for correo in ("dos@example.com", "tres@example.com"):
        await _crear_inscripcion(
            organizacion.id, uuid.UUID(evento_b["id"]), correo, status="confirmed"
        )

    conteos = await _contar_reservadas(organizacion.id)
    assert conteos["evento-a"] == 1
    assert conteos["evento-b"] == 2


async def test_reserved_count_conserva_el_orden_por_starts_at(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    tardio = await _crear_evento(
        cliente,
        cabeceras,
        slug="tardio",
        starts_at=(AHORA + timedelta(days=10)).isoformat(),
        ends_at=(AHORA + timedelta(days=11)).isoformat(),
    )
    await _publicar(cliente, cabeceras, tardio["id"])
    temprano = await _crear_evento(
        cliente,
        cabeceras,
        slug="temprano",
        starts_at=(AHORA + timedelta(days=1)).isoformat(),
        ends_at=(AHORA + timedelta(days=2)).isoformat(),
    )
    await _publicar(cliente, cabeceras, temprano["id"])

    async with SessionMaintenance() as session:
        filas = (
            await session.execute(
                repository.public_events_with_confirmed_count_query(organizacion.id)
            )
        ).all()
    assert [evento.slug for evento, _ in filas] == ["temprano", "tardio"]


async def test_el_listado_publico_tiene_limite_de_peticiones_por_ip(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    cabeceras = {"Host": organizacion.host}
    for _ in range(PUBLICO_POR_IP):
        respuesta = await cliente.get(PUBLIC_EVENTS, headers=cabeceras)
        assert respuesta.status_code == 200

    bloqueada = await cliente.get(PUBLIC_EVENTS, headers=cabeceras)
    assert bloqueada.status_code == 429
