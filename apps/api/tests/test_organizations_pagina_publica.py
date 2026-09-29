"""Página pública de organización: opt-in, sin datos privados y con sus eventos."""

from __future__ import annotations

import importlib.util
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from httpx import AsyncClient
from sqlalchemy import text

from app.core.database import SessionMaintenance
from app.modules.admin.router import _to_response
from app.modules.organizations.models import Organization
from tests.conftest import OrganizacionDePrueba, iniciar_sesion
from tests.test_events_public import _crear_evento, _publicar

ORGANIZACION = "/api/v1/organizations/me"
PUBLICO = "/api/v1/public/organizations"
CAMPOS_PUBLICOS = {
    "slug",
    "name",
    "description",
    "website",
    "address",
    "logo_url",
    "social_links",
}


async def _activar(cliente: AsyncClient, cabeceras: dict[str, str], **campos: object) -> None:
    respuesta = await cliente.patch(
        ORGANIZACION, headers=cabeceras, json={"public_page_enabled": True, **campos}
    )
    assert respuesta.status_code == 200, respuesta.text


def _fechas(desde_dias: int, duracion_dias: int = 1) -> dict[str, str]:
    ahora = datetime.now(UTC).replace(microsecond=0)
    inicio = ahora + timedelta(days=desde_dias)
    return {
        "starts_at": inicio.isoformat(),
        "ends_at": (inicio + timedelta(days=duracion_dias)).isoformat(),
    }


async def test_la_pagina_esta_desactivada_por_defecto_y_da_el_mismo_404_que_una_inexistente(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    apagada = await cliente.get(f"{PUBLICO}/{organizacion.slug}")
    inexistente = await cliente.get(f"{PUBLICO}/no-existe-nunca")
    assert apagada.status_code == 404
    assert inexistente.status_code == 404
    cuerpo_apagada = apagada.json()
    cuerpo_inexistente = inexistente.json()
    # Solo difiere `instance` (la URL pedida): nada revela cuál de los dos casos es.
    cuerpo_apagada.pop("instance")
    cuerpo_inexistente.pop("instance")
    assert cuerpo_apagada == cuerpo_inexistente

    eventos_apagada = await cliente.get(f"{PUBLICO}/{organizacion.slug}/events")
    eventos_inexistente = await cliente.get(f"{PUBLICO}/no-existe-nunca/events")
    assert eventos_apagada.status_code == eventos_inexistente.status_code == 404
    cuerpo_eventos_apagada = eventos_apagada.json()
    cuerpo_eventos_inexistente = eventos_inexistente.json()
    cuerpo_eventos_apagada.pop("instance")
    cuerpo_eventos_inexistente.pop("instance")
    assert cuerpo_eventos_apagada == cuerpo_eventos_inexistente == cuerpo_apagada


async def test_activada_expone_solo_los_campos_publicos_nunca_los_privados(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    await _activar(
        cliente,
        cabeceras,
        legal_name="Razón Social Privada S.L.",
        contact_email="privado@example.com",
        description="Quiénes somos",
        website="https://acme.example",
        address="Calle Mayor 1, Madrid",
    )

    respuesta = await cliente.get(f"{PUBLICO}/{organizacion.slug}")
    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert set(cuerpo) == CAMPOS_PUBLICOS
    assert cuerpo["description"] == "Quiénes somos"
    assert cuerpo["website"] == "https://acme.example"
    assert cuerpo["address"] == "Calle Mayor 1, Madrid"
    assert "Razón Social Privada" not in respuesta.text
    assert "privado@example.com" not in respuesta.text


async def test_desactivarla_vuelve_a_dar_404(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    await _activar(cliente, cabeceras)
    assert (await cliente.get(f"{PUBLICO}/{organizacion.slug}")).status_code == 200

    apagar = await cliente.patch(
        ORGANIZACION, headers=cabeceras, json={"public_page_enabled": False}
    )
    assert apagar.status_code == 200
    assert (await cliente.get(f"{PUBLICO}/{organizacion.slug}")).status_code == 404


async def test_una_organizacion_inactiva_no_sirve_su_pagina(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    await _activar(cliente, cabeceras)
    async with SessionMaintenance() as session:
        await session.execute(
            text("UPDATE organizations SET is_active = false WHERE id = :id"),
            {"id": organizacion.id},
        )
        await session.commit()

    assert (await cliente.get(f"{PUBLICO}/{organizacion.slug}")).status_code == 404
    assert (await cliente.get(f"{PUBLICO}/{organizacion.slug}/events")).status_code == 404


async def test_los_datos_editables_se_validan(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    for cuerpo in (
        {"website": "javascript:alert(1)"},
        {"website": "acme.example"},
        {"address": "x" * 301},
        {"public_page_enabled": None},
    ):
        respuesta = await cliente.patch(ORGANIZACION, headers=cabeceras, json=cuerpo)
        assert respuesta.status_code == 422, (cuerpo, respuesta.text)


async def test_el_panel_devuelve_direccion_e_interruptor(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    antes = (await cliente.get(ORGANIZACION, headers=cabeceras)).json()
    assert antes["public_page_enabled"] is False
    assert antes["address"] is None

    await _activar(cliente, cabeceras, address="Plaza Mayor 2")
    despues = (await cliente.get(ORGANIZACION, headers=cabeceras)).json()
    assert despues["public_page_enabled"] is True
    assert despues["address"] == "Plaza Mayor 2"


async def test_lista_solo_eventos_publicos_de_esa_organizacion_proximos_y_pasados(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    otra_organizacion: OrganizacionDePrueba,
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    await _activar(cliente, cabeceras)
    proximo_cerca = await _crear_evento(cliente, cabeceras, slug="cerca", **_fechas(2))
    proximo_lejos = await _crear_evento(cliente, cabeceras, slug="lejos", **_fechas(20))
    pasado_reciente = await _crear_evento(cliente, cabeceras, slug="reciente", **_fechas(-5))
    pasado_antiguo = await _crear_evento(cliente, cabeceras, slug="antiguo", **_fechas(-40))
    for evento in (proximo_cerca, proximo_lejos, pasado_reciente, pasado_antiguo):
        await _publicar(cliente, cabeceras, evento["id"])
    await _crear_evento(cliente, cabeceras, slug="borrador", **_fechas(3))
    oculto = await _crear_evento(cliente, cabeceras, slug="oculto", **_fechas(4))
    await _publicar(cliente, cabeceras, oculto["id"], visibility="hidden")

    _, cabeceras_b = await iniciar_sesion(cliente, otra_organizacion)
    ajeno = await _crear_evento(cliente, cabeceras_b, slug="ajeno", **_fechas(1))
    await _publicar(cliente, cabeceras_b, ajeno["id"])

    proximos = await cliente.get(f"{PUBLICO}/{organizacion.slug}/events")
    assert proximos.status_code == 200, proximos.text
    assert [e["slug"] for e in proximos.json()["items"]] == ["cerca", "lejos"]
    assert proximos.json()["total"] == 2
    assert all(e["organization"]["slug"] == organizacion.slug for e in proximos.json()["items"])

    pasados = await cliente.get(f"{PUBLICO}/{organizacion.slug}/events", params={"when": "past"})
    assert [e["slug"] for e in pasados.json()["items"]] == ["reciente", "antiguo"]


async def test_la_paginacion_respeta_limit_y_offset(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    await _activar(cliente, cabeceras)
    for numero in range(1, 4):
        evento = await _crear_evento(cliente, cabeceras, slug=f"e{numero}", **_fechas(numero))
        await _publicar(cliente, cabeceras, evento["id"])

    primera = (
        await cliente.get(f"{PUBLICO}/{organizacion.slug}/events", params={"limit": 2})
    ).json()
    segunda = (
        await cliente.get(f"{PUBLICO}/{organizacion.slug}/events", params={"limit": 2, "offset": 2})
    ).json()
    assert [e["slug"] for e in primera["items"]] == ["e1", "e2"]
    assert [e["slug"] for e in segunda["items"]] == ["e3"]
    assert primera["total"] == segunda["total"] == 3
    assert (
        await cliente.get(f"{PUBLICO}/{organizacion.slug}/events", params={"limit": 999})
    ).status_code == 422


async def test_page_public_es_real_en_los_contratos_de_evento(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_evento(cliente, cabeceras, slug="ficha")
    await _publicar(cliente, cabeceras, evento["id"])
    ruta = f"{PUBLICO}/{organizacion.slug}/events/ficha"

    assert (await cliente.get(ruta)).json()["organization"]["page_public"] is False
    await _activar(cliente, cabeceras)
    assert (await cliente.get(ruta)).json()["organization"]["page_public"] is True
    listado = (await cliente.get("/api/v1/public/events")).json()
    assert listado[0]["organization"]["page_public"] is True


def test_el_panel_de_plataforma_refleja_la_pagina_publica_y_la_direccion() -> None:
    """Regresión: `_to_response` de superadmin no pasaba los campos nuevos y los
    valores por defecto los tapaban devolviendo siempre `false`/`null`."""
    organizacion = Organization(
        slug="acme",
        name="Acme",
        is_active=True,
        address="Plaza Mayor 2",
        public_page_enabled=True,
    )
    organizacion.id = uuid.uuid4()

    respuesta = _to_response(organizacion)

    assert respuesta.public_page_enabled is True
    assert respuesta.address == "Plaza Mayor 2"


async def test_la_direccion_en_blanco_es_sin_direccion_y_la_web_exige_algo_tras_el_esquema(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    guardada = await cliente.patch(ORGANIZACION, headers=cabeceras, json={"address": "   "})
    assert guardada.status_code == 200
    assert guardada.json()["address"] is None

    for web in ("https://", "https://acme example"):
        rechazada = await cliente.patch(ORGANIZACION, headers=cabeceras, json={"website": web})
        assert rechazada.status_code == 422, web


async def test_la_migracion_antepone_el_esquema_a_las_webs_heredadas_sin_esquema(
    organizacion: OrganizacionDePrueba,
) -> None:
    ruta = (
        Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0059_pagina_publica_org.py"
    )
    especificacion = importlib.util.spec_from_file_location("migracion_0059", ruta)
    assert especificacion is not None and especificacion.loader is not None
    migracion = importlib.util.module_from_spec(especificacion)
    especificacion.loader.exec_module(migracion)

    async def web_de_la_organizacion() -> str | None:
        async with SessionMaintenance() as session:
            return (
                await session.execute(
                    text("SELECT website FROM organizations WHERE id = :id"),
                    {"id": organizacion.id},
                )
            ).scalar()

    for antes, despues in (
        ("acme.example", "https://acme.example"),
        ("  www.acme.example ", "https://www.acme.example"),
        ("http://ya-tiene.example", "http://ya-tiene.example"),
        ("HTTPS://MAYUSCULAS.example", "HTTPS://MAYUSCULAS.example"),
        ("   ", None),
    ):
        async with SessionMaintenance() as session:
            await session.execute(
                text("UPDATE organizations SET website = :web WHERE id = :id"),
                {"web": antes, "id": organizacion.id},
            )
            await session.execute(text(migracion._NORMALIZAR_WEB))
            await session.execute(text(migracion._QUITAR_WEB_VACIA))
            await session.commit()
        assert await web_de_la_organizacion() == despues, antes


async def test_los_cancelados_siguen_en_la_pagina_de_la_organizacion_marcados_como_cancelados(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    await _activar(cliente, cabeceras)
    proximo = await _crear_evento(cliente, cabeceras, slug="cancelado-proximo", **_fechas(3))
    pasado = await _crear_evento(cliente, cabeceras, slug="cancelado-pasado", **_fechas(-10))
    normal = await _crear_evento(cliente, cabeceras, slug="normal", **_fechas(5))
    oculto = await _crear_evento(cliente, cabeceras, slug="cancelado-oculto", **_fechas(6))
    for evento in (proximo, pasado, normal):
        await _publicar(cliente, cabeceras, evento["id"])
    await _publicar(cliente, cabeceras, oculto["id"], visibility="hidden")
    async with SessionMaintenance() as session:
        await session.execute(
            text(
                "UPDATE events SET status = 'cancelled', cancelled_at = now() "
                "WHERE slug IN ('cancelado-proximo', 'cancelado-pasado', 'cancelado-oculto')"
            )
        )
        await session.commit()

    proximos = (await cliente.get(f"{PUBLICO}/{organizacion.slug}/events")).json()
    pasados = (
        await cliente.get(f"{PUBLICO}/{organizacion.slug}/events", params={"when": "past"})
    ).json()

    assert [(e["slug"], e["cancelled"]) for e in proximos["items"]] == [
        ("cancelado-proximo", True),
        ("normal", False),
    ]
    assert [(e["slug"], e["cancelled"]) for e in pasados["items"]] == [("cancelado-pasado", True)]
    # El directorio general sigue sin listar cancelados; el oculto no sale en ningún sitio.
    general = [e["slug"] for e in (await cliente.get("/api/v1/public/events")).json()]
    assert general == ["normal"]
