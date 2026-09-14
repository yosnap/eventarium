"""Utilidades sin organización activa ni contexto RLS.

Ya no hay resolución de organización por `Host` en ningún punto de la API
(fase 6 del plan «organización sin dominio»): lo único que queda aquí es
`is_trusted_proxy` (usado por el limitador de tasa, ajeno a la organización)
y `base_url_de_organizacion` (enlaces de correos transaccionales).
"""

from __future__ import annotations

import ipaddress
import uuid

from app.core.config import get_settings


def is_trusted_proxy(ip: str | None) -> bool:
    """Indica si la IP de origen pertenece a una red de proxy de confianza."""
    if not ip:
        return False
    try:
        direccion = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(direccion in red for red in get_settings().trusted_proxy_networks)


async def base_url_de_organizacion(_organization_id: uuid.UUID) -> str:
    """URL pública base para un enlace que llega sin sesión ni contexto.

    Sin dominio por organización (fase 4 del plan de organización sin
    dominio), es siempre `settings.web_base_url` — una sola instalación, un
    solo dominio público, con independencia de la organización del recurso.
    El parámetro se conserva para no tocar los ocho puntos de llamada
    (correos transaccionales, redirecciones de Stripe): todos siguen
    pasando el `organization_id` del recurso, que ya no se usa para nada.
    """
    return get_settings().web_base_url
