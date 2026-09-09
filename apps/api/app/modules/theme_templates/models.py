"""Modelo de la tabla de instalación `theme_templates`."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Boolean, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin
from app.shared.identifiers import new_uuid7


class ThemeTemplate(Base, TimestampMixin):
    """Una entrada del catálogo de plantillas de tema.

    Tabla de instalación, sin `organization_id` y por tanto sin RLS: el
    catálogo es común a toda la instalación. `app_user` solo tiene `SELECT`
    (revocado el resto en `0014_plantillas_de_tema`); solo
    `app/modules/admin` escribe, con la sesión de mantenimiento
    (`app_maintainer`, `BYPASSRLS`).
    """

    __tablename__ = "theme_templates"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_uuid7)
    key: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    # Forma: {"dark": {token: valor, ...}, "light": {token: valor, ...}}, con
    # exactamente las claves de `TOKENS_DE_PLANTILLA` (schemas.py).
    tokens: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
