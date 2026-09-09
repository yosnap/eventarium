"""Endpoints de conexión Stripe Connect (fase 6 del PRD, fase 2 de trabajo):
onboarding, estado persistido, sincronización, reconexión tras
desautorización, aislamiento cross-tenant y bloqueo con `payments_enabled =
False`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import stripe
from httpx import AsyncClient
from sqlalchemy import select, update

from app.core.config import Settings
from app.core.database import SessionMaintenance
from app.modules.payments import router as payments_router
from app.modules.payments import stripe_client
from app.modules.payments.models import OrganizationStripeAccount
from tests.conftest import OrganizacionDePrueba, iniciar_sesion


def _settings_con_stripe() -> Settings:
    return Settings(
        stripe_secret_key="sk_test_" + "a" * 40,
        stripe_webhook_secret="whsec_" + "b" * 40,
    )


class _FakeV1:
    def __init__(self) -> None:
        self.accounts = SimpleNamespace(create_async=AsyncMock(), retrieve_async=AsyncMock())
        self.account_links = SimpleNamespace(create_async=AsyncMock())


class FakeStripeClient:
    def __init__(self) -> None:
        self.v1 = _FakeV1()
        self.creaciones = 0


@pytest.fixture
def pagos_simulados(monkeypatch: pytest.MonkeyPatch) -> FakeStripeClient:
    """Habilita `payments_enabled` en los tres módulos que leen `get_settings()`
    en tiempo de llamada y sustituye `stripe.StripeClient` por un doble que
    nunca abre red. Cada `crear_cuenta_conectada` fabrica un `acct_...` nuevo,
    incremental, para poder distinguir reconexiones."""
    instancia = FakeStripeClient()
    monkeypatch.setattr(payments_router, "get_settings", _settings_con_stripe)
    monkeypatch.setattr(stripe_client, "get_settings", _settings_con_stripe)
    monkeypatch.setattr(stripe_client.stripe, "StripeClient", lambda **_kwargs: instancia)

    async def _crear_cuenta(*, params: dict, options: dict) -> SimpleNamespace:
        instancia.creaciones += 1
        return SimpleNamespace(id=f"acct_fake_{instancia.creaciones}")

    instancia.v1.accounts.create_async.side_effect = _crear_cuenta

    async def _enlace_async(**_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(url=f"https://connect.stripe.com/setup/s/{uuid.uuid4()}")

    instancia.v1.account_links.create_async = AsyncMock(side_effect=_enlace_async)
    instancia.v1.accounts.retrieve_async.return_value = SimpleNamespace(
        charges_enabled=True, payouts_enabled=True, details_submitted=True
    )
    return instancia


def _url(organization_id: str, sufijo: str = "") -> str:
    return f"/api/v1/organizations/{organization_id}/stripe{sufijo}"


async def test_pagos_deshabilitados_devuelve_503_en_los_tres_endpoints(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    org_id = str(organizacion.id)

    respuesta_onboarding = await cliente.post(_url(org_id, "/onboarding"), headers=cabeceras)
    respuesta_estado = await cliente.get(_url(org_id), headers=cabeceras)
    respuesta_sync = await cliente.post(_url(org_id, "/sync"), headers=cabeceras)

    assert respuesta_onboarding.status_code == 503
    assert respuesta_estado.status_code == 503
    assert respuesta_sync.status_code == 503


async def test_onboarding_crea_cuenta_y_devuelve_url_de_un_solo_uso(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, pagos_simulados: FakeStripeClient
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    org_id = str(organizacion.id)

    respuesta = await cliente.post(_url(org_id, "/onboarding"), headers=cabeceras)
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["onboarding_url"].startswith("https://connect.stripe.com/")

    estado = await cliente.get(_url(org_id), headers=cabeceras)
    assert estado.status_code == 200, estado.text
    cuerpo = estado.json()
    assert cuerpo["connected"] is True
    assert cuerpo["charges_enabled"] is False  # todavía no se ha sincronizado


async def test_doble_onboarding_no_crea_segunda_cuenta_pero_genera_dos_urls(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, pagos_simulados: FakeStripeClient
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    org_id = str(organizacion.id)

    primera = await cliente.post(_url(org_id, "/onboarding"), headers=cabeceras)
    segunda = await cliente.post(_url(org_id, "/onboarding"), headers=cabeceras)

    assert primera.status_code == 200 and segunda.status_code == 200
    assert primera.json()["onboarding_url"] != segunda.json()["onboarding_url"]
    # Solo una llamada de creación de cuenta: la segunda reutiliza la fila activa.
    assert pagos_simulados.creaciones == 1

    async with SessionMaintenance() as session:
        cuentas = (
            (
                await session.execute(
                    select(OrganizationStripeAccount).where(
                        OrganizationStripeAccount.organization_id == organizacion.id
                    )
                )
            )
            .scalars()
            .all()
        )
    assert len(cuentas) == 1


async def test_sync_actualiza_las_banderas_persistidas(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, pagos_simulados: FakeStripeClient
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    org_id = str(organizacion.id)

    await cliente.post(_url(org_id, "/onboarding"), headers=cabeceras)
    respuesta = await cliente.post(_url(org_id, "/sync"), headers=cabeceras)

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["charges_enabled"] is True
    assert cuerpo["payouts_enabled"] is True
    assert cuerpo["details_submitted"] is True
    assert cuerpo["connected_at"] is not None


async def test_reconexion_tras_desautorizacion_crea_cuenta_nueva_sin_intervencion_manual(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, pagos_simulados: FakeStripeClient
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    org_id = str(organizacion.id)

    await cliente.post(_url(org_id, "/onboarding"), headers=cabeceras)
    async with SessionMaintenance() as session:
        cuenta_original = await session.scalar(
            select(OrganizationStripeAccount).where(
                OrganizationStripeAccount.organization_id == organizacion.id
            )
        )
        assert cuenta_original is not None
        cuenta_original_id = cuenta_original.id
        await session.execute(
            update(OrganizationStripeAccount)
            .where(OrganizationStripeAccount.id == cuenta_original_id)
            .values(deauthorized_at=datetime.now(UTC))
        )
        await session.commit()

    respuesta = await cliente.post(_url(org_id, "/onboarding"), headers=cabeceras)
    assert respuesta.status_code == 200, respuesta.text
    # Una organización sin cuenta activa (la única que había está
    # desautorizada) provoca una segunda creación de cuenta.
    assert pagos_simulados.creaciones == 2

    async with SessionMaintenance() as session:
        todas = (
            (
                await session.execute(
                    select(OrganizationStripeAccount).where(
                        OrganizationStripeAccount.organization_id == organizacion.id
                    )
                )
            )
            .scalars()
            .all()
        )
    assert len(todas) == 2
    antigua = next(c for c in todas if c.id == cuenta_original_id)
    nueva = next(c for c in todas if c.id != cuenta_original_id)
    assert antigua.deauthorized_at is not None
    assert nueva.deauthorized_at is None

    estado = await cliente.get(_url(org_id), headers=cabeceras)
    assert estado.json()["connected"] is True


async def test_una_organizacion_no_puede_leer_ni_conectar_el_stripe_de_otra(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    otra_organizacion: OrganizacionDePrueba,
    pagos_simulados: FakeStripeClient,
) -> None:
    _, cabeceras_a = await iniciar_sesion(cliente, organizacion)
    org_b_id = str(otra_organizacion.id)

    respuesta_get = await cliente.get(_url(org_b_id), headers=cabeceras_a)
    respuesta_onboarding = await cliente.post(_url(org_b_id, "/onboarding"), headers=cabeceras_a)
    respuesta_sync = await cliente.post(_url(org_b_id, "/sync"), headers=cabeceras_a)

    assert respuesta_get.status_code == 404
    assert respuesta_onboarding.status_code == 404
    assert respuesta_sync.status_code == 404
    # Ninguna llamada de creación de cuenta debe haberse producido para B.
    assert pagos_simulados.creaciones == 0


async def test_get_status_no_produce_ninguna_llamada_de_red_a_stripe(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, pagos_simulados: FakeStripeClient
) -> None:
    async with SessionMaintenance() as session:
        session.add(
            OrganizationStripeAccount(
                organization_id=organizacion.id,
                stripe_account_id="acct_ya_conectada",
                charges_enabled=True,
            )
        )
        await session.commit()

    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    respuesta = await cliente.get(_url(str(organizacion.id)), headers=cabeceras)

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["charges_enabled"] is True
    assert pagos_simulados.v1.accounts.retrieve_async.await_count == 0
    assert pagos_simulados.creaciones == 0


async def test_error_del_sdk_en_onboarding_llega_como_502(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, pagos_simulados: FakeStripeClient
) -> None:
    pagos_simulados.v1.accounts.create_async.side_effect = stripe.StripeError(
        "fallo simulado de la pasarela"
    )

    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    respuesta = await cliente.post(_url(str(organizacion.id), "/onboarding"), headers=cabeceras)

    assert respuesta.status_code == 502
    assert "fallo simulado de la pasarela" not in respuesta.text
