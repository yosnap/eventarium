"""Almacenamiento de objetos tras una interfaz agnóstica del proveedor.

Toda clave se construye con `build_object_key`, que fuerza el prefijo
`orgs/{organization_id}/`: una organización no puede escribir en el espacio de otra
aunque el llamante se equivoque. Toda subida pasa por `validate_upload`, que mira
los bytes reales y no la extensión ni el `Content-Type` declarado.
"""

from __future__ import annotations

import uuid
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


def validate_upload(contenido: bytes, *, max_bytes: int | None = None) -> tuple[str, str]:
    """Valida una imagen por sus bytes reales.

    Devuelve `(mime, extensión)`. Lanza `ValidationDomainError` si el tipo no está
    permitido o si excede el tamaño máximo.
    """
    settings = get_settings()
    limite = max_bytes if max_bytes is not None else settings.max_image_bytes

    if not contenido:
        raise ValidationDomainError("El fichero está vacío.")
    if len(contenido) > limite:
        raise ValidationDomainError(
            f"El fichero supera el tamaño máximo de {limite // (1024 * 1024)} MB."
        )

    mime = magic.from_buffer(contenido[:2048], mime=True)
    extension = ALLOWED_IMAGE_MIMES.get(mime)
    if extension is None:
        raise ValidationDomainError(
            f"Tipo de fichero no permitido: {mime}. Se aceptan PNG, JPEG y WebP."
        )
    return mime, extension


class StorageProvider(Protocol):
    """Contrato mínimo de almacenamiento usado por los servicios."""

    async def ensure_bucket(self) -> None: ...

    async def put_object(self, key: str, contenido: bytes, content_type: str) -> None: ...

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

    async def put_object(self, key: str, contenido: bytes, content_type: str) -> None:
        async with self._client() as s3:
            await s3.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=contenido,
                ContentType=content_type,
                # `inline` solo es seguro porque el tipo ya está en la lista permitida.
                ContentDisposition="inline",
            )

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
