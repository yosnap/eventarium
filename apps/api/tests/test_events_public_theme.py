"""Las páginas públicas que cuelgan de un evento (sesión, patrocinador,
políticas) devuelven la misma plantilla resuelta que su ficha: sin ella, el
visitante cambiaba de aspecto al pasar de la ficha a cualquiera de ellas."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select

from app.core.database import SessionMaintenance
from app.modules.theme_templates.models import ThemeTemplate
from tests.conftest import OrganizacionDePrueba, iniciar_sesion
from tests.test_sponsors_router import _crear_evento, _crear_tier, _publicar

PUBLIC_EVENTS = "/api/v1/public/events"
EVENTS = "/api/v1/events"


async def _plantilla_no_por_defecto() -> ThemeTemplate:
    """Una que no sea la de por defecto: si el evento heredara por error, el
    tema devuelto sería el por defecto y el test lo notaría."""
    async with SessionMaintenance() as session:
        plantilla = await session.scalar(
            select(ThemeTemplate).where(ThemeTemplate.is_default.is_(False)).limit(1)
        )
    assert plantilla is not None, "el catálogo necesita una plantilla que no sea la de por defecto"
    return plantilla


async def test_sesion_patrocinador_y_politicas_traen_el_tema_del_evento(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    plantilla = await _plantilla_no_por_defecto()
    evento = await _crear_evento(cliente, cabeceras, "tema-en-subpaginas")
    elegido = await cliente.patch(
        f"{EVENTS}/{evento['id']}",
        headers=cabeceras,
        json={"theme_template_id": str(plantilla.id)},
    )
    assert elegido.status_code == 200, elegido.text

    ahora = datetime.now(UTC)
    sesion = (
        await cliente.post(
            f"{EVENTS}/{evento['id']}/sessions",
            headers=cabeceras,
            json={
                "session_type": "talk",
                "title": "Charla",
                "starts_at": (ahora + timedelta(hours=1)).isoformat(),
                "ends_at": (ahora + timedelta(hours=2)).isoformat(),
            },
        )
    ).json()
    nivel = await _crear_tier(cliente, cabeceras, "Oro", 1)
    patrocinador = (
        await cliente.post(
            f"{EVENTS}/{evento['id']}/sponsors",
            headers=cabeceras,
            json={
                "tier_id": nivel["id"],
                "name": "Empresa",
                "contribution_type": "en_especie",
                "contribution_description": "Catering",
            },
        )
    ).json()
    await _publicar(cliente, cabeceras, evento["id"])

    base = f"{PUBLIC_EVENTS}/{evento['slug']}"
    ficha = (await cliente.get(base)).json()
    assert ficha["theme"]["key"] == plantilla.key

    for ruta in (
        f"{base}/sessions/{sesion['id']}",
        f"{base}/sponsors/{patrocinador['id']}",
        f"{base}/policies",
    ):
        respuesta = await cliente.get(ruta)
        assert respuesta.status_code == 200, (ruta, respuesta.text)
        assert respuesta.json()["theme"] == ficha["theme"], ruta
