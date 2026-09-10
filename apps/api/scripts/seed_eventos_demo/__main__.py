"""Punto de entrada del seed de eventos de demostración.

Uso:
    cd apps/api && uv run python -m scripts.seed_eventos_demo

Siembra 12 eventos de demostración sobre la organización `iawic`, cada uno
cubriendo una rama distinta de la ficha pública de evento: los tres modos de
inscripción, los tres formatos, con y sin portada, con y sin aforo, agenda vacía
/ de un día / de varios, sesiones con vídeo y con materiales, ponentes con y sin
perfil público, patrocinadores por nivel, y eventos multisede (1, 2 y 3 sedes).

Idempotente por diseño: cada paso busca por su clave natural antes de crear.

Notas de entorno: no hay cuenta de Stripe conectada, así que los eventos de pago
se crean en borrador y se les exige un tipo de entrada vigente, y para publicarlos
se relaja la guarda de `payments_enabled` solo durante esta llamada (ver
`siembra._publicar_eventos_de_pago`). La geocodificación se sustituye por una tabla
local de coordenadas por ciudad, así que el seed no llama a Nominatim.
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import maintenance_session
from app.core.storage import get_storage
from app.modules.events import service as events_service
from app.modules.events.models import SpeakerPublicProfile
from app.modules.organizations.models import Organization, OrganizationMember
from app.modules.roles.models import Role
from scripts.seed_eventos_demo.datos import EVENTOS, ORG_SLUG, PERSONAS
from scripts.seed_eventos_demo.imagenes import _geocode_por_tabla
from scripts.seed_eventos_demo.siembra import (
    _get_or_create_persona,
    _publicar_eventos,
    _sembrar_evento,
)


async def main() -> None:
    settings = get_settings()
    almacen = get_storage()
    await almacen.ensure_bucket()

    async with maintenance_session() as session:
        organizacion = await session.scalar(
            select(Organization).where(Organization.slug == ORG_SLUG)
        )
        if organizacion is None:
            raise RuntimeError(
                f"No existe la organización «{ORG_SLUG}»: ejecuta primero "
                "`uv run python -m app.cli seed`."
            )

        rol_speaker = await session.scalar(
            select(Role).where(Role.organization_id == organizacion.id, Role.key == "speaker")
        )
        if rol_speaker is None:
            raise RuntimeError(
                f"La organización «{ORG_SLUG}» no tiene el rol de sistema «speaker» clonado."
            )

        personas: dict[str, tuple[OrganizationMember, SpeakerPublicProfile | None]] = {}
        for datos_persona in PERSONAS:
            personas[datos_persona["email"]] = await _get_or_create_persona(
                session,
                organization_id=organizacion.id,
                speaker_role_id=rol_speaker.id,
                datos=datos_persona,
            )

        # La geocodificación se sustituye por la tabla local durante todo el
        # sembrado: sin red, determinista y sin límite de peticiones.
        with patch.object(events_service, "geocode_address", _geocode_por_tabla):
            eventos = [
                await _sembrar_evento(
                    session,
                    organization_id=organizacion.id,
                    spec=spec,
                    personas=personas,
                    almacen=almacen,
                )
                for spec in EVENTOS
            ]
            await _publicar_eventos(session, organization_id=organizacion.id, eventos=eventos)

    base = "http://localhost:4200"
    print("\n=== Catálogo de eventos de demostración (ficha de evento) ===\n")
    print(f"Base para las URLs: {base}")
    print(
        f"Aviso: `web_base_url` de la API es «{settings.web_base_url}» (Caddy, :8080), "
        "no «:4200» (dev server de Angular). En este entorno ambos resuelven al mismo "
        "host, así que los dos funcionan para navegar.\n"
    )
    print("--- Los 12 eventos (el último NO debe aparecer en público) ---")
    for spec in EVENTOS:
        print(f"{base}/eventos/{spec['slug']:<32} {spec['title']}")

    oculto = next((s for s in EVENTOS if s.get("visibility") == "hidden"), None)
    if oculto is not None:
        print(
            f"\nComprobación del evento oculto: {base}/eventos/{oculto['slug']} debe dar 404, "
            "y no debe salir en el listado."
        )
    print(f"\nListado completo: {base}/eventos")
    print(f"Portada:          {base}/\n")


if __name__ == "__main__":
    asyncio.run(main())
