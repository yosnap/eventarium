"""Formulario público de inscripción, verificación y consentimientos.

Fase 3 del PRD, fase 2 de trabajo. Mismo patrón que `test_events_public.py` y
`test_password_reset.py`: cliente HTTP real contra la app, `Host` para
resolver la organización, y la tarea de envío de correo mockeada (no se
prueba la entrega, solo que se encola cuando corresponde).
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.core.database import SessionMaintenance
from app.core.tasks import send_registration_verification_email
from app.modules.auth.verification import PROPOSITO_VERIFICACION_INSCRIPCION, generate_token
from app.modules.registrations.models import EventRegistrationQuestion
from tests.conftest import OrganizacionDePrueba, iniciar_sesion

EVENTS = "/api/v1/events"
VERIFY = "/api/v1/public/registrations/verify"
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


async def _crear_y_publicar_evento(
    cliente: AsyncClient, cabeceras: dict[str, str], slug: str, **overrides: object
) -> dict:
    creacion = await cliente.post(
        EVENTS, headers=cabeceras, json=_payload_evento(slug, **overrides)
    )
    assert creacion.status_code == 201, creacion.text
    evento = creacion.json()
    publicacion = await cliente.patch(
        f"{EVENTS}/{evento['id']}",
        headers=cabeceras,
        json={"status": "published", "visibility": "public"},
    )
    assert publicacion.status_code == 200, publicacion.text
    return publicacion.json()


def _payload_inscripcion(**overrides: object) -> dict:
    payload = {
        "email": "asistente@example.com",
        "full_name": "Asistente de Prueba",
        "answers": [],
        "data_processing_accepted": True,
        "marketing_accepted": False,
        "recording_accepted": False,
        "turnstile_token": "token-de-prueba",
    }
    payload.update(overrides)
    return payload


async def _inscribir(cliente: AsyncClient, host: str, slug: str, **overrides: object):
    return await cliente.post(
        f"/api/v1/public/events/{slug}/registrations",
        headers={"Host": host},
        json=_payload_inscripcion(**overrides),
    )


async def _estado(event_id: str, email: str) -> str | None:
    async with SessionMaintenance() as session:
        return await session.scalar(
            text("SELECT status FROM event_registrations WHERE event_id = :e AND email = :m"),
            {"e": event_id, "m": email},
        )


async def _contar_inscripciones(event_id: str, email: str) -> int:
    async with SessionMaintenance() as session:
        total = await session.scalar(
            text("SELECT count(*) FROM event_registrations WHERE event_id = :e AND email = :m"),
            {"e": event_id, "m": email},
        )
    return int(total or 0)


async def _registration_id(event_id: str, email: str) -> uuid.UUID:
    async with SessionMaintenance() as session:
        valor = await session.scalar(
            text("SELECT id FROM event_registrations WHERE event_id = :e AND email = :m"),
            {"e": event_id, "m": email},
        )
    assert valor is not None
    return valor


async def _verificar(cliente: AsyncClient, host: str, event_id: str, email: str) -> dict:
    registration_id = await _registration_id(event_id, email)
    token = await generate_token(PROPOSITO_VERIFICACION_INSCRIPCION, str(registration_id))
    respuesta = await cliente.post(VERIFY, headers={"Host": host}, json={"token": token})
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


async def _crear_pregunta(
    evento: dict,
    organizacion: OrganizacionDePrueba,
    *,
    type_: str,
    label: str,
    required: bool,
    options: list[str] | None = None,
) -> str:
    async with SessionMaintenance() as session:
        pregunta = EventRegistrationQuestion(
            event_id=uuid.UUID(evento["id"]),
            organization_id=organizacion.id,
            type=type_,
            label=label,
            required=required,
            sort_order=0,
            options=options,
        )
        session.add(pregunta)
        await session.commit()
        await session.refresh(pregunta)
        return str(pregunta.id)


@pytest.fixture(autouse=True)
def _correo_de_verificacion_encolado_sincrono():
    with patch.object(send_registration_verification_email, "kiq", new_callable=AsyncMock) as tarea:
        yield tarea


async def test_alta_con_verificacion_obligatoria_queda_pendiente_de_verificacion(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_y_publicar_evento(cliente, cabeceras, "libre")

    respuesta = await _inscribir(cliente, organizacion.host, "libre")
    assert respuesta.status_code == 202, respuesta.text
    assert await _estado(evento["id"], "asistente@example.com") == "pending_verification"


async def test_verificar_con_aforo_libre_confirma(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_y_publicar_evento(cliente, cabeceras, "aforo-libre", capacity=5)
    await _inscribir(cliente, organizacion.host, "aforo-libre")

    resultado = await _verificar(cliente, organizacion.host, evento["id"], "asistente@example.com")

    assert resultado["status"] == "confirmed"
    assert await _estado(evento["id"], "asistente@example.com") == "confirmed"


async def test_segunda_verificacion_tras_agotar_aforo_queda_en_lista_de_espera(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_y_publicar_evento(cliente, cabeceras, "aforo-uno", capacity=1)
    await _inscribir(cliente, organizacion.host, "aforo-uno", email="primero@example.com")
    await _inscribir(cliente, organizacion.host, "aforo-uno", email="segundo@example.com")

    primero = await _verificar(cliente, organizacion.host, evento["id"], "primero@example.com")
    segundo = await _verificar(cliente, organizacion.host, evento["id"], "segundo@example.com")

    assert primero["status"] == "confirmed"
    assert segundo["status"] == "waitlisted"


async def test_dos_verificaciones_simultaneas_no_superan_el_aforo(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    """El `SELECT ... FOR UPDATE` de `lock_event_for_capacity` serializa la
    evaluación de aforo: dos verificaciones concurrentes contra el último
    hueco no pueden confirmar a las dos personas."""
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_y_publicar_evento(cliente, cabeceras, "concurrencia", capacity=1)
    await _inscribir(cliente, organizacion.host, "concurrencia", email="uno@example.com")
    await _inscribir(cliente, organizacion.host, "concurrencia", email="dos@example.com")

    token_uno = await generate_token(
        PROPOSITO_VERIFICACION_INSCRIPCION,
        str(await _registration_id(evento["id"], "uno@example.com")),
    )
    token_dos = await generate_token(
        PROPOSITO_VERIFICACION_INSCRIPCION,
        str(await _registration_id(evento["id"], "dos@example.com")),
    )

    respuestas = await asyncio.gather(
        cliente.post(VERIFY, headers={"Host": organizacion.host}, json={"token": token_uno}),
        cliente.post(VERIFY, headers={"Host": organizacion.host}, json={"token": token_dos}),
    )
    estados = sorted(respuesta.json()["status"] for respuesta in respuestas)
    assert estados == ["confirmed", "waitlisted"]


async def test_evento_con_aprobacion_queda_pendiente_de_aprobacion_aunque_haya_aforo(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_y_publicar_evento(
        cliente, cabeceras, "con-aprobacion", registration_mode="approval", capacity=5
    )
    await _inscribir(cliente, organizacion.host, "con-aprobacion")

    resultado = await _verificar(cliente, organizacion.host, evento["id"], "asistente@example.com")

    assert resultado["status"] == "pending_approval"


async def test_evento_sin_verificacion_evalua_el_estado_al_enviar_el_formulario(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_y_publicar_evento(
        cliente, cabeceras, "sin-verificacion", email_verification_required=False, capacity=5
    )

    respuesta = await _inscribir(cliente, organizacion.host, "sin-verificacion")

    assert respuesta.status_code == 202, respuesta.text
    assert await _estado(evento["id"], "asistente@example.com") == "confirmed"


async def test_evento_de_pago_rechaza_el_alta_gratuita(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un evento `paid` solo admite inscripción a través del embudo de compra
    (`POST /public/events/{slug}/checkout`), que captura el tipo de entrada y
    el código de descuento en la misma transacción que crea la inscripción
    (fase 6 del PRD, hallazgo C1/C1b del code review). El endpoint gratuito
    (`POST /public/events/{slug}/registrations`) nunca los captura, así que
    antes dejaba una inscripción `pending_payment` sin ningún pago posible —
    ahora responde 409 sin llegar a crear nada. Publicar el evento exige
    además una cuenta Stripe operativa y un tipo de entrada vigente (fase 6,
    fase 2 de trabajo, hallazgos #4 y C1b): ambos se simulan aquí para no
    acoplar este test a esas fases."""
    from app.core.config import Settings
    from app.modules.events import service as events_service
    from app.modules.payments.models import OrganizationStripeAccount

    monkeypatch.setattr(
        events_service,
        "get_settings",
        lambda: Settings(
            stripe_secret_key="sk_test_" + "a" * 40, stripe_webhook_secret="whsec_" + "b" * 40
        ),
    )
    async with SessionMaintenance() as session:
        session.add(
            OrganizationStripeAccount(
                organization_id=organizacion.id,
                stripe_account_id=f"acct_{organizacion.slug}",
                charges_enabled=True,
            )
        )
        await session.commit()

    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    creacion = await cliente.post(
        EVENTS,
        headers=cabeceras,
        json=_payload_evento(
            "de-pago", registration_mode="paid", email_verification_required=False
        ),
    )
    assert creacion.status_code == 201, creacion.text
    evento_id = creacion.json()["id"]
    tipo = await cliente.post(
        f"{EVENTS}/{evento_id}/ticket-types",
        headers=cabeceras,
        json={"name": "General", "price_cents": 1000},
    )
    assert tipo.status_code == 201, tipo.text
    publicacion = await cliente.patch(
        f"{EVENTS}/{evento_id}",
        headers=cabeceras,
        json={"status": "published", "visibility": "public"},
    )
    assert publicacion.status_code == 200, publicacion.text
    evento = publicacion.json()

    respuesta = await _inscribir(cliente, organizacion.host, "de-pago")

    assert respuesta.status_code == 409, respuesta.text
    assert await _estado(evento["id"], "asistente@example.com") is None


async def test_sin_aceptar_tratamiento_de_datos_falla(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    await _crear_y_publicar_evento(cliente, cabeceras, "sin-consentir")

    respuesta = await _inscribir(
        cliente, organizacion.host, "sin-consentir", data_processing_accepted=False
    )

    assert respuesta.status_code == 422


async def test_el_mismo_email_no_crea_una_segunda_inscripcion_y_responde_igual(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_y_publicar_evento(cliente, cabeceras, "no-filtrado")

    primera = await _inscribir(cliente, organizacion.host, "no-filtrado")
    segunda = await _inscribir(cliente, organizacion.host, "no-filtrado")

    assert primera.status_code == segunda.status_code == 202
    assert primera.json() == segunda.json()
    assert await _contar_inscripciones(evento["id"], "asistente@example.com") == 1


async def test_reenviar_a_un_email_ya_inscrito_reencola_el_correo_de_verificacion(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    _correo_de_verificacion_encolado_sincrono: AsyncMock,
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    await _crear_y_publicar_evento(cliente, cabeceras, "reenvio")

    await _inscribir(cliente, organizacion.host, "reenvio")
    await _inscribir(cliente, organizacion.host, "reenvio")

    assert _correo_de_verificacion_encolado_sincrono.await_count == 2


async def test_token_invalido_da_error_generico(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    respuesta = await cliente.post(
        VERIFY, headers={"Host": organizacion.host}, json={"token": "inventado"}
    )
    assert respuesta.status_code == 422


async def test_evento_inexistente_da_404(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    respuesta = await _inscribir(cliente, organizacion.host, "no-existe")
    assert respuesta.status_code == 404


async def test_una_pregunta_obligatoria_sin_respuesta_falla(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_y_publicar_evento(cliente, cabeceras, "con-pregunta")
    await _crear_pregunta(
        evento, organizacion, type_="short_text", label="¿Empresa?", required=True
    )

    respuesta = await _inscribir(cliente, organizacion.host, "con-pregunta")

    assert respuesta.status_code == 422


async def test_una_respuesta_valida_se_guarda(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_y_publicar_evento(cliente, cabeceras, "con-respuesta")
    pregunta_id = await _crear_pregunta(
        evento,
        organizacion,
        type_="single_choice",
        label="¿Camiseta?",
        required=True,
        options=["S", "M", "L"],
    )

    respuesta = await _inscribir(
        cliente,
        organizacion.host,
        "con-respuesta",
        answers=[{"question_id": pregunta_id, "value": "M"}],
    )

    assert respuesta.status_code == 202, respuesta.text
    async with SessionMaintenance() as session:
        valor = await session.scalar(
            text(
                "SELECT a.value FROM event_registration_answers a "
                "JOIN event_registrations r ON r.id = a.registration_id "
                "WHERE r.event_id = :e"
            ),
            {"e": evento["id"]},
        )
    assert valor == "M"


async def test_una_opcion_invalida_falla(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_y_publicar_evento(cliente, cabeceras, "con-opcion-invalida")
    pregunta_id = await _crear_pregunta(
        evento,
        organizacion,
        type_="single_choice",
        label="¿Camiseta?",
        required=False,
        options=["S", "M", "L"],
    )

    respuesta = await _inscribir(
        cliente,
        organizacion.host,
        "con-opcion-invalida",
        answers=[{"question_id": pregunta_id, "value": "XL"}],
    )

    assert respuesta.status_code == 422


async def test_listar_preguntas_de_un_evento(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_y_publicar_evento(cliente, cabeceras, "con-listado-preguntas")
    await _crear_pregunta(
        evento, organizacion, type_="short_text", label="¿Empresa?", required=False
    )
    await _crear_pregunta(
        evento,
        organizacion,
        type_="single_choice",
        label="¿Camiseta?",
        required=True,
        options=["S", "M", "L"],
    )

    respuesta = await cliente.get(
        "/api/v1/public/events/con-listado-preguntas/registration-questions",
        headers={"Host": organizacion.host},
    )

    assert respuesta.status_code == 200, respuesta.text
    etiquetas = {pregunta["label"] for pregunta in respuesta.json()}
    assert etiquetas == {"¿Empresa?", "¿Camiseta?"}


async def test_una_respuesta_a_pregunta_ajena_falla(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    await _crear_y_publicar_evento(cliente, cabeceras, "sin-preguntas")

    respuesta = await _inscribir(
        cliente,
        organizacion.host,
        "sin-preguntas",
        answers=[{"question_id": str(uuid.uuid4()), "value": "lo que sea"}],
    )

    assert respuesta.status_code == 422
