"""Contrato HTTP de `/admin/email-settings`."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, EmailStr, Field, SecretStr

from app.modules.email_settings.presets import ModoTls, Proveedor

#: Write-only: se cifra al guardar y nunca vuelve en ninguna respuesta.
Contrasena = Annotated[
    SecretStr,
    Field(min_length=4, max_length=400, json_schema_extra={"writeOnly": True}),
]


class EmailSettingsIn(BaseModel):
    """Configuración a guardar o probar.

    `host` solo lo usa `custom`; `region` solo `ses`; el resto lo fija el
    preset. `tls_mode` solo se atiende si es `none` (custom y fuera de
    producción): el modo cifrado se deriva del puerto. `password` puede
    omitirse para reutilizar la ya guardada si el proveedor no cambia.
    """

    provider: Proveedor
    host: str | None = Field(default=None, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    region: str | None = Field(default=None, max_length=30)
    username: str | None = Field(default=None, max_length=255)
    password: Contrasena | None = None
    from_address: EmailStr
    tls_mode: ModoTls | None = None


class PresetOut(BaseModel):
    provider: Proveedor
    host: str | None
    port: int
    username: str | None


class EmailSettingsOut(BaseModel):
    """Estado de la configuración. **Nunca** la contraseña: solo su pista."""

    #: `database` si hay fila guardada; `environment` si se envía con `SMTP_*`.
    source: Literal["database", "environment"]
    provider: Proveedor | None
    host: str | None
    port: int | None
    tls_mode: ModoTls | None
    username: str | None
    region: str | None
    from_address: str | None
    has_password: bool
    password_hint: str | None
    updated_at: datetime | None
    #: Catálogo para el formulario: una sola fuente, sin copia en el cliente.
    presets: list[PresetOut]
    ses_regions: list[str]
    #: Fuera de producción el formulario admite Mailpit (`none`, puerto 1025).
    allow_insecure: bool


class EmailTestOut(BaseModel):
    """Resultado de la prueba. `ok=false` es un resultado, no un error HTTP."""

    ok: bool
    #: El correo de prueba siempre va a quien la pide, nunca a otra dirección.
    sent_to: str
    motivo: (
        Literal["autenticacion", "remitente_rechazado", "tls", "sin_conexion", "error"] | None
    ) = None
