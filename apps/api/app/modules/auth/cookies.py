"""Cookie de refresco: compartida por `auth/router.py` y por cualquier otro
endpoint que necesite emitir una sesión completa (p. ej. el autoservicio de
creación de organizaciones, que abre la primera sesión real de quien acaba de
verificar su correo).
"""

from __future__ import annotations

from fastapi import Response

from app.core.config import get_settings

# La cookie se limita a la ruta de auth: ningún otro endpoint necesita leerla,
# solo escribirla. El navegador acepta un `Set-Cookie` con este `path` venga
# la respuesta de la ruta que venga.
COOKIE_NOMBRE = "ia_week_refresh"
COOKIE_PATH = "/api/v1/auth"


def fijar_cookie_refresh(response: Response, refresh_token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=COOKIE_NOMBRE,
        value=refresh_token,
        max_age=settings.refresh_token_ttl_days * 24 * 3600,
        path=COOKIE_PATH,
        # Sin `Domain`: web y API comparten host tras Caddy, así que la cookie ya es
        # first-party. Añadir `Domain` solo ampliaría su alcance a subdominios.
        domain=settings.cookie_domain or None,
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )


def borrar_cookie_refresh(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        key=COOKIE_NOMBRE,
        path=COOKIE_PATH,
        domain=settings.cookie_domain or None,
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )
