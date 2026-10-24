"""Comprobaciones de la migración `0067_locale_en_invitacion` (fase 2).

`app_accept_invited_user` cambia de firma (4 -> 5 parámetros, añade
`p_locale`). Mismo patrón que `test_locale_registro_migracion.py` (fase 1):
sin sobrecargas huérfanas, `EXECUTE` cerrado a `PUBLIC`, `downgrade`
simétrico verificado mientras la base está abajo (no solo "sin error").

Regla dura del usuario: verificación de permisos únicamente con
`has_function_privilege(...)`, nunca `SET ROLE` / `SET LOCAL ROLE`. Pseudo-rol
PUBLIC en minúsculas (`'public'`; `'PUBLIC'` da "role does not exist").

Revisión explícita en el ciclo de downgrade: la revisión anterior de esta
migración es la que fase 1 le puso a la suya, nunca `-1` (con dos
migraciones encadenadas, `-1` revertiría la de esta fase, no permitiría
comprobar la cadena completa).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import text

from app.core.database import SessionMaintenance

API_DIR = Path(__file__).resolve().parents[1]

# `down_revision` real de esta migración = el `revision` que fase 1 fijó a la
# suya (`0066_locale_en_alta_de_cuenta`, no el `0063` que asumía el phase
# file — fase 1 tuvo que renumerarse por migraciones `0063`-`0065` ajenas ya
# existentes en `origin/develop`/`origin/main`. Verificado leyendo el fichero
# real de fase 1 y `alembic heads` antes de escribir esta migración).
REVISION_DE_FASE_1 = "0066_locale_en_alta_de_cuenta"
FIRMA_NUEVA = "app_accept_invited_user(uuid,text,text,text,text)"
FIRMA_VIEJA = "app_accept_invited_user(uuid,text,text,text)"


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
                "WHERE n.nspname = 'public' AND p.proname = 'app_accept_invited_user'"
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


async def test_app_user_puede_ejecutar_app_accept_invited_user() -> None:
    assert await _tiene_privilegio_de_ejecucion("app_user", FIRMA_NUEVA) is True


async def test_public_no_puede_ejecutar_app_accept_invited_user() -> None:
    assert await _tiene_privilegio_de_ejecucion("public", FIRMA_NUEVA) is False


async def test_sin_sobrecargas_huerfanas() -> None:
    assert await _numero_de_sobrecargas() == 1


async def test_downgrade_restaura_la_firma_de_fase_1_con_sus_permisos() -> None:
    _correr_alembic("downgrade", REVISION_DE_FASE_1)
    try:
        assert await _numero_de_sobrecargas() == 1
        assert await _tiene_privilegio_de_ejecucion("app_user", FIRMA_VIEJA) is True
        assert await _tiene_privilegio_de_ejecucion("public", FIRMA_VIEJA) is False
    finally:
        _correr_alembic("upgrade", "head")
    assert await _numero_de_sobrecargas() == 1
    assert await _tiene_privilegio_de_ejecucion("app_user", FIRMA_NUEVA) is True
