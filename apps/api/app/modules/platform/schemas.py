"""Esquemas de la identidad y las páginas legales de la plataforma."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, Field, field_validator

from app.core.locale import DEFAULT_LOCALE, LOCALES, Locale


class ThemeResolved(BaseModel):
    """Plantilla de tema efectiva del chrome de plataforma."""

    id: str
    key: str
    name: str
    tokens: dict[str, Any]
    # El modo con el que abre quien no ha elegido todavía (cookie de tema ausente).
    default_mode: str


class PlatformBrandingResponse(BaseModel):
    """Identidad de la plataforma tal y como la consume el endpoint público."""

    name: str
    logo_url: str | None = None
    favicon_url: str | None = None
    social_links: list[dict[str, Any]] = Field(default_factory=list)
    theme_template_id: str | None = None
    theme: ThemeResolved | None = None
    enabled_locales: list[Locale] = Field(default_factory=lambda: list(LOCALES))
    language_switcher_visible: bool = True


class PlatformBrandingUpdate(BaseModel):
    """Actualización de la identidad de plataforma.

    Todos los campos son opcionales: un campo ausente no se toca. `social_links`
    se reemplaza entero cuando viene (mismo contrato que `BrandingUpdate` de
    organización); `None` lo vacía.
    """

    name: Annotated[str, Field(min_length=1, max_length=160)] | None = None
    social_links: list[dict[str, Any]] | None = None
    theme_template_id: str | None = None
    # Idiomas que ofrece la web pública. El de por defecto no se puede quitar.
    enabled_locales: list[Locale] | None = None
    language_switcher_visible: bool | None = None

    @field_validator("enabled_locales")
    @classmethod
    def _incluye_el_idioma_por_defecto(cls, valor: list[Locale] | None) -> list[Locale] | None:
        if valor is None:
            return None
        if DEFAULT_LOCALE not in valor:
            raise ValueError(f"El idioma por defecto ({DEFAULT_LOCALE}) no se puede desactivar.")
        # Sin duplicados y en el orden del catálogo.
        return [locale for locale in LOCALES if locale in valor]


class PlatformLegalPageItem(BaseModel):
    """Una página legal de plataforma, con su contenido efectivo."""

    content: str
    is_custom: bool = Field(description="`true` si el admin ha editado esta página.")


class PlatformLegalPagesResponse(BaseModel):
    """Las cuatro páginas legales de la plataforma."""

    legal_notice: PlatformLegalPageItem
    privacy_policy: PlatformLegalPageItem
    cookies_policy: PlatformLegalPageItem
    registration_terms: PlatformLegalPageItem


class PlatformLegalPagesUpdate(BaseModel):
    """Actualización parcial de las páginas legales de plataforma.

    Un campo ausente no se toca; presente con `null` restaura la plantilla
    por defecto.
    """

    legal_notice_content: Annotated[str, Field(max_length=20_000)] | None = None
    privacy_policy_content: Annotated[str, Field(max_length=20_000)] | None = None
    cookies_policy_content: Annotated[str, Field(max_length=20_000)] | None = None
    registration_terms_content: Annotated[str, Field(max_length=20_000)] | None = None
