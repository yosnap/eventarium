"""Fijaciones compartidas de los tests de la pasarela de IA.

Registrado como plugin en `conftest.py` (mismo patrón que
`payments_test_helpers.py`) para que cada módulo de test no tenga que
importar las fijaciones por nombre.

La clave de cifrado la ponen **los tests**, nunca el entorno: el `.env` de
integración continua no define `AI_SETTINGS_ENCRYPTION_KEY`, así que un test
que dependiera de la del entorno pasaría en local y fallaría en CI.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from cryptography.fernet import Fernet
from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import SessionMaintenance
from app.modules.users.models import User
from tests.conftest import OrganizacionDePrueba, iniciar_sesion

#: Clave Fernet fija de la suite. Generada una vez por ejecución: no es un
#: secreto real y no sale de la base de datos de tests.
CLAVE_DE_CIFRADO = Fernet.generate_key().decode()

#: Clave de proveedor de ejemplo. Formato de NaN (`sk-…`), aunque el backend
#: no valida el prefijo de ningún proveedor a propósito.
CLAVE_DE_PROVEEDOR = "sk-clave-de-prueba-0000-1234"


@pytest.fixture
def cifrado(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """Instalación con cifrado configurado."""
    monkeypatch.setenv("AI_SETTINGS_ENCRYPTION_KEY", CLAVE_DE_CIFRADO)
    get_settings.cache_clear()
    yield CLAVE_DE_CIFRADO
    get_settings.cache_clear()


@pytest.fixture
def sin_cifrado(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Instalación sin `AI_SETTINGS_ENCRYPTION_KEY`."""
    monkeypatch.setenv("AI_SETTINGS_ENCRYPTION_KEY", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def hacer_superadmin(email: str) -> None:
    async with SessionMaintenance() as session:
        usuario = await session.scalar(select(User).where(User.email == email))
        assert usuario is not None
        usuario.is_superadmin = True
        await session.commit()


async def cabeceras_de_superadmin(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> dict[str, str]:
    """Promociona al propietario de la organización y devuelve sus cabeceras."""
    await hacer_superadmin(organizacion.owner_email)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    return cabeceras
