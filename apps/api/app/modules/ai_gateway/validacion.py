"""Validación SSRF del `api_base` de un proveedor `custom`.

Se aplica **solo** a `custom`, el único proveedor cuyo `api_base` lo escribe
quien configura (`proveedores.py`): las base URL de `nan_builders` y
`cheaper_inference` son constantes nuestras y no pasan por entrada de
usuario.

Distinta de `media/ssrf.py` (subida de imágenes por URL) en tres cosas que
esta necesita y aquella no, por eso no se reutiliza tal cual:

1. admite `http://localhost` fuera de producción, para poder apuntar a un
   modelo local durante el desarrollo;
2. normaliza IPv4-mapped (`::ffff:169.254.169.254`) **antes** de comparar —
   sin eso, la dirección de metadata de nube esquiva `is_link_local`
   (hallazgo S2-4 del red-team);
3. rechaza además CGNAT (`100.64.0.0/10`) y `0.0.0.0/8`, que no están
   cubiertos por `is_private` en todas las versiones de `ipaddress`.

Se llama al guardar (ambos niveles, fase 1) y en cada llamada (fase 2): el
DNS puede cambiar entre una cosa y la otra. Residuo aceptado y documentado:
queda una ventana TOCTOU entre resolver y conectar (DNS rebinding) que solo
se cerraría fijando la IP resuelta en la conexión.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

from app.modules.ai_gateway.errores import ErrorDeConfiguracionDeIa

#: Rangos que `ipaddress` no marca como privados pero tampoco son públicos.
_REDES_RESERVADAS_EXTRA = (
    ipaddress.ip_network("100.64.0.0/10"),  # CGNAT (RFC 6598)
    ipaddress.ip_network("0.0.0.0/8"),  # «esta red» (RFC 1122)
)

#: Direcciones de metadata de nube conocidas. `169.254.169.254` ya cae en
#: `is_link_local`; se listan para que la intención sea explícita.
_IPS_DE_METADATA = frozenset({"169.254.169.254", "fd00:ec2::254"})

#: Nombres que nunca se resuelven a un host público.
_NOMBRES_LOCALES = frozenset({"localhost", "localhost.localdomain", "ip6-localhost"})


class ApiBaseInvalido(ErrorDeConfiguracionDeIa):
    code = "api_base_invalido"


def _normalizar(
    ip: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    """`::ffff:169.254.169.254` → `169.254.169.254`.

    Sin esta normalización, una IPv6 que envuelve una IPv4 reservada no
    dispara ninguna de las comprobaciones de `ipaddress` sobre la IPv4.
    """
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return ip.ipv4_mapped
    return ip


def ip_es_insegura(bruta: str) -> bool:
    """`True` si la IP no es pública. Normaliza IPv4-mapped antes de decidir."""
    ip = _normalizar(ipaddress.ip_address(bruta))
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
        or str(ip) in _IPS_DE_METADATA
    ):
        return True
    return any(ip in red for red in _REDES_RESERVADAS_EXTRA if red.version == ip.version)


def _resolver(host: str) -> list[str]:
    try:
        resultados = socket.getaddrinfo(host, None)
    except socket.gaierror as error:
        raise ApiBaseInvalido(
            "No se ha podido resolver el host de la URL del proveedor."
        ) from error
    if not resultados:
        raise ApiBaseInvalido("No se ha podido resolver el host de la URL del proveedor.")
    return [str(direccion[0]) for *_resto, direccion in resultados]


def validar_api_base(url: str, *, es_produccion: bool) -> str:
    """Rechaza cualquier `api_base` que no sea HTTPS a un host público.

    Devuelve la URL normalizada (sin barra final) para encadenar. Lanza
    `ApiBaseInvalido` (422) con el motivo: el porqué del rechazo importa para
    el mensaje, así que no devuelve un booleano.
    """
    partes = urlsplit(url.strip())
    if partes.scheme not in {"http", "https"}:
        raise ApiBaseInvalido("La URL del proveedor debe empezar por https://.")

    host = (partes.hostname or "").lower()
    if not host:
        raise ApiBaseInvalido("La URL del proveedor no tiene host.")

    es_local = host in _NOMBRES_LOCALES or _es_ip_de_loopback(host)
    if partes.scheme == "http":
        # `http://` solo se tolera contra la propia máquina y fuera de
        # producción: en cualquier otro caso viajarían en claro la clave del
        # proveedor y el contenido de las facturas.
        if es_produccion or not es_local:
            raise ApiBaseInvalido("La URL del proveedor debe empezar por https://.")
        return url.strip().rstrip("/")

    if es_local:
        if es_produccion:
            raise ApiBaseInvalido(
                "La URL del proveedor no puede apuntar a la propia máquina en producción."
            )
        return url.strip().rstrip("/")

    for bruta in _resolver(host):
        try:
            insegura = ip_es_insegura(bruta)
        except ValueError as error:
            raise ApiBaseInvalido(
                "El host de la URL del proveedor no resuelve a una IP válida."
            ) from error
        if insegura:
            raise ApiBaseInvalido(
                "La URL del proveedor resuelve a una dirección de red interna o reservada."
            )

    return url.strip().rstrip("/")


def _es_ip_de_loopback(host: str) -> bool:
    try:
        ip = _normalizar(ipaddress.ip_address(host))
    except ValueError:
        return False
    return ip.is_loopback
