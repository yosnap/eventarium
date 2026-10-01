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
from app.core.email_template import pie_texto_plano, plantilla_html
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


# --- Identidad de plataforma para el correo (logo dinámico + nombre de marca) ---

#: Content-type del logo: solo los que `ALLOWED_IMAGE_MIMES` admite para el
#: logo (png/jpeg/webp). Defensa en profundidad — `PlatformMedia` ya valida
#: contra esa lista en la subida —, pero el `cid:` solo se embebe si el tipo es
#: uno de esos tres (en cualquier otro caso, cabecera sin logo).
_MIMES_LOGO = frozenset({"image/png", "image/jpeg", "image/webp"})

#: `Content-ID` fijo del logo: la cabecera lo referencia por `cid:`.
CID_LOGO = "logo@eventarium"

#: Nombre de marca para el caso extremo de no poder leer la identidad (base de
#: datos caída): es el nombre por defecto de la plataforma, estable. Solo se
#: usa ahí; lo normal es el `branding.name` de la fila.
NOMBRE_MARCA_RESALTO = "Eventarium"


@dataclass(frozen=True, slots=True)
class Branding:
    """Identidad de plataforma para el correo: nombre de marca + logo.

    `logo` son los bytes ya leídos del almacén y `logo_mime` su content-type;
    si no hay logo o no es legible, ambos son `None` y la cabecera se queda
    solo con el nombre de marca (el pie legal siempre sale, no depende del logo).
    """

    nombre: str
    logo: bytes | None = None
    logo_mime: str | None = None


_cache_branding: tuple[float, Branding] | None = None
_cerrojo_branding = asyncio.Lock()


def invalidar_branding_en_cache() -> None:
    """Para que el proceso que guarda la identidad use ya el logo nuevo."""
    global _cache_branding
    _cache_branding = None


async def branding_efectiva() -> Branding:
    """La identidad de plataforma, con caché corta por proceso.

    El worker es quien envía casi todo: sin caché, cada correo abriría una
    sesión y haría una lectura al almacén. Mismo patrón que
    `configuracion_efectiva`: caché corta (30 s) y, si no se puede leer, cae a
    «solo nombre de marca» (nunca se rompe el envío) y se cachea poco para
    reintentar pronto.
    """
    global _cache_branding
    async with _cerrojo_branding:
        ahora = time.monotonic()
        if _cache_branding is not None and _cache_branding[0] > ahora:
            return _cache_branding[1]
        try:
            branding = await _leer_branding()
            ttl = TTL_CONFIGURACION_SEGUNDOS
        except Exception:
            logger.critical(
                "No se puede leer la identidad de plataforma; el correo se envía sin logo.",
                exc_info=True,
            )
            branding = Branding(nombre=NOMBRE_MARCA_RESALTO)
            ttl = TTL_TRAS_FALLO_SEGUNDOS
        _cache_branding = (ahora + ttl, branding)
        return branding


async def _leer_branding() -> Branding:
    # Importación diferida: `platform` y `media` dependen de `core` y no al
    # revés (mismo patrón que `_leer_de_base_de_datos`). Los bytes del logo
    # salen de `core.storage`, que no es ninguna feature.
    from app.core.database import SessionApp
    from app.core.storage import get_storage
    from app.modules.media.models import PlatformMedia
    from app.modules.platform import repository
    from app.modules.platform.models import NOMBRE_PLATAFORMA

    async with SessionApp() as session:
        fila = await repository.get_platform_branding(session)
        nombre = fila.name or NOMBRE_PLATAFORMA
        # Resolver la clave del logo: vía `logo_media_id` (la subida actual) o
        # vía `logo_object_key` (la vía antigua). Mismo criterio que
        # `branding_publico`.
        if fila.logo_media_id is not None:
            media = await session.get(PlatformMedia, fila.logo_media_id)
            clave: str | None = media.object_key if media else None
        elif fila.logo_object_key:
            clave = fila.logo_object_key
        else:
            clave = None

    if not clave:
        return Branding(nombre=nombre)

    almacen = get_storage()
    contenido, mime = await almacen.get_object(clave)
    if mime not in _MIMES_LOGO:
        logger.warning("El logo no es png/jpeg/webp (%s); el correo va sin logo.", mime)
        return Branding(nombre=nombre)
    return Branding(nombre=nombre, logo=contenido, logo_mime=mime)


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
    """Envía un mensaje con una configuración concreta (la efectiva o una a probar).

    El cuerpo va con la plantilla de plataforma: cabecera con el logo (embebedo
    por `cid:`), cuerpo y pie con los enlaces legales. El HTML se construye con
    `plantilla_html` y al texto plano se le añade el pie en líneas. Los adjuntos
    (p. ej. el QR de la entrada) se envuelven en `multipart/mixed` por fuera del
    alternativo, que sigue intacto.
    """
    branding = await branding_efectiva()
    base_url = get_settings().web_base_url
    logo_html = (
        f'<img src="cid:{CID_LOGO}" alt="" style="max-width:160px;height:auto;" />'
        if branding.logo is not None
        else None
    )
    html_plantilla = plantilla_html(
        body,
        nombre_marca=branding.nombre,
        logo_html=logo_html,
        base_url=base_url,
    )
    texto_con_pie = f"{body}\n\n{pie_texto_plano(base_url=base_url)}"

    mensaje = _armar_mensaje(
        from_address=config.from_address,
        to=to,
        subject=subject,
        texto=texto_con_pie,
        html=html_plantilla,
        logo=branding.logo,
        logo_mime=branding.logo_mime,
        attachments=attachments,
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


def _armar_mensaje(
    *,
    from_address: str,
    to: str,
    subject: str,
    texto: str,
    html: str,
    logo: bytes | None,
    logo_mime: str | None,
    attachments: Sequence[EmailAttachment],
) -> EmailMessage:
    """El mensaje MIME con la plantilla: alternativo (+logo `cid:`) + adjuntos.

    - Sin adjuntos: la raíz es `multipart/alternative` con `text/plain` y
      `text/html` (o `multipart/related` con el logo embebido si lo hay).
    - Con adjuntos: la raíz pasa a ser `multipart/mixed` que envuelve el
      alternativo de antes y cada adjunto como `image/*`; así la plantilla y
      el adjunto no se descolocan.
    """
    alternativo = EmailMessage()
    alternativo.make_alternative()
    plano = EmailMessage()
    plano.set_content(texto)
    alternativo.attach(plano)

    if logo is not None and logo_mime is not None:
        relacionado = EmailMessage()
        relacionado.set_content(html, subtype="html")
        principal, secundario = logo_mime.split("/", 1)
        relacionado.add_related(
            logo,
            maintype=principal,
            subtype=secundario,
            filename="logo",
            cid=CID_LOGO,
        )
        alternativo.attach(relacionado)
    else:
        html_parte = EmailMessage()
        html_parte.set_content(html, subtype="html")
        alternativo.attach(html_parte)

    if not attachments:
        alternativo["From"] = from_address
        alternativo["To"] = to
        alternativo["Subject"] = subject
        return alternativo

    mensaje = EmailMessage()
    mensaje["From"] = from_address
    mensaje["To"] = to
    mensaje["Subject"] = subject
    mensaje.make_mixed()
    mensaje.attach(alternativo)
    for adjunto in attachments:
        mensaje.add_attachment(
            adjunto.content,
            maintype=adjunto.maintype,
            subtype=adjunto.subtype,
            filename=adjunto.filename,
        )
    return mensaje


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
