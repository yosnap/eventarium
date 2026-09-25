"""Reglas de `/admin/email-settings`. Siempre con la sesión de mantenimiento."""

from __future__ import annotations

import logging
import ssl

import aiosmtplib
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.email import configuracion_de_entorno, enviar_con
from app.core.settings_crypto import cifrar_clave, descifrar_clave, pista_de_clave
from app.modules.email_settings.models import ID_FILA_DE_PLATAFORMA, PlatformEmailSettings
from app.modules.email_settings.presets import (
    PRESETS,
    REGIONES_SES,
    ConfigSmtp,
    ConfiguracionDeCorreoInvalida,
    resolver_host,
    resolver_tls,
    validar_host,
    validar_puerto,
)
from app.modules.email_settings.schemas import (
    EmailSettingsIn,
    EmailSettingsOut,
    EmailTestOut,
    PresetOut,
)

logger = logging.getLogger(__name__)

ASUNTO_DE_PRUEBA = "Eventarium: prueba del proveedor de correo"
CUERPO_DE_PRUEBA = (
    "Este correo confirma que el proveedor de correo configurado en el panel "
    "de la plataforma acepta envíos.\n\n"
    "Si lo has recibido, puedes guardar la configuración."
)


def _es_produccion() -> bool:
    return get_settings().app_env == "production"


async def leer_fila(session: AsyncSession) -> PlatformEmailSettings | None:
    return await session.get(PlatformEmailSettings, ID_FILA_DE_PLATAFORMA)


def vista(fila: PlatformEmailSettings | None) -> EmailSettingsOut:
    """Lo que ve el admin. Sin fila, describe el respaldo de entorno sin secretos."""
    presets = [
        PresetOut(provider=clave, host=p.host, port=p.port, username=p.username)
        for clave, p in PRESETS.items()
    ]
    regiones = sorted(REGIONES_SES)
    inseguro = not _es_produccion()
    if fila is None:
        entorno = configuracion_de_entorno()
        return EmailSettingsOut(
            source="environment",
            provider=None,
            host=entorno.host,
            port=entorno.port,
            tls_mode=entorno.tls_mode,
            username=None,
            region=None,
            from_address=entorno.from_address,
            has_password=bool(entorno.password),
            password_hint=None,
            updated_at=None,
            presets=presets,
            ses_regions=regiones,
            allow_insecure=inseguro,
        )
    return EmailSettingsOut(
        source="database",
        provider=fila.provider,  # type: ignore[arg-type]
        host=fila.host,
        port=fila.port,
        tls_mode=fila.tls_mode,  # type: ignore[arg-type]
        username=fila.username,
        region=fila.region,
        from_address=fila.from_address,
        has_password=True,
        password_hint=fila.password_hint,
        updated_at=fila.updated_at,
        presets=presets,
        ses_regions=regiones,
        allow_insecure=inseguro,
    )


async def _config_desde(datos: EmailSettingsIn, fila: PlatformEmailSettings | None) -> ConfigSmtp:
    """Valida el formulario y construye la conexión, sin guardar nada.

    La contraseña omitida se toma de la fila guardada solo si el proveedor es
    el mismo: reutilizar la API key de Resend contra otro servidor la
    enviaría a quien no corresponde.
    """
    produccion = _es_produccion()
    preset = PRESETS[datos.provider]
    port = datos.port or preset.port
    validar_puerto(port, es_produccion=produccion)
    host = resolver_host(datos.provider, host=datos.host, region=datos.region)
    await validar_host(host, es_produccion=produccion)
    tls = resolver_tls(datos.provider, port, datos.tls_mode, es_produccion=produccion)

    username = preset.username or (datos.username or "").strip()
    if not username:
        raise ConfiguracionDeCorreoInvalida("Falta el usuario SMTP.")

    if datos.password is not None:
        password = datos.password.get_secret_value()
    elif fila is not None and fila.provider == datos.provider:
        password = descifrar_clave(fila.password_encrypted)
    else:
        raise ConfiguracionDeCorreoInvalida("Falta la contraseña o API key.")

    return ConfigSmtp(
        host=host,
        port=port,
        username=username,
        password=password,
        tls_mode=tls,
        from_address=str(datos.from_address),
    )


async def guardar(session: AsyncSession, datos: EmailSettingsIn) -> PlatformEmailSettings:
    fila = await leer_fila(session)
    config = await _config_desde(datos, fila)
    # Cifrar antes de tocar la fila: sin clave de cifrado sale
    # `CifradoNoConfigurado` (503) y no queda nada a medias.
    cifrada = cifrar_clave(config.password)
    if fila is None:
        fila = PlatformEmailSettings(id=ID_FILA_DE_PLATAFORMA)
        session.add(fila)
    fila.provider = datos.provider
    fila.host = config.host
    fila.port = config.port
    fila.tls_mode = config.tls_mode
    fila.username = config.username
    fila.password_encrypted = cifrada
    fila.password_hint = pista_de_clave(config.password)
    fila.from_address = config.from_address
    fila.region = datos.region if datos.provider == "ses" else None
    await session.flush()
    await session.refresh(fila)
    return fila


async def borrar(session: AsyncSession) -> bool:
    fila = await leer_fila(session)
    if fila is None:
        return False
    await session.delete(fila)
    await session.flush()
    return True


async def config_para_probar(session: AsyncSession, datos: EmailSettingsIn) -> ConfigSmtp:
    """Valida el formulario (y toma la contraseña guardada si procede)."""
    return await _config_desde(datos, await leer_fila(session))


async def probar(config: ConfigSmtp, *, destinatario: str) -> EmailTestOut:
    """Envío real al propio superadmin (no a una dirección libre: no es un relay).

    Sin sesión de base de datos: el envío puede tardar hasta el timeout SMTP y
    no debe retener una conexión del pool de mantenimiento mientras tanto.
    Al cliente solo le llega una categoría del fallo; el detalle, al log.
    """
    try:
        await enviar_con(config, to=destinatario, subject=ASUNTO_DE_PRUEBA, body=CUERPO_DE_PRUEBA)
    except aiosmtplib.SMTPAuthenticationError:
        logger.warning("Prueba de correo: autenticación rechazada por %s", config.host)
        return EmailTestOut(ok=False, sent_to=destinatario, motivo="autenticacion")
    except (
        aiosmtplib.SMTPSenderRefused,
        aiosmtplib.SMTPRecipientsRefused,
        aiosmtplib.SMTPDataError,
    ):
        logger.warning("Prueba de correo: envío rechazado por %s", config.host, exc_info=True)
        return EmailTestOut(ok=False, sent_to=destinatario, motivo="remitente_rechazado")
    except ssl.SSLError:
        # El fallo que tumbó producción (TLS implícito contra un puerto STARTTLS).
        logger.warning("Prueba de correo: fallo TLS con %s", config.host, exc_info=True)
        return EmailTestOut(ok=False, sent_to=destinatario, motivo="tls")
    except (aiosmtplib.SMTPConnectError, aiosmtplib.SMTPTimeoutError, OSError) as error:
        if isinstance(error.__cause__, ssl.SSLError) or "SSL" in str(error):
            logger.warning("Prueba de correo: fallo TLS con %s", config.host, exc_info=True)
            return EmailTestOut(ok=False, sent_to=destinatario, motivo="tls")
        logger.warning("Prueba de correo: sin conexión con %s", config.host, exc_info=True)
        return EmailTestOut(ok=False, sent_to=destinatario, motivo="sin_conexion")
    except aiosmtplib.SMTPException:
        logger.warning("Prueba de correo: error SMTP con %s", config.host, exc_info=True)
        return EmailTestOut(ok=False, sent_to=destinatario, motivo="error")
    return EmailTestOut(ok=True, sent_to=destinatario)
