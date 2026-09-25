"""Configuración del proveedor de correo de la instalación. Una sola fila.

Mismo patrón que `platform_ai_settings`: fila única (`id = 1`), credencial
cifrada en reposo con su pista, y `app_user` solo puede leerla (la escribe el
admin con la sesión de mantenimiento, migración 0057). A diferencia de la IA,
la fila existe entera o no existe: borrarla devuelve el envío a las variables
`SMTP_*` del entorno.
"""

from __future__ import annotations

from sqlalchemy import CheckConstraint, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin

ID_FILA_DE_PLATAFORMA = 1


class PlatformEmailSettings(Base, TimestampMixin):
    __tablename__ = "platform_email_settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_platform_email_settings_fila_unica"),
        CheckConstraint(
            "provider IN ('resend', 'acumbamail', 'ses', 'custom')",
            name="ck_platform_email_settings_proveedor",
        ),
        CheckConstraint(
            "tls_mode IN ('implicit', 'starttls', 'none')",
            name="ck_platform_email_settings_tls",
        ),
        CheckConstraint("port BETWEEN 1 AND 65535", name="ck_platform_email_settings_puerto"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=ID_FILA_DE_PLATAFORMA)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    tls_mode: Mapped[str] = mapped_column(String(10), nullable=False)
    username: Mapped[str] = mapped_column(String(255), nullable=False)
    password_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    password_hint: Mapped[str] = mapped_column(String(8), nullable=False)
    from_address: Mapped[str] = mapped_column(String(320), nullable=False)
    #: Solo en `ses`: el host sale de ella.
    region: Mapped[str | None] = mapped_column(String(30), nullable=True)
