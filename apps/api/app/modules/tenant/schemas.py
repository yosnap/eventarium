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


class PlatformBrandingBlock(BaseModel):
    """Identidad de la plataforma, presente en cualquier host.

    Es el bloque que el chrome de la web pública debe usar: la marca global de
    la instalación, no la de la organización. Un host de plataforma lo sirve
    sin organización ninguna; un host de organización lo sirve además de la
    suya. Reproduce a propósito los campos del schema de `modules.platform`,
    para que el contrato público del tenant no dependa del módulo interno.
    """

    name: str
    logo_url: str | None = None
    favicon_url: str | None = None
    social_links: list[dict[str, object]] = Field(default_factory=list)
    theme_template_id: str | None = None
    theme: ResolvedTheme | None = None


class BrandingResponse(BaseModel):
    """Identidad visual resuelta por host.

    Dos bloques: `platform` (siempre presente, identidad de la instalación) y
    los campos de nivel raíz (`organization_*`, `template_key`, `theme`,
    `logo_url`…) que describen la organización y son `None` en un host de
    plataforma. Los campos de raíz se conservan mientras el cliente actual los
    siga consumiendo; el bloque `platform` es el contrato nuevo.
    """

    platform: PlatformBrandingBlock

    organization_id: str | None = None
    organization_name: str | None = None
    organization_slug: str | None = None
    template_key: str | None = Field(
        default=None, description="Plantilla de la página pública: classic | minimal"
    )
    theme: ResolvedTheme | None = None
    social_links: list[SocialLink] = Field(default_factory=list)
    organizer_blurb: str | None = None
    logo_url: str | None = None
    favicon_url: str | None = None
