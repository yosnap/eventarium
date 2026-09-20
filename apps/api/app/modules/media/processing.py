"""Procesamiento de imagen para la biblioteca de medios.

Lista de tipos permitidos PROPIA de este módulo (`MEDIA_LIBRARY_IMAGE_MIMES`):
nunca se amplía `ALLOWED_IMAGE_MIMES` de `app/core/storage.py`, que también
gobierna `presigned_put_url` y, vía `ALLOWED_DOCUMENT_MIMES`, los
justificantes de gasto — ampliar el valor por defecto habilitaría GIF en los
cuatro llamadores existentes sin que nadie lo hubiera decidido (hallazgo de
red-team, plan `260918-1944`).
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Literal

from PIL import Image, ImageFile
from PIL.Image import DecompressionBombError

from app.shared.errors import ValidationDomainError

MEDIA_LIBRARY_IMAGE_MIMES: dict[str, str] = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
    "image/gif": "gif",
}

#: Techo de píxeles (ancho × alto) antes de decodificar completo — cierra la
#: bomba de descompresión sin necesidad de cargar el fichero entero en
#: memoria. 40 megapíxeles cubre con margen cualquier foto de cámara o móvil
#: razonable (una réflex de 24 MP declara ~24_000_000).
LIMITE_DE_PIXELES = 40_000_000

Image.MAX_IMAGE_PIXELS = LIMITE_DE_PIXELES

#: Perfiles de redimensionado. `logo`: logos/favicons/patrocinadores.
#: `default`: portadas de evento — necesitan más resolución.
_PERFILES: dict[str, tuple[int, int]] = {
    "logo": (800, 800),
    "default": (1920, 1920),
}

Perfil = Literal["logo", "default"]


@dataclass(frozen=True)
class ImagenProcesada:
    contenido: bytes
    mime_type: str
    width: int
    height: int


def _dimensiones_dentro_del_limite(buffer: bytes) -> tuple[int, int]:
    """Lee las dimensiones sin decodificar los píxeles (`Image.open` es
    perezoso: no llama a `.load()`). Lanza `ValidationDomainError` si supera
    el techo, antes de que nada intente decodificar el fichero completo."""
    try:
        with Image.open(io.BytesIO(buffer)) as imagen:
            ancho, alto = imagen.size
    except DecompressionBombError as error:
        raise ValidationDomainError("La imagen supera el límite de píxeles permitido.") from error
    except Exception as error:  # noqa: BLE001 — fichero no decodificable como imagen
        raise ValidationDomainError("No se ha podido leer la imagen.") from error

    if ancho * alto > LIMITE_DE_PIXELES:
        raise ValidationDomainError("La imagen supera el límite de píxeles permitido.")
    return ancho, alto


def procesar_imagen(buffer: bytes, mime: str, perfil: Perfil) -> ImagenProcesada:
    """Convierte a WebP y redimensiona, salvo GIF (se sube tal cual para no
    perder la animación) — ambos casos pasan primero por la comprobación de
    dimensiones."""
    ancho, alto = _dimensiones_dentro_del_limite(buffer)

    if mime == "image/gif":
        return ImagenProcesada(contenido=buffer, mime_type="image/gif", width=ancho, height=alto)

    max_ancho, max_alto = _PERFILES[perfil]
    try:
        with Image.open(io.BytesIO(buffer)) as original:
            convertida = (
                original.convert("RGBA")
                if original.mode in ("P", "LA")
                else original.convert("RGB")
            )
            if ancho > max_ancho or alto > max_alto:
                # `Image.thumbnail` mantiene la proporción y nunca agranda
                # (no hay `withoutEnlargement` explícito en Pillow: `thumbnail`
                # ya se comporta así por contrato).
                convertida.thumbnail((max_ancho, max_alto), Image.Resampling.LANCZOS)
            salida = io.BytesIO()
            convertida.save(salida, format="WEBP", quality=85)
            contenido_final = salida.getvalue()
            ancho_final, alto_final = convertida.size
    except DecompressionBombError as error:
        raise ValidationDomainError("La imagen supera el límite de píxeles permitido.") from error

    return ImagenProcesada(
        contenido=contenido_final,
        mime_type="image/webp",
        width=ancho_final,
        height=alto_final,
    )


# Pillow, por defecto, trunca en silencio un fichero cortado en vez de fallar
# — preferible que reviente con un error claro a servir una imagen a medias.
ImageFile.LOAD_TRUNCATED_IMAGES = False
