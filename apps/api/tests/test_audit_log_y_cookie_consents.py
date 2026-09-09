"""`audit_log`/`cookie_consents`: aislamiento entre tests y forma del modelo.

Solo `app_maintainer` (`SessionMaintenance`, BYPASSRLS) puede escribir en
`audit_log` — `app_user` no tiene ningún privilegio sobre ella (comprobado en
`test_sponsors_legal_auditoria_migracion.py`). Aquí se comprueba que la
adición de ambas tablas a `TABLAS` en `conftest.py` realmente evita que una
fila de un test contamine al siguiente.
"""

from __future__ import annotations

from sqlalchemy import func, select

from app.core.audit import AuditLog
from app.core.database import SessionMaintenance
from app.modules.legal.models import CookieConsent
from tests.conftest import OrganizacionDePrueba


async def _contar(modelo: type) -> int:
    async with SessionMaintenance() as session:
        total = await session.scalar(select(func.count()).select_from(modelo))
    return int(total or 0)


async def test_audit_log_empieza_vacia_en_cada_test() -> None:
    assert await _contar(AuditLog) == 0


async def test_escribir_en_audit_log_no_sobrevive_al_siguiente_test(
    organizacion: OrganizacionDePrueba,
) -> None:
    async with SessionMaintenance() as session:
        session.add(
            AuditLog(
                actor_user_id=organizacion.owner_id,
                organization_id=organizacion.id,
                action="organization.created",
                entity_type="organization",
                entity_id=str(organizacion.id),
                detail={"slug": organizacion.slug},
            )
        )
        await session.commit()

    assert await _contar(AuditLog) == 1


async def test_audit_log_de_verdad_esta_vacia_tras_el_test_anterior() -> None:
    """Si `audit_log` no estuviera en `TABLAS`, esta fila heredaría la del
    test anterior y el assert de arriba fallaría de forma intermitente."""
    assert await _contar(AuditLog) == 0


async def test_cookie_consents_empieza_vacia_en_cada_test() -> None:
    assert await _contar(CookieConsent) == 0


async def test_escribir_un_consentimiento_de_cookies_sin_datos_personales(
    organizacion: OrganizacionDePrueba,
) -> None:
    async with SessionMaintenance() as session:
        consentimiento = CookieConsent(
            organization_id=organizacion.id,
            categories_accepted=["necessary", "analytics"],
        )
        session.add(consentimiento)
        await session.commit()

    assert not hasattr(CookieConsent, "user_id")
    assert not hasattr(CookieConsent, "ip_hash")
    assert not hasattr(CookieConsent, "ip_address")
    assert await _contar(CookieConsent) == 1
