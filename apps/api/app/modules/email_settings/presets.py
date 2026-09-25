"""Catálogo cerrado de proveedores de correo y reglas de conexión.

Funciones puras (salvo la resolución DNS de `validar_host`): las usan el
servicio del admin y el envío real (`app/core/email.py`).

TLS: el modo **no** es una casilla libre. Un `use_tls=True` sobre el puerto
587 rompió el correo de producción el 25-sep (`WRONG_VERSION_NUMBER`: 587
espera STARTTLS y se le habló TLS implícito). Por eso el modo se deriva del
puerto — 465/2465 → TLS implícito, el resto → STARTTLS obligatorio — y solo
`custom` puede pedir `none`, y nunca en producción (existe para Mailpit).
"""

from __future__ import annotations

import asyncio
import socket
from dataclasses import dataclass
from typing import Literal

from app.modules.ai_gateway.validacion import ip_es_insegura
from app.shared.errors import ValidationDomainError

Proveedor = Literal["resend", "acumbamail", "ses", "custom"]
ModoTls = Literal["implicit", "starttls", "none"]

PUERTOS_TLS_IMPLICITO = frozenset({465, 2465})
#: Puertos SMTP de envío conocidos. Cualquier otro se rechaza: el formulario
#: no debe servir para abrir conexiones a puertos arbitrarios (red-team).
PUERTOS_PERMITIDOS = frozenset({25, 465, 587, 2465, 2525, 2587})
#: Solo fuera de producción: Mailpit escucha en 1025.
PUERTOS_DE_DESARROLLO = frozenset({1025})

REGIONES_SES = frozenset(
    {
        "us-east-1", "us-east-2", "us-west-1", "us-west-2", "ca-central-1",
        "sa-east-1", "eu-west-1", "eu-west-2", "eu-west-3", "eu-central-1",
        "eu-south-1", "eu-north-1", "il-central-1", "me-south-1", "af-south-1",
        "ap-south-1", "ap-southeast-1", "ap-southeast-2", "ap-northeast-1",
        "ap-northeast-2", "ap-northeast-3",
    }
)  # fmt: skip


@dataclass(frozen=True, slots=True)
class Preset:
    host: str | None
    port: int
    username: str | None


#: Valores por defecto. `host=None`: lo escribe quien configura (`custom`) o
#: sale de la región (`ses`). `username=None`: lo da el proveedor a cada cuenta.
PRESETS: dict[Proveedor, Preset] = {
    # https://resend.com/docs/send-with-smtp — usuario fijo, contraseña = API key.
    "resend": Preset(host="smtp.resend.com", port=465, username="resend"),
    "acumbamail": Preset(host="smtp.acumbamail.com", port=587, username=None),
    # Credenciales SMTP propias de SES, no las de IAM.
    "ses": Preset(host=None, port=465, username=None),
    "custom": Preset(host=None, port=587, username=None),
}


@dataclass(frozen=True, slots=True)
class ConfigSmtp:
    """Todo lo necesario para abrir una conexión SMTP y enviar."""

    host: str
    port: int
    username: str
    password: str
    tls_mode: ModoTls
    from_address: str


class ConfiguracionDeCorreoInvalida(ValidationDomainError):
    """422 con un `code` estable para el formulario del admin."""

    code = "configuracion_de_correo_invalida"

    def __init__(self, detail: str) -> None:
        super().__init__(detail, extra={"code": self.code})


def modo_tls_por_puerto(port: int) -> ModoTls:
    return "implicit" if port in PUERTOS_TLS_IMPLICITO else "starttls"


def host_de_ses(region: str) -> str:
    if region not in REGIONES_SES:
        raise ConfiguracionDeCorreoInvalida("La región de Amazon SES no es válida.")
    return f"email-smtp.{region}.amazonaws.com"


def resolver_host(provider: Proveedor, *, host: str | None, region: str | None) -> str:
    """Host efectivo: el del preset, el de la región (SES) o el escrito (custom)."""
    if provider == "ses":
        return host_de_ses(region or "")
    preset = PRESETS[provider].host
    if preset is not None:
        return preset
    limpio = (host or "").strip().lower()
    if not limpio:
        raise ConfiguracionDeCorreoInvalida("Falta el servidor SMTP.")
    return limpio


def resolver_tls(
    provider: Proveedor, port: int, pedido: ModoTls | None, *, es_produccion: bool
) -> ModoTls:
    """Modo TLS efectivo. Solo `custom` puede pedir `none`, y fuera de producción."""
    if pedido == "none":
        if provider != "custom" or es_produccion:
            raise ConfiguracionDeCorreoInvalida(
                "El envío sin cifrar solo se permite en desarrollo y con SMTP personalizado."
            )
        return "none"
    return modo_tls_por_puerto(port)


def validar_puerto(port: int, *, es_produccion: bool) -> None:
    permitidos = PUERTOS_PERMITIDOS if es_produccion else PUERTOS_PERMITIDOS | PUERTOS_DE_DESARROLLO
    if port not in permitidos:
        raise ConfiguracionDeCorreoInvalida(
            "Puerto no permitido. Usa uno de: "
            + ", ".join(str(p) for p in sorted(permitidos))
            + "."
        )


async def validar_host(host: str, *, es_produccion: bool) -> None:
    """En producción, el servidor tiene que resolver solo a IPs públicas.

    Sin esto, el formulario serviría para que la instalación abriera
    conexiones a `redis`, `postgres` o la metadata de la nube (SSRF). Fuera
    de producción se permite todo (Mailpit vive en la red interna).
    """
    if not es_produccion:
        return
    try:
        # Resolución asíncrona: un DNS lento no debe congelar el event loop.
        resultados = await asyncio.get_running_loop().getaddrinfo(host, None)
    except (socket.gaierror, UnicodeError) as error:
        raise ConfiguracionDeCorreoInvalida("No se ha podido resolver el servidor SMTP.") from error
    direcciones = {str(r[4][0]) for r in resultados}
    if not direcciones or any(_insegura(ip) for ip in direcciones):
        raise ConfiguracionDeCorreoInvalida("El servidor SMTP tiene que ser una dirección pública.")


def _insegura(ip: str) -> bool:
    """Lo que no se puede interpretar (p. ej. `fe80::1%eth0`) cuenta como inseguro."""
    try:
        return ip_es_insegura(ip)
    except ValueError:
        return True
