"""CRUD del catálogo de plantillas de tema (`app/modules/theme_templates`).

Fase 1 del plan de UX/UI: modelo, validación de lista blanca/formato,
validación de contraste en el backend (decisión A de la sesión 3 de
validación) y privilegios de `app_user` sobre la tabla de instalación.

Tabla de valores conocidos usada por `test_parser_de_contraste_...` (los
mismos números que debe reproducir el parser de `contrast.ts` en el
cliente, con tolerancia ±0,01 — ver `PARES_CRITICOS` y el riesgo de
divergencia del parser `oklch()` documentado en la fase 1 del plan):

| Color A                          | Color B    | Ratio esperado |
|-----------------------------------|------------|-----------------|
| `#ffffff`                         | `#000000`  | 21.0            |
| `#00ff87`                         | `#04140d`  | ~14.09          |
| `oklch(94% 0.180 152.4)`           | `#000000`  | ~16.82          |
"""

from __future__ import annotations

import copy
import os
import subprocess
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.core.database import SessionMaintenance
from app.modules.theme_templates.contrast import (
    PARES_CRITICOS,
    comprobar_contraste_de_plantilla,
    razon_de_contraste,
)
from app.modules.users.models import User
from tests.conftest import OrganizacionDePrueba, iniciar_sesion

API_DIR = Path(__file__).resolve().parents[2]
ADMIN_THEME_TEMPLATES = "/api/v1/admin/theme-templates"

# Mismos literales que siembra `0014_plantillas_de_tema` (no se importan: los
# nombres de fichero de Alembic empiezan por dígito y no son un módulo
# Python normal). Una copia de trabajo por test evita que una mutación se
# filtre a otro test.
_TOKENS_OSCURO: dict[str, str] = {
    "bg": "#080808",
    "surface": "#141414",
    "surface-2": "#0f0f0f",
    "surface-hi": "oklch(23% 0 90)",
    "border": "#222222",
    "border-strong": "#2a2a2a",
    "fg": "#f0f0f0",
    "muted": "#999999",
    "faint": "#555555",
    "accent": "#00ff87",
    "accent-hi": "oklch(94% 0.180 152.4)",
    "accent-dim": "oklch(87.6% 0.229 152.4 / .10)",
    "on-accent": "#04140d",
    "warn": "#ff4f00",
    "warn-dim": "oklch(75% 0.2 41 / .12)",
    "danger": "#ff4d4f",
    "danger-dim": "oklch(70% 0.2 15 / .12)",
    "nav-bg": "#0a0a0a",
    "backdrop": "oklch(0% 0 0 / .6)",
    "shadow-md": "oklch(0% 0 0 / .4)",
    "shadow-lg": "oklch(0% 0 0 / .55)",
}

_TOKENS_CLARO: dict[str, str] = {
    "bg": "oklch(97% 0 0)",
    "surface": "oklch(100% 0 0)",
    "surface-2": "oklch(93% 0 0)",
    "surface-hi": "oklch(89% 0 0)",
    "border": "oklch(85% 0 0)",
    "border-strong": "oklch(75% 0 0)",
    "fg": "oklch(15% 0 0)",
    "muted": "oklch(42% 0 0)",
    "faint": "oklch(65% 0 0)",
    "accent": "oklch(45% 0.15 152.4)",
    "accent-hi": "oklch(38% 0.16 152.4)",
    "accent-dim": "oklch(45% 0.15 152.4 / .10)",
    "on-accent": "oklch(100% 0 0)",
    "warn": "oklch(42% 0.15 41)",
    "warn-dim": "oklch(42% 0.15 41 / .12)",
    "danger": "oklch(45% 0.19 15)",
    "danger-dim": "oklch(45% 0.19 15 / .12)",
    "nav-bg": "oklch(100% 0 0)",
    "backdrop": "oklch(0% 0 0 / .45)",
    "shadow-md": "oklch(0% 0 0 / .12)",
    "shadow-lg": "oklch(0% 0 0 / .16)",
}


def _tokens_validos() -> dict[str, dict[str, str]]:
    return {"dark": copy.deepcopy(_TOKENS_OSCURO), "light": copy.deepcopy(_TOKENS_CLARO)}


async def _hacer_superadmin(email: str) -> None:
    async with SessionMaintenance() as session:
        usuario = await session.scalar(select(User).where(User.email == email))
        assert usuario is not None
        usuario.is_superadmin = True
        await session.commit()


@pytest.fixture(autouse=True)
async def _restaurar_catalogo_tras_cada_test() -> AsyncIterator[None]:
    """`theme_templates` no está en la lista de truncado global de
    `conftest.py` (truncarla borraría la semilla de `0014` para el resto de
    la suite, que no vuelve a sembrarse hasta el siguiente `alembic upgrade
    head`). En su lugar, cada test de este fichero deja el catálogo como lo
    encontró: solo `oscuro`/`claro`, con `oscuro` por defecto."""
    yield
    async with SessionMaintenance() as session:
        await session.execute(
            text("DELETE FROM theme_templates WHERE key NOT IN ('oscuro', 'claro')")
        )
        # Dos `UPDATE` separados, no uno con `is_default = (key = 'oscuro')`:
        # el índice único parcial se comprueba fila a fila, no al final de la
        # sentencia, así que una sola sentencia puede dejar dos filas en
        # `true` a la vez según el orden interno de Postgres.
        await session.execute(text("UPDATE theme_templates SET is_default = false"))
        await session.execute(
            text("UPDATE theme_templates SET is_default = true WHERE key = 'oscuro'")
        )
        await session.commit()


async def _superadmin_headers(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> dict[str, str]:
    await _hacer_superadmin(organizacion.owner_email)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    return cabeceras


# --- Lectura y permisos --------------------------------------------------


async def test_listar_plantillas_incluye_las_dos_sembradas(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    cabeceras = await _superadmin_headers(cliente, organizacion)
    respuesta = await cliente.get(ADMIN_THEME_TEMPLATES, headers=cabeceras)
    assert respuesta.status_code == 200
    claves = {plantilla["key"] for plantilla in respuesta.json()}
    assert {"oscuro", "claro"}.issubset(claves)
    oscuro = next(p for p in respuesta.json() if p["key"] == "oscuro")
    assert oscuro["is_default"] is True


async def test_endpoints_rechazan_a_quien_no_es_superadmin(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    assert (await cliente.get(ADMIN_THEME_TEMPLATES, headers=cabeceras)).status_code == 403
    assert (
        await cliente.post(
            ADMIN_THEME_TEMPLATES,
            headers=cabeceras,
            json={"key": "otra", "name": "Otra", "tokens": _tokens_validos()},
        )
    ).status_code == 403


# --- Alta -----------------------------------------------------------------


async def test_crear_plantilla_valida(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    cabeceras = await _superadmin_headers(cliente, organizacion)
    respuesta = await cliente.post(
        ADMIN_THEME_TEMPLATES,
        headers=cabeceras,
        json={"key": "prueba", "name": "Prueba", "tokens": _tokens_validos()},
    )
    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["key"] == "prueba"
    assert cuerpo["is_default"] is False


async def test_crear_plantilla_rechaza_token_desconocido(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    cabeceras = await _superadmin_headers(cliente, organizacion)
    tokens = _tokens_validos()
    tokens["dark"]["color-inventado"] = "#123456"

    respuesta = await cliente.post(
        ADMIN_THEME_TEMPLATES,
        headers=cabeceras,
        json={"key": "invalida", "name": "Inválida", "tokens": tokens},
    )
    assert respuesta.status_code == 422

    lista = await cliente.get(ADMIN_THEME_TEMPLATES, headers=cabeceras)
    assert "invalida" not in {p["key"] for p in lista.json()}


async def test_crear_plantilla_rechaza_token_faltante(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    cabeceras = await _superadmin_headers(cliente, organizacion)
    tokens = _tokens_validos()
    del tokens["light"]["accent"]

    respuesta = await cliente.post(
        ADMIN_THEME_TEMPLATES,
        headers=cabeceras,
        json={"key": "incompleta", "name": "Incompleta", "tokens": tokens},
    )
    assert respuesta.status_code == 422


async def test_crear_plantilla_rechaza_formato_de_color_invalido(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    cabeceras = await _superadmin_headers(cliente, organizacion)
    for valor_invalido in ("rebeccapurple", "rgb(0 255 0)", "var(--fg)", "#12345"):
        tokens = _tokens_validos()
        tokens["dark"]["fg"] = valor_invalido
        respuesta = await cliente.post(
            ADMIN_THEME_TEMPLATES,
            headers=cabeceras,
            json={"key": "formato-malo", "name": "Formato malo", "tokens": tokens},
        )
        assert respuesta.status_code == 422, valor_invalido


async def test_crear_plantilla_rechaza_contraste_insuficiente_y_no_crea_fila(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    cabeceras = await _superadmin_headers(cliente, organizacion)
    tokens = _tokens_validos()
    # `fg` casi idéntico a `bg`: contraste insuficiente en el par fg/bg.
    tokens["dark"]["fg"] = "#0a0a0a"

    respuesta = await cliente.post(
        ADMIN_THEME_TEMPLATES,
        headers=cabeceras,
        json={"key": "sin-contraste", "name": "Sin contraste", "tokens": tokens},
    )
    assert respuesta.status_code == 422
    detalle = respuesta.json()
    pares = detalle.get("errors", [])
    assert any(e["primero"] == "fg" and e["segundo"] == "bg" and e["modo"] == "dark" for e in pares)

    lista = await cliente.get(ADMIN_THEME_TEMPLATES, headers=cabeceras)
    assert "sin-contraste" not in {p["key"] for p in lista.json()}


async def test_crear_plantilla_rechaza_contraste_insuficiente_solo_en_modo_claro(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    """El modo oscuro válido no debe enmascarar un fallo que solo está en el claro."""
    cabeceras = await _superadmin_headers(cliente, organizacion)
    tokens = _tokens_validos()
    tokens["light"]["muted"] = "oklch(97% 0 0)"  # casi igual que `light.surface`

    respuesta = await cliente.post(
        ADMIN_THEME_TEMPLATES,
        headers=cabeceras,
        json={"key": "claro-roto", "name": "Claro roto", "tokens": tokens},
    )
    assert respuesta.status_code == 422
    pares = respuesta.json().get("errors", [])
    assert any(e["modo"] == "light" for e in pares)
    assert all(e["modo"] != "dark" for e in pares)


# --- Edición ---------------------------------------------------------------


async def test_editar_plantilla_marca_is_default_y_desmarca_la_anterior(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    cabeceras = await _superadmin_headers(cliente, organizacion)
    lista = (await cliente.get(ADMIN_THEME_TEMPLATES, headers=cabeceras)).json()
    claro = next(p for p in lista if p["key"] == "claro")
    oscuro = next(p for p in lista if p["key"] == "oscuro")

    respuesta = await cliente.patch(
        f"{ADMIN_THEME_TEMPLATES}/{claro['id']}", headers=cabeceras, json={"is_default": True}
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["is_default"] is True

    lista_tras = (await cliente.get(ADMIN_THEME_TEMPLATES, headers=cabeceras)).json()
    oscuro_tras = next(p for p in lista_tras if p["id"] == oscuro["id"])
    assert oscuro_tras["is_default"] is False


async def test_editar_plantilla_rechaza_contraste_insuficiente_y_no_modifica_la_fila(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    cabeceras = await _superadmin_headers(cliente, organizacion)
    lista = (await cliente.get(ADMIN_THEME_TEMPLATES, headers=cabeceras)).json()
    oscuro = next(p for p in lista if p["key"] == "oscuro")
    tokens_originales = oscuro["tokens"]

    tokens_rotos = copy.deepcopy(tokens_originales)
    tokens_rotos["dark"]["warn"] = tokens_rotos["dark"]["surface"]

    respuesta = await cliente.patch(
        f"{ADMIN_THEME_TEMPLATES}/{oscuro['id']}", headers=cabeceras, json={"tokens": tokens_rotos}
    )
    assert respuesta.status_code == 422

    tras = await cliente.get(ADMIN_THEME_TEMPLATES, headers=cabeceras)
    oscuro_tras = next(p for p in tras.json() if p["id"] == oscuro["id"])
    assert oscuro_tras["tokens"] == tokens_originales


async def test_editar_plantilla_con_id_inexistente_devuelve_404(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    cabeceras = await _superadmin_headers(cliente, organizacion)
    respuesta = await cliente.patch(
        f"{ADMIN_THEME_TEMPLATES}/00000000-0000-0000-0000-000000000000",
        headers=cabeceras,
        json={"name": "No existe"},
    )
    assert respuesta.status_code == 404


# --- Privilegios de base de datos -----------------------------------------


async def test_app_user_puede_leer_pero_no_escribir_theme_templates() -> None:
    from app.core.database import SessionApp

    async with SessionApp() as session, session.begin():
        filas = (await session.execute(text("SELECT id FROM theme_templates"))).all()
        assert len(filas) >= 2

    with pytest.raises(DBAPIError):
        async with SessionApp() as session, session.begin():
            await session.execute(
                text(
                    "INSERT INTO theme_templates (id, key, name, tokens, is_default) "
                    "VALUES (gen_random_uuid(), 'intruso', 'Intruso', '{}'::jsonb, false)"
                )
            )


# --- Migración -------------------------------------------------------------


def _correr_alembic(*comando: str) -> None:
    entorno = os.environ.copy()
    resultado = subprocess.run(  # noqa: S603 — argv fijo, sin entrada externa
        [sys.executable, "-m", "alembic", *comando],
        cwd=API_DIR,
        env=entorno,
        capture_output=True,
        text=True,
    )
    assert resultado.returncode == 0, resultado.stderr


async def _columnas_de_branding() -> set[str]:
    async with SessionMaintenance() as session:
        filas = await session.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'organization_branding'"
            )
        )
        return {fila[0] for fila in filas}


async def test_ciclo_de_migracion_0014_es_reversible_sin_tocar_otras_columnas() -> None:
    """El `downgrade` de `0014` retira `theme_template_id` sin tocar ninguna otra
    columna. Con `0015_retirada_colores_branding` ya encadenada detrás de `0014`,
    `downgrade -1` desde `head` desharía `0015` (que sí toca `colors`/`fonts`), no
    `0014`; por eso se baja primero explícitamente a la propia revisión `0014`
    antes de medir, para aislar el efecto de su downgrade del de `0015`."""
    _correr_alembic("downgrade", "0014_plantillas_de_tema")
    antes = await _columnas_de_branding()
    assert "theme_template_id" in antes

    _correr_alembic("downgrade", "0013_pagos_stripe_connect")
    despues_de_bajar = await _columnas_de_branding()
    assert "theme_template_id" not in despues_de_bajar
    assert despues_de_bajar == antes - {"theme_template_id"}

    _correr_alembic("upgrade", "head")
    restauradas = await _columnas_de_branding()
    assert "theme_template_id" in restauradas
    assert "colors" not in restauradas
    assert "fonts" not in restauradas


# --- Contraste (unitario, sin HTTP) ---------------------------------------


def test_las_plantillas_sembradas_pasan_la_validacion_de_contraste() -> None:
    for tokens in (_tokens_validos(), {"dark": _TOKENS_OSCURO, "light": _TOKENS_CLARO}):
        assert comprobar_contraste_de_plantilla(tokens) == []


def test_pares_criticos_no_esta_vacio() -> None:
    assert len(PARES_CRITICOS) == 7


@pytest.mark.parametrize(
    ("color_a", "color_b", "ratio_esperado"),
    [
        ("#ffffff", "#000000", 21.0),
        ("#00ff87", "#04140d", 14.09),
        ("oklch(94% 0.180 152.4)", "#000000", 16.82),
    ],
)
def test_parser_de_contraste_contra_tabla_de_valores_conocidos(
    color_a: str, color_b: str, ratio_esperado: float
) -> None:
    assert razon_de_contraste(color_a, color_b) == pytest.approx(ratio_esperado, abs=0.01)
