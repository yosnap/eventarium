"""Derivación de la familia de acento a partir de un único color
(`app/modules/theme_templates/accent_palette.py`).

Fase 1 del plan «diseño del evento». No es una réplica exacta del tema por
defecto de la plataforma (ver docstring del módulo bajo prueba): el
criterio de éxito es que el matiz se conserve y que `on-accent` cumpla el
mínimo AA contra `accent` Y `accent-hi`, en un barrido de matices — no la
igualdad bit a bit con `tokens.css`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.modules.theme_templates.accent_palette import (
    CROMA_MAXIMA,
    UMBRAL_CROMA_MINIMO,
    derivar_paleta_de_acento,
    fusionar_overrides,
    hex_a_oklch,
)
from app.modules.theme_templates.contrast import razon_de_contraste

CONTRASTE_MINIMO_AA = 4.5

# Fixture única compartida con el lado TypeScript
# (`accent-palette.spec.ts`) — red de seguridad contra una divergencia
# futura entre las dos implementaciones de la fórmula, no la fuente de
# verdad de la fórmula en sí (ver docstring del módulo bajo prueba).
RUTA_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "casos_paleta_acento.json"
FIXTURE = json.loads(RUTA_FIXTURE.read_text(encoding="utf-8"))

MATICES_DE_PRUEBA: tuple[str, ...] = tuple(caso["hex"] for caso in FIXTURE["matices"])
COLORES_ACROMATICOS: tuple[str, ...] = tuple(caso["hex"] for caso in FIXTURE["acromaticos"])


@pytest.mark.parametrize("hex_color", MATICES_DE_PRUEBA)
def test_on_accent_cumple_aa_contra_accent_y_accent_hi(hex_color: str) -> None:
    paleta = derivar_paleta_de_acento(hex_color)
    for modo in ("dark", "light"):
        valores = paleta[modo]
        ratio_accent = razon_de_contraste(valores["on-accent"], valores["accent"])
        ratio_accent_hi = razon_de_contraste(valores["on-accent"], valores["accent-hi"])
        assert ratio_accent >= CONTRASTE_MINIMO_AA, (
            f"{hex_color} modo {modo}: on-accent/accent = {ratio_accent:.2f}"
        )
        assert ratio_accent_hi >= CONTRASTE_MINIMO_AA, (
            f"{hex_color} modo {modo}: on-accent/accent-hi = {ratio_accent_hi:.2f}"
        )


@pytest.mark.parametrize("hex_color", MATICES_DE_PRUEBA)
def test_conserva_el_matiz_de_entrada(hex_color: str) -> None:
    _, _, tono_entrada = hex_a_oklch(hex_color)
    paleta = derivar_paleta_de_acento(hex_color)
    # El H se extrae del propio accent devuelto (formato "oklch(L% C H)").
    tono_salida = float(paleta["dark"]["accent"].split()[-1].rstrip(")"))
    assert abs(tono_salida - tono_entrada) < 0.1


@pytest.mark.parametrize("caso", FIXTURE["matices"], ids=lambda caso: caso["hex"])
def test_fixture_compartido_hue_esperado(caso: dict) -> None:
    _, _, tono = hex_a_oklch(caso["hex"])
    assert abs(tono - caso["h_esperado"]) < caso["tolerancia_h"]


@pytest.mark.parametrize("caso", FIXTURE["matices"], ids=lambda caso: caso["hex"])
def test_fixture_compartido_on_accent_esperado(caso: dict) -> None:
    paleta = derivar_paleta_de_acento(caso["hex"])
    for modo in ("dark", "light"):
        assert paleta[modo]["on-accent"] == caso["on_accent"][modo]


def test_croma_se_clampa_a_croma_maxima() -> None:
    # #00ff00 es croma muy alto en OKLCH; el resultado nunca debe superarlo.
    paleta = derivar_paleta_de_acento("#00ff00")
    croma_salida = float(paleta["dark"]["accent"].split()[1])
    assert croma_salida <= CROMA_MAXIMA + 1e-9


def test_caso_de_referencia_verde_plataforma_conserva_hue() -> None:
    """No exige igualdad con tokens.css (ver docstring del módulo) — solo que
    el matiz del verde de referencia (H≈152.4) se conserve razonablemente."""
    _, _, tono = hex_a_oklch("#00ff87")
    assert 145 < tono < 160


@pytest.mark.parametrize("hex_color", COLORES_ACROMATICOS)
def test_colores_acromaticos_bajo_el_umbral(hex_color: str) -> None:
    _, croma, _ = hex_a_oklch(hex_color)
    assert croma < UMBRAL_CROMA_MINIMO


def test_fusionar_overrides_no_muta_el_diccionario_original() -> None:
    tokens_originales = {
        "dark": {"accent": "oklch(50% 0.1 100)", "fg": "#ffffff"},
        "light": {"accent": "oklch(50% 0.1 100)", "fg": "#000000"},
    }
    tokens_copia_de_control = {modo: dict(valores) for modo, valores in tokens_originales.items()}

    fusionar_overrides(tokens_originales, {"accent": "#22c55e"})

    assert tokens_originales == tokens_copia_de_control, (
        "fusionar_overrides no debe mutar el diccionario de tokens recibido"
    )


def test_fusionar_overrides_degrada_ante_accent_no_parseable() -> None:
    """Un dato corrupto en BD (saltándose el validador de escritura) no debe
    propagar la excepción: se sirve la plantilla sin ese override."""
    tokens = {"dark": {"accent": "oklch(50% 0.1 100)"}, "light": {"accent": "oklch(50% 0.1 100)"}}
    resultado = fusionar_overrides(tokens, {"accent": "no-es-un-color"})
    assert resultado["dark"]["accent"] == "oklch(50% 0.1 100)"


def test_fusionar_overrides_aplica_fuentes_a_los_dos_modos() -> None:
    tokens = {"dark": {"font-display": "Bebas Neue"}, "light": {"font-display": "Bebas Neue"}}
    resultado = fusionar_overrides(tokens, {"font-display": "Oswald"})
    assert resultado["dark"]["font-display"] == "Oswald"
    assert resultado["light"]["font-display"] == "Oswald"


def test_fusionar_overrides_dos_llamadas_consecutivas_no_se_pisan() -> None:
    """Simula dos eventos que comparten la misma plantilla (mismo dict de
    tokens en memoria) y personalizan un acento distinto cada uno: el
    resultado de la primera llamada no debe cambiar tras la segunda."""
    tokens_compartidos = {
        "dark": {"accent": "oklch(50% 0.1 100)", "fg": "#ffffff"},
        "light": {"accent": "oklch(50% 0.1 100)", "fg": "#000000"},
    }

    resultado_evento_1 = fusionar_overrides(tokens_compartidos, {"accent": "#22c55e"})
    accent_evento_1_antes = resultado_evento_1["dark"]["accent"]

    resultado_evento_2 = fusionar_overrides(tokens_compartidos, {"accent": "#3b82f6"})

    assert resultado_evento_1["dark"]["accent"] == accent_evento_1_antes
    assert resultado_evento_1["dark"]["accent"] != resultado_evento_2["dark"]["accent"]
    assert tokens_compartidos["dark"]["accent"] == "oklch(50% 0.1 100)"


def test_fusionar_overrides_degrada_si_overrides_no_es_un_dict() -> None:
    """`theme_overrides` corrupto en BD (p. ej. una lista, escrito por SQL
    directo saltándose el validador) no debe tumbar la página pública."""
    tokens = {"dark": {"accent": "oklch(50% 0.1 100)"}, "light": {"accent": "oklch(50% 0.1 100)"}}
    resultado = fusionar_overrides(tokens, ["accent", "x"])  # type: ignore[arg-type]
    assert resultado["dark"]["accent"] == "oklch(50% 0.1 100)"


def test_fusionar_overrides_degrada_ante_accent_no_string() -> None:
    """Un `accent` corrupto que no sea ni siquiera una cadena (p. ej. un
    dict anidado) no debe propagar un `AttributeError` sin capturar."""
    tokens = {"dark": {"accent": "oklch(50% 0.1 100)"}, "light": {"accent": "oklch(50% 0.1 100)"}}
    resultado = fusionar_overrides(tokens, {"accent": {"no": "es un str"}})
    assert resultado["dark"]["accent"] == "oklch(50% 0.1 100)"
