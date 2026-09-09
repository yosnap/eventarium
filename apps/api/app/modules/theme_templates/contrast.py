"""Cálculo de contraste según WCAG 2.1, puerto directo de
`apps/web/src/app/core/theming/contrast.ts`.

Decisión A de la sesión 3 de validación del plan de UX/UI: el bloqueo por
contraste no puede vivir solo en el cliente, porque lo que se guarda en el
catálogo de plantillas lo ve cada visitante de cada organización que la
elija. Este módulo reproduce, en Python, exactamente el mismo cálculo que
`contrast.ts`: mismo umbral, mismos coeficientes de luminancia, mismo parser
hexadecimal y el mismo parser `oklch()` (oklch → oklab → sRGB lineal →
sRGB). Los dos lados se prueban contra la misma tabla de valores conocidos
(ver `tests/modules/test_theme_templates.py`) para que no diverjan.

Un color que no se pueda parsear nunca es un `None` descartado en silencio:
el backend ya rechaza por formato antes de llegar aquí (lista blanca +
`_es_formato_de_color_valido` en `schemas.py`), así que un color no
parseable en este punto significa que los dos controles discrepan entre sí.
Se falla ruidosamente con `ColorNoParseableError`.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

# Mínimo exigido por WCAG 2.1 AA para texto normal. Espejo de `contrast.ts:9`.
CONTRASTE_MINIMO_AA = 4.5

# Pares de tokens que deben ser legibles juntos, en los dos modos de cada
# plantilla. Contrato de dos lados con `PARES_CRITICOS` de
# `apps/web/src/app/core/theming/contrast.ts`: si diverge, el test de
# `tests/modules/test_theme_templates.py` que compara ambas listas falla.
PARES_CRITICOS: tuple[tuple[str, str], ...] = (
    ("fg", "bg"),
    ("fg", "surface"),
    ("muted", "surface"),
    ("on-accent", "accent"),
    ("fg", "surface-2"),
    ("danger", "surface"),
    ("warn", "surface"),
)

_HEX_RE = re.compile(r"^[0-9a-f]{3}$|^[0-9a-f]{6}$", re.IGNORECASE)
_OKLCH_RE = re.compile(
    r"^oklch\(\s*([0-9.]+)(%)?\s+([0-9.]+)\s+([0-9.]+)\s*(?:/\s*[0-9.]+%?\s*)?\)$",
    re.IGNORECASE,
)


class ColorNoParseableError(ValueError):
    """Un color con formato en principio admitido no se ha podido convertir a RGB.

    Solo puede ocurrir si la validación de formato de `schemas.py` y este
    parser discrepan entre sí: un fallo real de programación, no una entrada
    de usuario mal formada (esa ya se rechazó antes con 422).
    """


def _canal_lineal(valor_0_255: float) -> float:
    proporcion = valor_0_255 / 255
    return (
        proporcion / 12.92 if proporcion <= 0.03928 else ((proporcion + 0.055) / 1.055) ** 2.4
    )


def parse_hex_color(color: str) -> tuple[float, float, float] | None:
    """Convierte `#rgb` o `#rrggbb` a componentes 0-255. `None` si no es hex válido."""
    limpio = color.strip().removeprefix("#")
    if not _HEX_RE.match(limpio):
        return None
    expandido = "".join(c * 2 for c in limpio) if len(limpio) == 3 else limpio
    return (
        int(expandido[0:2], 16),
        int(expandido[2:4], 16),
        int(expandido[4:6], 16),
    )


def parse_oklch_color(color: str) -> tuple[float, float, float] | None:
    """Convierte `oklch(L C H)` (con `%` opcional en `L` y canal alfa opcional) a
    componentes sRGB 0-255. `None` si no encaja con el formato.

    Conversión: oklch → oklab → sRGB lineal → sRGB, idéntica a la que usa
    `apps/web/src/app/core/theming/contrast.ts`.
    """
    coincidencia = _OKLCH_RE.match(color.strip())
    if coincidencia is None:
        return None

    l_bruto, es_porcentaje, c_bruto, h_bruto = coincidencia.groups()
    ele = float(l_bruto) / 100 if es_porcentaje else float(l_bruto)
    croma = float(c_bruto)
    tono_rad = math.radians(float(h_bruto))

    a = croma * math.cos(tono_rad)
    b = croma * math.sin(tono_rad)

    l_ = ele + 0.3963377774 * a + 0.2158037573 * b
    m_ = ele - 0.1055613458 * a - 0.0638541728 * b
    s_ = ele - 0.0894841775 * a - 1.2914855480 * b

    ele_cubo = l_**3
    m_cubo = m_**3
    s_cubo = s_**3

    r_lineal = 4.0767416621 * ele_cubo - 3.3077115913 * m_cubo + 0.2309699292 * s_cubo
    g_lineal = -1.2684380046 * ele_cubo + 2.6097574011 * m_cubo - 0.3413193965 * s_cubo
    b_lineal = -0.0041960863 * ele_cubo - 0.7034186147 * m_cubo + 1.7076147010 * s_cubo

    def _codificar_srgb(componente_lineal: float) -> float:
        recortado = min(max(componente_lineal, 0.0), 1.0)
        codificado = (
            12.92 * recortado
            if recortado <= 0.0031308
            else 1.055 * (recortado ** (1 / 2.4)) - 0.055
        )
        return round(codificado * 255, 6)

    return (
        _codificar_srgb(r_lineal),
        _codificar_srgb(g_lineal),
        _codificar_srgb(b_lineal),
    )


def parse_color(color: str) -> tuple[float, float, float] | None:
    """Intenta hex y luego `oklch()`. `None` si ninguno de los dos encaja."""
    return parse_hex_color(color) if color.strip().startswith("#") else parse_oklch_color(color)


def luminancia_relativa(color: str) -> float | None:
    """Luminancia relativa WCAG. `None` si el color no se puede parsear."""
    rgb = parse_color(color)
    if rgb is None:
        return None
    r, g, b = (_canal_lineal(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def razon_de_contraste(primero: str, segundo: str) -> float:
    """Razón de contraste WCAG entre dos colores (de 1:1 a 21:1).

    A diferencia de `contrast.ts` (que devuelve `null` con cualquier valor no
    parseable, pensado para un aviso silencioso en el editor), esta función
    **falla ruidosamente**: en el backend, llegar aquí con un color no
    parseable significa que la validación de formato ya debería haberlo
    rechazado con 422, así que es un error de programación, no una entrada
    inválida más.
    """
    l_primero = luminancia_relativa(primero)
    l_segundo = luminancia_relativa(segundo)
    if l_primero is None or l_segundo is None:
        no_parseable = primero if l_primero is None else segundo
        raise ColorNoParseableError(
            f"El color «{no_parseable}» pasó la validación de formato pero no se pudo "
            "convertir a RGB; revisa que schemas.py y contrast.py acepten el mismo formato."
        )
    claro = max(l_primero, l_segundo)
    oscuro = min(l_primero, l_segundo)
    return (claro + 0.05) / (oscuro + 0.05)


@dataclass(frozen=True, slots=True)
class IncumplimientoDeContraste:
    """Un par crítico que no llega al mínimo AA, en un modo concreto."""

    primero: str
    segundo: str
    modo: str
    ratio: float


def comprobar_contraste_de_plantilla(
    tokens: dict[str, dict[str, str]],
) -> list[IncumplimientoDeContraste]:
    """Evalúa `PARES_CRITICOS` en los modos `dark` y `light` de `tokens`.

    Devuelve la lista (posiblemente vacía) de pares que no llegan a
    `CONTRASTE_MINIMO_AA`. No valida la lista blanca de tokens ni su formato:
    eso ya lo hace `schemas.py` antes de llegar aquí.
    """
    incumplimientos: list[IncumplimientoDeContraste] = []
    for modo in ("dark", "light"):
        valores = tokens.get(modo, {})
        for primero, segundo in PARES_CRITICOS:
            if primero not in valores or segundo not in valores:
                continue
            ratio = razon_de_contraste(valores[primero], valores[segundo])
            if ratio < CONTRASTE_MINIMO_AA:
                incumplimientos.append(
                    IncumplimientoDeContraste(
                        primero=primero,
                        segundo=segundo,
                        modo=modo,
                        ratio=round(ratio, 2),
                    )
                )
    return incumplimientos
