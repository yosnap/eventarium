"""Datos de demostración.

Idempotente por diseño: se puede ejecutar tantas veces como haga falta. Cada paso
busca antes de crear, y la contraseña del owner solo se genera la primera vez —
volver a sembrar no debe invalidar la sesión de nadie.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import generate_password, hash_password
from app.modules.organizations import service
from app.modules.organizations.models import (
    Organization,
    OrganizationDomain,
    OrganizationMember,
)
from app.modules.roles.models import Role
from app.modules.roles.system_roles import OWNER_KEY
from app.modules.users.models import User

DEMO_SLUG = "iawic"
DEMO_NAME = "IA Week Valencia"
DEMO_HOST = "localhost"


@dataclass(frozen=True, slots=True)
class SeedResult:
    """Resultado de una siembra, para informar por consola."""

    organization_slug: str
    owner_email: str
    owner_password: str | None
    created: bool


async def seed_demo(session: AsyncSession, *, reset_password: bool = False) -> SeedResult:
    """Crea (o completa) la organización de demostración y su usuario propietario."""
    settings = get_settings()

    organizacion = await session.scalar(select(Organization).where(Organization.slug == DEMO_SLUG))
    nueva = organizacion is None
    if organizacion is None:
        organizacion = await service.create_organization(
            session,
            slug=DEMO_SLUG,
            name=DEMO_NAME,
            host=DEMO_HOST,
            legal_name="Asociación IA Week Valencia",
            contact_email="hola@example.com",
        )
    else:
        # La organización existe: basta con asegurar que el dominio sigue registrado.
        dominio = await session.scalar(
            select(OrganizationDomain).where(OrganizationDomain.host == DEMO_HOST)
        )
        if dominio is None:
            await service.add_domain(
                session, organization_id=organizacion.id, host=DEMO_HOST, is_primary=True
            )

    rol_owner = await session.scalar(
        select(Role).where(Role.organization_id == organizacion.id, Role.key == OWNER_KEY)
    )
    if rol_owner is None:
        roles = await service.clone_system_roles(session, organizacion.id)
        rol_owner = roles[OWNER_KEY]

    correo = settings.seed_owner_email.strip().lower()
    usuario = await session.scalar(select(User).where(User.email == correo))
    contraseña: str | None = None

    if usuario is None:
        contraseña = settings.seed_owner_password or generate_password()
        usuario = User(
            email=correo,
            first_name="Propietario",
            last_name="De demostración",
            password_hash=hash_password(contraseña),
            is_active=True,
            is_superadmin=True,
        )
        session.add(usuario)
        await session.flush()
    elif reset_password:
        contraseña = settings.seed_owner_password or generate_password()
        usuario.password_hash = hash_password(contraseña)

    membresia = await session.scalar(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == organizacion.id,
            OrganizationMember.user_id == usuario.id,
            OrganizationMember.role_id == rol_owner.id,
        )
    )
    if membresia is None:
        session.add(
            OrganizationMember(
                organization_id=organizacion.id,
                user_id=usuario.id,
                role_id=rol_owner.id,
                profile_data={},
            )
        )

    await session.flush()
    return SeedResult(
        organization_slug=organizacion.slug,
        owner_email=correo,
        owner_password=contraseña,
        created=nueva,
    )
