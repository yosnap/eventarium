"""Campos de idioma de las respuestas públicas con contenido del organizador."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.core.locale import DEFAULT_LOCALE, Locale


class ContentLocaleInfo(BaseModel):
    """En qué idioma se sirve el contenido y en cuáles está al día.

    La web usa `source_locale` y `up_to_date_locales` para decidir `canonical`
    y `hreflang` de la página, y `served_locale` para avisar cuando el contenido
    se muestra en el idioma original.
    """

    source_locale: Locale = DEFAULT_LOCALE
    up_to_date_locales: list[Locale] = Field(default_factory=lambda: [DEFAULT_LOCALE])
    served_locale: Locale = DEFAULT_LOCALE
    # Campos que se muestran en el original porque falta su traducción.
    pending_fields: int = 0


class TranslationItem(BaseModel):
    """Un texto traducible tal como lo ve el panel."""

    entity_type: str
    entity_id: str
    field: str
    original: str
    value: str | None = None
    origin: Literal["ia", "manual", "revisada"] | None = None
    # `pendiente`: sin traducción; `desactualizada`: hecha sobre otro original.
    status: Literal["al_dia", "desactualizada", "pendiente"]


class TranslationEditor(BaseModel):
    """Los textos de una entidad en un idioma, para su pestaña del formulario."""

    locale: Locale
    source_locale: Locale
    # Idiomas en que publica la organización: sin un segundo idioma no hay pestañas.
    locales: list[Locale]
    items: list[TranslationItem]
    # La organización tiene clave de IA propia: sin ella no hay traducción automática.
    auto_translation_available: bool = False


class TranslationInput(BaseModel):
    entity_type: str = Field(max_length=30)
    entity_id: str = Field(max_length=36)
    field: str = Field(max_length=200)
    # Vacío o `None` borra la traducción: el campo vuelve a mostrarse en el original.
    value: str | None = Field(default=None, max_length=50_000)


class TranslationSave(BaseModel):
    items: list[TranslationInput] = Field(max_length=500)


class TranslationReview(BaseModel):
    entity_type: str = Field(max_length=30)
    entity_id: str = Field(max_length=36)
    field: str = Field(max_length=200)
    # El original que vio quien revisa: si ya no es el actual, 409.
    original: str | None = Field(default=None, max_length=50_000)


class LocaleProgress(BaseModel):
    locale: Locale
    total: int
    up_to_date: int


class EventTranslationSummary(BaseModel):
    """«Inglés: 12/14 campos al día» en la ficha del evento."""

    source_locale: Locale
    locales: list[LocaleProgress]
    auto_translation_available: bool = False


class PublishedTranslationEstimate(BaseModel):
    """Lo que costaría traducir ahora los eventos publicados a un idioma."""

    events: int
    texts: int
    # Orientativo; `None` si no hay clave propia de IA.
    estimated_cost_usd: str | None
    auto_translation_available: bool


class PublishedTranslationQueued(BaseModel):
    events: int
