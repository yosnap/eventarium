"""Aislamiento entre organizaciones para `sponsor_tiers`/`sponsors`.

Mismo patrón que `test_events_rls_isolation.py`: una comprobación de lectura
(RLS) y otra de escritura cruzada (las FK compuestas contra `(id,
organization_id)` del padre, que es lo que de verdad impide que un
`sponsor` apunte al `tier` o al `event` de otra organización).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.core.database import SessionApp, SessionMaintenance, set_organization_context
from app.modules.events.models import Event
from app.modules.organizations.repository import unsafe_select_all
from app.modules.sponsors.models import Sponsor, SponsorTier
from tests.conftest import OrganizacionDePrueba

TABLAS_CON_ORGANIZACION = (SponsorTier, Sponsor)

AHORA = datetime.now(UTC)


class DatosDePrueba:
    __slots__ = ("event_id", "tier_id", "sponsor_id")

    def __init__(self, *, event_id: uuid.UUID, tier_id: uuid.UUID, sponsor_id: uuid.UUID) -> None:
        self.event_id = event_id
        self.tier_id = tier_id
        self.sponsor_id = sponsor_id


async def _crear_datos_de_prueba(organizacion: OrganizacionDePrueba) -> DatosDePrueba:
    async with SessionMaintenance() as session:
        evento = Event(
            organization_id=organizacion.id,
            slug=f"evento-{organizacion.slug}",
            title="Evento de prueba",
            status="published",
            visibility="public",
            starts_at=AHORA,
            ends_at=AHORA + timedelta(days=1),
            location_mode="online",
        )
        session.add(evento)
        await session.flush()

        nivel = SponsorTier(
            organization_id=organizacion.id,
            name=f"Oro {organizacion.slug}",
            display_order=1,
            logo_size="large",
        )
        session.add(nivel)
        await session.flush()

        patrocinador = Sponsor(
            event_id=evento.id,
            tier_id=nivel.id,
            organization_id=organizacion.id,
            name=f"Patrocinador {organizacion.slug}",
            contribution_type="monetaria",
        )
        session.add(patrocinador)
        await session.flush()

        await session.commit()
        return DatosDePrueba(event_id=evento.id, tier_id=nivel.id, sponsor_id=patrocinador.id)


@pytest.mark.parametrize("modelo", TABLAS_CON_ORGANIZACION)
async def test_una_sesion_solo_ve_las_filas_de_su_organizacion(
    organizacion: OrganizacionDePrueba,
    otra_organizacion: OrganizacionDePrueba,
    modelo: type,
) -> None:
    await _crear_datos_de_prueba(organizacion)
    await _crear_datos_de_prueba(otra_organizacion)

    async with SessionApp() as session:
        async with session.begin():
            await set_organization_context(session, organizacion.id)
            filas = await unsafe_select_all(session, modelo)

    assert filas, f"debería ver sus propias filas de {modelo.__tablename__}"
    ajenas = [f for f in filas if f.organization_id != organizacion.id]
    assert not ajenas, f"{modelo.__tablename__} filtró filas de otra organización"


async def test_no_se_puede_crear_un_patrocinador_sobre_un_evento_ajeno(
    organizacion: OrganizacionDePrueba, otra_organizacion: OrganizacionDePrueba
) -> None:
    datos_propios = await _crear_datos_de_prueba(organizacion)
    datos_ajenos = await _crear_datos_de_prueba(otra_organizacion)

    with pytest.raises(DBAPIError):
        async with SessionApp() as session:
            async with session.begin():
                await set_organization_context(session, organizacion.id)
                session.add(
                    Sponsor(
                        event_id=datos_ajenos.event_id,
                        tier_id=datos_propios.tier_id,
                        organization_id=organizacion.id,
                        name="Patrocinador intruso",
                        contribution_type="monetaria",
                    )
                )
                await session.flush()

    async with SessionMaintenance() as session:
        encontrado = await session.scalar(
            text("SELECT count(*) FROM sponsors WHERE name = 'Patrocinador intruso'")
        )
    assert encontrado == 0


async def test_no_se_puede_crear_un_patrocinador_con_un_nivel_ajeno(
    organizacion: OrganizacionDePrueba, otra_organizacion: OrganizacionDePrueba
) -> None:
    datos_propios = await _crear_datos_de_prueba(organizacion)
    datos_ajenos = await _crear_datos_de_prueba(otra_organizacion)

    with pytest.raises(DBAPIError):
        async with SessionApp() as session:
            async with session.begin():
                await set_organization_context(session, organizacion.id)
                session.add(
                    Sponsor(
                        event_id=datos_propios.event_id,
                        tier_id=datos_ajenos.tier_id,
                        organization_id=organizacion.id,
                        name="Patrocinador intruso",
                        contribution_type="monetaria",
                    )
                )
                await session.flush()

    async with SessionMaintenance() as session:
        encontrado = await session.scalar(
            text("SELECT count(*) FROM sponsors WHERE name = 'Patrocinador intruso'")
        )
    assert encontrado == 0


async def test_no_se_puede_leer_un_tier_ajeno(
    organizacion: OrganizacionDePrueba, otra_organizacion: OrganizacionDePrueba
) -> None:
    datos_ajenos = await _crear_datos_de_prueba(otra_organizacion)

    async with SessionApp() as session:
        async with session.begin():
            await set_organization_context(session, organizacion.id)
            fila = await session.get(SponsorTier, datos_ajenos.tier_id)
    assert fila is None


async def test_borrar_un_nivel_con_patrocinadores_activos_falla_por_integridad(
    organizacion: OrganizacionDePrueba,
) -> None:
    """Sin `ondelete` en `sponsors.tier_id`: `RESTRICT` por defecto. El
    servicio traduce esto a 409 (`test_sponsors_service.py`); esta prueba
    confirma que la base de datos también lo bloquea por su cuenta."""
    datos = await _crear_datos_de_prueba(organizacion)

    with pytest.raises((DBAPIError, IntegrityError)):
        async with SessionMaintenance() as session:
            await session.execute(
                text("DELETE FROM sponsor_tiers WHERE id = :id"), {"id": datos.tier_id}
            )
            await session.commit()
