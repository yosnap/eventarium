"""Comprobaciones de la migración `0012_patrocinio_legal_auditoria`.

Fase 5 del PRD, fase 1 de trabajo: privilegios de `app_user` sobre las cuatro
tablas nuevas (positiva para las de dominio, negativa para las de
instalación) y el ciclo `upgrade` -> `downgrade` -> `upgrade` limpio.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import text

from app.core.database import SessionMaintenance

API_DIR = Path(__file__).resolve().parents[1]


async def _tiene_privilegio(tabla: str, privilegio: str) -> bool:
    async with SessionMaintenance() as session:
        resultado = await session.scalar(
            text("SELECT has_table_privilege('app_user', :tabla, :privilegio)"),
            {"tabla": tabla, "privilegio": privilegio},
        )
    return bool(resultado)


@pytest.mark.parametrize("tabla", ["sponsor_tiers", "sponsors"])
async def test_app_user_tiene_select_sobre_las_tablas_de_dominio(tabla: str) -> None:
    assert await _tiene_privilegio(tabla, "SELECT") is True


async def test_app_user_no_puede_leer_ni_borrar_audit_log() -> None:
    assert await _tiene_privilegio("audit_log", "SELECT") is False
    assert await _tiene_privilegio("audit_log", "DELETE") is False


async def test_app_user_solo_puede_insertar_en_cookie_consents() -> None:
    assert await _tiene_privilegio("cookie_consents", "SELECT") is False
    assert await _tiene_privilegio("cookie_consents", "INSERT") is True


def test_ciclo_de_migracion_limpio() -> None:
    """`upgrade head` -> `downgrade -1` -> `upgrade head` sin errores.

    Usa el mismo `sys.executable`/entorno que la fixture de sesión
    (`tests.conftest.migraciones`), que ya ha dejado la base en `head` antes
    de que arranque cualquier test.
    """
    entorno = os.environ.copy()
    for comando in (
        ["downgrade", "-1"],
        ["upgrade", "head"],
    ):
        resultado = subprocess.run(  # noqa: S603 — argv fijo, sin entrada externa
            [sys.executable, "-m", "alembic", *comando],
            cwd=API_DIR,
            env=entorno,
            capture_output=True,
            text=True,
        )
        assert resultado.returncode == 0, resultado.stderr
