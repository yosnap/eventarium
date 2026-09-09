"""`_asegurar_venta_posible` (fase 6 del PRD, fase 2 de trabajo): bloqueo de
**venta**, no de configuracion — decision #13 del plan. Crear y editar un
evento `paid` en borrador funciona sin Stripe conectado; solo publicarlo
(`published` + `paid`) exige `payments_enabled` y una cuenta con
`charges_enabled = true`. Invocada desde `create_event` **y** `update_event`
(hallazgo #4 del red-team): antes de esta fase, `create_event` no validaba
nada de estado.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from app.core.database import SessionMaintenance
from app.modules.events import service as events_service
from app.modules.payments.models import OrganizationStripeAccount
from tests.conftest import OrganizacionDePrueba, iniciar_sesion

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


@pytest.fixture(autouse=True)
def _pagos_habilitados(monkeypatch: pytest.MonkeyPatch) -> None:
    """Por defecto en los tests de este fichero, `payments_enabled = True`:
    lo que se prueba es el bloqueo por falta de cuenta activa, no por falta
    de configuración (esa combinación tiene su propio test explícito)."""
    from app.core.config import Settings

    def _settings_con_stripe() -> Settings:
        return Settings(
            stripe_secret_key="sk_test_" + "a" * 40,
            stripe_webhook_secret="whsec_" + "b" * 40,
        )

    monkeypatch.setattr(events_service, "get_settings", _settings_con_stripe)


async def _conectar_cuenta_operativa(organizacion: OrganizacionDePrueba) -> None:
    async with SessionMaintenance() as session:
        session.add(
            OrganizationStripeAccount(
                organization_id=organizacion.id,
                stripe_account_id=f"acct_{organizacion.slug}",
                charges_enabled=True,
            )
        )
        await session.commit()


async def test_crear_evento_paid_publicado_sin_stripe_da_409(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    respuesta = await cliente.post(
        EVENTS,
        headers=cabeceras,
        json=_payload_evento(
            "evento-paid-alta", status="published", registration_mode="paid", visibility="public"
        ),
    )
    assert respuesta.status_code == 409, respuesta.text


async def test_crear_evento_paid_en_borrador_sin_stripe_funciona(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    respuesta = await cliente.post(
        EVENTS,
        headers=cabeceras,
        json=_payload_evento("evento-paid-borrador", registration_mode="paid"),
    )
    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json()["status"] == "draft"


async def test_editar_evento_paid_en_borrador_sin_stripe_funciona(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    creado = await cliente.post(
        EVENTS, headers=cabeceras, json=_payload_evento("evento-paid-editar-borrador")
    )
    assert creado.status_code == 201
    evento_id = creado.json()["id"]

    respuesta = await cliente.patch(
        f"{EVENTS}/{evento_id}", headers=cabeceras, json={"registration_mode": "paid"}
    )
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["registration_mode"] == "paid"


async def test_publicar_editando_a_paid_sin_stripe_da_409(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    creado = await cliente.post(
        EVENTS, headers=cabeceras, json=_payload_evento("evento-paid-publicar-edicion")
    )
    evento_id = creado.json()["id"]

    respuesta = await cliente.patch(
        f"{EVENTS}/{evento_id}",
        headers=cabeceras,
        json={"status": "published", "registration_mode": "paid", "visibility": "public"},
    )
    assert respuesta.status_code == 409, respuesta.text


async def test_publicar_evento_paid_con_charges_enabled_funciona(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    await _conectar_cuenta_operativa(organizacion)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    respuesta = await cliente.post(
        EVENTS,
        headers=cabeceras,
        json=_payload_evento(
            "evento-paid-operativo",
            status="published",
            registration_mode="paid",
            visibility="public",
        ),
    )
    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json()["status"] == "published"


async def test_publicar_evento_paid_sin_payments_enabled_da_409(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Aunque hubiera una cuenta con `charges_enabled = true`, sin las dos
    variables de Stripe configuradas la instalación entera falla cerrado."""
    from app.core.config import Settings

    monkeypatch.setattr(events_service, "get_settings", Settings)
    await _conectar_cuenta_operativa(organizacion)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    respuesta = await cliente.post(
        EVENTS,
        headers=cabeceras,
        json=_payload_evento(
            "evento-paid-sin-instalacion",
            status="published",
            registration_mode="paid",
            visibility="public",
        ),
    )
    assert respuesta.status_code == 409, respuesta.text


async def test_evento_free_publicado_no_pasa_por_la_guarda_de_venta(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    """Control: un evento `free` publicado nunca exige Stripe, con o sin
    `payments_enabled`."""
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    respuesta = await cliente.post(
        EVENTS,
        headers=cabeceras,
        json=_payload_evento("evento-free-publicado", status="published", visibility="public"),
    )
    assert respuesta.status_code == 201, respuesta.text
