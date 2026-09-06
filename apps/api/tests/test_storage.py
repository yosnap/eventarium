"""Almacenamiento de objetos: validación por contenido y espacio por organización."""

from __future__ import annotations

import base64
import uuid

import pytest

from app.core.storage import build_object_key, get_storage, validate_upload
from app.shared.errors import ValidationDomainError

# Ficheros reales mínimos: libmagic mira más allá de la firma inicial.
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
JPEG = bytes.fromhex("ffd8ffe000104a464946") + b"\x00" * 32
WEBP = b"RIFF" + (40).to_bytes(4, "little") + b"WEBPVP8 " + b"\x00" * 32
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'


def test_la_clave_siempre_lleva_el_prefijo_de_la_organizacion() -> None:
    organizacion = uuid.uuid4()
    clave = build_object_key(organizacion, "branding/logo", "png")
    assert clave.startswith(f"orgs/{organizacion}/branding/logo/")
    assert clave.endswith(".png")


def test_dos_claves_seguidas_no_colisionan() -> None:
    organizacion = uuid.uuid4()
    assert build_object_key(organizacion, "logo", "png") != build_object_key(
        organizacion, "logo", "png"
    )


@pytest.mark.parametrize(("contenido", "extension"), [(PNG, "png"), (JPEG, "jpg"), (WEBP, "webp")])
def test_acepta_los_formatos_permitidos(contenido: bytes, extension: str) -> None:
    _, resultado = validate_upload(contenido)
    assert resultado == extension


def test_rechaza_svg() -> None:
    """SVG admite <script>: servido desde nuestro host sería XSS almacenado."""
    with pytest.raises(ValidationDomainError):
        validate_upload(SVG)


def test_rechaza_un_ejecutable_disfrazado_de_imagen() -> None:
    """La extensión no decide nada: se miran los bytes reales."""
    with pytest.raises(ValidationDomainError):
        validate_upload(b"MZ\x90\x00" + b"\x00" * 64)


def test_rechaza_ficheros_demasiado_grandes() -> None:
    with pytest.raises(ValidationDomainError):
        validate_upload(PNG + b"\x00" * 1024, max_bytes=64)


def test_rechaza_fichero_vacio() -> None:
    with pytest.raises(ValidationDomainError):
        validate_upload(b"")


async def test_subida_y_url_publica_contra_seaweedfs() -> None:
    almacen = get_storage()
    organizacion = uuid.uuid4()
    clave = build_object_key(organizacion, "branding/logo", "png")

    await almacen.put_object(clave, PNG, "image/png")
    try:
        url = almacen.public_url(clave)
        assert url.endswith(clave)
        assert "/media/" in url

        firmada = await almacen.presigned_get_url(clave)
        assert clave in firmada
    finally:
        await almacen.delete_object(clave)


async def test_presigned_put_rechaza_tipos_no_permitidos() -> None:
    almacen = get_storage()
    clave = build_object_key(uuid.uuid4(), "branding/logo", "svg")
    with pytest.raises(ValidationDomainError):
        await almacen.presigned_put_url(clave, "image/svg+xml")
