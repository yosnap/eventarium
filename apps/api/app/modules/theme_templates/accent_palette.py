"""Deriva la familia de acento de una plantilla (accent/accent-hi/accent-dim/
on-accent, en los dos modos) a partir de un único color elegido por el
organizador de un evento.

Mismo criterio de portabilidad que `contrast.py` respecto a `contrast.ts`:
esta conversión sRGB -> OKLCH es la dirección inversa de
`parse_oklch_color` (que ya vive en `contrast.py`), y un puerto directo de
`apps/web/src/app/core/theming/oklch.ts::componentesOklchDeHex` (misma
función, mismos coeficientes de Björn Ottosson) — los dos lados se prueban
contra el mismo fixture de casos conocidos
(`tests/fixtures/casos_paleta_acento.json`, fase 3 del plan «diseño del
evento») para que no diverjan.

La fórmula es una aproximación calibrada para funcionar con cualquier
matiz de entrada, no una réplica exacta del tema por defecto de la
plataforma (`tokens.css`): ese usa croma distinto entre `accent`/`accent-hi`
y entre modos, y `on-accent` no siempre es blanco/negro puro. Aquí se
prioriza una regla simple y verificable (mismo H/C en las cuatro
variantes, L fija por variante/modo, `on-accent` por el peor contraste
entre `accent` y `accent-hi`) sobre la fidelidad bit a bit a un caso
concreto.

`CROMA_MAXIMA` se fijó en 0.15, no en el 0.2286 del verde de referencia de
la plataforma: a croma más alto, varios matices (cian/verdes saturados)
producen colores fuera del gamut sRGB y pares `on-accent`/`accent-hi` por
debajo del mínimo AA (medido en el red-team de este plan: hasta 4.15:1 con
croma 0.23, bajo el 4.5:1 exigido). 0.15 se verifica en un barrido de 12
matices en `tests/modules/test_accent_palette.py`.
"""

from __future__ import annotations

import logging
import math
from typing import Any

from app.modules.theme_templates.contrast import parse_hex_color, razon_de_contraste

logger = logging.getLogger(__name__)

#: Por debajo de este croma el matiz no está perceptualmente definido:
#: blanco, negro y cualquier gris darían el mismo resultado sin aviso. Se
#: usa como umbral de rechazo en `schemas.py::validar_theme_overrides`.
UMBRAL_CROMA_MINIMO = 0.02

#: Ver docstring del módulo: por qué no el croma real de la plantilla de
#: referencia.
CROMA_MAXIMA = 0.15

L_OSCURO_ACCENT = 0.8761
L_OSCURO_ACCENT_HI = 0.94
L_CLARO_ACCENT = 0.45
L_CLARO_ACCENT_HI = 0.52


def hex_a_oklch(hex_color: str) -> tuple[float, float, float]:
    """`#rrggbb` -> `(L 0-1, C, H en grados)`.

    Dirección inversa de `contrast.py::parse_oklch_color`: sRGB -> sRGB
    lineal -> OKLab (coeficientes de Björn Ottosson) -> OKLCH.
    """
    rgb = parse_hex_color(hex_color)
    if rgb is None:
        # El formato ya se validó en schemas.py antes de llegar aquí: un
        # `None` aquí es un error de programación, no una entrada de
        # usuario (mismo criterio que `ColorNoParseableError` en
        # `contrast.py`).
        raise ValueError(f"«{hex_color}» no es un hex válido tras pasar la validación de formato.")

    def lineal(canal_0_255: float) -> float:
        proporcion = canal_0_255 / 255
        if proporcion <= 0.04045:
            return proporcion / 12.92
        return ((proporcion + 0.055) / 1.055) ** 2.4

    r, g, b = (lineal(canal) for canal in rgb)

    l_ = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m_ = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s_ = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)

    ele = 0.2104542553 * l_ + 0.793617785 * m_ - 0.0040720468 * s_
    a = 1.9779984951 * l_ - 2.428592205 * m_ + 0.4505937099 * s_
    b2 = 0.0259040371 * l_ + 0.7827717662 * m_ - 0.808675766 * s_

    croma = math.sqrt(a * a + b2 * b2)
    tono = math.degrees(math.atan2(b2, a)) % 360
    return ele, croma, tono


def _mejor_on_accent(accent: str, accent_hi: str) -> str:
    """Blanco o negro, el que cumpla mejor el PEOR de los dos contrastes
    (contra `accent` y contra `accent-hi` — este último es el fondo real
    del estado `:hover` de los botones, `apps/web/.../button.ts`)."""
    candidatos = ("#ffffff", "#000000")

    def peor_ratio(candidato: str) -> float:
        return min(razon_de_contraste(candidato, accent), razon_de_contraste(candidato, accent_hi))

    return max(candidatos, key=peor_ratio)


def derivar_paleta_de_acento(hex_color: str) -> dict[str, dict[str, str]]:
    """Deriva `{accent, accent-hi, accent-dim, on-accent}` para `dark` y
    `light` a partir de un único color hex.

    Se descarta la luminosidad (L) del color de entrada a propósito: fijar
    L por variante/modo es lo que garantiza el contraste mínimo AA
    independientemente de qué tan claro u oscuro sea el color que elija el
    organizador.
    """
    _, croma_bruto, tono = hex_a_oklch(hex_color)
    croma = min(croma_bruto, CROMA_MAXIMA)

    resultado: dict[str, dict[str, str]] = {}
    for modo, l_base, l_hi in (
        ("dark", L_OSCURO_ACCENT, L_OSCURO_ACCENT_HI),
        ("light", L_CLARO_ACCENT, L_CLARO_ACCENT_HI),
    ):
        accent = f"oklch({l_base * 100:.2f}% {croma:.4f} {tono:.2f})"
        accent_hi = f"oklch({l_hi * 100:.2f}% {croma:.4f} {tono:.2f})"
        resultado[modo] = {
            "accent": accent,
            "accent-hi": accent_hi,
            "accent-dim": accent.replace(")", " / 0.1)"),
            "on-accent": _mejor_on_accent(accent, accent_hi),
        }
    return resultado


def fusionar_overrides(
    tokens: dict[str, dict[str, str]], overrides: dict[str, Any]
) -> dict[str, dict[str, str]]:
    """Fusiona `theme_overrides` SOBRE una copia de `tokens` (nunca in-situ:
    ver docstring de `_tema_del_evento`, que es quien llama a esto).

    Si la derivación del acento falla (dato corrupto en BD que se saltó el
    validador de escritura), se ignora el override de acento y se
    devuelve la plantilla sin él — nunca se propaga la excepción: un tema
    roto no debe tumbar la página pública del evento. `overrides` mismo
    puede llegar corrupto (p. ej. una lista en vez de un dict, si se
    escribió por SQL directo saltándose `validar_theme_overrides`): se
    trata igual, degradando sin propagar."""
    resultado = {modo: dict(valores) for modo, valores in tokens.items()}
    if not isinstance(overrides, dict):
        logger.warning(
            "theme_overrides no es un dict (tipo=%s); se sirve la plantilla sin personalizar.",
            type(overrides).__name__,
        )
        return resultado
    if "accent" in overrides:
        try:
            paleta = derivar_paleta_de_acento(overrides["accent"])
        except (ValueError, TypeError, AttributeError):
            logger.warning(
                "No se pudo derivar la paleta de acento de theme_overrides=%r; "
                "se sirve la plantilla sin ese override.",
                overrides.get("accent"),
            )
            paleta = {}
        for modo in resultado:
            resultado[modo].update(paleta.get(modo, {}))
    for token in ("font-display", "font-body"):
        if token in overrides:
            for modo in resultado:
                resultado[modo][token] = overrides[token]
    return resultado
