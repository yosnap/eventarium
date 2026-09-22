"""Rotación de `AI_SETTINGS_ENCRYPTION_KEY` (`rotate-ai-encryption-key`).

Es el único camino que descifra y re-cifra **todas** las credenciales de la
instalación de golpe: se prueba de ida y vuelta contra la base de datos real,
con la fila de plataforma y la de una organización.
"""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from app.cli import recifrar_claves_de_ia
from app.core.database import SessionMaintenance
from app.modules.ai_gateway.crypto import cifrar_clave, descifrar_clave
from app.modules.ai_gateway.errores import CredencialIlegible
from app.modules.ai_gateway.models import (
    ID_FILA_DE_PLATAFORMA,
    OrganizationAiSettings,
    PlatformAiSettings,
)
from tests.conftest import OrganizacionDePrueba

CLAVE_DE_PLATAFORMA = "sk-clave-de-plataforma-1111"
CLAVE_DE_ORGANIZACION = "sk-clave-de-organizacion-2222"


async def test_la_rotacion_recifra_todas_las_filas_con_la_clave_nueva(
    organizacion: OrganizacionDePrueba,
) -> None:
    antigua = Fernet.generate_key().decode()
    nueva = Fernet.generate_key().decode()

    async with SessionMaintenance() as session:
        session.add(
            PlatformAiSettings(
                id=ID_FILA_DE_PLATAFORMA,
                provider="nan_builders",
                default_model="deepseek-v4-flash",
                api_key_encrypted=cifrar_clave(CLAVE_DE_PLATAFORMA, clave_de_cifrado=antigua),
                api_key_hint=CLAVE_DE_PLATAFORMA[-4:],
            )
        )
        session.add(
            OrganizationAiSettings(
                organization_id=organizacion.id,
                provider="cheaper_inference",
                default_model="gpt-5.4",
                api_key_encrypted=cifrar_clave(CLAVE_DE_ORGANIZACION, clave_de_cifrado=antigua),
                api_key_hint=CLAVE_DE_ORGANIZACION[-4:],
            )
        )
        await session.commit()

    total = await recifrar_claves_de_ia(clave_antigua=antigua, clave_nueva=nueva)
    assert total == 2

    async with SessionMaintenance() as session:
        plataforma = await session.scalar(select(PlatformAiSettings))
        propia = await session.scalar(select(OrganizationAiSettings))
    assert plataforma is not None and propia is not None

    for cifrada, en_claro in (
        (plataforma.api_key_encrypted, CLAVE_DE_PLATAFORMA),
        (propia.api_key_encrypted, CLAVE_DE_ORGANIZACION),
    ):
        assert cifrada is not None
        assert descifrar_clave(cifrada, clave_de_cifrado=nueva) == en_claro
        # Y ya no descifran con la antigua: la rotación escribió de verdad.
        with pytest.raises(CredencialIlegible):
            descifrar_clave(cifrada, clave_de_cifrado=antigua)
