"""Comprobaciones de la migración `0063_locale_en_alta_de_cuenta` (fase 1).

`app_create_unverified_user` cambia de firma (3 -> 4 parámetros, añade
`p_locale`). Verifica que no queda ninguna sobrecarga huérfana, que el
`EXECUTE` sigue sin estar abierto a `PUBLIC`, y que el `downgrade` es
simétrico (deja la firma vieja con sus propios grants, no solo "sin error").

Regla dura del usuario: verificación de permisos únicamente con
`has_function_privilege(...)`, nunca `SET ROLE` / `SET LOCAL ROLE` (un
incidente real documentado tumbó Postgres en producción con ese comando).
El pseudo-rol PUBLIC se escribe `'public'` en minúsculas: PostgreSQL no lo
reconoce en mayúsculas (`role "PUBLIC" does not exist`).

El ciclo de migración usa revisiones **explícitas**, nunca `downgrade -1`:
en cuanto exista la migración de fase 2 encadenada a esta, `-1` revertiría
la de fase 2, no esta.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import text

from app.core.database import SessionMaintenance

API_DIR = Path(__file__).resolve().parents[1]

# `down_revision` real fijado por fase 1 (ver Implementation Steps paso 1 del
# phase file): verificado contra `alembic heads` antes de escribir este test.
REVISION_ANTERIOR = "0062_sin_enlaces_antiguos"
FIRMA_NUEVA = "app_create_unverified_user(uuid,text,text,text)"
FIRMA_VIEJA = "app_create_unverified_user(uuid,text,text)"


async def _tiene_privilegio_de_ejecucion(rol: str, firma: str) -> bool:
    # Solo lectura de catálogo. NUNCA `SET ROLE` / `SET LOCAL ROLE`.
    async with SessionMaintenance() as session:
        resultado = await session.scalar(
            text("SELECT has_function_privilege(:rol, :firma, 'EXECUTE')"),
            {"rol": rol, "firma": firma},
        )
    return bool(resultado)


async def _numero_de_sobrecargas() -> int:
    async with SessionMaintenance() as session:
        return await session.scalar(
            text(
                "SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
                "WHERE n.nspname = 'public' AND p.proname = 'app_create_unverified_user'"
            )
        )


def _correr_alembic(*comando: str) -> None:
    entorno = os.environ.copy()
    resultado = subprocess.run(  # noqa: S603 - argv fijo, sin entrada externa
        [sys.executable, "-m", "alembic", *comando],
        cwd=API_DIR,
        env=entorno,
        capture_output=True,
        text=True,
    )
    assert resultado.returncode == 0, resultado.stderr


async def test_app_user_puede_ejecutar_app_create_unverified_user() -> None:
    assert await _tiene_privilegio_de_ejecucion("app_user", FIRMA_NUEVA) is True


async def test_public_no_puede_ejecutar_app_create_unverified_user() -> None:
    assert await _tiene_privilegio_de_ejecucion("public", FIRMA_NUEVA) is False


async def test_sin_sobrecargas_huerfanas() -> None:
    assert await _numero_de_sobrecargas() == 1


async def test_downgrade_restaura_la_firma_vieja_con_sus_permisos() -> None:
    _correr_alembic("downgrade", REVISION_ANTERIOR)
    try:
        assert await _numero_de_sobrecargas() == 1
        assert await _tiene_privilegio_de_ejecucion("app_user", FIRMA_VIEJA) is True
        assert await _tiene_privilegio_de_ejecucion("public", FIRMA_VIEJA) is False
    finally:
        _correr_alembic("upgrade", "head")
    assert await _numero_de_sobrecargas() == 1
    assert await _tiene_privilegio_de_ejecucion("app_user", FIRMA_NUEVA) is True
