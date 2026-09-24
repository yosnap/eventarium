"""Verificación de las credenciales del MCP (fase de claves de API).

Una sola puerta para todo lo que llega a `/mcp`: resuelve la conexión, exige
que la cuenta siga activa, que la persona siga siendo miembro y tenga
`mcp:connect`, y calcula los ámbitos efectivos (concedidos ∩ rol actual).
Todo se recalcula en cada petición: quitar un rol o el permiso corta la
siguiente llamada sin tocar la conexión.
"""

from __future__ import annotations

import time

from mcp.server.auth.provider import AccessToken, TokenVerifier
from sqlalchemy import select, text

from app.core.database import SessionApp, set_organization_context
from app.core.permissions import Permission
from app.modules.mcp import service
from app.modules.mcp.models import McpConnection
from app.modules.mcp.scopes import ambitos_efectivos


class VerificadorEventarium(TokenVerifier):
    async def verify_token(self, token: str) -> AccessToken | None:
        if not token.startswith(service.PREFIJO_CLAVE):
            return None
        async with SessionApp() as session:
            async with session.begin():
                fila = (
                    await session.execute(
                        text(
                            "SELECT connection_id, organization_id, user_id, user_active "
                            "FROM app_resolve_mcp_key(:hash)"
                        ),
                        {"hash": service.huella(token)},
                    )
                ).first()
                if fila is None or not fila.user_active:
                    return None
                await set_organization_context(session, fila.organization_id, fila.user_id)
                permisos = await service.permisos_en_organizacion(
                    session, fila.organization_id, fila.user_id
                )
                # Sin membresía no hay permisos; sin `mcp:connect` el dueño no le
                # ha dado acceso al MCP (o se lo ha quitado).
                if Permission.MCP_CONNECT not in permisos:
                    return None
                conexion = await session.scalar(
                    select(McpConnection).where(McpConnection.id == fila.connection_id)
                )
                if conexion is None:  # pragma: no cover - la función ya la encontró
                    return None
                ambitos = ambitos_efectivos(conexion.scopes, permisos)
                await service.registrar_uso(session, conexion.id)
        return AccessToken(
            token=token,
            client_id=str(conexion.id),
            scopes=sorted(ambitos),
            expires_at=int(conexion.expires_at.timestamp()),
            subject=str(conexion.user_id),
            claims={
                "connection_id": str(conexion.id),
                "organization_id": str(conexion.organization_id),
                "user_id": str(conexion.user_id),
                "permisos": sorted(p.value for p in permisos),
                "event_ids": (
                    None if conexion.event_ids is None else [str(e) for e in conexion.event_ids]
                ),
                "verificado_en": int(time.time()),
            },
        )
