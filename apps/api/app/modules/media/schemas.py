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


class MediaCropRequest(BaseModel):
    """Rectángulo de recorte normalizado (0-1 respecto al tamaño actual)."""

    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)


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
