"""Autoservicio de creación de organizaciones (fase 2 del PRD).

Separado de `modules/admin` (único módulo autorizado a usar la dependencia con
`BYPASSRLS`) y de `router.py` (que ya exige pertenecer a una organización): este router
usa siempre el motor de la API (`engine_app`, sin `BYPASSRLS`), nunca el de
mantenimiento — lo comprueba el mismo test estático de la fase 0, ampliado a cualquier
módulo fuera de `admin`.

Solo la primerísima fila de `organizations` necesita saltarse RLS (la política exige
`id = app_current_organization()`, y una organización que aún no existe no puede ser
el contexto de nadie). Se resuelve con `app_create_organization_row`, una función
`SECURITY DEFINER` de alcance mínimo. En cuanto esa fila existe, el resto —clonar
roles, dominio, branding, membresía del propietario— se hace fijando el contexto RLS a
la organización nueva y reutilizando el código normal (`organization_service`), no una
versión reimplementada que pudiera divergir del alta por superadmin.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Request, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.core.database import set_organization_context
from app.core.deps import DbDep, VerifiedUserDep
from app.core.ratelimit import CHECK_SLUG_POR_IP, CREAR_ORGANIZACION_POR_IP, limit_per_ip
from app.core.turnstile import require_turnstile
from app.modules.organizations import service as organization_service
from app.modules.organizations.models import (
    OrganizationBranding,
    OrganizationDomain,
    OrganizationMember,
)
from app.modules.organizations.schemas import (
    RESERVED_SLUGS,
    SLUG_PATTERN,
    CheckSlugResponse,
    SelfServiceOrganizationCreate,
    SelfServiceOrganizationResponse,
)
from app.modules.roles.system_roles import OWNER_KEY
from app.shared.errors import ConflictError, ValidationDomainError
from app.shared.identifiers import new_uuid7

router = APIRouter(prefix="/organizations", tags=["organizaciones"])

_SLUG_RE = re.compile(SLUG_PATTERN)


def _slug_valido(slug: str) -> bool:
    return bool(_SLUG_RE.fullmatch(slug)) and slug not in RESERVED_SLUGS


@router.get(
    "/check-slug",
    summary="Comprobar disponibilidad de un identificador de organización",
    description=(
        "Ayuda de UX para sugerir un subdominio libre mientras se escribe. No es la "
        "validación de seguridad: la creación real vuelve a comprobarlo y el `UNIQUE` "
        "de la base de datos es la única fuente de verdad ante una carrera."
    ),
    response_model=CheckSlugResponse,
    dependencies=[limit_per_ip("check-slug", CHECK_SLUG_POR_IP)],
)
async def check_slug(slug: str, session: DbDep) -> CheckSlugResponse:
    slug_limpio = slug.strip().lower()
    if not _slug_valido(slug_limpio):
        return CheckSlugResponse(available=False)
    disponible = (
        await session.execute(text("SELECT app_check_slug_available(:slug)"), {"slug": slug_limpio})
    ).scalar_one()
    return CheckSlugResponse(available=bool(disponible))


@router.post(
    "",
    summary="Crear una organización (autoservicio)",
    description=(
        "Exige correo verificado y Turnstile. La persona autenticada queda como "
        "`owner`; el subdominio se registra como `{slug}.DOMINIO_BASE`."
    ),
    status_code=status.HTTP_201_CREATED,
    response_model=SelfServiceOrganizationResponse,
    dependencies=[limit_per_ip("crear-organizacion", CREAR_ORGANIZACION_POR_IP)],
)
async def create_organization(
    datos: SelfServiceOrganizationCreate,
    persona: VerifiedUserDep,
    request: Request,
    session: DbDep,
) -> SelfServiceOrganizationResponse:
    await require_turnstile(request, datos.turnstile_token)

    slug_limpio = datos.slug.strip().lower()
    if not _slug_valido(slug_limpio):
        raise ValidationDomainError(
            f"El identificador «{slug_limpio}» no es válido o está reservado."
        )

    settings = get_settings()
    host = f"{slug_limpio}.{settings.dominio_base}" if settings.dominio_base else slug_limpio

    organization_id = new_uuid7()
    try:
        await session.execute(
            text("SELECT app_create_organization_row(:id, :slug, :name)"),
            {"id": organization_id, "slug": slug_limpio, "name": datos.name},
        )
    except IntegrityError as exc:
        # Condición de carrera con otra creación simultánea del mismo slug: el
        # `UNIQUE` de la base de datos es la única fuente de verdad, `check-slug` es
        # solo ayuda de UX.
        raise ConflictError(f"El identificador «{slug_limpio}» ya está en uso.") from exc

    # La organización ya existe: se fija el contexto RLS a ella y el resto se hace con
    # el rol normal de la API, reutilizando exactamente el mismo código que el alta
    # por superadmin (`organization_service.clone_system_roles`) — no una versión
    # aparte que pudiera divergir con el tiempo.
    await set_organization_context(session, organization_id, persona.id)

    roles_clonados = await organization_service.clone_system_roles(session, organization_id)
    owner_role = roles_clonados[OWNER_KEY]

    session.add(OrganizationDomain(organization_id=organization_id, host=host, is_primary=True))
    session.add(
        OrganizationBranding(
            organization_id=organization_id,
            template_key="classic",
            social_links=[],
        )
    )

    # El registro no pide nombre; se guarda ahora que la persona lo ha dado. La
    # política `tenant_users` ya permite actualizar la propia fila
    # (`id = app_current_user()`), fijado arriba junto con el contexto de la
    # organización — no hace falta ninguna función `SECURITY DEFINER` para esto.
    await session.execute(
        text("UPDATE users SET first_name = :first_name, last_name = :last_name WHERE id = :id"),
        {"first_name": datos.first_name, "last_name": datos.last_name, "id": persona.id},
    )

    session.add(
        OrganizationMember(
            organization_id=organization_id,
            user_id=persona.id,
            role_id=owner_role.id,
            profile_data={},
        )
    )
    await session.flush()

    return SelfServiceOrganizationResponse(id=str(organization_id), slug=slug_limpio, host=host)
