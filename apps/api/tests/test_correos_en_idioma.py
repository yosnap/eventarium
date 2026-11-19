"""Correos en el idioma de quien los recibe.

Cada tarea de correo recibe `locale=` por palabra clave; sin él (mensajes ya
encolados con la firma antigua) sale en español. La inscripción guarda el
idioma de la página desde la que se hizo y lo usan sus correos y el pago
diferido.

Las tareas se ejecutan dentro de `asyncio.create_task`: fijan el idioma en el
contexto, y así no se queda fijado para los tests siguientes.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Coroutine, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, patch

import jwt
import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core import mensajes
from app.core.config import get_settings
from app.core.database import SessionMaintenance
from app.core.tasks import (
    LONGITUD_MAXIMA_DEL_ASUNTO,
    send_event_cancelled_email,
    send_invitation_email,
    send_password_reset_email,
    send_registration_confirmed_email,
    send_registration_payment_link_email,
    send_registration_verification_email,
)
from app.modules.events.models import Event
from app.modules.payments import checkout_service
from app.modules.payments.models import EventPayment, EventTicketType
from app.modules.registrations.models import EventRegistration
from tests.conftest import OrganizacionDePrueba, iniciar_sesion
from tests.payments_test_helpers import (
    FakeStripeClient,
    _crear_organizacion_con_stripe,
    _sesion_creada,
)

BASE = "https://acme.test"
ORGANIZACION = str(uuid.uuid4())

TRADUCCIONES = {
    "Verifica tu inscripción": "Verify your registration",
    "Tu inscripción está confirmada": "Your registration is confirmed",
    "Completa el pago de tu entrada": "Complete your ticket payment",
    "Recupera tu contraseña": "Reset your password",
}


@pytest.fixture
def catalogo_en(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        mensajes, "catalogo", lambda locale: TRADUCCIONES if locale == "en-US" else {}
    )


@pytest.fixture
def proveedor() -> Iterator[AsyncMock]:
    with (
        patch("app.core.tasks.get_email_provider") as proveedor_mock,
        patch("app.core.tasks.base_url_de_organizacion", return_value=BASE),
    ):
        falso = AsyncMock()
        proveedor_mock.return_value = falso
        yield falso


async def _en_su_contexto(corrutina: Coroutine[Any, Any, None]) -> None:
    await asyncio.create_task(corrutina)


def _qr() -> str:
    return jwt.encode(
        {"tid": str(uuid.uuid4()), "eid": str(uuid.uuid4())},
        "secreto-de-prueba-de-mas-de-treinta-y-dos-caracteres",
        algorithm="HS256",
    )


def _correo(locale: str | None, tarea: str) -> Coroutine[Any, Any, None]:
    extra = {"locale": locale} if locale else {}
    if tarea == "verificacion":
        return send_registration_verification_email.original_func(
            "p@example.com", "tok", ORGANIZACION, **extra
        )
    if tarea == "confirmacion":
        return send_registration_confirmed_email.original_func(
            "p@example.com", ORGANIZACION, "tok", _qr(), **extra
        )
    if tarea == "pago":
        return send_registration_payment_link_email.original_func(
            "p@example.com",
            ORGANIZACION,
            "https://checkout.stripe.com/c/cs_1",
            "tok",
            "11/18/2026 6:30 PM",
            **extra,
        )
    return send_password_reset_email.original_func("p@example.com", "tok", **extra)


_WEB = get_settings().web_base_url

# (tarea, asunto en inglés, asunto en español, enlaces en inglés, enlaces en español)
CASOS = [
    (
        "verificacion",
        "Verify your registration",
        "Verifica tu inscripción",
        [f"{BASE}/en/verify-registration?token=tok"],
        [f"{BASE}/verificar-inscripcion?token=tok"],
    ),
    (
        "confirmacion",
        "Your registration is confirmed",
        "Tu inscripción está confirmada",
        [f"{BASE}/en/my-ticket?token=tok", f"{BASE}/en/cancel-registration?token=tok"],
        [f"{BASE}/mi-entrada?token=tok", f"{BASE}/cancelar-inscripcion?token=tok"],
    ),
    (
        "pago",
        "Complete your ticket payment",
        "Completa el pago de tu entrada",
        [f"{BASE}/en/cancel-registration?token=tok"],
        [f"{BASE}/cancelar-inscripcion?token=tok"],
    ),
    (
        "recuperacion",
        "Reset your password",
        "Recupera tu contraseña",
        [f"{_WEB}/en/forgot-password/new?token=tok"],
        [f"{_WEB}/recuperar-contrasena/nueva?token=tok"],
    ),
]


@pytest.mark.parametrize(("tarea", "asunto_en", "_asunto_es", "enlaces_en", "_enlaces_es"), CASOS)
async def test_con_locale_en_us_sale_en_ingles_y_con_rutas_traducidas(
    catalogo_en: None,
    proveedor: AsyncMock,
    tarea: str,
    asunto_en: str,
    _asunto_es: str,
    enlaces_en: list[str],
    _enlaces_es: list[str],
) -> None:
    await _en_su_contexto(_correo("en-US", tarea))

    kwargs = proveedor.send.await_args.kwargs
    assert kwargs["subject"] == asunto_en
    for enlace in enlaces_en:
        assert enlace in kwargs["body"]


@pytest.mark.parametrize(("tarea", "_asunto_en", "asunto_es", "_enlaces_en", "enlaces_es"), CASOS)
async def test_sin_locale_sale_en_espanol_como_los_mensajes_ya_encolados(
    catalogo_en: None,
    proveedor: AsyncMock,
    tarea: str,
    _asunto_en: str,
    asunto_es: str,
    _enlaces_en: list[str],
    enlaces_es: list[str],
) -> None:
    await _en_su_contexto(_correo(None, tarea))

    kwargs = proveedor.send.await_args.kwargs
    assert kwargs["subject"] == asunto_es
    assert "/en/" not in kwargs["body"]
    for enlace in enlaces_es:
        assert enlace in kwargs["body"]


async def test_un_salto_de_linea_en_el_nombre_no_parte_el_asunto(proveedor: AsyncMock) -> None:
    await _en_su_contexto(
        send_invitation_email.original_func(
            "p@example.com", "tok", ORGANIZACION, "Acme\r\nBcc: otro@example.com", "Ponente"
        )
    )

    asunto = proveedor.send.await_args.kwargs["subject"]
    assert asunto == "Te han invitado a «Acme Bcc: otro@example[.]com»"
    assert "\n" not in asunto and "\r" not in asunto


async def test_las_urls_escritas_por_el_organizador_no_llegan_enlazables(
    proveedor: AsyncMock,
) -> None:
    await _en_su_contexto(
        send_event_cancelled_email.original_func(
            "p@example.com",
            ORGANIZACION,
            "Gala en acme-login.com",
            "Pide el reembolso en https://phishing.example/pago",
            False,
        )
    )

    cuerpo = proveedor.send.await_args.kwargs["body"]
    assert "https://phishing.example" not in cuerpo
    assert "https[:]//phishing[.]example/pago" in cuerpo
    assert "«Gala en acme-login[.]com»" in cuerpo


async def test_un_asunto_largo_se_recorta(proveedor: AsyncMock) -> None:
    await _en_su_contexto(
        send_invitation_email.original_func("p@example.com", "tok", ORGANIZACION, "A" * 400, "R")
    )

    assert len(proveedor.send.await_args.kwargs["subject"]) == LONGITUD_MAXIMA_DEL_ASUNTO


# --- La inscripción guarda su idioma ----------------------------------------


async def _evento_publicado(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, slug: str
) -> str:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    ahora = datetime.now(UTC).replace(microsecond=0)
    creacion = await cliente.post(
        "/api/v1/events",
        headers=cabeceras,
        json={
            "slug": slug,
            "title": "Evento con idioma",
            "starts_at": (ahora + timedelta(days=3)).isoformat(),
            "ends_at": (ahora + timedelta(days=4)).isoformat(),
            "location_mode": "in_person",
        },
    )
    assert creacion.status_code == 201, creacion.text
    evento = creacion.json()
    publicacion = await cliente.patch(
        f"/api/v1/events/{evento['id']}",
        headers=cabeceras,
        json={"status": "published", "visibility": "public"},
    )
    assert publicacion.status_code == 200, publicacion.text
    return str(evento["slug"])


async def _inscribirse(
    cliente: AsyncClient, slug: str, email: str, accept_language: str
) -> AsyncMock:
    """Envía el formulario y devuelve el `kiq` del correo encolado."""
    with (
        patch.object(send_registration_verification_email, "kiq", new_callable=AsyncMock) as v,
        patch.object(send_registration_confirmed_email, "kiq", new_callable=AsyncMock) as c,
    ):
        respuesta = await cliente.post(
            f"/api/v1/public/organizations/acme/events/{slug}/registrations",
            headers={"Accept-Language": accept_language},
            json={
                "email": email,
                "full_name": "English Speaker",
                "answers": [],
                "data_processing_accepted": True,
                "marketing_accepted": False,
                "recording_accepted": False,
                "turnstile_token": "token-de-prueba",
            },
        )
    assert respuesta.status_code == 202, respuesta.text
    encolado = v if v.await_args else c
    assert encolado.await_args is not None
    return encolado


async def _idioma_guardado(email: str) -> str | None:
    async with SessionMaintenance() as session:
        return await session.scalar(
            select(EventRegistration.locale).where(EventRegistration.email == email)
        )


async def test_la_inscripcion_guarda_el_idioma_de_la_pagina(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    slug = await _evento_publicado(cliente, organizacion, "idioma-inscripcion")

    encolado = await _inscribirse(cliente, slug, "english@example.com", "en-US,en;q=0.9")

    assert await _idioma_guardado("english@example.com") == "en-US"
    assert encolado.await_args is not None
    assert encolado.await_args.kwargs["locale"] == "en-US"


async def test_reenviar_el_formulario_cambia_el_idioma_al_de_la_nueva_peticion(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    slug = await _evento_publicado(cliente, organizacion, "idioma-reenvio")
    await _inscribirse(cliente, slug, "cambia@example.com", "en-US,en;q=0.9")

    reenvio = await _inscribirse(cliente, slug, "cambia@example.com", "es-ES,es;q=0.9")

    assert await _idioma_guardado("cambia@example.com") == "es-ES"
    assert reenvio.await_args is not None
    assert reenvio.await_args.kwargs["locale"] == "es-ES"


# --- Pagos diferidos ---------------------------------------------------------


async def test_el_pago_diferido_vuelve_a_la_web_en_el_idioma_de_la_inscripcion(
    organizacion: OrganizacionDePrueba, fake: FakeStripeClient
) -> None:
    stripe_account_id = await _crear_organizacion_con_stripe(organizacion)
    ahora = datetime.now(UTC)
    async with SessionMaintenance() as session:
        evento = Event(
            organization_id=organizacion.id,
            slug="pago-diferido-en",
            title="Evento de pago",
            status="published",
            visibility="public",
            starts_at=ahora + timedelta(days=5),
            ends_at=ahora + timedelta(days=6),
            location_mode="online",
            registration_mode="paid",
            timezone="Europe/Madrid",
        )
        session.add(evento)
        await session.flush()
        tipo = EventTicketType(
            organization_id=organizacion.id, event_id=evento.id, name="General", price_cents=1000
        )
        session.add(tipo)
        await session.flush()
        inscripcion = EventRegistration(
            event_id=evento.id,
            organization_id=organizacion.id,
            email="diferido@example.com",
            full_name="Deferred Payment",
            status="pending_payment",
            ticket_type_id=tipo.id,
            payment_expires_at=ahora + timedelta(minutes=45),
            locale="en-US",
        )
        session.add(inscripcion)
        await session.flush()
        session.add(
            EventPayment(
                organization_id=organizacion.id,
                event_id=evento.id,
                registration_id=inscripcion.id,
                stripe_account_id=stripe_account_id,
                ticket_type_id=tipo.id,
                amount_cents=1000,
                currency="eur",
                status="pending",
            )
        )
        await session.commit()

    fake.v1.checkout.sessions.create_async.return_value = _sesion_creada("cs_diferido")
    with patch.object(
        send_registration_payment_link_email, "kiq", new_callable=AsyncMock
    ) as correo:
        await _en_su_contexto(checkout_service.dispatch_pending_payment_links())

    parametros = fake.v1.checkout.sessions.create_async.await_args.kwargs["params"]
    assert "/en/payment/return?" in parametros["success_url"]
    assert "/en/payment/cancelled?" in parametros["cancel_url"]
    correo.assert_awaited_once()
    assert correo.await_args.kwargs["locale"] == "en-US"
    expira_el = correo.await_args.args[4]
    assert expira_el.endswith(("AM", "PM"))
