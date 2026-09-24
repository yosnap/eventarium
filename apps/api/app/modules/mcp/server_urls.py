"""URLs públicas del MCP, sin dependencias para que las importe cualquiera."""

from __future__ import annotations

from app.core.config import get_settings


def url_del_recurso() -> str:
    """El recurso protegido (RFC 9728): la URL que añade el cliente."""
    return get_settings().web_base_url.rstrip("/") + "/mcp"


def url_del_emisor() -> str:
    """El servidor de autorización. Bajo `/mcp` para que Caddy lo mande a la
    API y no choque con rutas de la web."""
    return get_settings().web_base_url.rstrip("/") + "/mcp/oauth"
