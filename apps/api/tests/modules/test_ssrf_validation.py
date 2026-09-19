"""Validación SSRF de la biblioteca de medios
(`app/modules/media/ssrf.py`). Sin red: se prueba contra IPs literales
conocidas, nunca resolviendo un hostname real (evita depender de cómo
resuelva DNS el entorno de CI)."""

from __future__ import annotations

import pytest

from app.modules.media.ssrf import validar_url_publica_segura
from app.shared.errors import ValidationDomainError


def test_rechaza_esquema_no_https() -> None:
    with pytest.raises(ValidationDomainError):
        validar_url_publica_segura("http://ejemplo.com/imagen.png")


def test_rechaza_localhost_por_nombre() -> None:
    with pytest.raises(ValidationDomainError):
        validar_url_publica_segura("https://localhost/imagen.png")


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",  # loopback
        "10.0.0.5",  # RFC1918 privada
        "172.16.0.5",  # RFC1918 privada
        "192.168.1.5",  # RFC1918 privada
        "169.254.169.254",  # metadata de nube (AWS/GCP/Azure)
        "0.0.0.0",  # noqa: S104 — sin especificar, no un bind; es un caso de prueba
        "::1",  # loopback IPv6
        "fd00::1",  # unique local IPv6 (equivalente a RFC1918)
        "fe80::1",  # link-local IPv6
    ],
)
def test_rechaza_ips_internas_o_reservadas_por_literal(ip: str) -> None:
    with pytest.raises(ValidationDomainError):
        validar_url_publica_segura(f"https://{ip}/imagen.png")


def test_acepta_una_ip_publica_por_literal() -> None:
    # 8.8.8.8 (resolutor público de Google): IP pública real, sin depender
    # de que ningún hostname resuelva de una forma concreta en CI.
    assert validar_url_publica_segura("https://8.8.8.8/imagen.png") == "https://8.8.8.8/imagen.png"


def test_rechaza_host_vacio() -> None:
    with pytest.raises(ValidationDomainError):
        validar_url_publica_segura("https:///imagen.png")
