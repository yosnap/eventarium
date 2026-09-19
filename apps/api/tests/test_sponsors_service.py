"""Servicio mínimo de niveles de patrocinio: el 409 al borrar un nivel con
patrocinadores activos, no un 500 de `IntegrityError` sin capturar.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.core.database import SessionApp, set_organization_context
from app.modules.events.models import Event
from app.modules.sponsors import service as sponsors_service
from app.modules.sponsors.models import Sponsor
from app.shared.errors import ConflictError, NotFoundError
from tests.conftest import OrganizacionDePrueba

AHORA = datetime.now(UTC)


async def test_borrar_un_nivel_sin_patrocinadores_funciona(
    organizacion: OrganizacionDePrueba,
) -> None:
    async with SessionApp() as session:
        async with session.begin():
            await set_organization_context(session, organizacion.id)
            nivel = await sponsors_service.create_tier(
                session,
                organization_id=organizacion.id,
                datos={"name": "Bronce", "display_order": 3, "logo_size": "small"},
            )
            tier_id = nivel.id

    async with SessionApp() as session:
        async with session.begin():
            await set_organization_context(session, organizacion.id)
            await sponsors_service.delete_tier(
                session, organization_id=organizacion.id, tier_id=tier_id
            )


async def test_borrar_un_nivel_con_patrocinadores_activos_da_409(
    organizacion: OrganizacionDePrueba,
) -> None:
    async with SessionApp() as session:
        async with session.begin():
            await set_organization_context(session, organizacion.id)
            nivel = await sponsors_service.create_tier(
                session,
                organization_id=organizacion.id,
                datos={"name": "Oro", "display_order": 1, "logo_size": "large"},
            )
            evento = Event(
                organization_id=organizacion.id,
                slug="evento-con-patrocinio",
                title="Evento con patrocinio",
                status="published",
                visibility="public",
                starts_at=AHORA,
                ends_at=AHORA + timedelta(days=1),
                location_mode="online",
            )
            session.add(evento)
            await session.flush()
            session.add(
                Sponsor(
                    event_id=evento.id,
                    tier_id=nivel.id,
                    organization_id=organizacion.id,
                    name="Patrocinador activo",
                    contribution_type="monetaria",
                )
            )
            await session.flush()
            tier_id = nivel.id

    with pytest.raises(ConflictError):
        async with SessionApp() as session:
            async with session.begin():
                await set_organization_context(session, organizacion.id)
                await sponsors_service.delete_tier(
                    session, organization_id=organizacion.id, tier_id=tier_id
                )


async def test_borrar_un_nivel_inexistente_da_404(organizacion: OrganizacionDePrueba) -> None:
    async with SessionApp() as session:
        async with session.begin():
            await set_organization_context(session, organizacion.id)
            with pytest.raises(NotFoundError):
                await sponsors_service.delete_tier(
                    session, organization_id=organizacion.id, tier_id=uuid.uuid4()
                )
