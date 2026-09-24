"""Contexto de cada llamada al MCP y los controles que toda herramienta pasa.

El verificador (`auth.py`) resuelve la conexión una vez por petición HTTP y
deja el resultado en el `AccessToken` del SDK (`claims`). Las herramientas lo
recuperan con `contexto_actual()` y **deben** pasar por:

- `exigir_ambito(...)`: la conexión tiene ese ámbito y el rol de la persona
  todavía lo respalda;
- `exigir_evento(event_id)`: el evento está entre los permitidos de la
  conexión. Fuera de la lista se comporta como inexistente (mismo error que
  un evento que no existe), para no revelar qué eventos hay.

Un test de contrato recorre las herramientas registradas y comprueba que
todas usan `herramienta(...)`, que aplica el límite por conexión.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.mcpserver.exceptions import ToolError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import SessionApp, set_organization_context
from app.core.permissions import Permission
from app.modules.mcp.scopes import Ambito
from app.shared.errors import DomainError


class ErrorDeHerramienta(ToolError):
    """Error legible para el asistente. Hereda de `ToolError` porque el SDK
    solo pasa al cliente el mensaje de esas; cualquier otra excepción la
    convierte en un «Error executing tool» genérico (y está bien que así sea
    con los errores inesperados, que no deben filtrar detalles)."""


@dataclass(frozen=True, slots=True)
class ContextoMcp:
    connection_id: uuid.UUID
    organization_id: uuid.UUID
    user_id: uuid.UUID
    ambitos: frozenset[Ambito]
    permisos: frozenset[Permission]
    # `None` = todos los eventos de la organización.
    event_ids: frozenset[uuid.UUID] | None

    def exigir_ambito(self, ambito: Ambito) -> None:
        if ambito not in self.ambitos:
            raise ErrorDeHerramienta(
                f"Esta conexión no tiene el permiso «{ambito.value}». La persona puede "
                "concederlo desde Eventarium, si su rol se lo permite."
            )

    def exigir_evento(self, event_id: uuid.UUID) -> None:
        if self.event_ids is not None and event_id not in self.event_ids:
            raise ErrorDeHerramienta("El evento no existe.")

    def exigir_permiso(self, permiso: Permission, mensaje: str) -> None:
        if permiso not in self.permisos:
            raise ErrorDeHerramienta(mensaje)


def contexto_actual() -> ContextoMcp:
    token = get_access_token()
    if token is None or not token.claims:
        raise ErrorDeHerramienta("Conexión no autenticada.")
    datos = token.claims
    return ContextoMcp(
        connection_id=uuid.UUID(datos["connection_id"]),
        organization_id=uuid.UUID(datos["organization_id"]),
        user_id=uuid.UUID(datos["user_id"]),
        ambitos=frozenset(Ambito(a) for a in token.scopes),
        permisos=frozenset(Permission(p) for p in datos["permisos"]),
        event_ids=(
            None
            if datos["event_ids"] is None
            else frozenset(uuid.UUID(e) for e in datos["event_ids"])
        ),
    )


@asynccontextmanager
async def sesion(contexto: ContextoMcp) -> AsyncIterator[AsyncSession]:
    """La misma sesión que una petición web: rol de la API, transacción y RLS
    de la organización de la conexión, con la persona como usuario."""
    try:
        async with SessionApp() as session:
            async with session.begin():
                await set_organization_context(session, contexto.organization_id, contexto.user_id)
                yield session
    except DomainError as exc:
        # Las mismas reglas de negocio que la web (slug repetido, sesión fuera
        # del evento…), con su mensaje, en vez de un error genérico.
        raise ErrorDeHerramienta(exc.detail) from exc
