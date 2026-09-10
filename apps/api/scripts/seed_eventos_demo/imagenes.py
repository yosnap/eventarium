"""Generación de imágenes PNG (portadas y logos) sin dependencias externas.

El proyecto no tiene Pillow y el storage rechaza SVG (`ALLOWED_IMAGE_MIMES` en
`app/core/storage.py` admite solo PNG/JPEG/WebP, validados por bytes reales), así
que los PNG se construyen a mano: firma + IHDR + IDAT (`zlib.compress` de las
scanlines) + IEND. Son imágenes abstractas y deterministas derivadas del slug o
del nombre — sin texto, que ya lo pinta la propia ficha.
"""

from __future__ import annotations

import hashlib
import struct
import zlib

from scripts.seed_eventos_demo.datos import COORDENADAS

ANCHO_PORTADA = 1200
ALTO_PORTADA = 400
LADO_LOGO = 240


def _chunk(tipo: bytes, datos: bytes) -> bytes:
    """Bloque PNG con su CRC, según la especificación."""
    return (
        struct.pack(">I", len(datos))
        + tipo
        + datos
        + struct.pack(">I", zlib.crc32(tipo + datos) & 0xFFFFFFFF)
    )


def _png(filas: list[bytes], ancho: int, alto: int) -> bytes:
    """PNG RGB de 8 bits a partir de las filas ya construidas (sin canal alfa)."""
    cabecera = struct.pack(">IIBBBBB", ancho, alto, 8, 2, 0, 0, 0)
    crudo = b"".join(filas)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", cabecera)
        + _chunk(b"IDAT", zlib.compress(crudo, 9))
        + _chunk(b"IEND", b"")
    )


def _color(texto: str, *, claro: int = 60, oscuro: int = 200) -> tuple[int, int, int]:
    """Color RGB determinista y legible derivado de un texto, para que cada
    portada y cada logo sean reconociblemente distintos sin salir del mismo rango."""
    digest = hashlib.sha256(texto.encode()).digest()
    return (
        claro + digest[0] % (oscuro - claro),
        claro + digest[1] % (oscuro - claro),
        claro + digest[2] % (oscuro - claro),
    )


def _portada(slug: str) -> bytes:
    """Degradado vertical entre dos tonos derivados del slug del evento."""
    inicio = _color(slug, claro=30, oscuro=90)
    fin = _color(slug + "-fin", claro=140, oscuro=220)
    filas = []
    for y in range(ALTO_PORTADA):
        t = y / (ALTO_PORTADA - 1)
        fila = bytes(round(inicio[i] + (fin[i] - inicio[i]) * t) for i in range(3))
        filas.append(b"\x00" + fila * ANCHO_PORTADA)
    return _png(filas, ANCHO_PORTADA, ALTO_PORTADA)


def _logo(nombre: str) -> bytes:
    """Cuadrado sólido con un borde más claro, cuadrado al tamaño que espera el CSS."""
    relleno = _color(nombre, claro=40, oscuro=160)
    borde = _color(nombre + "-borde", claro=200, oscuro=245)
    grosor = LADO_LOGO // 12
    filas = []
    for y in range(LADO_LOGO):
        en_borde_y = y < grosor or y >= LADO_LOGO - grosor
        if en_borde_y:
            fila = bytes(borde)
        else:
            fila = (
                bytes(borde) * grosor
                + bytes(relleno) * (LADO_LOGO - 2 * grosor)
                + bytes(borde) * grosor
            )
        filas.append(b"\x00" + fila)
    return _png(filas, LADO_LOGO, LADO_LOGO)


def _sin_acentos(texto: str) -> str:
    """Minúsculas y sin diacríticos, para que «València» empareje con «Valencia»
    sin listar cada variante ortográfica de cada ciudad."""
    reemplazos = str.maketrans("áàäâãéèëêíìïîóòöôõúùüûñç", "aaaaaeeeeiiiiooooouuuunc")
    return texto.lower().translate(reemplazos)


async def _geocode_por_tabla(address: str | None) -> tuple[float, float] | None:
    """Devuelve las coordenadas de la ciudad que aparezca en `address`, sin red.

    Reemplaza a `events_service.geocode_address` (Nominatim) durante el seed: el
    resultado es determinista, no depende de Internet y no consume el límite de
    1 petición/segundo. Si no reconoce ninguna ciudad, devuelve `None`, que el
    servicio traduce a «sin coordenadas» — exactamente el mismo contrato.
    """
    if not address:
        return None
    direccion = _sin_acentos(address)
    for ciudad, coordenadas in COORDENADAS.items():
        if _sin_acentos(ciudad) in direccion:
            return coordenadas
    return None
