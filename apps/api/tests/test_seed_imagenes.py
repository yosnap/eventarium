"""Los PNG que genera el seed deben decodificar completos.

Regresión de un bug real: `_logo` escribía las filas del borde con un solo
píxel en lugar de repetirlo a lo ancho, así que el IDAT no cubría el tamaño
que declara el IHDR y los navegadores recibían una imagen truncada. `file`
y `sips` solo leen la cabecera, así que el PNG «parecía» válido: la única
comprobación fiable es descomprimir el IDAT y medir.
"""

from __future__ import annotations

import struct
import zlib

from scripts.seed_eventos_demo.imagenes import (
    ALTO_PORTADA,
    ANCHO_PORTADA,
    LADO_LOGO,
    _logo,
    _portada,
)


def _medir_idat(png: bytes) -> tuple[int, int, int]:
    """Devuelve (ancho, alto, bytes del IDAT descomprimido) de un PNG plano RGB."""
    assert png[:8] == b"\x89PNG\r\n\x1a\n", "no es un PNG"
    pos = 8
    idat = b""
    ancho = alto = 0
    while pos < len(png):
        (longitud,) = struct.unpack(">I", png[pos : pos + 4])
        tipo = png[pos + 4 : pos + 8]
        if tipo == b"IHDR":
            ancho, alto = struct.unpack(">II", png[pos + 8 : pos + 16])
        elif tipo == b"IDAT":
            idat += png[pos + 8 : pos + 8 + longitud]
        pos += 12 + longitud
    return ancho, alto, len(zlib.decompress(idat))


def test_logo_cubre_todo_el_lienzo() -> None:
    ancho, alto, crudo = _medir_idat(_logo("Nébula Data Labs"))
    assert (ancho, alto) == (LADO_LOGO, LADO_LOGO)
    # RGB de 8 bits sin filtro: alto × (1 byte de filtro + ancho × 3 canales).
    assert crudo == alto * (ancho * 3 + 1)


def test_portada_cubre_todo_el_lienzo() -> None:
    ancho, alto, crudo = _medir_idat(_portada("demo-completo-presencial"))
    assert (ancho, alto) == (ANCHO_PORTADA, ALTO_PORTADA)
    assert crudo == alto * (ancho * 3 + 1)
