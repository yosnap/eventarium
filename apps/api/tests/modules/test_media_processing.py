"""Procesamiento de imagen de la biblioteca de medios
(`app/modules/media/processing.py`). Sin BD ni red: funciones puras."""

from __future__ import annotations

import io

import pytest
from PIL import Image

from app.modules.media.processing import procesar_imagen
from app.shared.errors import ValidationDomainError


def _png(ancho: int, alto: int) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (ancho, alto), color=(20, 120, 200)).save(buffer, format="PNG")
    return buffer.getvalue()


def _gif(ancho: int, alto: int) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (ancho, alto), color=(200, 20, 20)).save(buffer, format="GIF")
    return buffer.getvalue()


def test_convierte_png_a_webp_y_redimensiona_al_maximo_del_perfil() -> None:
    resultado = procesar_imagen(_png(2000, 1000), "image/png", "logo")
    assert resultado.mime_type == "image/webp"
    assert resultado.width <= 800
    assert resultado.height <= 800
    # Proporción conservada (2:1).
    assert abs(resultado.width / resultado.height - 2.0) < 0.05


def test_no_agranda_una_imagen_mas_pequena_que_el_maximo() -> None:
    resultado = procesar_imagen(_png(100, 50), "image/png", "default")
    assert resultado.width == 100
    assert resultado.height == 50


def test_gif_se_sube_tal_cual_sin_recodificar() -> None:
    original = _gif(300, 200)
    resultado = procesar_imagen(original, "image/gif", "default")
    assert resultado.mime_type == "image/gif"
    assert resultado.contenido == original
    assert resultado.width == 300
    assert resultado.height == 200


def test_rechaza_una_imagen_por_encima_del_techo_de_pixeles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Generar una imagen real por encima de 40 megapíxeles sería demasiado
    # lento/pesado para un test; se baja el techo del módulo a algo que una
    # imagen pequeña sí supere, y se comprueba que el rechazo llega desde
    # `procesar_imagen` (no solo desde la constante en aislamiento).
    monkeypatch.setattr("app.modules.media.processing.LIMITE_DE_PIXELES", 100)
    with pytest.raises(ValidationDomainError):
        procesar_imagen(_png(50, 50), "image/png", "logo")


def test_rechaza_un_fichero_que_no_es_una_imagen() -> None:
    with pytest.raises(ValidationDomainError):
        procesar_imagen(b"esto no es una imagen", "image/png", "logo")
