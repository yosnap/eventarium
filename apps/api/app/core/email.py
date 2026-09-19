"""Envío de correo.

`EmailProvider` es un protocolo mínimo para poder sustituir el proveedor sin tocar a
quien lo llama. En desarrollo apunta a Mailpit (SMTP sin TLS ni autenticación, no sale
a Internet); en producción, cualquier SMTP genérico tras la misma interfaz.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol

import aiosmtplib

from app.core.config import get_settings


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


class SmtpEmailProvider:
    """Proveedor SMTP genérico, válido tanto para Mailpit como para un servidor real."""

    async def send(
        self, *, to: str, subject: str, body: str, attachments: Sequence[EmailAttachment] = ()
    ) -> None:
        settings = get_settings()
        mensaje = EmailMessage()
        mensaje["From"] = settings.smtp_from
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
