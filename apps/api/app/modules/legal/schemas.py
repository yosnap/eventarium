"""Esquemas del módulo legal: páginas legales y consentimiento de cookies."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.core.locale import DEFAULT_LOCALE, Locale

# Categorías válidas del banner de cookies. `necessary` siempre presente: el
# propio banner no permite rechazarla porque no es rastreo, es lo mínimo para
# que la web funcione (decisión #3 del plan, `cookie_consents` es anónimo).
CookieCategory = Literal["necessary", "analytics", "marketing"]


class LegalPageResponse(BaseModel):
    """Contenido efectivo (editado o de plantilla) de una página legal."""

    content: str
    served_locale: Locale = Field(
        default=DEFAULT_LOCALE,
        description="Idioma del texto servido: `es-ES` si no hay versión en el idioma pedido.",
    )
    available_locales: list[Locale] = Field(
        default_factory=lambda: [DEFAULT_LOCALE],
        description="Idiomas con versión propia: los que la página anuncia a los buscadores.",
    )


class CookieConsentCreate(BaseModel):
    """Decisión del banner de cookies a registrar."""

    categories: Annotated[list[CookieCategory], Field(min_length=1)]
