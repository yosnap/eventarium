"""`sanear()`: la clave de proveedor no debe sobrevivir en ninguna de sus
formas transformadas habituales dentro de un mensaje de error eco."""

from __future__ import annotations

import base64
from urllib.parse import quote

from app.modules.ai_gateway.errores import sanear


def test_sanear_sustituye_el_literal_en_texto_plano() -> None:
    assert sanear("clave inválida: sk-abc123", "sk-abc123") == "clave inválida: ***"


def test_sanear_sin_clave_no_toca_el_texto() -> None:
    assert sanear("mensaje sin nada que ocultar", "") == "mensaje sin nada que ocultar"


def test_sanear_sustituye_la_clave_en_un_header_basic_auth_eco() -> None:
    clave = "sk-abc123"
    basic = base64.b64encode(f"{clave}:".encode()).decode()
    texto = f"petición rechazada: Authorization: Basic {basic}"

    saneado = sanear(texto, clave)

    assert basic not in saneado
    assert "***" in saneado


def test_sanear_sustituye_la_clave_percent_encoded_en_una_url_eco() -> None:
    clave = "sk-abc/123+456"
    codificada = quote(clave, safe="")
    texto = f"GET /v1/models?api_key={codificada} -> 401"

    saneado = sanear(texto, clave)

    assert codificada not in saneado
    assert "***" in saneado


def test_sanear_no_falla_si_la_clave_no_aparece_de_ninguna_forma() -> None:
    assert sanear("error genérico del proveedor", "sk-abc123") == "error genérico del proveedor"
