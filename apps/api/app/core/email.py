"""Envío de correo.

`EmailProvider` es un protocolo mínimo para poder sustituir el proveedor sin tocar a
quien lo llama. En desarrollo apunta a Mailpit (SMTP sin TLS ni autenticación, no sale
a Internet); en producción, cualquier SMTP genérico tras la misma interfaz.

De dónde sale la conexión: la fila `platform_email_settings` si existe (la
guarda el superadmin desde el panel); si no, las variables `SMTP_*` del
entorno. Se resuelve **en cada envío** y no al arrancar, porque la API, el
worker y el scheduler son procesos distintos sin un canal para avisarse: una
caché corta por proceso (`TTL_CONFIGURACION_SEGUNDOS`) acota cuánto tarda un
cambio del panel en llegar al worker, que es quien envía casi todo.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Any, Protocol

import aiosmtplib

from app.core.config import get_settings
from app.modules.email_settings.presets import ConfigSmtp, ModoTls, modo_tls_por_puerto

TTL_CONFIGURACION_SEGUNDOS = 30.0
#: Sin él, un servidor que no responde deja colgada la tarea (o la petición
#: de prueba del panel) el minuto entero por defecto de `aiosmtplib`.
TIMEOUT_SMTP_SEGUNDOS = 20.0

#: Tras un fallo al leer la fila: reintentar pronto sin martillear la base.
TTL_TRAS_FALLO_SEGUNDOS = 5.0

logger = logging.getLogger(__name__)
_cache: tuple[float, ConfigSmtp] | None = None
_cerrojo = asyncio.Lock()


@dataclass(frozen=True, slots=True)
class EmailAttachment:
    """Un adjunto binario (fase 4 del PRD: el QR de la entrada en PNG)."""

    filename: str
    content: bytes
    maintype: str
    subtype: str


class EmailProvider(Protocol):
    async def send(  # noqa: D102
        self, *, to: str, subject: str, body: str, attachments: Sequence[EmailAttachment] = ()
    ) -> None: ...


def invalidar_configuracion_en_cache() -> None:
    """Para que el proceso que guarda en el panel use ya la configuración nueva."""
    global _cache
    _cache = None


def configuracion_de_entorno() -> ConfigSmtp:
    """Respaldo `SMTP_*`: desarrollo (Mailpit) y la instalación sin configurar.

    `SMTP_USE_TLS=true` significa «exigir cifrado» y el modo sale del puerto;
    antes era siempre TLS implícito, y con el 587 no conectaba nunca.
    """
    settings = get_settings()
    modo: ModoTls = modo_tls_por_puerto(settings.smtp_port) if settings.smtp_use_tls else "none"
    return ConfigSmtp(
        host=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_user,
        password=settings.smtp_password,
        tls_mode=modo,
        from_address=settings.smtp_from,
    )


async def configuracion_efectiva() -> ConfigSmtp:
    """La fila del panel si existe; si no, el entorno. Con caché corta.

    Lee con `app_user` (la migración 0057 le da solo `SELECT`), no con el rol
    de mantenimiento: el camino de envío no necesita saltarse RLS. El cerrojo
    evita que, al caducar la caché, cada envío concurrente abra su sesión.

    Si la fila no se puede leer o descifrar (base de datos caída, clave de
    cifrado rotada sin `rotate-ai-encryption-key`), se cae al entorno con un
    log crítico en vez de dejar la instalación sin ningún correo; esa caída
    se cachea poco para reintentar pronto.
    """
    global _cache
    async with _cerrojo:
        ahora = time.monotonic()
        if _cache is not None and _cache[0] > ahora:
            return _cache[1]
        try:
            config, ttl = await _leer_de_base_de_datos(), TTL_CONFIGURACION_SEGUNDOS
        except Exception:
            logger.critical(
                "No se puede leer la configuración de correo guardada; "
                "se usan las variables SMTP_* del entorno.",
                exc_info=True,
            )
            config, ttl = configuracion_de_entorno(), TTL_TRAS_FALLO_SEGUNDOS
        _cache = (ahora + ttl, config)
        return config


async def _leer_de_base_de_datos() -> ConfigSmtp:
    # Importación diferida: `email_settings` depende de `core` y no al revés.
    from app.core.database import SessionApp
    from app.core.settings_crypto import descifrar_clave
    from app.modules.email_settings.models import ID_FILA_DE_PLATAFORMA, PlatformEmailSettings

    async with SessionApp() as session:
        fila = await session.get(PlatformEmailSettings, ID_FILA_DE_PLATAFORMA)
    if fila is None:
        return configuracion_de_entorno()
    if fila.tls_mode == "none" and get_settings().app_env == "production":
        logger.error("El correo guardado se envía sin cifrar en producción; revisa el panel.")
    return ConfigSmtp(
        host=fila.host,
        port=fila.port,
        username=fila.username,
        password=descifrar_clave(fila.password_encrypted),
        tls_mode=fila.tls_mode,  # type: ignore[arg-type]
        from_address=fila.from_address,
    )


def parametros_tls(modo: ModoTls) -> dict[str, Any]:
    """Traducción a `aiosmtplib` (5.x): `use_tls` y `start_tls` juntos es `ValueError`.

    `none` no prohíbe cifrar: deja a `aiosmtplib` usar STARTTLS si el servidor
    lo ofrece (lo que hacía antes el respaldo de entorno sin TLS).
    """
    if modo == "implicit":
        return {"use_tls": True, "start_tls": False}
    if modo == "starttls":
        return {"use_tls": False, "start_tls": True}
    return {"use_tls": False, "start_tls": None}


async def enviar_con(
    config: ConfigSmtp,
    *,
    to: str,
    subject: str,
    body: str,
    attachments: Sequence[EmailAttachment] = (),
) -> None:
    """Envía un mensaje con una configuración concreta (la efectiva o una a probar)."""
    mensaje = EmailMessage()
    mensaje["From"] = config.from_address
    mensaje["To"] = to
    mensaje["Subject"] = subject
    mensaje.set_content(body)
    for adjunto in attachments:
        mensaje.add_attachment(
            adjunto.content,
            maintype=adjunto.maintype,
            subtype=adjunto.subtype,
            filename=adjunto.filename,
        )

    await aiosmtplib.send(
        mensaje,
        hostname=config.host,
        port=config.port,
        username=config.username or None,
        password=config.password or None,
        timeout=TIMEOUT_SMTP_SEGUNDOS,
        **parametros_tls(config.tls_mode),
    )


class SmtpEmailProvider:
    """Proveedor SMTP genérico, válido tanto para Mailpit como para un servidor real."""

    async def send(
        self, *, to: str, subject: str, body: str, attachments: Sequence[EmailAttachment] = ()
    ) -> None:
        config = await configuracion_efectiva()
        await enviar_con(config, to=to, subject=subject, body=body, attachments=attachments)


_provider: EmailProvider = SmtpEmailProvider()


def get_email_provider() -> EmailProvider:
    """Instancia única del proveedor de correo."""
    return _provider
