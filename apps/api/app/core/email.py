"""Envío de correo.

`EmailProvider` es un protocolo mínimo para poder sustituir el proveedor sin tocar a
quien lo llama. En desarrollo apunta a Mailpit (SMTP sin TLS ni autenticación, no sale
a Internet); en producción, cualquier SMTP genérico tras la misma interfaz.
"""

from __future__ import annotations

from email.message import EmailMessage
from typing import Protocol

import aiosmtplib

from app.core.config import get_settings


class EmailProvider(Protocol):
    async def send(self, *, to: str, subject: str, body: str) -> None: ...  # noqa: D102


class SmtpEmailProvider:
    """Proveedor SMTP genérico, válido tanto para Mailpit como para un servidor real."""

    async def send(self, *, to: str, subject: str, body: str) -> None:
        settings = get_settings()
        mensaje = EmailMessage()
        mensaje["From"] = settings.smtp_from
        mensaje["To"] = to
        mensaje["Subject"] = subject
        mensaje.set_content(body)

        await aiosmtplib.send(
            mensaje,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user or None,
            password=settings.smtp_password or None,
            use_tls=settings.smtp_use_tls,
        )


_provider: EmailProvider = SmtpEmailProvider()


def get_email_provider() -> EmailProvider:
    """Instancia única del proveedor de correo."""
    return _provider
