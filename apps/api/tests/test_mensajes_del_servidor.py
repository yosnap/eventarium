"""Mensajes del servidor en el idioma de quien pregunta."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel, Field, field_validator

from app.core import mensajes
from app.core.locale import IdiomaMiddleware
from app.core.mensajes import t
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

    @field_validator("nombre")
    @classmethod
    def _no_admin(cls, valor: str) -> str:
        if valor == "admin":
            raise ValueError("El nombre no puede ser «admin».")
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
