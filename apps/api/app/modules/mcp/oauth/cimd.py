"""Client ID Metadata Documents (CIMD): el `client_id` de un cliente OAuth es
una URL HTTPS que publica sus metadatos, y el servidor de autorización la lee
en vez de exigir un registro previo (forma preferida en la especificación MCP
2026-07-28, la que usan Claude y ChatGPT).

Leer una URL que elige un tercero es una puerta a la red interna (SSRF), así
que la descarga es deliberadamente estricta:

- solo `https`, puerto 443, sin credenciales en la URL;
- se resuelve el nombre **antes** de conectar y se rechaza cualquier IP que
  no sea pública (privada, loopback, link-local, metadatos de la nube,
  CGNAT…), y se conecta a **esa misma IP** con el nombre original como SNI:
  un DNS que cambie entre la comprobación y la conexión no sirve de nada;
- sin seguir redirecciones, 3 s de tiempo, 64 KB como máximo y JSON;
- el resultado se cachea una hora en Redis.
"""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
import logging
import socket
from typing import Any
from urllib.parse import urlsplit

import httpx
from mcp.shared.auth import OAuthClientInformationFull
from pydantic import ValidationError

from app.core.redis_client import get_redis
from app.modules.mcp.scopes import Ambito

logger = logging.getLogger(__name__)

TIEMPO_MAXIMO = 3.0
TAMANO_MAXIMO = 64 * 1024
CACHE_SEGUNDOS = 3600


class CimdNoValido(Exception):
    """La URL no se puede usar como identificador de cliente."""


def es_url_cimd(client_id: str) -> bool:
    return client_id.startswith("https://")


def _ip_publica(direccion: str) -> bool:
    ip = ipaddress.ip_address(direccion)
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
        or (ip.version == 4 and ip in ipaddress.ip_network("100.64.0.0/10"))
        or (ip.version == 6 and ip.ipv4_mapped is not None)
    )


def _validar_url(url: str) -> tuple[str, str]:
    partes = urlsplit(url)
    if partes.scheme != "https" or not partes.hostname:
        raise CimdNoValido("El identificador de cliente debe ser una URL https.")
    if partes.username or partes.password or partes.fragment:
        raise CimdNoValido("El identificador de cliente no puede llevar credenciales.")
    if partes.port not in (None, 443):
        raise CimdNoValido("El identificador de cliente debe usar el puerto 443.")
    ruta = partes.path or "/"
    if partes.query:
        ruta += "?" + partes.query
    return partes.hostname, ruta


async def _resolver_ip_publica(host: str) -> str:
    try:
        direcciones = await asyncio.get_running_loop().getaddrinfo(
            host, 443, type=socket.SOCK_STREAM
        )
    except OSError as exc:
        raise CimdNoValido("No se ha podido resolver el cliente.") from exc
    ips = {info[4][0] for info in direcciones}
    if not ips or not all(_ip_publica(ip) for ip in ips):
        raise CimdNoValido("El cliente apunta a una dirección no permitida.")
    return sorted(ips)[0]


async def _descargar(url: str) -> dict[str, Any]:
    host, ruta = _validar_url(url)
    ip = await _resolver_ip_publica(host)
    destino = f"https://[{ip}]{ruta}" if ":" in ip else f"https://{ip}{ruta}"
    async with httpx.AsyncClient(timeout=TIEMPO_MAXIMO, follow_redirects=False) as http:
        async with http.stream(
            "GET",
            destino,
            headers={"Host": host, "Accept": "application/json"},
            extensions={"sni_hostname": host},
        ) as respuesta:
            if respuesta.status_code != 200:
                raise CimdNoValido("El cliente no publica sus metadatos.")
            tipo = respuesta.headers.get("content-type", "")
            if "application/json" not in tipo:
                raise CimdNoValido("Los metadatos del cliente no son JSON.")
            cuerpo = b""
            async for trozo in respuesta.aiter_bytes():
                cuerpo += trozo
                if len(cuerpo) > TAMANO_MAXIMO:
                    raise CimdNoValido("Los metadatos del cliente son demasiado grandes.")
    try:
        datos = json.loads(cuerpo)
    except ValueError as exc:
        raise CimdNoValido("Los metadatos del cliente no son JSON.") from exc
    if not isinstance(datos, dict):
        raise CimdNoValido("Los metadatos del cliente no son válidos.")
    return datos


HOSTS_LOCALES = {"localhost", "127.0.0.1", "::1"}


def redireccion_permitida(uri: str) -> bool:
    """`https`; `http` solo hacia la propia máquina (clientes de terminal como
    Claude Code); o un esquema propio de aplicación (`cursor://`, RFC 8252).
    Nunca `http` hacia otro sitio ni `javascript:`/`data:`."""
    partes = urlsplit(uri)
    esquema = partes.scheme.lower()
    if esquema == "https":
        return bool(partes.hostname)
    if esquema == "http":
        return partes.hostname in HOSTS_LOCALES
    return bool(esquema) and esquema not in {"javascript", "data", "file", "vbscript"}


def _a_cliente(url: str, datos: dict[str, Any]) -> OAuthClientInformationFull:
    if datos.get("client_id") != url:
        raise CimdNoValido("Los metadatos no corresponden a este cliente.")
    redirecciones = datos.get("redirect_uris") or []
    if not redirecciones or not all(
        isinstance(r, str) and redireccion_permitida(r) for r in redirecciones
    ):
        raise CimdNoValido("El cliente declara direcciones de retorno no permitidas.")
    try:
        return OAuthClientInformationFull(
            client_id=url,
            client_name=datos.get("client_name"),
            client_uri=datos.get("client_uri"),
            logo_uri=datos.get("logo_uri"),
            redirect_uris=datos.get("redirect_uris") or [],
            grant_types=["authorization_code", "refresh_token"],
            response_types=["code"],
            # Sin `scope`, el SDK rechaza en `/authorize` cualquier ámbito
            # pedido. Qué se concede lo decide la persona al consentir.
            scope=" ".join(a.value for a in Ambito),
            token_endpoint_auth_method="none",  # noqa: S106 - cliente público con PKCE
        )
    except ValidationError as exc:
        raise CimdNoValido("Los metadatos del cliente no son válidos.") from exc


async def resolver(url: str) -> OAuthClientInformationFull | None:
    clave = f"mcp:cimd:{hashlib.sha256(url.encode()).hexdigest()}"
    redis = get_redis()
    guardado = await redis.get(clave)
    try:
        if guardado:
            return _a_cliente(url, json.loads(guardado))
        datos = await _descargar(url)
        cliente = _a_cliente(url, datos)
    except (CimdNoValido, httpx.HTTPError) as exc:
        logger.info("CIMD rechazado para %s: %s", url, exc)
        return None
    await redis.set(clave, json.dumps(datos), ex=CACHE_SEGUNDOS)
    return cliente
