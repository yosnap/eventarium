"""Comprobaciones de la migración `0071_normaliza_locale_usuarios`."""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path

from sqlalchemy import text

from app.core.database import SessionMaintenance

API_DIR = Path(__file__).resolve().parents[1]
REVISION_ANTERIOR = "0070_locale_en_invitacion"


def _correr_alembic(*comando: str) -> None:
    resultado = subprocess.run(  # noqa: S603 - argv fijo, sin entrada externa
        [sys.executable, "-m", "alembic", *comando],
        cwd=API_DIR,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
    )
    assert resultado.returncode == 0, resultado.stderr


async def test_los_idiomas_fuera_del_catalogo_pasan_al_que_les_corresponde() -> None:
    cuentas = {
        uuid.uuid4(): ("en", "en-US"),
        uuid.uuid4(): ("en-GB", "en-US"),
        uuid.uuid4(): ("es", "es-ES"),
        uuid.uuid4(): ("fr-FR", "es-ES"),
        uuid.uuid4(): ("en-US", "en-US"),
    }
    async with SessionMaintenance() as session:
        for id_cuenta, (antes, _) in cuentas.items():
            await session.execute(
                text(
                    "INSERT INTO users (id, email, locale, is_active, is_superadmin) "
                    "VALUES (:id, :email, :locale, true, false)"
                ),
                {"id": id_cuenta, "email": f"locale-{id_cuenta}@example.com", "locale": antes},
            )
        await session.commit()
    try:
        _correr_alembic("downgrade", REVISION_ANTERIOR)
        _correr_alembic("upgrade", "head")
        async with SessionMaintenance() as session:
            filas = await session.execute(
                text("SELECT id, locale FROM users WHERE id = ANY(:ids)"),
                {"ids": list(cuentas)},
            )
            despues = dict(filas.tuples().all())
        assert despues == {id_cuenta: esperado for id_cuenta, (_, esperado) in cuentas.items()}
    finally:
        async with SessionMaintenance() as session:
            await session.execute(
                text("DELETE FROM users WHERE id = ANY(:ids)"), {"ids": list(cuentas)}
            )
            await session.commit()
