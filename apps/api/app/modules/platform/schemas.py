"""Esquemas de la identidad y las páginas legales de la plataforma."""

from __future__ import annotations

from typing import Annotated, Any, Literal

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
            raise ValueError("El idioma por defecto no se puede desactivar.")
        # Sin duplicados y en el orden del catálogo.
        return [locale for locale in LOCALES if locale in valor]


class PlatformLegalTranslation(BaseModel):
    """La versión traducida guardada de una página, aunque no se sirva (para el
    editor del superadmin)."""

    content: str | None
    origin: str | None = Field(description="`ia`, `manual` o `revisada`.")
    status: str | None = Field(
        description=(
            "`al_dia` (se sirve), `desactualizada` (escrita a mano para un español que ya "
            "cambió), `pendiente`, `en_curso` o `error`."
        )
    )


class PlatformLegalPageItem(BaseModel):
    """Una página legal de plataforma, con su contenido efectivo."""

    content: str
    is_custom: bool = Field(
        description="`true` si el admin ha editado esta página en el idioma pedido."
    )
    served_locale: Locale = Field(
        default="es-ES",
        description=(
            "Idioma del texto servido. Si se pidió otro y no hay versión escrita a mano, "
            "es `es-ES` y la web muestra el aviso de contenido original."
        ),
    )
    available_locales: list[Locale] = Field(
        default_factory=lambda: [DEFAULT_LOCALE],
        description=(
            "Idiomas que se anuncian a los buscadores: el español y las versiones escritas o "
            "revisadas a mano que están al día."
        ),
    )
    machine_translated: bool = Field(
        default=False,
        description="El texto servido es una traducción automática sin revisar.",
    )
    translation: PlatformLegalTranslation | None = Field(
        default=None,
        description="La versión guardada en el idioma pedido (para el editor).",
    )


class PlatformLegalPageReview(BaseModel):
    """Qué versión traducida se marca como revisada."""

    page: Literal["legal_notice", "privacy_policy", "cookies_policy", "registration_terms"]
    locale: Locale
    content: Annotated[str, Field(max_length=20_000)] = Field(
        description="El texto que se confirma, tal como lo ve el superadmin."
    )


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
    locale: Locale = Field(
        default=DEFAULT_LOCALE,
        description=(
            "Idioma de la versión que se edita. En otro idioma, un texto la guarda como "
            "escrita a mano; `null` la devuelve a la traducción automática."
        ),
    )
