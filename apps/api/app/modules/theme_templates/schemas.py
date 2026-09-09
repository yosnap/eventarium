"""Esquemas del catálogo de plantillas de tema.

`TOKENS_DE_PLANTILLA` es un contrato de dos lados con la lista equivalente
del cliente (`apps/web/src/app/core/theming/theme-template.model.ts`):
mismas 21 claves, documentado en la fase 6 del plan de UX/UI. Cubre las
familias de superficie, borde, texto, acento y señales, más el chrome
(`nav-bg`, `backdrop`, `shadow-md`, `shadow-lg`) — espaciado, radios,
tipografía y su escala siguen siendo de plataforma y no entran aquí.
"""

from __future__ import annotations

import re
from typing import Annotated, Any

from pydantic import BaseModel, Field, field_validator

MODOS_DE_PLANTILLA: tuple[str, str] = ("dark", "light")

TOKENS_DE_PLANTILLA: frozenset[str] = frozenset(
    {
        # Superficie.
        "bg",
        "surface",
        "surface-2",
        "surface-hi",
        # Borde.
        "border",
        "border-strong",
        # Texto.
        "fg",
        "muted",
        "faint",
        # Acento.
        "accent",
        "accent-hi",
        "accent-dim",
        "on-accent",
        # Señales.
        "warn",
        "warn-dim",
        "danger",
        "danger-dim",
        # Chrome.
        "nav-bg",
        "backdrop",
        "shadow-md",
        "shadow-lg",
    }
)

_HEX_6_RE = re.compile(r"^#[0-9a-f]{6}$", re.IGNORECASE)
# `L` exige `%`: contrato de dos lados con `PATRON_OKLCH` de
# `apps/web/src/app/core/theming/contrast.ts:39`, que también lo exige. Antes este
# regex aceptaba `L` sin `%`, así que un token que pasaba aquí podía fallar en
# silencio al aplicarse en cliente.
_OKLCH_RE = re.compile(
    r"^oklch\(\s*[0-9.]+%\s+[0-9.]+\s+[0-9.]+\s*(?:/\s*[0-9.]+%?\s*)?\)$",
    re.IGNORECASE,
)
# `--shadow-md`/`--shadow-lg` no son un color suelto: son un `box-shadow` completo con
# un color oklch/hex embebido (ver `tokens.css` y `apply-tokens.ts:TOKENS_DE_SOMBRA`).
# Exigir que la cadena ENTERA sea solo un color los rechazaría siempre con 422.
TOKENS_DE_SOMBRA: frozenset[str] = frozenset({"shadow-md", "shadow-lg"})
_SOMBRA_CON_COLOR_RE = re.compile(
    r"oklch\(\s*[0-9.]+%\s+[0-9.]+\s+[0-9.]+\s*(?:/\s*[0-9.]+%?\s*)?\)|#[0-9a-f]{6}",
    re.IGNORECASE,
)


def es_formato_de_color_valido(valor: str) -> bool:
    """Hex de 6 dígitos u `oklch(...)`, los dos formatos que entiende `contrast.py`."""
    valor_limpio = valor.strip()
    return bool(_HEX_6_RE.match(valor_limpio) or _OKLCH_RE.match(valor_limpio))


def es_formato_de_sombra_valido(valor: str) -> bool:
    """`box-shadow` completo con un color oklch/hex embebido en algún punto de la
    cadena (p. ej. `0 4px 12px oklch(0% 0 0 / 0.35)`), no un color suelto."""
    return bool(_SOMBRA_CON_COLOR_RE.search(valor.strip()))


def validar_tokens_de_plantilla(tokens: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Valida la forma completa de `tokens`: dos modos, lista blanca cerrada y
    formato de color admitido en cada valor. Lanza `ValueError` con el primer
    problema encontrado (Pydantic lo traduce a 422)."""
    claves_de_modo = set(tokens.keys())
    if claves_de_modo != set(MODOS_DE_PLANTILLA):
        raise ValueError(
            f"«tokens» debe declarar exactamente los modos {MODOS_DE_PLANTILLA}, "
            f"y llegaron: {sorted(claves_de_modo)}."
        )

    for modo in MODOS_DE_PLANTILLA:
        valores = tokens[modo]
        if not isinstance(valores, dict):
            raise ValueError(f"El modo «{modo}» debe ser un objeto de token → color.")

        claves = set(valores.keys())
        faltantes = TOKENS_DE_PLANTILLA - claves
        desconocidas = claves - TOKENS_DE_PLANTILLA
        if faltantes:
            raise ValueError(f"Faltan tokens en el modo «{modo}»: {sorted(faltantes)}.")
        if desconocidas:
            raise ValueError(f"Tokens desconocidos en el modo «{modo}»: {sorted(desconocidas)}.")

        for token, valor in valores.items():
            if not isinstance(valor, str):
                raise ValueError(
                    f"El token «{token}» del modo «{modo}» debe ser una cadena de texto."
                )
            if token in TOKENS_DE_SOMBRA:
                if not es_formato_de_sombra_valido(valor):
                    raise ValueError(
                        f"El token «{token}» del modo «{modo}» tiene un formato de "
                        f"box-shadow no admitido: «{valor}». Se espera un box-shadow "
                        "completo con un color hex u oklch(...) embebido."
                    )
            elif not es_formato_de_color_valido(valor):
                raise ValueError(
                    f"El token «{token}» del modo «{modo}» tiene un formato de color no "
                    f"admitido: «{valor}». Se admite hex de 6 dígitos u oklch(...)."
                )

    return tokens


class ThemeTemplateCreate(BaseModel):
    """Alta de una plantilla de tema."""

    key: Annotated[str, Field(min_length=1, max_length=40, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")]
    name: Annotated[str, Field(min_length=1, max_length=80)]
    tokens: dict[str, Any]
    is_default: bool = False

    @field_validator("tokens")
    @classmethod
    def _validar_tokens(cls, valor: dict[str, Any]) -> dict[str, dict[str, str]]:
        return validar_tokens_de_plantilla(valor)


class ThemeTemplateUpdate(BaseModel):
    """Edición de `name`, `tokens` e `is_default`. No se puede cambiar `key`."""

    name: Annotated[str, Field(min_length=1, max_length=80)] | None = None
    tokens: dict[str, Any] | None = None
    is_default: bool | None = None

    @field_validator("tokens")
    @classmethod
    def _validar_tokens(cls, valor: dict[str, Any] | None) -> dict[str, dict[str, str]] | None:
        if valor is None:
            return None
        return validar_tokens_de_plantilla(valor)


class ThemeTemplateResponse(BaseModel):
    """Una plantilla tal y como la ve la superadministración."""

    id: str
    key: str
    name: str
    tokens: dict[str, dict[str, str]]
    is_default: bool


class ThemeTemplateCatalogItem(BaseModel):
    """Una plantilla tal y como la ve el catálogo del panel de la organización."""

    id: str
    key: str
    name: str
    tokens: dict[str, dict[str, str]]


class ContrasteInsuficienteDetalle(BaseModel):
    """Un par crítico incumplido, tal y como se enumera en el 422."""

    primero: str
    segundo: str
    modo: str
    ratio: float
