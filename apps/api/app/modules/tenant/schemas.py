"""Esquemas públicos del tenant (los consume el frontend en el arranque)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ResolvedTheme(BaseModel):
    """La plantilla de tema de la plataforma, ya resuelta.

    Resolución: `COALESCE(platform_branding.theme_template_id, la que tiene
    is_default)`. `None` si por lo que sea no hubiera ninguna plantilla en el
    catálogo — defensa para que el cliente se quede con la base de
    `tokens.css` en vez de romper.
    """

    id: str
    key: str
    name: str
    tokens: dict[str, dict[str, str]]
    # Modo de apertura de la plantilla ('dark' | 'light'), para el fallback del
    # conmutador cuando el visitante aún no ha elegido.
    default_mode: str


class PlatformBrandingBlock(BaseModel):
    """Identidad de la plataforma: la única marca del chrome de la web pública.

    Eventarium es una SaaS centralizada (modelo Luma): sin dominio por
    organización, no hay ninguna identidad "del host visitado" distinta de
    esta — solo la de la instalación.
    """

    name: str
    logo_url: str | None = None
    favicon_url: str | None = None
    social_links: list[dict[str, object]] = Field(default_factory=list)
    theme_template_id: str | None = None
    theme: ResolvedTheme | None = None


class BrandingResponse(BaseModel):
    """Identidad visual de la instalación."""

    platform: PlatformBrandingBlock
