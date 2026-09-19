"""`purge-orphaned-media` — el único punto que borra de verdad (almacén +
fila) una imagen en papelera. Estrictamente manual: nada del proyecto lo
invoca por sí solo (ver docstring del comando en `app/cli.py`).

Prueba la función `purgar_medios_huerfanos` directamente, no el comando Typer
(`purge_orphaned_media`): este test ya corre dentro de un bucle de eventos
(`asyncio_mode = "auto"`), y ese comando llama a `asyncio.run(...)` — anidar
un segundo `asyncio.run` dentro de un bucle ya en marcha falla.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.cli import purgar_medios_huerfanos
from app.core.database import SessionMaintenance
from app.core.storage import get_storage
from app.modules.media.models import Media
from tests.conftest import OrganizacionDePrueba


async def _crear_fila_en_papelera(
    organizacion: OrganizacionDePrueba, *, dias_en_papelera: int
) -> uuid.UUID:
    clave = f"media/branding/{uuid.uuid4().hex}.webp"
    await get_storage().put_object(clave, b"contenido de prueba", "image/webp")

    async with SessionMaintenance() as session:
        fila = Media(
            organization_id=organizacion.id,
            kind="branding",
            uploaded_by_user_id=organizacion.owner_id,
            object_key=clave,
            filename="i.webp",
            mime_type="image/webp",
            size=20,
            deleted_at=datetime.now(UTC) - timedelta(days=dias_en_papelera),
        )
        session.add(fila)
        await session.commit()
        return fila.id


async def test_purga_solo_lo_que_lleva_mas_de_n_dias_en_la_papelera(
    organizacion: OrganizacionDePrueba,
) -> None:
    antigua = await _crear_fila_en_papelera(organizacion, dias_en_papelera=40)
    reciente = await _crear_fila_en_papelera(organizacion, dias_en_papelera=1)

    total = await purgar_medios_huerfanos(older_than_days=30)
    assert total == 1

    async with SessionMaintenance() as session:
        ids_restantes = (await session.execute(select(Media.id))).scalars().all()
    assert antigua not in ids_restantes
    assert reciente in ids_restantes
