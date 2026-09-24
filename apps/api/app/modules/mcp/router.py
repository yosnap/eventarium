"""Conexiones MCP propias de la persona: crear claves de API, listarlas y
revocarlas. Exige `mcp:connect` en la organización activa."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from app.core.deps import CurrentUserDep, DbDep, require_permission
from app.core.permissions import Permission
from app.modules.mcp import service
from app.modules.mcp.models import McpConnection
from app.modules.mcp.scopes import AMBITOS_POR_DEFECTO, Ambito
from app.modules.mcp.server import url_del_recurso

router = APIRouter(prefix="/users/me/mcp-connections", tags=["mcp"])


class ConexionOut(BaseModel):
    id: str
    name: str
    method: str
    scopes: list[str]
    event_ids: list[str] | None
    key_prefix: str | None
    created_at: datetime
    expires_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None


class CrearClaveIn(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=120)]
    scopes: list[Ambito] = Field(default_factory=lambda: list(AMBITOS_POR_DEFECTO))
    # `None` = todos los eventos de la organización.
    event_ids: list[uuid.UUID] | None = None
    days: Annotated[int, Field(ge=1, le=service.DIAS_MAXIMOS)] = service.DIAS_POR_DEFECTO


class ClaveCreadaOut(BaseModel):
    connection: ConexionOut
    # Se enseña una sola vez: después solo se guarda su huella.
    api_key: str
    mcp_url: str


def conexion_out(conexion: McpConnection) -> ConexionOut:
    return ConexionOut(
        id=str(conexion.id),
        name=conexion.name,
        method=conexion.method,
        scopes=list(conexion.scopes),
        event_ids=None if conexion.event_ids is None else [str(e) for e in conexion.event_ids],
        key_prefix=conexion.key_prefix,
        created_at=conexion.created_at,
        expires_at=conexion.expires_at,
        last_used_at=conexion.last_used_at,
        revoked_at=conexion.revoked_at,
    )


@router.get(
    "",
    summary="Mis conexiones MCP en la organización activa",
    response_model=list[ConexionOut],
    dependencies=[require_permission(Permission.MCP_CONNECT)],
)
async def list_my_connections(usuario: CurrentUserDep, session: DbDep) -> list[ConexionOut]:
    conexiones = await service.listar_de_persona(
        session, organization_id=usuario.organization_id, user_id=usuario.id
    )
    return [conexion_out(c) for c in conexiones]


@router.post(
    "",
    summary="Crear una clave de API para conectar un asistente",
    status_code=status.HTTP_201_CREATED,
    response_model=ClaveCreadaOut,
    dependencies=[require_permission(Permission.MCP_CONNECT)],
)
async def create_api_key(
    datos: CrearClaveIn, usuario: CurrentUserDep, session: DbDep
) -> ClaveCreadaOut:
    creada = await service.crear_clave(
        session,
        organization_id=usuario.organization_id,
        user_id=usuario.id,
        nombre=datos.name,
        ambitos=[a.value for a in datos.scopes],
        event_ids=datos.event_ids,
        dias=datos.days,
    )
    await session.refresh(creada.conexion)
    return ClaveCreadaOut(
        connection=conexion_out(creada.conexion), api_key=creada.clave, mcp_url=url_del_recurso()
    )


@router.delete(
    "/{connection_id}",
    summary="Revocar una conexión propia",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[require_permission(Permission.MCP_CONNECT)],
)
async def revoke_my_connection(
    connection_id: uuid.UUID, usuario: CurrentUserDep, session: DbDep
) -> None:
    await service.revocar(
        session,
        organization_id=usuario.organization_id,
        connection_id=connection_id,
        actor_user_id=usuario.id,
        solo_propia=True,
    )
