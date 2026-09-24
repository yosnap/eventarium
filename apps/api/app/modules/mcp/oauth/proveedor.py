"""Proveedor OAuth del MCP sobre el servidor de autorización del SDK oficial.

El SDK se encarga del protocolo (metadatos RFC 8414, PKCE S256, validación de
`redirect_uri`, registro dinámico y revocación); `resource` solo se transporta
y la audiencia del token la fija siempre `tokens.emitir`. Aquí solo va lo
propio de Eventarium:

- **Clientes**: por CIMD (el `client_id` es una URL, `cimd.py`) o por registro
  dinámico (tabla `mcp_oauth_clients`), siempre con direcciones de retorno
  que pasen `redireccion_permitida`. El secreto de un cliente dinámico
  confidencial no se guarda: es un HMAC de su `client_id` y se recalcula.
- **Autorizar**: se guarda la solicitud unos minutos en Redis y se manda a la
  persona a la pantalla de consentimiento de la web, con su sesión normal. Al
  aprobar (`consentimiento.py`) se crea la conexión y un código de un solo uso.
- **Tokens**: `tokens.py`. La renovación rota en cada uso bajo bloqueo de la
  fila; presentar una ya rotada revoca la conexión entera, salvo en los
  segundos justo después de rotar (un reintento del propio cliente).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import time
import uuid
from datetime import UTC, datetime

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    AuthorizeError,
    OAuthAuthorizationServerProvider,
    RefreshToken,
    RegistrationError,
    TokenError,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from sqlalchemy import select, text

from app.core.config import get_settings
from app.core.database import SessionApp, set_organization_context
from app.core.redis_client import get_redis
from app.modules.mcp.models import McpConnection, McpOAuthClient
from app.modules.mcp.oauth import cimd, tokens

VIDA_SOLICITUD = 600
VIDA_CODIGO = 60
# Margen tras rotar en el que presentar el token anterior se rechaza sin
# revocar: dos renovaciones en vuelo o un reintento tras un corte.
GRACIA_ROTACION = 30
_SOLICITUD = "mcp:oauth:solicitud:"
_CODIGO = "mcp:oauth:codigo:"
_ROTADO = "mcp:oauth:rotado:"
logger = logging.getLogger(__name__)


def clave_de_solicitud(identificador: str) -> str:
    return _SOLICITUD + identificador


def clave_de_codigo(codigo: str) -> str:
    return _CODIGO + codigo


def _respuesta(conexion: McpConnection, emitidos: tokens.TokensEmitidos) -> OAuthToken:
    return OAuthToken(
        access_token=emitidos.acceso,
        token_type="Bearer",  # noqa: S106 - tipo de token, no una credencial
        expires_in=emitidos.expira_en,
        scope=" ".join(conexion.scopes),
        refresh_token=emitidos.renovacion,
    )


def _secreto_de_cliente(client_id: str) -> str:
    """Secreto de un cliente dinámico confidencial, derivado y nunca guardado."""
    clave = get_settings().mcp_jwt_secret_efectivo.encode()
    return hmac.new(
        clave, b"mcp:oauth:cliente:v1:" + client_id.encode(), hashlib.sha256
    ).hexdigest()


async def _conexion_con_contexto(  # type: ignore[no-untyped-def]
    session, connection_id: uuid.UUID, *, bloquear: bool = False
) -> McpConnection | None:
    fila = (
        await session.execute(
            text(
                "SELECT connection_id, organization_id, user_id, user_active "
                "FROM app_resolve_mcp_connection(:id)"
            ),
            {"id": connection_id},
        )
    ).first()
    if fila is None or not fila.user_active:
        return None
    await set_organization_context(session, fila.organization_id, fila.user_id)
    consulta = select(McpConnection).where(McpConnection.id == connection_id)
    if bloquear:
        consulta = consulta.with_for_update()
    conexion: McpConnection | None = await session.scalar(consulta)
    return conexion


class ProveedorOAuth(
    OAuthAuthorizationServerProvider[AuthorizationCode, RefreshToken, AccessToken]
):
    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        if cimd.es_url_cimd(client_id):
            return await cimd.resolver(client_id)
        async with SessionApp() as session:
            fila = await session.get(McpOAuthClient, client_id)
            if fila is None:
                return None
            cliente = OAuthClientInformationFull.model_validate(fila.metadata_)
            if cliente.token_endpoint_auth_method != "none":  # noqa: S105 - método, no secreto
                cliente.client_secret = _secreto_de_cliente(cliente.client_id or "")
            return cliente

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        redirecciones = [str(r) for r in client_info.redirect_uris or []]
        if not redirecciones or not all(cimd.redireccion_permitida(r) for r in redirecciones):
            raise RegistrationError(
                error="invalid_redirect_uri",
                error_description="Direcciones de retorno no permitidas.",
            )
        # El SDK devuelve al cliente este mismo objeto: el secreto aleatorio
        # que ha acuñado se sustituye por el derivado, y no se guarda ninguno.
        if client_info.client_secret is not None:
            client_info.client_secret = _secreto_de_cliente(client_info.client_id or "")
        async with SessionApp() as session:
            async with session.begin():
                session.add(
                    McpOAuthClient(
                        client_id=client_info.client_id,
                        metadata_=client_info.model_dump(
                            mode="json", exclude_none=True, exclude={"client_secret"}
                        ),
                    )
                )

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        if not params.code_challenge:
            raise AuthorizeError(error="invalid_request", error_description="PKCE es obligatorio.")
        identificador = secrets.token_urlsafe(24)
        await get_redis().set(
            clave_de_solicitud(identificador),
            json.dumps(
                {
                    "client_id": client.client_id,
                    "client_name": client.client_name,
                    "dinamico": not cimd.es_url_cimd(client.client_id),
                    "redirect_uri": str(params.redirect_uri),
                    "redirect_explicit": params.redirect_uri_provided_explicitly,
                    "code_challenge": params.code_challenge,
                    "scopes": params.scopes or [],
                    "state": params.state,
                    "resource": params.resource,
                }
            ),
            ex=VIDA_SOLICITUD,
        )
        base = get_settings().web_base_url.rstrip("/")
        return f"{base}/oauth/consentimiento?solicitud={identificador}"

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        guardado = await get_redis().get(clave_de_codigo(authorization_code))
        if not guardado:
            return None
        datos = json.loads(guardado)
        if datos["client_id"] != client.client_id:
            return None
        return AuthorizationCode(
            code=authorization_code,
            scopes=datos["scopes"],
            expires_at=datos["expires_at"],
            client_id=datos["client_id"],
            code_challenge=datos["code_challenge"],
            redirect_uri=datos["redirect_uri"],
            redirect_uri_provided_explicitly=datos["redirect_explicit"],
            resource=datos["resource"],
            subject=datos["connection_id"],
        )

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        # Un solo uso de verdad: el primero que lo borra se lo queda.
        if not await get_redis().getdel(clave_de_codigo(authorization_code.code)):
            raise TokenError("invalid_grant", "El código ya se ha usado o ha caducado.")
        async with SessionApp() as session:
            async with session.begin():
                conexion = await _conexion_con_contexto(
                    session, uuid.UUID(authorization_code.subject or "")
                )
                if conexion is None:
                    raise TokenError("invalid_grant", "La conexión ya no es válida.")
                emitidos = tokens.emitir(conexion)
                return _respuesta(conexion, emitidos)

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        async with SessionApp() as session:
            async with session.begin():
                fila = (
                    await session.execute(
                        text(
                            "SELECT connection_id, organization_id, user_id, es_anterior "
                            "FROM app_resolve_mcp_refresh(:hash)"
                        ),
                        {"hash": tokens.huella(refresh_token)},
                    )
                ).first()
                if fila is None:
                    return None
                await set_organization_context(session, fila.organization_id, fila.user_id)
                conexion = await session.scalar(
                    select(McpConnection).where(McpConnection.id == fila.connection_id)
                )
                if conexion is None:
                    return None
                otro_cliente = conexion.oauth_client_id != client.client_id
                # La reutilización se mira antes que el cliente: un token rotado
                # presentado desde otro cliente es una filtración igual.
                if fila.es_anterior:
                    if not otro_cliente and await get_redis().exists(
                        _ROTADO + tokens.huella(refresh_token)
                    ):
                        # Recién rotado: se toma por reintento, no por filtración.
                        logger.warning(
                            "Renovación MCP con token recién rotado (conexión %s, cliente %s)",
                            conexion.id,
                            client.client_id,
                        )
                        return None
                    # Alguien ha presentado un token ya rotado: se ha filtrado.
                    # Se revoca la conexión entera, también para quien la tenía.
                    conexion.revoked_at = datetime.now(UTC)
                    return None
                if otro_cliente:
                    return None
                return RefreshToken(
                    token=refresh_token,
                    client_id=client.client_id,
                    scopes=list(conexion.scopes),
                    expires_at=int(conexion.expires_at.timestamp()),
                    subject=str(conexion.id),
                )

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        async with SessionApp() as session:
            async with session.begin():
                # Bajo bloqueo: de dos renovaciones simultáneas con el mismo
                # token solo una encuentra su huella vigente.
                conexion = await _conexion_con_contexto(
                    session, uuid.UUID(refresh_token.subject or ""), bloquear=True
                )
                presentada = tokens.huella(refresh_token.token)
                if conexion is None or conexion.refresh_hash != presentada:
                    raise TokenError("invalid_grant", "El token de renovación ya no es válido.")
                # La marca va antes del commit: si Redis falla, no se rota y el
                # cliente puede reintentar con el mismo token sin que se tome
                # por reutilización.
                await get_redis().set(_ROTADO + presentada, "1", ex=GRACIA_ROTACION)
                emitidos = tokens.emitir(conexion)
        return _respuesta(conexion, emitidos)

    async def load_access_token(self, token: str) -> AccessToken | None:
        # La verificación real (cuenta activa, permisos, ámbitos) la hace
        # `VerificadorEventarium`; aquí basta con la firma y la conexión.
        connection_id = tokens.verificar_acceso(token)
        if connection_id is None:
            return None
        async with SessionApp() as session:
            async with session.begin():
                conexion = await _conexion_con_contexto(session, connection_id)
        if conexion is None or conexion.oauth_client_id is None:
            return None
        return AccessToken(
            token=token,
            # El SDK solo revoca si coincide con el cliente que lo pide.
            client_id=conexion.oauth_client_id,
            scopes=[],
            expires_at=int(time.time()) + tokens.DURACION_ACCESO_SEGUNDOS,
            subject=str(connection_id),
        )

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        """RFC 7009: el cliente se desconecta. Se revoca la conexión entera."""
        connection_id = token.subject
        if not connection_id:
            return
        async with SessionApp() as session:
            async with session.begin():
                conexion = await _conexion_con_contexto(session, uuid.UUID(connection_id))
                if conexion is not None and conexion.revoked_at is None:
                    conexion.revoked_at = datetime.now(UTC)
