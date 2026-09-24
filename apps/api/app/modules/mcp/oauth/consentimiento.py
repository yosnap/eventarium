"""Pantalla de consentimiento OAuth: la parte de la API.

La web (`/oauth/consentimiento`, con la sesión normal de la persona) lee la
solicitud pendiente y la aprueba o la deniega. Aprobar crea la conexión con
los ámbitos y eventos que la persona elige, dentro de lo que su rol permite, y
un código de un solo uso que el cliente canjea en `/mcp/oauth/token`.

- Aprobar y denegar son **POST** y pasan por `bloquear_escritura_si_impersona`
  (router raíz de la API): desde una sesión de suplantación de plataforma no
  se puede conectar un asistente en nombre de otra persona.
- La solicitud se consume al aprobar o denegar: no se puede reutilizar.
"""

from __future__ import annotations

import json
import secrets
import time
import uuid
from typing import Any

from fastapi import APIRouter
from mcp.server.auth.provider import construct_redirect_uri
from pydantic import BaseModel, Field

from app.core.deps import CurrentUserDep, DbDep, require_permission
from app.core.permissions import Permission
from app.core.redis_client import get_redis
from app.modules.mcp import service
from app.modules.mcp.oauth.proveedor import VIDA_CODIGO, clave_de_codigo, clave_de_solicitud
from app.modules.mcp.scopes import AMBITOS_POR_DEFECTO, PERMISO_REQUERIDO, Ambito
from app.modules.mcp.server_urls import url_del_emisor
from app.modules.organizations.models import Organization
from app.shared.errors import NotFoundError, ValidationDomainError

router = APIRouter(prefix="/oauth/solicitudes", tags=["mcp"])


class SolicitudOut(BaseModel):
    client_id: str
    client_name: str | None
    # Cliente por registro dinámico: nadie lo ha verificado (su nombre lo pone
    # quien lo registra). Los CIMD al menos se identifican por su dominio.
    no_verificado: bool
    redirect_uri: str
    # En qué organización actuará: la activa de la sesión.
    organization_name: str
    ambitos_pedidos: list[str]
    ambitos_permitidos: list[str]
    ambitos_por_defecto: list[str]


class AprobarIn(BaseModel):
    scopes: list[Ambito] = Field(min_length=1)
    event_ids: list[uuid.UUID] | None = None


class RedireccionOut(BaseModel):
    redirect_to: str


async def _solicitud(identificador: str) -> dict[str, Any]:
    guardada = await get_redis().get(clave_de_solicitud(identificador))
    if not guardada:
        raise NotFoundError("La solicitud no existe o ha caducado. Vuelve a conectar el asistente.")
    datos: dict[str, Any] = json.loads(guardada)
    return datos


@router.get(
    "/{solicitud_id}",
    summary="Solicitud de conexión OAuth pendiente",
    response_model=SolicitudOut,
    dependencies=[require_permission(Permission.MCP_CONNECT)],
)
async def ver_solicitud(solicitud_id: str, usuario: CurrentUserDep, session: DbDep) -> SolicitudOut:
    datos = await _solicitud(solicitud_id)
    permisos = await service.permisos_en_organizacion(session, usuario.organization_id, usuario.id)
    organizacion = await session.get(Organization, usuario.organization_id)
    # Si el cliente pidió ámbitos, no se concede nada fuera de ellos (OAuth).
    permitidos = [
        a.value
        for a in Ambito
        if PERMISO_REQUERIDO[a] in permisos and (not datos["scopes"] or a.value in datos["scopes"])
    ]
    pedidos = [a for a in datos["scopes"] if a in permitidos] or [
        a.value for a in AMBITOS_POR_DEFECTO if a.value in permitidos
    ]
    return SolicitudOut(
        client_id=datos["client_id"],
        client_name=datos["client_name"],
        no_verificado=datos["dinamico"],
        redirect_uri=datos["redirect_uri"],
        organization_name=organizacion.name if organizacion else "",
        ambitos_pedidos=datos["scopes"],
        ambitos_permitidos=permitidos,
        ambitos_por_defecto=[a for a in pedidos if a != Ambito.EVENTOS_CANCELAR.value],
    )


@router.post(
    "/{solicitud_id}/aprobar",
    summary="Aprobar la conexión y volver al asistente",
    response_model=RedireccionOut,
    dependencies=[require_permission(Permission.MCP_CONNECT)],
)
async def aprobar(
    solicitud_id: str, datos: AprobarIn, usuario: CurrentUserDep, session: DbDep
) -> RedireccionOut:
    solicitud = await _solicitud(solicitud_id)
    fuera = [
        a.value for a in datos.scopes if solicitud["scopes"] and a.value not in solicitud["scopes"]
    ]
    if fuera:
        raise ValidationDomainError(f"El asistente no ha pedido: {', '.join(fuera)}.")
    conexion = await service.crear_conexion_oauth(
        session,
        organization_id=usuario.organization_id,
        user_id=usuario.id,
        nombre=solicitud["client_name"] or solicitud["client_id"],
        client_id=solicitud["client_id"],
        ambitos=[a.value for a in datos.scopes],
        event_ids=datos.event_ids,
    )
    # La conexión existe antes de que exista un código que apunte a ella.
    await session.commit()
    codigo = secrets.token_urlsafe(32)
    redis = get_redis()
    await redis.set(
        clave_de_codigo(codigo),
        json.dumps(
            {
                "client_id": solicitud["client_id"],
                "connection_id": str(conexion.id),
                "code_challenge": solicitud["code_challenge"],
                "redirect_uri": solicitud["redirect_uri"],
                "redirect_explicit": solicitud["redirect_explicit"],
                "scopes": list(conexion.scopes),
                "resource": solicitud["resource"],
                "expires_at": time.time() + VIDA_CODIGO,
            }
        ),
        ex=VIDA_CODIGO,
    )
    await redis.delete(clave_de_solicitud(solicitud_id))
    return RedireccionOut(
        redirect_to=construct_redirect_uri(
            solicitud["redirect_uri"], code=codigo, state=solicitud["state"], iss=url_del_emisor()
        )
    )


@router.post(
    "/{solicitud_id}/denegar",
    summary="Denegar la conexión y volver al asistente",
    response_model=RedireccionOut,
    dependencies=[require_permission(Permission.MCP_CONNECT)],
)
async def denegar(solicitud_id: str, usuario: CurrentUserDep) -> RedireccionOut:
    solicitud = await _solicitud(solicitud_id)
    await get_redis().delete(clave_de_solicitud(solicitud_id))
    return RedireccionOut(
        redirect_to=construct_redirect_uri(
            solicitud["redirect_uri"],
            error="access_denied",
            error_description="La persona no ha autorizado la conexión.",
            state=solicitud["state"],
            iss=url_del_emisor(),
        )
    )
