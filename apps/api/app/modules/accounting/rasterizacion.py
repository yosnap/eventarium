"""Rasterización de justificantes antes de enviarlos al motor de visión.

Vive **antes** del adaptador de OCR y fuera de él a propósito: el adaptador
solo acepta imágenes, y esa es la garantía por diseño de que ningún PDF llega
nunca a un proveedor externo (plan.md Decisión #10). Un PDF admite JavaScript,
adjuntos y referencias remotas; una imagen rasterizada no lleva nada de eso.

El límite de páginas se aplica **al convertir**, no contando antes las páginas
del PDF crudo: contar exige ya parsear el documento, que es justo la parte
insegura, así que se abre una vez y se convierten como mucho `max_paginas`.

`pypdfium2` y no `pdf2image`: trae el binario de PDFium dentro de la rueda, sin
añadir `poppler-utils` a la imagen Docker.

Todo lo que pypdfium2 o Pillow puedan lanzar sobre un fichero malformado se
traduce a `DocumentoIlegible`, que el worker convierte en `payload_invalido`:
un justificante roto deja el borrador fallido y explicado, nunca revienta el
worker.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

from app.shared.errors import ValidationDomainError

#: Formato de las páginas rasterizadas. PNG y no WebP: es el formato de imagen
#: que cualquier proveedor OpenAI-compatible acepta sin discusión, y aquí no
#: se busca compresión sino que el modelo lo lea.
MIME_RASTERIZADO = "image/png"
EXTENSION_RASTERIZADA = "png"

#: Resolución nominal de un PDF: 72 puntos por pulgada. Se usa para traducir
#: el ancho en puntos de la página al factor de escala que pide PDFium.
PUNTOS_POR_PULGADA = 72.0

#: Tope de escala. Un PDF con una página diminuta (un ticket de 3 cm) daría
#: un factor enorme al intentar llevarlo al ancho objetivo, y con él una
#: imagen de cientos de megapíxeles.
ESCALA_MAXIMA = 6.0

#: MIME de imagen → nombre de formato de Pillow. Una imagen reescalada se
#: vuelve a codificar en su propio formato: pasar una foto JPEG a PNG la
#: haría varias veces más grande, justo lo contrario de lo que se busca.
FORMATO_DE_PILLOW = {"image/png": "PNG", "image/jpeg": "JPEG", "image/webp": "WEBP"}


class DocumentoIlegible(ValidationDomainError):
    """El documento no se puede abrir o rasterizar."""


@dataclass(frozen=True, slots=True)
class ImagenParaOcr:
    """Una imagen ya lista para el adaptador. Nunca un PDF."""

    contenido: bytes
    mime: str
    extension: str


def _escala(ancho_en_puntos: float, ancho_maximo_px: int) -> float:
    if ancho_en_puntos <= 0:
        return 1.0
    return min(ancho_maximo_px / ancho_en_puntos, ESCALA_MAXIMA)


def rasterizar_pdf(contenido: bytes, *, max_paginas: int, ancho_maximo_px: int) -> list[bytes]:
    """PDF → lista de PNG, como mucho `max_paginas`.

    Síncrona y bloqueante (PDFium lo es): quien la llame desde el bucle de
    eventos tiene que hacerlo con `asyncio.to_thread`.
    """
    import pypdfium2 as pdfium
    from PIL import Image

    documento = None
    try:
        documento = pdfium.PdfDocument(contenido)
        total = len(documento)
        if total == 0:
            raise DocumentoIlegible("El PDF no tiene ninguna página.")

        paginas: list[bytes] = []
        for indice in range(min(total, max_paginas)):
            pagina = documento[indice]
            mapa = pagina.render(scale=_escala(pagina.get_width(), ancho_maximo_px))
            imagen: Image.Image = mapa.to_pil()
            try:
                buffer = io.BytesIO()
                imagen.convert("RGB").save(buffer, format="PNG", optimize=True)
                paginas.append(buffer.getvalue())
            finally:
                imagen.close()
        return paginas
    except DocumentoIlegible:
        raise
    except Exception as error:  # noqa: BLE001 - PDFium lanza tipos propios y genéricos
        raise DocumentoIlegible("No se ha podido leer el PDF del justificante.") from error
    finally:
        if documento is not None:
            documento.close()


def reescalar_imagen(contenido: bytes, mime: str, *, ancho_maximo_px: int) -> bytes:
    """Lleva una imagen subida al mismo ancho máximo que las páginas de un PDF.

    Sin esto, un justificante fotografiado con el móvil viaja al modelo con
    sus megapíxeles enteros: tokens de más en cada llamada y más riesgo de que
    el proveedor rechace el cuerpo. Devuelve los bytes originales cuando la
    imagen ya cabe, para no recodificar sin necesidad.

    Síncrona y bloqueante, igual que `rasterizar_pdf`: quien la llame desde el
    bucle de eventos tiene que hacerlo con `asyncio.to_thread`.
    """
    from PIL import Image

    formato = FORMATO_DE_PILLOW.get(mime)
    if formato is None:
        raise DocumentoIlegible(f"Tipo de justificante no rasterizable: {mime}.")
    try:
        with Image.open(io.BytesIO(contenido)) as imagen:
            if imagen.width <= ancho_maximo_px:
                return contenido
            alto = max(1, round(imagen.height * ancho_maximo_px / imagen.width))
            # `RGB` y no el modo original: vale para los tres formatos
            # admitidos (JPEG no acepta alfa) y el canal alfa no aporta nada a
            # un motor de visión.
            reducida = imagen.convert("RGB").resize(
                (ancho_maximo_px, alto), Image.Resampling.LANCZOS
            )
            try:
                buffer = io.BytesIO()
                reducida.save(buffer, format=formato)
                return buffer.getvalue()
            finally:
                reducida.close()
    except DocumentoIlegible:
        raise
    except Exception as error:  # noqa: BLE001 - Pillow lanza tipos propios y genéricos
        raise DocumentoIlegible("No se ha podido leer la imagen del justificante.") from error


def preparar_para_ocr(
    contenido: bytes, mime: str, *, max_paginas: int, ancho_maximo_px: int
) -> list[ImagenParaOcr]:
    """Documento subido → imágenes que el adaptador puede enviar.

    Una imagen se reescala al ancho máximo si lo supera (ya la validó
    `validate_upload` por bytes reales); un PDF se rasteriza. Cualquier otro
    MIME es un fallo de programación del llamador, no una entrada de usuario:
    `validate_upload` ya rechazó todo lo demás antes de crear el borrador.
    """
    if mime == "application/pdf":
        return [
            ImagenParaOcr(contenido=pagina, mime=MIME_RASTERIZADO, extension=EXTENSION_RASTERIZADA)
            for pagina in rasterizar_pdf(
                contenido, max_paginas=max_paginas, ancho_maximo_px=ancho_maximo_px
            )
        ]

    from app.core.storage import ALLOWED_IMAGE_MIMES

    extension = ALLOWED_IMAGE_MIMES.get(mime)
    if extension is None:
        raise DocumentoIlegible(f"Tipo de justificante no rasterizable: {mime}.")
    ajustada = reescalar_imagen(contenido, mime, ancho_maximo_px=ancho_maximo_px)
    return [ImagenParaOcr(contenido=ajustada, mime=mime, extension=extension)]
