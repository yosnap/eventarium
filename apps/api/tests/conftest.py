"""Configuración de la suite de tests.

Los tests corren contra PostgreSQL, Redis y SeaweedFS **reales**: RLS, las cookies y
los presigned URL son justamente lo que hay que verificar, y un doble no reproduce
ninguno de los tres.

Aislamiento entre tests: `TRUNCATE … CASCADE`, no rollback de transacción. Un test de
RLS necesita abrir sus propias transacciones y fijar el contexto en cada una; una
transacción externa envolvente lo haría imposible.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

# Las variables tienen que estar puestas antes de importar nada de `app`: los motores
# se crean al importar `app.core.database`.
API_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = API_DIR.parents[1]

sys.path.insert(0, str(API_DIR))


def _cargar_env_de_tests() -> None:
    fichero = REPO_ROOT / "infra" / "env" / ".env"
    valores: dict[str, str] = {}
    if fichero.exists():
        for linea in fichero.read_text(encoding="utf-8").splitlines():
            limpia = linea.strip()
            if not limpia or limpia.startswith("#") or "=" not in limpia:
                continue
            clave, _, valor = limpia.partition("=")
            valores[clave.strip()] = valor.strip()

    os.environ["APP_ENV"] = "test"
    os.environ["DEFAULT_ORGANIZATION_SLUG"] = ""
    for clave, valor in valores.items():
        os.environ.setdefault(clave, valor)

    # La suite escribe en la base de datos de tests, nunca en la de desarrollo.
    for destino, origen in (
        ("DATABASE_URL", "TEST_DATABASE_URL"),
        ("DATABASE_MIGRATIONS_URL", "TEST_DATABASE_MIGRATIONS_URL"),
    ):
        if origen in os.environ:
            os.environ[destino] = os.environ[origen]


_cargar_env_de_tests()

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import select, text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.core.database import (  # noqa: E402
    SessionApp,
    SessionMaintenance,
    engine_app,
    engine_maintenance,
    set_organization_context,
)
from app.core.permissions import Permission  # noqa: E402
from app.core.redis_client import close_redis, get_redis  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.main import create_app  # noqa: E402
from app.modules.organizations import service as organization_service  # noqa: E402
from app.modules.organizations.models import OrganizationMember  # noqa: E402
from app.modules.roles.models import Role, RolePermission  # noqa: E402
from app.modules.roles.system_roles import OWNER_KEY  # noqa: E402
from app.modules.users.models import User  # noqa: E402

TABLAS = (
    "role_permissions",
    "role_profile_fields",
    "organization_members",
    "roles",
    "organization_branding",
    "organization_domains",
    "user_social_links",
    "users",
    "organizations",
)


@pytest.fixture(scope="session", autouse=True)
def migraciones() -> None:
    """Aplica el esquema a la base de datos de tests una sola vez."""
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=API_DIR,
        check=True,
        env=os.environ.copy(),
        capture_output=True,
    )


@pytest.fixture(autouse=True)
async def limpiar_datos() -> AsyncIterator[None]:
    """Vacía las tablas antes de cada test y limpia Redis."""
    async with SessionMaintenance() as session:
        await session.execute(text(f"TRUNCATE {', '.join(TABLAS)} RESTART IDENTITY CASCADE"))
        await session.commit()
    await get_redis().flushdb()
    yield


@pytest.fixture(scope="session", autouse=True)
async def cerrar_recursos() -> AsyncIterator[None]:
    yield
    await close_redis()
    await engine_app.dispose()
    await engine_maintenance.dispose()


@pytest.fixture
async def maintenance_db() -> AsyncIterator[AsyncSession]:
    """Sesión con el rol de mantenimiento (BYPASSRLS)."""
    async with SessionMaintenance() as session:
        yield session
        await session.commit()


@pytest.fixture
async def app_db() -> AsyncIterator[AsyncSession]:
    """Sesión con el rol de la API, sin contexto de organización fijado."""
    async with SessionApp() as session:
        async with session.begin():
            yield session


@pytest.fixture
async def cliente() -> AsyncIterator[AsyncClient]:
    """Cliente HTTP contra la aplicación, sin ejecutar el lifespan."""
    aplicacion = create_app()
    transporte = ASGITransport(app=aplicacion)
    async with AsyncClient(
        transport=transporte, base_url="http://localhost", follow_redirects=True
    ) as http:
        yield http


class OrganizacionDePrueba:
    """Datos de una organización creada para un test."""

    __slots__ = ("id", "slug", "host", "owner_id", "owner_email", "owner_password", "owner_role_id")

    def __init__(
        self,
        *,
        id: uuid.UUID,
        slug: str,
        host: str,
        owner_id: uuid.UUID,
        owner_email: str,
        owner_password: str,
        owner_role_id: uuid.UUID,
    ) -> None:
        self.id = id
        self.slug = slug
        self.host = host
        self.owner_id = owner_id
        self.owner_email = owner_email
        self.owner_password = owner_password
        self.owner_role_id = owner_role_id


async def crear_organizacion(
    slug: str, host: str, *, owner_password: str = "contraseña-de-prueba"
) -> OrganizacionDePrueba:
    """Crea una organización con su propietario usando el rol de mantenimiento."""
    async with SessionMaintenance() as session:
        organizacion = await organization_service.create_organization(
            session, slug=slug, name=f"Organización {slug}", host=host
        )
        rol = await session.scalar(
            select(Role).where(Role.organization_id == organizacion.id, Role.key == OWNER_KEY)
        )
        assert rol is not None
        # `localhost` y los TLD reservados (.test) no valen como dominio de correo.
        correo = f"owner@{slug}.com"
        usuario = User(
            email=correo,
            full_name="Propietario",
            password_hash=hash_password(owner_password),
            is_active=True,
        )
        session.add(usuario)
        await session.flush()
        session.add(
            OrganizationMember(
                organization_id=organizacion.id,
                user_id=usuario.id,
                role_id=rol.id,
                profile_data={},
            )
        )
        await session.commit()
        return OrganizacionDePrueba(
            id=organizacion.id,
            slug=organizacion.slug,
            host=host,
            owner_id=usuario.id,
            owner_email=correo,
            owner_password=owner_password,
            owner_role_id=rol.id,
        )


@pytest.fixture
async def organizacion() -> OrganizacionDePrueba:
    """Organización principal de los tests, alcanzable en el host `localhost`."""
    return await crear_organizacion("acme", "localhost")


@pytest.fixture
async def otra_organizacion() -> OrganizacionDePrueba:
    """Segunda organización, para comprobar el aislamiento."""
    return await crear_organizacion("rival", "rival.test")


async def iniciar_sesion(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> tuple[str, dict[str, str]]:
    """Hace login y devuelve el access token y las cabeceras listas para usar."""
    respuesta = await cliente.post(
        "/api/v1/auth/login",
        json={"email": organizacion.owner_email, "password": organizacion.owner_password},
        headers={"Host": organizacion.host},
    )
    assert respuesta.status_code == 200, respuesta.text
    token = respuesta.json()["access_token"]
    return token, {"Host": organizacion.host, "Authorization": f"Bearer {token}"}


async def crear_rol(
    organizacion: OrganizacionDePrueba,
    *,
    key: str,
    permisos: list[Permission],
    nombre: str | None = None,
) -> uuid.UUID:
    """Crea un rol a medida con permisos concretos, saltándose la API."""
    async with SessionMaintenance() as session:
        rol = Role(
            organization_id=organizacion.id,
            key=key,
            name=nombre or key.capitalize(),
            is_system=False,
        )
        session.add(rol)
        await session.flush()
        for permiso in permisos:
            session.add(
                RolePermission(
                    role_id=rol.id,
                    permission=permiso.value,
                    organization_id=organizacion.id,
                )
            )
        await session.commit()
        return rol.id


async def crear_usuario_con_rol(
    organizacion: OrganizacionDePrueba,
    role_key: str,
    *,
    password: str = "otra-contraseña-de-prueba",
) -> tuple[str, str]:
    """Da de alta a alguien con el rol indicado. Devuelve (correo, contraseña)."""
    async with SessionMaintenance() as session:
        rol = await session.scalar(
            select(Role).where(Role.organization_id == organizacion.id, Role.key == role_key)
        )
        assert rol is not None, f"no existe el rol {role_key}"
        correo = f"{role_key}@{organizacion.slug}.com"
        usuario = User(
            email=correo,
            full_name=f"Persona {role_key}",
            password_hash=hash_password(password),
            is_active=True,
        )
        session.add(usuario)
        await session.flush()
        session.add(
            OrganizationMember(
                organization_id=organizacion.id,
                user_id=usuario.id,
                role_id=rol.id,
                profile_data={},
            )
        )
        await session.commit()
        return correo, password


async def iniciar_sesion_como(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, role_key: str
) -> tuple[str, dict[str, str]]:
    """Crea a alguien con ese rol y devuelve sus cabeceras ya autenticadas."""
    correo, contraseña = await crear_usuario_con_rol(organizacion, role_key)
    respuesta = await cliente.post(
        "/api/v1/auth/login",
        json={"email": correo, "password": contraseña},
        headers={"Host": organizacion.host},
    )
    assert respuesta.status_code == 200, respuesta.text
    token = respuesta.json()["access_token"]
    return token, {"Host": organizacion.host, "Authorization": f"Bearer {token}"}


__all__ = [
    "OrganizacionDePrueba",
    "crear_organizacion",
    "crear_rol",
    "crear_usuario_con_rol",
    "iniciar_sesion",
    "iniciar_sesion_como",
    "set_organization_context",
]
