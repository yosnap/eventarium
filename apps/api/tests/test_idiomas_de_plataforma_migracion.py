"""Comprobaciones de la migración `0072_idiomas_de_plataforma`."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.database import SessionMaintenance

API_DIR = Path(__file__).resolve().parents[1]
REVISION_ANTERIOR = "0071_normaliza_locale_usuarios"


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
                "WHERE table_name = 'platform_branding'"
            )
        )
        return {fila[0] for fila in filas}


async def test_downgrade_quita_las_columnas_y_upgrade_las_devuelve() -> None:
    _correr_alembic("downgrade", REVISION_ANTERIOR)
    try:
        assert {"enabled_locales", "language_switcher_visible"}.isdisjoint(await _columnas())
    finally:
        _correr_alembic("upgrade", "head")
    assert {"enabled_locales", "language_switcher_visible"} <= await _columnas()


async def test_la_base_impide_quitar_el_idioma_por_defecto() -> None:
    async with SessionMaintenance() as session:
        with pytest.raises(IntegrityError):
            await session.execute(
                text(
                    "INSERT INTO platform_branding (singleton, name, enabled_locales) "
                    "VALUES ('prueba-idiomas', 'X', ARRAY['en-US']::varchar[])"
                )
            )
        await session.rollback()
