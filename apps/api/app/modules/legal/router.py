"""Endpoints del módulo legal.

Tres routers:

- `router_admin`: edición de las cuatro páginas legales desde el panel
  (`organizations:write`), mismo prefijo `/organizations/me/...` que
  `branding`/`sponsor-tiers`.
- `router_public`: lectura pública de cada página legal, resuelta por
  organización vía host (mismo patrón que `tenant/router.py`).
- `router_cookie_consent`: `POST /public/cookie-consent`, sin autenticación,
  con `limit_per_ip` (mismo patrón que `registrations/public_router.py`).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from sqlalchemy import insert

from app.core.deps import CurrentUserDep, DbDep, OrganizationDep, require_permission
from app.core.permissions import Permission
from app.core.ratelimit import COOKIE_CONSENT_POR_IP, LEGAL_PAGES_POR_IP, limit_per_ip
from app.modules.legal.models import CookieConsent
from app.modules.legal.schemas import (
    CookieConsentCreate,
    LegalPageAdminItem,
    LegalPageResponse,
    LegalPagesAdminResponse,
    LegalPagesUpdate,
)
from app.modules.legal.templates import resolve_legal_page
from app.modules.organizations import repository as organizations_repository
from app.modules.organizations.models import Organization
from app.shared.errors import NotFoundError

router_admin = APIRouter(prefix="/organizations/me/legal-pages", tags=["legal"])
router_public = APIRouter(prefix="/public/legal", tags=["público"])
router_cookie_consent = APIRouter(prefix="/public", tags=["público"])


async def _obtener_organizacion_o_404(session: DbDep, organization_id: uuid.UUID) -> Organization:
    organizacion = await organizations_repository.get_organization(session, organization_id)
    if organizacion is None:
        raise NotFoundError("La organización no existe.")
    return organizacion


@router_admin.get(
    "",
    summary="Contenido de las cuatro páginas legales",
    response_model=LegalPagesAdminResponse,
    dependencies=[require_permission(Permission.ORGANIZATIONS_READ)],
)
async def get_legal_pages(usuario: CurrentUserDep, session: DbDep) -> LegalPagesAdminResponse:
    organizacion = await _obtener_organizacion_o_404(session, usuario.organization_id)

    return LegalPagesAdminResponse(
        legal_notice=LegalPageAdminItem(
            content=resolve_legal_page(organizacion, "aviso-legal"),
            is_custom=organizacion.legal_notice_content is not None,
        ),
        privacy_policy=LegalPageAdminItem(
            content=resolve_legal_page(organizacion, "privacidad"),
            is_custom=organizacion.privacy_policy_content is not None,
        ),
        cookies_policy=LegalPageAdminItem(
            content=resolve_legal_page(organizacion, "cookies"),
            is_custom=organizacion.cookies_policy_content is not None,
        ),
        registration_terms=LegalPageAdminItem(
            content=resolve_legal_page(organizacion, "condiciones-de-inscripcion"),
            is_custom=organizacion.registration_terms_content is not None,
        ),
    )


@router_admin.patch(
    "",
    summary="Editar el contenido de las páginas legales",
    description=(
        "Un campo ausente no se toca; un campo presente con `null` restaura la "
        "plantilla por defecto de esa página."
    ),
    response_model=LegalPagesAdminResponse,
    dependencies=[require_permission(Permission.ORGANIZATIONS_WRITE)],
)
async def update_legal_pages(
    datos: LegalPagesUpdate, usuario: CurrentUserDep, session: DbDep
) -> LegalPagesAdminResponse:
    organizacion = await _obtener_organizacion_o_404(session, usuario.organization_id)

    for campo, valor in datos.model_dump(exclude_unset=True).items():
        limpio = valor.strip() if isinstance(valor, str) else None
        setattr(organizacion, campo, limpio or None)
    await session.flush()
    return await get_legal_pages(usuario, session)


async def _pagina_publica(
    organizacion: OrganizationDep, session: DbDep, clave: str
) -> LegalPageResponse:
    entidad = await _obtener_organizacion_o_404(session, organizacion.id)
    return LegalPageResponse(content=resolve_legal_page(entidad, clave))


@router_public.get(
    "/aviso-legal",
    summary="Aviso legal",
    response_model=LegalPageResponse,
    dependencies=[limit_per_ip("legal-aviso-legal", LEGAL_PAGES_POR_IP)],
)
async def public_legal_notice(organizacion: OrganizationDep, session: DbDep) -> LegalPageResponse:
    return await _pagina_publica(organizacion, session, "aviso-legal")


@router_public.get(
    "/privacidad",
    summary="Política de privacidad",
    response_model=LegalPageResponse,
    dependencies=[limit_per_ip("legal-privacidad", LEGAL_PAGES_POR_IP)],
)
async def public_privacy_policy(organizacion: OrganizationDep, session: DbDep) -> LegalPageResponse:
    return await _pagina_publica(organizacion, session, "privacidad")


@router_public.get(
    "/cookies",
    summary="Política de cookies",
    response_model=LegalPageResponse,
    dependencies=[limit_per_ip("legal-cookies", LEGAL_PAGES_POR_IP)],
)
async def public_cookies_policy(organizacion: OrganizationDep, session: DbDep) -> LegalPageResponse:
    return await _pagina_publica(organizacion, session, "cookies")


@router_public.get(
    "/condiciones-de-inscripcion",
    summary="Condiciones de inscripción",
    response_model=LegalPageResponse,
    dependencies=[limit_per_ip("legal-condiciones-inscripcion", LEGAL_PAGES_POR_IP)],
)
async def public_registration_terms(
    organizacion: OrganizationDep, session: DbDep
) -> LegalPageResponse:
    return await _pagina_publica(organizacion, session, "condiciones-de-inscripcion")


@router_cookie_consent.post(
    "/cookie-consent",
    summary="Registrar una decisión del banner de cookies",
    description=(
        "Anónimo por diseño: sin `user_id`, sin email y sin ningún campo de IP o su "
        "hash (decisión #3 del plan). `necessary` debe estar siempre presente: el "
        "banner no permite rechazarla."
    ),
    status_code=204,
    dependencies=[limit_per_ip("cookie-consent", COOKIE_CONSENT_POR_IP)],
)
async def create_cookie_consent(
    datos: CookieConsentCreate, organizacion: OrganizationDep, session: DbDep
) -> None:
    if "necessary" not in datos.categories:
        # `necessary` no es rastreo, es lo mínimo para que la web funcione: el
        # banner nunca ofrece la opción de rechazarla, así que una petición sin
        # ella es un uso incorrecto del endpoint, no una decisión legítima.
        datos = CookieConsentCreate(categories=[*datos.categories, "necessary"])

    # `insert()` de Core, no `session.add(...)`: el ORM añadiría `RETURNING`
    # para leer `created_at` (`server_default=func.now()`), y `app_user` solo
    # tiene `GRANT INSERT` sobre esta tabla (migración `0012`, decisión #4 del
    # plan) — `INSERT ... RETURNING` exige además `SELECT` sobre las columnas
    # devueltas, que este rol no tiene a propósito.
    await session.execute(
        insert(CookieConsent).values(
            organization_id=organizacion.id,
            categories_accepted=list(dict.fromkeys(datos.categories)),
        )
    )
