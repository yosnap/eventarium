"""Catálogo de idiomas y resolución del idioma de cada petición."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.codigos_de_idioma import CODIGOS_ISO_639_1
from app.core.locale import (
    DEFAULT_LOCALE,
    LOCALES,
    PREFIJO_DE_URL,
    RUTAS_WEB,
    IdiomaDep,
    IdiomaMiddleware,
    buscar_locale,
    idioma_actual,
    normalizar_locale,
    resolver_accept_language,
    resolver_idioma_de_peticion,
)
from app.modules.organizations.schemas import RESERVED_SLUGS

RAIZ = Path(__file__).resolve().parents[3]
CATALOGO_WEB = RAIZ / "apps" / "web" / "src" / "app" / "core" / "i18n" / "locale-de-cuenta.ts"


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        ("es-ES", "es-ES"),
        ("en-US", "en-US"),
        ("EN-us", "en-US"),
        ("en", "en-US"),
        ("en-GB", "en-US"),
        ("es-MX", "es-ES"),
        ("fr-FR", None),
        ("", None),
        (None, None),
    ],
)
def test_buscar_locale(valor: str | None, esperado: str | None) -> None:
    assert buscar_locale(valor) == esperado


def test_normalizar_locale_cae_al_idioma_por_defecto() -> None:
    assert normalizar_locale("fr") == DEFAULT_LOCALE
    assert normalizar_locale(None) == DEFAULT_LOCALE


@pytest.mark.parametrize(
    ("cabecera", "esperado"),
    [
        (None, "es-ES"),
        ("", "es-ES"),
        ("en-US,en;q=0.9", "en-US"),
        ("fr-FR,fr;q=0.9,en;q=0.8,es;q=0.7", "en-US"),
        ("es;q=0.5,en;q=0.9", "en-US"),
        ("en;q=0,es", "es-ES"),
        ("de-DE,fr;q=0.8", "es-ES"),
        ("*", "es-ES"),
        ("en;q=abc,es;q=0.1", "es-ES"),
        ("es,en", "es-ES"),
    ],
)
def test_resolver_accept_language(cabecera: str | None, esperado: str) -> None:
    assert resolver_accept_language(cabecera) == esperado


def test_el_parametro_idioma_manda_sobre_la_cabecera() -> None:
    assert resolver_idioma_de_peticion("en-US", "es-ES") == "en-US"
    assert resolver_idioma_de_peticion("xx", "en") == "en-US"
    assert resolver_idioma_de_peticion(None, None) == "es-ES"


async def test_el_middleware_fija_el_idioma_de_la_peticion() -> None:
    app = FastAPI()
    app.add_middleware(IdiomaMiddleware)

    @app.get("/idioma")
    async def leer(idioma: IdiomaDep) -> dict[str, str]:
        return {"dependencia": idioma, "contexto": idioma_actual()}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as cliente:
        ingles = await cliente.get("/idioma", headers={"Accept-Language": "en-GB,en;q=0.9"})
        por_parametro = await cliente.get("/idioma?idioma=en-US")
        sin_cabecera = await cliente.get("/idioma")

    assert ingles.json() == {"dependencia": "en-US", "contexto": "en-US"}
    assert por_parametro.json()["dependencia"] == "en-US"
    assert sin_cabecera.json()["dependencia"] == "es-ES"
    # Fuera de la petición el contexto vuelve al idioma por defecto.
    assert idioma_actual() == "es-ES"


@pytest.mark.skipif(not CATALOGO_WEB.exists(), reason="falta apps/web en este checkout")
def test_el_catalogo_coincide_con_el_de_la_web() -> None:
    texto = CATALOGO_WEB.read_text(encoding="utf-8")
    declaracion = re.search(r"LOCALES_DE_CUENTA\s*=\s*\[([^\]]*)\]", texto)
    assert declaracion, "no se encuentra LOCALES_DE_CUENTA en la web"
    assert tuple(re.findall(r"'([^']+)'", declaracion.group(1))) == LOCALES


def test_ningun_codigo_de_idioma_puede_ser_una_organizacion() -> None:
    assert CODIGOS_ISO_639_1 <= RESERVED_SLUGS
    assert {"en", "es", "fr", "de", "en-us", "es-es"} <= RESERVED_SLUGS


@pytest.mark.skipif(not CATALOGO_WEB.exists(), reason="falta apps/web en este checkout")
def test_los_prefijos_de_url_coinciden_con_los_de_la_web() -> None:
    texto = (CATALOGO_WEB.parent / "idioma.ts").read_text(encoding="utf-8")
    bloque = re.search(r"PREFIJO_DE_IDIOMA[^=]*=\s*\{([^}]*)\}", texto)
    assert bloque, "no se encuentra PREFIJO_DE_IDIOMA en la web"
    web = dict(re.findall(r"'([^']+)':\s*'([^']*)'", bloque.group(1)))
    assert web == PREFIJO_DE_URL


RUTAS_TRADUCIDAS_WEB = CATALOGO_WEB.parent / "rutas-traducidas.ts"


def _rutas_traducidas_de_la_web() -> dict[str, str]:
    texto = RUTAS_TRADUCIDAS_WEB.read_text(encoding="utf-8")
    bloque = re.search(r"'en-US':\s*\{([^}]*)\}", texto)
    assert bloque, "no se encuentran las rutas en inglés de la web"
    pares = re.findall(r"(?:'([^']+)'|([\w-]+)):\s*'([^']+)'", bloque.group(1))
    return {con_comillas or sin_comillas: valor for con_comillas, sin_comillas, valor in pares}


@pytest.mark.skipif(not RUTAS_TRADUCIDAS_WEB.exists(), reason="falta apps/web en este checkout")
def test_las_rutas_que_enlaza_la_api_coinciden_con_las_de_la_web() -> None:
    web = _rutas_traducidas_de_la_web()
    for ruta, traducida in RUTAS_WEB["en-US"].items():
        assert web.get(ruta) == traducida, ruta


@pytest.mark.skipif(not RUTAS_TRADUCIDAS_WEB.exists(), reason="falta apps/web en este checkout")
def test_las_rutas_publicas_traducidas_estan_reservadas() -> None:
    primeros = {
        ruta.split("/", 1)[0]
        for par in _rutas_traducidas_de_la_web().items()
        for ruta in par
        if not ruta.startswith(":")
    }
    assert primeros, "no se ha leído ninguna ruta traducida"
    assert primeros - RESERVED_SLUGS == set()
