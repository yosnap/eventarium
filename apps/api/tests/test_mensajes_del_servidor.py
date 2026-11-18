"""Mensajes del servidor en el idioma de quien pregunta."""

from __future__ import annotations

import logging

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core import mensajes
from app.core.locale import IdiomaMiddleware
from app.core.mensajes import ErrorDeValidacion, t
from app.core.mensajes.extraer import extraer
from app.shared.errors import NotFoundError, register_exception_handlers


def test_todos_los_mensajes_son_literales() -> None:
    """Un mensaje con f-string o variable no se puede traducir: hay que escribirlo
    como plantilla con `{parámetros}` y pasarlos en `params=`."""
    assert extraer().no_literales == []


def test_todos_los_mensajes_estan_traducidos() -> None:
    sin_traducir = sorted(extraer().mensajes - set(mensajes.catalogo("en-US")))
    assert sin_traducir == [], (
        f"{len(sin_traducir)} mensajes sin traducir; ejecuta `pnpm i18n:traducir`"
    )


@pytest.fixture
def catalogo_de_prueba(monkeypatch: pytest.MonkeyPatch) -> None:
    traducciones = {
        "No existe el evento {slug}.": "There is no event {slug}.",
        "Recurso no encontrado": "Resource not found",
        "Este campo es obligatorio.": "This field is required.",
        "Debe tener al menos {min_length} caracteres.": (
            "Must have at least {min_length} characters."
        ),
        "El nombre no puede ser «admin».": "The name cannot be “admin”.",
        "El nombre «{nombre}» está reservado.": "The name “{nombre}” is reserved.",
        "El correo electrónico no es válido.": "The email address is not valid.",
        "Error interno": "Internal error",
        "Se ha producido un error inesperado.": "An unexpected error occurred.",
    }
    monkeypatch.setattr(
        mensajes, "catalogo", lambda locale: traducciones if locale == "en-US" else {}
    )


def test_t_traduce_y_rellena_los_parametros(catalogo_de_prueba: None) -> None:
    assert t("No existe el evento {slug}.", "en-US", slug="iawic") == "There is no event iawic."
    assert t("No existe el evento {slug}.", "es-ES", slug="iawic") == "No existe el evento iawic."
    assert t("Sin traducción {x}.", "en-US", x=1) == "Sin traducción 1."


class _Alta(BaseModel):
    nombre: str = Field(min_length=3)
    edad: int
    correo: EmailStr | None = None

    @field_validator("nombre")
    @classmethod
    def _no_admin(cls, valor: str) -> str:
        if valor == "admin":
            raise ValueError("El nombre no puede ser «admin».")
        if valor == "root":
            raise ErrorDeValidacion(
                "El nombre «{nombre}» está reservado.", params={"nombre": valor}
            )
        return valor


def _app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)
    app.add_middleware(IdiomaMiddleware)

    @app.get("/eventos/{slug}")
    async def evento(slug: str) -> None:
        raise NotFoundError("No existe el evento {slug}.", params={"slug": slug}, code="evento")

    @app.post("/altas")
    async def alta(datos: _Alta) -> None:
        return None

    @app.get("/fallo")
    async def fallo() -> None:
        raise RuntimeError("fallo inesperado")

    return app


async def test_errores_de_dominio_en_el_idioma_de_la_peticion(catalogo_de_prueba: None) -> None:
    async with AsyncClient(transport=ASGITransport(app=_app()), base_url="http://t") as cliente:
        ingles = (await cliente.get("/eventos/iawic", headers={"Accept-Language": "en"})).json()
        espanol = (await cliente.get("/eventos/iawic")).json()
    assert ingles["detail"] == "There is no event iawic."
    assert ingles["title"] == "Resource not found"
    assert ingles["code"] == "evento"
    assert ingles["params"] == {"slug": "iawic"}
    assert espanol["detail"] == "No existe el evento iawic."


async def test_errores_de_validacion_en_el_idioma_de_la_peticion(
    catalogo_de_prueba: None,
) -> None:
    async with AsyncClient(transport=ASGITransport(app=_app()), base_url="http://t") as cliente:
        corto = await cliente.post(
            "/altas", json={"nombre": "ab"}, headers={"Accept-Language": "en"}
        )
        admin = await cliente.post(
            "/altas", json={"nombre": "admin", "edad": 3}, headers={"Accept-Language": "en"}
        )
        espanol = await cliente.post("/altas", json={"nombre": "ab"})
    mensajes_en = {e["campo"]: e["mensaje"] for e in corto.json()["errors"]}
    assert mensajes_en["body.nombre"] == "Must have at least 3 characters."
    assert mensajes_en["body.edad"] == "This field is required."
    assert admin.json()["errors"][0]["mensaje"] == "The name cannot be “admin”."
    mensajes_es = {e["campo"]: e["mensaje"] for e in espanol.json()["errors"]}
    assert mensajes_es["body.edad"] == "Este campo es obligatorio."


async def test_cada_error_de_validacion_dice_si_viene_de_un_validador_propio(
    catalogo_de_prueba: None,
) -> None:
    async with AsyncClient(transport=ASGITransport(app=_app()), base_url="http://t") as cliente:
        respuesta = await cliente.post(
            "/altas", json={"nombre": "admin"}, headers={"Accept-Language": "en"}
        )
    errores = {e["campo"]: e for e in respuesta.json()["errors"]}
    assert errores["body.nombre"] == {
        "campo": "body.nombre",
        "mensaje": "The name cannot be “admin”.",
        "propio": True,
    }
    assert errores["body.edad"]["propio"] is False


async def test_un_validador_con_parametros_se_traduce_con_sus_datos(
    catalogo_de_prueba: None,
) -> None:
    async with AsyncClient(transport=ASGITransport(app=_app()), base_url="http://t") as cliente:
        ingles = await cliente.post(
            "/altas", json={"nombre": "root", "edad": 3}, headers={"Accept-Language": "en"}
        )
        espanol = await cliente.post("/altas", json={"nombre": "root", "edad": 3})
    assert ingles.json()["errors"][0]["mensaje"] == "The name “root” is reserved."
    assert espanol.json()["errors"][0]["mensaje"] == "El nombre «root» está reservado."


async def test_el_correo_no_valido_de_pydantic_se_traduce(catalogo_de_prueba: None) -> None:
    async with AsyncClient(transport=ASGITransport(app=_app()), base_url="http://t") as cliente:
        respuesta = await cliente.post(
            "/altas",
            json={"nombre": "ana", "edad": 3, "correo": "sin-arroba"},
            headers={"Accept-Language": "en"},
        )
    (error,) = respuesta.json()["errors"]
    assert error["campo"] == "body.correo"
    assert error["mensaje"] == "The email address is not valid."


async def test_el_error_500_sale_en_el_idioma_de_la_peticion(catalogo_de_prueba: None) -> None:
    transporte = ASGITransport(app=_app(), raise_app_exceptions=False)
    async with AsyncClient(transport=transporte, base_url="http://t") as cliente:
        ingles = await cliente.get("/fallo", headers={"Accept-Language": "en"})
        por_parametro = await cliente.get("/fallo", params={"idioma": "en"})
        espanol = await cliente.get("/fallo")
    assert ingles.status_code == 500
    assert ingles.json()["title"] == "Internal error"
    assert ingles.json()["detail"] == "An unexpected error occurred."
    assert por_parametro.json()["detail"] == "An unexpected error occurred."
    assert espanol.json()["detail"] == "Se ha producido un error inesperado."


@pytest.fixture
def referencia_de_prueba(monkeypatch: pytest.MonkeyPatch) -> set[tuple[str, str]]:
    """Un catálogo de referencia con una sola clave, sin traducir al inglés."""
    monkeypatch.setattr(mensajes, "LOCALE_DE_REFERENCIA", "es-ES")
    monkeypatch.setattr(
        mensajes, "catalogo", lambda locale: {"Clave conocida.": "x"} if locale == "es-ES" else {}
    )
    avisados: set[tuple[str, str]] = set()
    monkeypatch.setattr(mensajes, "_avisados", avisados)
    return avisados


def test_t_no_registra_ni_guarda_un_texto_desconocido(
    referencia_de_prueba: set[tuple[str, str]], caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger=mensajes.__name__):
        assert t("Texto de alguien: ana@example.com", "en-US") == (
            "Texto de alguien: ana@example.com"
        )
        assert t("Clave conocida.", "en-US") == "Clave conocida."
    assert referencia_de_prueba == {("en-US", "Clave conocida.")}
    assert [registro.getMessage() for registro in caplog.records] == [
        "Mensaje sin traducir a en-US: 'Clave conocida.'"
    ]


def test_los_avisos_sin_traducir_estan_acotados(
    referencia_de_prueba: set[tuple[str, str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mensajes, "MAX_AVISADOS", 0)
    t("Clave conocida.", "en-US")
    assert referencia_de_prueba == set()
