"""Política de complejidad de contraseñas del registro público."""

from __future__ import annotations

import pytest

from app.core.security import password_meets_complexity


@pytest.mark.parametrize(
    "password",
    [
        "Una-Contraseña-Larga-1!",
        "Abcdefg1!",
        "P@ssw0rd123",
    ],
)
def test_contrasenas_validas(password: str) -> None:
    assert password_meets_complexity(password) is True


@pytest.mark.parametrize(
    "password",
    [
        "sin-mayuscula-1!",  # sin mayúscula
        "SIN-MINUSCULA-1!",  # sin minúscula
        "SinNumeroNiSimbolo",  # sin número ni carácter especial
        "SinSimbolo123",  # sin carácter especial
        "Corto1!",  # menos de 8 caracteres
    ],
)
def test_contrasenas_invalidas(password: str) -> None:
    assert password_meets_complexity(password) is False
