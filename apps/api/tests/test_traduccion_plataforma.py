"""Traducción del contenido de la plataforma (legal y categorías) con la IA de la
plataforma: su propia contabilidad y tope, la regla de servicio del legal y que
nunca pisa lo escrito a mano."""

from __future__ import annotations

import json
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import func, select, update

from app.core.database import SessionMaintenance
from app.modules.ai_gateway.models import AiUsageRecord, PlatformAiSettings, PlatformAiUsage
from app.modules.platform import traduccion
from tests.ai_gateway_test_helpers import (
    ProveedorSimulado,
    configurar_plataforma,
    respuesta_de_chat,
)
from tests.conftest import OrganizacionDePrueba
from tests.test_events_categorias import ADMIN as CATEGORIAS
from tests.test_events_categorias import _superadmin
from tests.test_legal_pages_y_cookie_consent import PLATFORM_LEGAL_ADMIN, PUBLIC_LEGAL


def _traducir_todo(proveedor: ProveedorSimulado) -> None:
    """El proveedor devuelve «EN: <texto>» para cada clave que reciba."""

    def responder(cuerpo: dict) -> dict:
        textos = json.loads(cuerpo["messages"][-1]["content"])
        return respuesta_de_chat(
            contenido=json.dumps({clave: f"EN: {texto}" for clave, texto in textos.items()})
        )

    proveedor.responder = responder


async def _usos_de_plataforma() -> list[PlatformAiUsage]:
    async with SessionMaintenance() as session:
        return list(await session.scalars(select(PlatformAiUsage)))


async def test_la_ia_de_plataforma_traduce_el_legal_con_aviso_y_sin_indexar(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    cifrado: str,
    proveedor_simulado: ProveedorSimulado,
) -> None:
    await configurar_plataforma()
    _traducir_todo(proveedor_simulado)

    assert await traduccion.traducir_legal() == 4

    en_ingles = (await cliente.get(f"{PUBLIC_LEGAL}/privacidad?idioma=en-US")).json()
    assert en_ingles["served_locale"] == "en-US"
    assert en_ingles["content"].startswith("EN: ")
    assert en_ingles["machine_translated"] is True
    # Sin revisar no se anuncia a los buscadores.
    assert en_ingles["available_locales"] == ["es-ES"]
    # El gasto es de la plataforma, no de ninguna organización.
    usos = await _usos_de_plataforma()
    assert len(usos) == 4
    assert {uso.status for uso in usos} == {"liquidado"}
    async with SessionMaintenance() as session:
        assert await session.scalar(select(func.count()).select_from(AiUsageRecord)) == 0
    # Sin cambios, una segunda pasada no vuelve a llamar.
    assert await traduccion.traducir_legal() == 0
    assert len(proveedor_simulado.peticiones) == 4

    # Revisada: sin aviso, indexable, y la IA ya no la toca.
    cabeceras = await _superadmin(cliente, organizacion)
    revisada = await cliente.post(
        f"{PLATFORM_LEGAL_ADMIN}/review",
        headers=cabeceras,
        json={"page": "privacy_policy", "locale": "en-US"},
    )
    assert revisada.status_code == 200, revisada.text
    tras_revisar = (await cliente.get(f"{PUBLIC_LEGAL}/privacidad?idioma=en-US")).json()
    assert tras_revisar["machine_translated"] is False
    assert tras_revisar["available_locales"] == ["es-ES", "en-US"]


async def test_un_cambio_del_espanol_rehace_la_ia_y_no_pisa_lo_escrito_a_mano(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    cifrado: str,
    proveedor_simulado: ProveedorSimulado,
) -> None:
    await configurar_plataforma()
    _traducir_todo(proveedor_simulado)
    cabeceras = await _superadmin(cliente, organizacion)
    await traduccion.traducir_legal()
    await cliente.patch(
        PLATFORM_LEGAL_ADMIN,
        headers=cabeceras,
        json={"locale": "en-US", "cookies_policy_content": "Cookies by hand."},
    )

    await cliente.patch(
        PLATFORM_LEGAL_ADMIN,
        headers=cabeceras,
        json={"privacy_policy_content": "Privacidad nueva.", "cookies_policy_content": "Cookies."},
    )
    # Mientras no se rehace, la traducción vieja no se sirve.
    vieja = (await cliente.get(f"{PUBLIC_LEGAL}/privacidad?idioma=en-US")).json()
    assert vieja["served_locale"] == "es-ES"

    assert await traduccion.traducir_legal() == 1
    privacidad = (await cliente.get(f"{PUBLIC_LEGAL}/privacidad?idioma=en-US")).json()
    assert privacidad["content"] == "EN: Privacidad nueva."
    # La de cookies está escrita a mano: queda desfasada y se sirve el español.
    cookies = (await cliente.get(f"{PUBLIC_LEGAL}/cookies?idioma=en-US")).json()
    assert cookies["served_locale"] == "es-ES"
    editor = (await cliente.get(f"{PLATFORM_LEGAL_ADMIN}?idioma=en-US", headers=cabeceras)).json()
    assert editor["cookies_policy"]["translation"]["status"] == "desactualizada"
    assert editor["cookies_policy"]["translation"]["content"] == "Cookies by hand."


async def test_sin_ia_de_plataforma_o_sin_presupuesto_no_llama_y_sirve_el_espanol(
    cliente: AsyncClient,
    cifrado: str,
    proveedor_simulado: ProveedorSimulado,
) -> None:
    assert await traduccion.traducir_legal() == 0

    await configurar_plataforma()
    async with SessionMaintenance() as session, session.begin():
        await session.execute(
            update(PlatformAiSettings).values(translation_monthly_cap_usd=Decimal("0.000001"))
        )
    assert await traduccion.traducir_legal() == 0

    assert proveedor_simulado.peticiones == []
    usos = await _usos_de_plataforma()
    assert [(uso.status, uso.error_code) for uso in usos] == [("fallido", "limite_superado")]
    respuesta = (await cliente.get(f"{PUBLIC_LEGAL}/privacidad?idioma=en-US")).json()
    assert respuesta["served_locale"] == "es-ES"


async def test_las_categorias_se_rellenan_con_ia_sin_tocar_lo_escrito_a_mano(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    cifrado: str,
    proveedor_simulado: ProveedorSimulado,
) -> None:
    await configurar_plataforma()
    _traducir_todo(proveedor_simulado)
    cabeceras = await _superadmin(cliente, organizacion)
    con_mano = await cliente.post(
        CATEGORIAS,
        headers=cabeceras,
        json={"slug": "con-mano", "name": "Talleres", "name_i18n": {"en-US": "Workshops"}},
    )
    sin_mano = await cliente.post(
        CATEGORIAS, headers=cabeceras, json={"slug": "sin-mano", "name": "Charlas"}
    )
    assert con_mano.status_code == sin_mano.status_code == 201

    await traduccion.traducir_categorias()

    catalogo = {c["slug"]: c for c in (await cliente.get(CATEGORIAS, headers=cabeceras)).json()}
    assert catalogo["con-mano"]["name_i18n"] == {"en-US": "Workshops"}
    assert catalogo["con-mano"]["name_i18n_origin"] == {"en-US": "manual"}
    assert catalogo["sin-mano"]["name_i18n"] == {"en-US": "EN: Charlas"}
    assert catalogo["sin-mano"]["name_i18n_origin"] == {"en-US": "ia"}

    # Al renombrar, lo de la IA se rehace; lo escrito a mano se queda.
    for slug, nombre in (("con-mano", "Talleres prácticos"), ("sin-mano", "Ponencias")):
        await cliente.patch(
            f"{CATEGORIAS}/{catalogo[slug]['id']}", headers=cabeceras, json={"name": nombre}
        )
    await traduccion.traducir_categorias()
    catalogo = {c["slug"]: c for c in (await cliente.get(CATEGORIAS, headers=cabeceras)).json()}
    assert catalogo["con-mano"]["name_i18n"] == {"en-US": "Workshops"}
    assert catalogo["sin-mano"]["name_i18n"] == {"en-US": "EN: Ponencias"}


async def test_el_superadmin_ve_y_cambia_el_tope_pero_no_puede_quitarlo(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    cifrado: str,
    proveedor_simulado: ProveedorSimulado,
) -> None:
    await configurar_plataforma()
    _traducir_todo(proveedor_simulado)
    await traduccion.traducir_legal()
    cabeceras = await _superadmin(cliente, organizacion)

    vista = (await cliente.get("/api/v1/admin/ai-settings", headers=cabeceras)).json()
    assert Decimal(vista["translation_monthly_cap_usd"]) == Decimal("5")
    assert vista["translation_daily_calls"] == 200
    assert Decimal(vista["translation_spent_usd"]) > 0

    cambiado = await cliente.put(
        "/api/v1/admin/ai-settings",
        headers=cabeceras,
        json={"translation_monthly_cap_usd": "12.5", "translation_daily_calls": 50},
    )
    assert cambiado.status_code == 200, cambiado.text
    assert Decimal(cambiado.json()["translation_monthly_cap_usd"]) == Decimal("12.5")
    for invalido in ({"translation_monthly_cap_usd": "0"}, {"translation_daily_calls": 0}):
        rechazado = await cliente.put("/api/v1/admin/ai-settings", headers=cabeceras, json=invalido)
        assert rechazado.status_code == 422
