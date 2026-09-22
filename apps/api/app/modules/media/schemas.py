"""Esquemas de la biblioteca de medios."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class MediaResponse(BaseModel):
    id: str
    kind: str
    url: str
    filename: str
    mime_type: str
    size: int
    width: int | None = None
    height: int | None = None
    alt: str | None = None
    folder_id: str | None = None
    uploaded_by_user_id: str
    created_at: datetime


class MediaAssignRequest(BaseModel):
    """Cuerpo JSON que aceptan, además de multipart, los endpoints de subida
    ya existentes (logo/portada/patrocinador/identidad de plataforma) para
    asignar una imagen YA subida a la biblioteca, sin volver a procesarla."""

    media_id: str


class MediaUpdateRequest(BaseModel):
    alt: str | None = None
    folder_id: str | None = None
    # Mismo límite que la columna `filename` (`String(255)`): rechazado
    # aquí con 422 en vez de dejar que Postgres lo haga con un 500.
    filename: str | None = Field(default=None, max_length=255)


class MediaFolderResponse(BaseModel):
    id: str
    name: str
    slug: str


class MediaFolderCreate(BaseModel):
    name: str
    slug: str
    kind: str


class PlatformMediaFolderCreate(BaseModel):
    """Igual que `MediaFolderCreate` pero sin `kind`: la biblioteca de
    plataforma tiene un único contexto (la identidad de la instalación)."""

    name: str
    slug: str


class MediaInUseError(BaseModel):
    """Cuerpo de la respuesta 409 cuando se intenta borrar un medio en uso."""

    detail: str
    used_by: list[dict[str, str]]


class MediaUsageResponse(BaseModel):
    """En qué recursos está en uso un medio — consulta previa a
    «Sobrescribir original» (irreversible), para avisar de a cuántos sitios
    afecta antes de confirmar. Mismo `used_by` que `MediaInUseError`."""

    used_by: list[dict[str, str]]
