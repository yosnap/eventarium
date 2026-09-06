"""Esquemas públicos del tenant (los consume el frontend en el arranque)."""

from __future__ import annotations

from pydantic import BaseModel, Field

# Paleta de respaldo, usada solo cuando una organización aún no ha personalizado
# su branding. Cumple contraste AA sobre fondo claro.
DEFAULT_COLORS: dict[str, str] = {
    "primary": "#1d4ed8",
    "primary-contrast": "#ffffff",
    "secondary": "#0f766e",
    "surface": "#ffffff",
    "surface-muted": "#f1f5f9",
    "text": "#0f172a",
    "text-muted": "#475569",
    "border": "#cbd5e1",
    "danger": "#b91c1c",
    "success": "#15803d",
}

DEFAULT_FONTS: dict[str, str] = {
    "sans": "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif",
    "heading": "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif",
}


class SocialLink(BaseModel):
    """Enlace a una red social del organizador."""

    kind: str = Field(description="Identificador de la red: x, linkedin, instagram…")
    url: str


class BrandingResponse(BaseModel):
    """Identidad visual de la organización resuelta por host."""

    organization_id: str
    organization_name: str
    organization_slug: str
    template_key: str = Field(description="Plantilla de la página pública: classic | minimal")
    colors: dict[str, str]
    fonts: dict[str, str]
    social_links: list[SocialLink]
    organizer_blurb: str | None = None
    logo_url: str | None = None
    favicon_url: str | None = None
