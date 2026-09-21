"""Cifrado en reposo de las claves de proveedor y su validación de arranque.

Sin base de datos: son funciones puras más el validador de `Settings`.
"""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError

from app.core.config import Settings, get_settings
from app.modules.ai_gateway.crypto import (
    cifrado_disponible,
    cifrar_clave,
    descifrar_clave,
    pista_de_clave,
)
from app.modules.ai_gateway.errores import CifradoNoConfigurado, CredencialIlegible
from tests.ai_gateway_test_helpers import CLAVE_DE_PROVEEDOR


def test_ida_y_vuelta(cifrado: str) -> None:
    cifrada = cifrar_clave(CLAVE_DE_PROVEEDOR)
    assert cifrada != CLAVE_DE_PROVEEDOR
    assert CLAVE_DE_PROVEEDOR not in cifrada
    assert descifrar_clave(cifrada) == CLAVE_DE_PROVEEDOR


def test_dos_cifrados_de_la_misma_clave_no_son_iguales(cifrado: str) -> None:
    """Fernet lleva IV aleatorio: dos filas con la misma clave no se delatan."""
    assert cifrar_clave(CLAVE_DE_PROVEEDOR) != cifrar_clave(CLAVE_DE_PROVEEDOR)


def test_sin_clave_de_cifrado_es_error_de_dominio(sin_cifrado: None) -> None:
    assert cifrado_disponible() is False
    with pytest.raises(CifradoNoConfigurado):
        cifrar_clave(CLAVE_DE_PROVEEDOR)


def test_token_de_otra_clave_no_descifra(cifrado: str) -> None:
    """Rotar la clave sin re-cifrar da `CredencialIlegible`, nunca un 500."""
    ajena = Fernet(Fernet.generate_key()).encrypt(CLAVE_DE_PROVEEDOR.encode()).decode()
    with pytest.raises(CredencialIlegible):
        descifrar_clave(ajena)


def test_texto_que_no_es_un_token(cifrado: str) -> None:
    with pytest.raises(CredencialIlegible):
        descifrar_clave("esto-no-es-un-token-fernet")


def test_pista_son_los_ultimos_cuatro_caracteres() -> None:
    assert pista_de_clave("sk-abcdefgh1234") == "1234"


def test_una_clave_corta_no_deja_pista() -> None:
    """Devolverla entera sería justo lo que la pista evita."""
    assert pista_de_clave("sk-1") == ""


def _entorno_minimo(**extra: str) -> dict[str, str]:
    base = get_settings()
    valores = {
        "database_url": base.database_url,
        "database_migrations_url": base.database_migrations_url,
        "s3_endpoint": base.s3_endpoint,
        "s3_access_key": base.s3_access_key,
        "s3_secret_key": base.s3_secret_key,
        "s3_public_base_url": base.s3_public_base_url,
        "redis_url": base.redis_url,
        "jwt_secret": base.jwt_secret,
        "ticket_qr_secret": base.ticket_qr_secret,
    }
    valores.update(extra)
    return valores


def test_una_clave_de_cifrado_invalida_impide_arrancar() -> None:
    """Falla al construir `Settings`, no en el primer `PUT`."""
    with pytest.raises(ValidationError):
        Settings(**_entorno_minimo(ai_settings_encryption_key="no-es-fernet"))  # type: ignore[arg-type]


def test_una_clave_de_cifrado_valida_arranca() -> None:
    ajustes = Settings(**_entorno_minimo(ai_settings_encryption_key=Fernet.generate_key().decode()))  # type: ignore[arg-type]
    assert ajustes.ai_settings_encryption_key


def test_sin_clave_de_cifrado_arranca_igual() -> None:
    """Una instalación que no usa IA no deja de arrancar por esto."""
    ajustes = Settings(**_entorno_minimo(ai_settings_encryption_key=""))  # type: ignore[arg-type]
    assert ajustes.ai_settings_encryption_key == ""
