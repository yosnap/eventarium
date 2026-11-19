"""Comprobaciones de la migración `0074_traducciones_de_contenido`."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import text

from app.core.database import SessionMaintenance

API_DIR = Path(__file__).resolve().parents[1]
REVISION_ANTERIOR = "0073_idioma_de_inscripcion"


def _correr_alembic(*comando: str) -> None:
    resultado = subprocess.run(  # noqa: S603 - argv fijo, sin entrada externa
        [sys.executable, "-m", "alembic", *comando],
        cwd=API_DIR,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
    )
    assert resultado.returncode == 0, resultado.stderr


async def _estado() -> dict[str, object]:
    async with SessionMaintenance() as session:
        tabla = await session.scalar(text("SELECT to_regclass('content_translations')"))
        columnas = {
            (fila[0], fila[1])
            for fila in await session.execute(
                text(
                    "SELECT table_name, column_name FROM information_schema.columns "
                    "WHERE (table_name, column_name) IN (('organizations', 'content_locales'), "
                    "('organizations', 'source_locale'), ('events', 'source_locale'), "
                    "('event_categories', 'name_i18n'))"
                )
            )
        }
    return {"tabla": tabla, "columnas": columnas}


async def test_downgrade_quita_la_tabla_y_las_columnas_y_upgrade_las_devuelve() -> None:
    _correr_alembic("downgrade", REVISION_ANTERIOR)
    try:
        estado = await _estado()
        assert estado["tabla"] is None
        assert estado["columnas"] == set()
    finally:
        _correr_alembic("upgrade", "head")
    estado = await _estado()
    assert estado["tabla"] is not None
    assert len(estado["columnas"]) == 4  # type: ignore[arg-type]


async def test_la_tabla_tiene_rls_forzado() -> None:
    async with SessionMaintenance() as session:
        fila = (
            await session.execute(
                text(
                    "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                    "WHERE relname = 'content_translations'"
                )
            )
        ).one()
    assert tuple(fila) == (True, True)
