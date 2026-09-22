"""Almacenamiento de objetos tras una interfaz agnóstica del proveedor.

Toda clave se construye con `build_object_key`, que fuerza el prefijo
`orgs/{organization_id}/`: una organización no puede escribir en el espacio de otra
aunque el llamante se equivoque. Toda subida pasa por `validate_upload`, que mira
los bytes reales y no la extensión ni el `Content-Type` declarado.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Protocol

import aioboto3
import magic
from botocore.config import Config as BotoConfig

from app.core.config import get_settings
from app.shared.errors import ValidationDomainError

# SVG queda fuera a propósito: admite <script> y sería XSS almacenado servido desde
# nuestro propio host. Volverá cuando exista un saneado explícito.
ALLOWED_IMAGE_MIMES: dict[str, str] = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
}

# Justificantes de gasto (fase 7 del PRD): las tres imágenes de siempre más
# PDF. Nunca se usa como valor por defecto de `validate_upload` — todo
# llamador de esta fase lo pasa explícito junto con `max_bytes=
# settings.max_document_bytes`, para no dejar que un justificante de 6 MB
# pase por el límite pensado para logos (plan.md Decisión #9).
ALLOWED_DOCUMENT_MIMES: dict[str, str] = {
    **ALLOWED_IMAGE_MIMES,
    "application/pdf": "pdf",
}


class UploadedObject:
    """Resultado de una subida."""

    __slots__ = ("key", "content_type", "size")

    def __init__(self, key: str, content_type: str, size: int) -> None:
        self.key = key
        self.content_type = content_type
        self.size = size


def build_object_key(organization_id: uuid.UUID, kind: str, extension: str) -> str:
    """`orgs/{organization_id}/{kind}/{uuid}.{ext}` — nunca acepta una clave externa."""
    kind_limpio = kind.strip("/").replace("..", "")
    if not kind_limpio:
        raise ValueError("El tipo de objeto no puede estar vacío")
    return f"orgs/{organization_id}/{kind_limpio}/{uuid.uuid4().hex}.{extension}"


def build_platform_object_key(kind: str, extension: str) -> str:
    """`platform/{kind}/{uuid}.{ext}` — objetos de la instalación, no de un tenant.

    Mismo contrato que `build_object_key` (la clave la construye siempre el
    servidor, nunca un valor de la petición), pero con prefijo propio para que
    los objetos de plataforma no se confundan con los de una organización en el
    mismo bucket. No lleva `organization_id` porque no pertenecen a ninguna.
    """
    kind_limpio = kind.strip("/").replace("..", "")
    if not kind_limpio:
        raise ValueError("El tipo de objeto no puede estar vacío")
    return f"platform/{kind_limpio}/{uuid.uuid4().hex}.{extension}"


def validate_upload(
    contenido: bytes,
    *,
    max_bytes: int | None = None,
    allowed_mimes: dict[str, str] | None = None,
) -> tuple[str, str]:
    """Valida un fichero por sus bytes reales, nunca por su extensión o `Content-Type` declarado.

    Devuelve `(mime, extensión)`. Lanza `ValidationDomainError` si el tipo no está
    permitido o si excede el tamaño máximo. `allowed_mimes` por defecto es
    `ALLOWED_IMAGE_MIMES` (retrocompatible con las llamadas de branding/portada/logo
    existentes); los justificantes de gasto pasan `ALLOWED_DOCUMENT_MIMES` explícito.
    """
    settings = get_settings()
    limite = max_bytes if max_bytes is not None else settings.max_image_bytes
    mimes = allowed_mimes if allowed_mimes is not None else ALLOWED_IMAGE_MIMES

    if not contenido:
        raise ValidationDomainError("El fichero está vacío.")
    if len(contenido) > limite:
        raise ValidationDomainError(
            f"El fichero supera el tamaño máximo de {limite // (1024 * 1024)} MB."
        )

    mime = magic.from_buffer(contenido[:2048], mime=True)
    extension = mimes.get(mime)
    if extension is None:
        tipos = ", ".join(sorted(mimes))
        raise ValidationDomainError(f"Tipo de fichero no permitido: {mime}. Se aceptan {tipos}.")
    return mime, extension


class StorageProvider(Protocol):
    """Contrato mínimo de almacenamiento usado por los servicios."""

    async def ensure_bucket(self) -> None: ...

    async def put_object(
        self, key: str, contenido: bytes, content_type: str, *, content_disposition: str = "inline"
    ) -> None: ...

    async def get_object(self, key: str) -> tuple[bytes, str]: ...

    async def delete_object(self, key: str) -> None: ...

    async def presigned_get_url(self, key: str, *, expires_in: int = 3600) -> str: ...

    async def presigned_put_url(
        self, key: str, content_type: str, *, expires_in: int = 900
    ) -> str: ...

    def public_url(self, key: str) -> str: ...

    async def healthcheck(self) -> bool: ...


class S3StorageProvider:
    """Implementación S3 (SeaweedFS por defecto, path-style)."""

    def __init__(self) -> None:
        settings = get_settings()
        self._bucket = settings.s3_bucket
        self._public_base_url = settings.s3_public_base_url
        self._session = aioboto3.Session()
        self._client_kwargs: dict[str, Any] = {
            "service_name": "s3",
            "endpoint_url": settings.s3_endpoint,
            "aws_access_key_id": settings.s3_access_key,
            "aws_secret_access_key": settings.s3_secret_key,
            "region_name": settings.s3_region,
            # SeaweedFS no soporta virtual-host addressing.
            "config": BotoConfig(s3={"addressing_style": "path"}, signature_version="s3v4"),
        }

    def _client(self) -> Any:
        return self._session.client(**self._client_kwargs)

    async def ensure_bucket(self) -> None:
        async with self._client() as s3:
            try:
                await s3.head_bucket(Bucket=self._bucket)
            except Exception:
                await s3.create_bucket(Bucket=self._bucket)

    async def put_object(
        self, key: str, contenido: bytes, content_type: str, *, content_disposition: str = "inline"
    ) -> None:
        async with self._client() as s3:
            await s3.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=contenido,
                ContentType=content_type,
                # `inline` solo es seguro porque el tipo por defecto ya está en la
                # lista de imágenes permitidas; los justificantes de gasto (que
                # admiten PDF, capaz de ejecutar JavaScript) pasan `attachment`
                # explícito — nunca se sirven `inline` desde nuestro origen.
                ContentDisposition=content_disposition,
            )

    async def get_object(self, key: str) -> tuple[bytes, str]:
        """Lee un objeto completo. Solo para el proxy autenticado de descarga
        (justificantes): nunca se expone por `public_url`."""
        async with self._client() as s3:
            respuesta = await s3.get_object(Bucket=self._bucket, Key=key)
            contenido: bytes = await respuesta["Body"].read()
            content_type: str = respuesta.get("ContentType", "application/octet-stream")
            return contenido, content_type

    async def delete_object(self, key: str) -> None:
        async with self._client() as s3:
            await s3.delete_object(Bucket=self._bucket, Key=key)

    async def presigned_get_url(self, key: str, *, expires_in: int = 3600) -> str:
        async with self._client() as s3:
            url: str = await s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": key},
                ExpiresIn=expires_in,
            )
            return url

    async def presigned_put_url(self, key: str, content_type: str, *, expires_in: int = 900) -> str:
        if content_type not in ALLOWED_IMAGE_MIMES:
            raise ValidationDomainError(f"Tipo de fichero no permitido: {content_type}.")
        async with self._client() as s3:
            url: str = await s3.generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": self._bucket,
                    "Key": key,
                    "ContentType": content_type,
                },
                ExpiresIn=expires_in,
            )
            return url

    def public_url(self, key: str) -> str:
        """URL pública servida por Caddy en `/media/*`, no por el endpoint S3."""
        return f"{self._public_base_url}/{key.lstrip('/')}"

    async def healthcheck(self) -> bool:
        try:
            async with self._client() as s3:
                await s3.head_bucket(Bucket=self._bucket)
            return True
        except Exception:
            return False


_provider: StorageProvider | None = None


def get_storage() -> StorageProvider:
    """Proveedor único de almacenamiento."""
    global _provider
    if _provider is None:
        _provider = S3StorageProvider()
    return _provider


def public_url_versionada(key: str, actualizado_en: datetime) -> str:
    """`public_url()` con `?v=<epoch>` — `/media/*` se sirve con
    `Cache-Control: ... immutable` (Caddyfile) porque la clave lleva un UUID
    y, hasta ahora, su contenido nunca cambiaba tras subirse. «Sobrescribir
    original» (`media/service.py`) rompe justo esa asunción: reemplaza los
    bytes de una `object_key` ya existente sin cambiarla. Sin este parámetro,
    el navegador (y cualquier CDN intermedio) seguiría sirviendo la imagen
    vieja hasta que expire la caché — el mismo síntoma que el hallazgo
    original del usuario ("la imagen no hace nada"), pero en producción y
    durante 24h en vez de una recarga. `updated_at` cambia solo cuando
    cambian los bytes o los metadatos (columna con `onupdate`), así que una
    imagen nunca sobrescrita sigue teniendo una URL estable de verdad.

    En milisegundos, no segundos: subir y sobrescribir en la misma prueba (o
    en dos peticiones humanas seguidas) puede caer dentro del mismo segundo,
    lo que dejaría el `?v=` idéntico y el caché sin invalidar de verdad."""
    return f"{get_storage().public_url(key)}?v={int(actualizado_en.timestamp() * 1000)}"
