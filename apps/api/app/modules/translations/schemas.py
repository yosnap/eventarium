"""Campos de idioma de las respuestas públicas con contenido del organizador."""

from __future__ import annotations

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
