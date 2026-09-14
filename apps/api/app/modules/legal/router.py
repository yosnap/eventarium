"""Endpoints del módulo legal.

Dos routers:

- `router_public`: lectura pública de cada página legal. Eventarium es una
  SaaS centralizada (como Luma): las cuatro páginas son siempre las de
  plataforma, con independencia del host de organización desde el que se
  pidan — no hay contenido legal propio de organización (decisión del
  usuario, 2026-09-14; antes sí lo había, editable desde
  `/organizations/me/legal-pages`, retirado en este cambio).
- `router_cookie_consent`: `POST /public/cookie-consent`, sin autenticación,
  con `limit_per_ip` (mismo patrón que `registrations/public_router.py`). Se
  mantiene por organización: es el registro de qué aceptó cada visitante en
  el sitio de esa organización, no el texto legal en sí.

  **Pendiente, fuera del alcance de la fase 2 del plan de organización sin
  dominio**: sigue resolviendo por host (`OrganizationDep`/`PublicDbDep`).
  A diferencia del resto de endpoints públicos, este no cuelga de ningún
  recurso (evento, inscripción, invitación) del que resolver la organización
  — es un registro de consentimiento por visita, sin más identificador. Con
  una sola instalación y sin sitio propio por organización, no está decidido
  si esto sigue teniendo sentido "por organización" o si pasa a ser un
  registro de plataforma (como ya lo son las cuatro páginas legales); es una
  decisión de producto, no solo un cambio de mecanismo de resolución.
"""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import DbPlataformaDep, OrganizationDep, PublicDbDep
from app.core.ratelimit import COOKIE_CONSENT_POR_IP, LEGAL_PAGES_POR_IP, limit_per_ip
from app.modules.legal.models import CookieConsent
from app.modules.legal.schemas import CookieConsentCreate, LegalPageResponse
from app.modules.platform import service as platform_service
from app.modules.platform.service import ATRIBUTO_DE_PAGINA as _ATRIBUTO_DE_PAGINA

router_public = APIRouter(prefix="/public/legal", tags=["público"])
router_cookie_consent = APIRouter(prefix="/public", tags=["público"])


async def _pagina_publica(session: AsyncSession, clave: str) -> LegalPageResponse:
    paginas = await platform_service.legal_pages_publicas(session)
    return LegalPageResponse(content=getattr(paginas, _ATRIBUTO_DE_PAGINA[clave]).content)


@router_public.get(
    "/aviso-legal",
    summary="Aviso legal",
    response_model=LegalPageResponse,
    dependencies=[limit_per_ip("legal-aviso-legal", LEGAL_PAGES_POR_IP)],
)
async def public_legal_notice(session: DbPlataformaDep) -> LegalPageResponse:
    return await _pagina_publica(session, "aviso-legal")


@router_public.get(
    "/privacidad",
    summary="Política de privacidad",
    response_model=LegalPageResponse,
    dependencies=[limit_per_ip("legal-privacidad", LEGAL_PAGES_POR_IP)],
)
async def public_privacy_policy(session: DbPlataformaDep) -> LegalPageResponse:
    return await _pagina_publica(session, "privacidad")


@router_public.get(
    "/cookies",
    summary="Política de cookies",
    response_model=LegalPageResponse,
    dependencies=[limit_per_ip("legal-cookies", LEGAL_PAGES_POR_IP)],
)
async def public_cookies_policy(session: DbPlataformaDep) -> LegalPageResponse:
    return await _pagina_publica(session, "cookies")


@router_public.get(
    "/condiciones-de-inscripcion",
    summary="Condiciones de inscripción",
    response_model=LegalPageResponse,
    dependencies=[limit_per_ip("legal-condiciones-inscripcion", LEGAL_PAGES_POR_IP)],
)
async def public_registration_terms(session: DbPlataformaDep) -> LegalPageResponse:
    return await _pagina_publica(session, "condiciones-de-inscripcion")


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
    datos: CookieConsentCreate, organizacion: OrganizationDep, session: PublicDbDep
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
