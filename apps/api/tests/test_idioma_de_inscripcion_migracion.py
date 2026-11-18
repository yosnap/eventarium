"""Comprobaciones de la migración `0073_idioma_de_inscripcion`."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import text

from app.core.database import SessionMaintenance

API_DIR = Path(__file__).resolve().parents[1]
REVISION_ANTERIOR = "0072_idiomas_de_plataforma"


def _correr_alembic(*comando: str) -> None:
    resultado = subprocess.run(  # noqa: S603 - argv fijo, sin entrada externa
        [sys.executable, "-m", "alembic", *comando],
        cwd=API_DIR,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
    )
    assert resultado.returncode == 0, resultado.stderr


async def _columnas() -> set[str]:
    async with SessionMaintenance() as session:
        filas = await session.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'event_registrations'"
            )
        )
        return {fila[0] for fila in filas}


async def test_downgrade_quita_las_columnas_y_upgrade_las_devuelve() -> None:
    _correr_alembic("downgrade", REVISION_ANTERIOR)
    try:
        assert {"locale"}.isdisjoint(await _columnas())
    finally:
        _correr_alembic("upgrade", "head")
    assert {"locale"} <= await _columnas()


async def test_la_base_solo_admite_idiomas_del_catalogo() -> None:
    async with SessionMaintenance() as session:
        definicion = await session.scalar(
            text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conname = 'ck_event_registrations_locale'"
            )
        )
    assert definicion is not None
    assert "es-ES" in definicion and "en-US" in definicion
