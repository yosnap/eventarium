"""`events.payment_checkout_window_minutes` (fase 6 del PRD, fase 1 de
trabajo): rango 30-1439, por defecto 30, validado en el schema y en el
`CHECK` de base de datos. No es un ajuste de instalación: es un campo del
evento (validación, sesión 1 del plan).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.core.database import SessionMaintenance
from tests.conftest import OrganizacionDePrueba, iniciar_sesion

EVENTS = "/api/v1/events"

AHORA = datetime.now(UTC).replace(microsecond=0)


def _payload_evento(slug: str = "evento-ventana", **overrides: object) -> dict:
    payload = {
        "slug": slug,
        "title": "Evento con ventana de pago",
        "starts_at": AHORA.isoformat(),
        "ends_at": (AHORA + timedelta(days=2)).isoformat(),
        "location_mode": "in_person",
    }
    payload.update(overrides)
    return payload


async def test_un_evento_nuevo_toma_30_minutos_por_defecto(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    respuesta = await cliente.post(EVENTS, headers=cabeceras, json=_payload_evento())
    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json()["payment_checkout_window_minutes"] == 30


@pytest.mark.parametrize("valor", [30, 1439])
async def test_valores_limite_se_aceptan(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, valor: int
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    respuesta = await cliente.post(
        EVENTS,
        headers=cabeceras,
        json=_payload_evento(f"evento-limite-{valor}", payment_checkout_window_minutes=valor),
    )
    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json()["payment_checkout_window_minutes"] == valor


@pytest.mark.parametrize("valor", [29, 1440])
async def test_valores_fuera_de_rango_dan_422_al_crear(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, valor: int
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    respuesta = await cliente.post(
        EVENTS,
        headers=cabeceras,
        json=_payload_evento(f"evento-fuera-rango-{valor}", payment_checkout_window_minutes=valor),
    )
    assert respuesta.status_code == 422


@pytest.mark.parametrize("valor", [29, 1440])
async def test_valores_fuera_de_rango_dan_422_al_editar(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, valor: int
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    creacion = await cliente.post(
        EVENTS, headers=cabeceras, json=_payload_evento("evento-editar-ventana")
    )
    assert creacion.status_code == 201
    evento_id = creacion.json()["id"]

    edicion = await cliente.patch(
        f"{EVENTS}/{evento_id}",
        headers=cabeceras,
        json={"payment_checkout_window_minutes": valor},
    )
    assert edicion.status_code == 422


async def test_un_update_directo_en_base_de_datos_con_29_lo_rechaza_el_check(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    creacion = await cliente.post(
        EVENTS, headers=cabeceras, json=_payload_evento("evento-check-directo")
    )
    assert creacion.status_code == 201
    evento_id = creacion.json()["id"]

    with pytest.raises((DBAPIError, IntegrityError)):
        async with SessionMaintenance() as session:
            await session.execute(
                text("UPDATE events SET payment_checkout_window_minutes = 29 WHERE id = :id"),
                {"id": evento_id},
            )
            await session.commit()


async def test_no_hay_ningun_ajuste_de_ventana_de_checkout_en_core() -> None:
    """`grep -rn "payment_checkout_window_minutes" apps/api/app/core/` no
    devuelve nada: la ventana no es un ajuste de instalación."""
    core_dir = Path(__file__).resolve().parents[2] / "app" / "core"
    coincidencias = [
        fichero
        for fichero in core_dir.rglob("*.py")
        if "payment_checkout_window_minutes" in fichero.read_text(encoding="utf-8")
    ]
    assert coincidencias == []
