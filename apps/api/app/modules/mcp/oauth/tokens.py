"""Tokens OAuth del MCP.

- **Acceso**: JWT de 15 minutos firmado con un secreto propio
  (`mcp_jwt_secret_efectivo`), con `type = "mcp_access"` y `aud` = URL del MCP.
  La API web rechaza cualquier token con `type` distinto de `access` y con
  otro secreto, y el MCP exige los suyos: un token no vale en el otro lado.
- **Renovación**: opaco, 256 bits, rota en cada uso. En base de datos solo su
  huella (y la del anterior, para detectar reutilización).
"""

from __future__ import annotations

import hashlib
import secrets
import time
import uuid
from dataclasses import dataclass

import jwt

from app.core.config import get_settings
from app.modules.mcp.models import McpConnection
from app.modules.mcp.server_urls import url_del_recurso

TIPO_ACCESO = "mcp_access"
DURACION_ACCESO_SEGUNDOS = 15 * 60
PREFIJO_RENOVACION = "evtmr_"


def huella(valor: str) -> str:
    return hashlib.sha256(valor.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class TokensEmitidos:
    acceso: str
    renovacion: str
    expira_en: int


def emitir(conexion: McpConnection) -> TokensEmitidos:
    """Emite un par nuevo y deja en la conexión la huella del de renovación
    (la del anterior pasa a `refresh_hash_anterior`). El llamador confirma."""
    ahora = int(time.time())
    acceso = jwt.encode(
        {
            "type": TIPO_ACCESO,
            "aud": url_del_recurso(),
            "sub": str(conexion.user_id),
            "org": str(conexion.organization_id),
            "cid": str(conexion.id),
            "scope": " ".join(conexion.scopes),
            "iat": ahora,
            "exp": ahora + DURACION_ACCESO_SEGUNDOS,
            "jti": uuid.uuid4().hex,
        },
        get_settings().mcp_jwt_secret_efectivo,
        algorithm="HS256",
    )
    renovacion = PREFIJO_RENOVACION + secrets.token_urlsafe(32)
    conexion.refresh_hash_anterior = conexion.refresh_hash
    conexion.refresh_hash = huella(renovacion)
    return TokensEmitidos(acceso=acceso, renovacion=renovacion, expira_en=DURACION_ACCESO_SEGUNDOS)


def verificar_acceso(token: str) -> uuid.UUID | None:
    """Id de la conexión si el token es un acceso MCP válido para este
    recurso; `None` en cualquier otro caso (caducado, otra audiencia, otro
    tipo, otra firma)."""
    try:
        datos = jwt.decode(
            token,
            get_settings().mcp_jwt_secret_efectivo,
            algorithms=["HS256"],
            audience=url_del_recurso(),
            options={"require": ["exp", "aud", "type", "cid", "sub"]},
        )
    except jwt.PyJWTError:
        return None
    if datos.get("type") != TIPO_ACCESO:
        return None
    try:
        return uuid.UUID(datos["cid"])
    except (ValueError, TypeError):
        return None
