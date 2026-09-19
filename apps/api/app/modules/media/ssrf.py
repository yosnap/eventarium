"""Validación SSRF para la subida de medios por URL externa.

Riesgo residual documentado, no eliminado (hallazgo de red-team, plan
`260918-1944`): existe una ventana entre resolver el host y conectar
(DNS rebinding con TTL bajo). Cerrarla del todo exigiría fijar la conexión
a la IP ya validada (pinning), que con `httpx` no es trivial sin escribir un
transporte a medida. Se acepta el riesgo por ser de explotación difícil
(exige control del DNS de la víctima en una ventana de milisegundos) — queda
escrito aquí para que sea una decisión conocida, no un descubrimiento en
producción.
"""

from __future__ import annotations

import ipaddress
import socket

from app.shared.errors import ValidationDomainError

#: Direcciones de metadata de nube conocidas, por si `ipaddress` no las
#: cubre ya con `is_link_local` (169.254.0.0/16 sí lo es; se listan de
#: todos modos para que la intención quede explícita, no implícita en un
#: efecto colateral de `is_link_local`).
_METADATA_IPS = frozenset({"169.254.169.254", "fd00:ec2::254"})


def _ip_es_insegura(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
        or str(ip) in _METADATA_IPS
    )


def validar_url_publica_segura(url: str) -> str:
    """Rechaza cualquier URL que no sea HTTPS a un host público.

    Devuelve la propia `url` si pasa la validación (para encadenar).
    Lanza `ValidationDomainError` en cualquier otro caso: no es un booleano
    porque el motivo del rechazo importa para el mensaje de error.
    """
    if not url.lower().startswith("https://"):
        raise ValidationDomainError("Solo se admiten URLs https://.")

    host = url[len("https://") :].split("/", 1)[0].split(":", 1)[0].split("@")[-1]
    if not host:
        raise ValidationDomainError("URL sin host.")

    try:
        resultados = socket.getaddrinfo(host, None)
    except socket.gaierror as error:
        raise ValidationDomainError("No se ha podido resolver el host de la URL.") from error

    if not resultados:
        raise ValidationDomainError("No se ha podido resolver el host de la URL.")

    for _familia, _tipo, _proto, _canonico, direccion in resultados:
        ip_bruta = direccion[0]
        try:
            ip = ipaddress.ip_address(ip_bruta)
        except ValueError as error:
            raise ValidationDomainError("El host de la URL no resuelve a una IP válida.") from error
        if _ip_es_insegura(ip):
            raise ValidationDomainError(
                "La URL resuelve a una dirección de red interna o reservada."
            )

    return url
