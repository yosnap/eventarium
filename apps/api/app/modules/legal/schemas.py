"""Esquemas del módulo legal: páginas legales y consentimiento de cookies."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

# Categorías válidas del banner de cookies. `necessary` siempre presente: el
# propio banner no permite rechazarla porque no es rastreo, es lo mínimo para
# que la web funcione (decisión #3 del plan, `cookie_consents` es anónimo).
CookieCategory = Literal["necessary", "analytics", "marketing"]


class LegalPageResponse(BaseModel):
    """Contenido efectivo (editado o de plantilla) de una página legal."""

    content: str


class LegalPageAdminItem(BaseModel):
    """Una página legal tal y como la ve el panel de edición."""

    content: str
    is_custom: bool = Field(description="`true` si la organización ha editado esta página.")


class LegalPagesAdminResponse(BaseModel):
    """Las cuatro páginas legales, con su contenido efectivo y si están editadas."""

    legal_notice: LegalPageAdminItem
    privacy_policy: LegalPageAdminItem
    cookies_policy: LegalPageAdminItem
    registration_terms: LegalPageAdminItem


class LegalPagesUpdate(BaseModel):
    """Actualización parcial de las páginas legales.

    Mismo patrón que `OrganizationUpdate`: un campo ausente no se toca: un
    campo presente con valor `null` restaura la plantilla por defecto (ver
    `Organization.legal_notice_content` y hermanos, `NULL` = plantilla).
    """

    legal_notice_content: Annotated[str, Field(max_length=20_000)] | None = None
    privacy_policy_content: Annotated[str, Field(max_length=20_000)] | None = None
    cookies_policy_content: Annotated[str, Field(max_length=20_000)] | None = None
    registration_terms_content: Annotated[str, Field(max_length=20_000)] | None = None


class CookieConsentCreate(BaseModel):
    """Decisión del banner de cookies a registrar."""

    categories: Annotated[list[CookieCategory], Field(min_length=1)]
