"""Esquemas públicos del tenant (los consume el frontend en el arranque)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SocialLink(BaseModel):
    """Enlace a una red social del organizador."""

    kind: str = Field(description="Identificador de la red: x, linkedin, instagram…")
    url: str


class ResolvedTheme(BaseModel):
    """La plantilla de tema de la organización, ya resuelta.

    Resolución: `COALESCE(branding.theme_template_id, la que tiene
    is_default)`, hecha en la misma consulta de `GET /tenant/branding`. `None`
    si por lo que sea no hubiera ninguna plantilla en el catálogo — defensa
    para que el cliente se quede con la base de `tokens.css` en vez de
    romper.
    """

    id: str
    key: str
    name: str
    tokens: dict[str, dict[str, str]]


class BrandingResponse(BaseModel):
    """Identidad visual de la organización resuelta por host."""

    organization_id: str
    organization_name: str
    organization_slug: str
    template_key: str = Field(description="Plantilla de la página pública: classic | minimal")
    theme: ResolvedTheme | None = None
    social_links: list[SocialLink]
    organizer_blurb: str | None = None
    logo_url: str | None = None
    favicon_url: str | None = None
