"""Verificación de Cloudflare Turnstile.

Protege los endpoints públicos que escriben y envían correo (registro, reenvío de
verificación) frente a scripts automatizados. **Fail-closed**: si Cloudflare no
responde, la petición se rechaza (503) — a diferencia del chequeo de contraseñas
filtradas, que no es un control de sesión crítico y sí puede fallar abierto.
"""

from __future__ import annotations

import httpx
from fastapi import Request

from app.core.config import get_settings
from app.core.ratelimit import client_ip
from app.shared.errors import DomainError, ServiceUnavailableError

SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


class InvalidTurnstileTokenError(DomainError):
    status_code = 422
    title = "Verificación anti-bot no válida"


async def verify_turnstile_token(token: str, remote_ip: str | None) -> bool:
    """Comprueba un token de Turnstile contra Cloudflare."""
    settings = get_settings()
    datos = {"secret": settings.turnstile_secret_key, "response": token}
    if remote_ip:
        datos["remoteip"] = remote_ip
    try:
        async with httpx.AsyncClient(timeout=5.0) as cliente:
            respuesta = await cliente.post(SITEVERIFY_URL, data=datos)
            respuesta.raise_for_status()
    except httpx.HTTPError as exc:
        raise ServiceUnavailableError(
            "El servicio de verificación anti-bot no está disponible. Inténtalo de nuevo."
        ) from exc
    return bool(respuesta.json().get("success"))


async def require_turnstile(request: Request, token: str) -> None:
    """Exige un Turnstile válido, salvo que esté desactivado (solo fuera de producción)."""
    settings = get_settings()
    if not settings.turnstile_enabled:
        return
    if not await verify_turnstile_token(token, client_ip(request)):
        raise InvalidTurnstileTokenError("La verificación anti-bot no es válida.")
