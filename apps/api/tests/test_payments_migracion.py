"""Comprobaciones de la migración `0013_pagos_stripe_connect`.

Fase 6 del PRD, fase 1 de trabajo: privilegios de `app_user` sobre las seis
tablas nuevas (positiva para las cinco de dominio, negativa para
`stripe_webhook_events`, tabla de instalación) y el ciclo `upgrade` ->
`downgrade` -> `upgrade` limpio, también desde cero (mismo patrón que
`test_sponsors_legal_auditoria_migracion.py`, fase 5).
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import text

from app.core.database import SessionMaintenance
from app.modules.events.models import Event
from tests.conftest import OrganizacionDePrueba

API_DIR = Path(__file__).resolve().parents[1]

TABLAS_DE_DOMINIO = (
    "organization_stripe_accounts",
    "event_ticket_types",
    "event_discount_codes",
    "event_payments",
    "event_payment_refunds",
)


async def _tiene_privilegio(tabla: str, privilegio: str) -> bool:
    async with SessionMaintenance() as session:
        resultado = await session.scalar(
            text("SELECT has_table_privilege('app_user', :tabla, :privilegio)"),
            {"tabla": tabla, "privilegio": privilegio},
        )
    return bool(resultado)


@pytest.mark.parametrize("tabla", TABLAS_DE_DOMINIO)
async def test_app_user_tiene_select_sobre_las_tablas_de_dominio(tabla: str) -> None:
    assert await _tiene_privilegio(tabla, "SELECT") is True


async def test_app_user_no_puede_leer_ni_borrar_stripe_webhook_events() -> None:
    assert await _tiene_privilegio("stripe_webhook_events", "SELECT") is False
    assert await _tiene_privilegio("stripe_webhook_events", "DELETE") is False


def _correr_alembic(*comando: str) -> None:
    entorno = os.environ.copy()
    resultado = subprocess.run(  # noqa: S603 — argv fijo, sin entrada externa
        [sys.executable, "-m", "alembic", *comando],
        cwd=API_DIR,
        env=entorno,
        capture_output=True,
        text=True,
    )
    assert resultado.returncode == 0, resultado.stderr


def test_ciclo_de_migracion_limpio() -> None:
    """`upgrade head` -> `downgrade -1` -> `upgrade head` sin errores."""
    _correr_alembic("downgrade", "-1")
    _correr_alembic("upgrade", "head")


def test_ciclo_de_migracion_desde_cero() -> None:
    """`downgrade base` -> `upgrade head` sin errores ni pérdida de permisos.

    Deja la base en `head` al terminar para no romper el resto de la suite,
    que depende de la fixture de sesión `migraciones`.
    """
    _correr_alembic("downgrade", "base")
    _correr_alembic("upgrade", "head")


async def test_un_evento_existente_antes_de_la_migracion_toma_30_minutos(
    organizacion: OrganizacionDePrueba,
) -> None:
    """Un evento creado con el esquema en `0012` (sin la columna) queda con
    `payment_checkout_window_minutes = 30` al aplicar `0013`, gracias al
    `server_default="30"` del `add_column` — sin intervención manual."""
    ahora = datetime.now(UTC)
    async with SessionMaintenance() as session:
        evento = Event(
            organization_id=organizacion.id,
            slug="evento-anterior-a-la-migracion",
            title="Evento anterior a la migración",
            status="draft",
            visibility="public",
            starts_at=ahora,
            ends_at=ahora + timedelta(days=1),
            location_mode="online",
        )
        session.add(evento)
        await session.commit()
        evento_id = evento.id

    _correr_alembic("downgrade", "-1")
    _correr_alembic("upgrade", "head")

    async with SessionMaintenance() as session:
        valor = await session.scalar(
            text("SELECT payment_checkout_window_minutes FROM events WHERE id = :id"),
            {"id": evento_id},
        )
    assert valor == 30
