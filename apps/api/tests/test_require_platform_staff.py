"""`require_platform_staff` (`app/core/deps.py`): acepta `is_superadmin` o
`platform_role == 'soporte'`, ambos leídos de la fila `users` en cada
llamada, y rechaza siempre un token de impersonación — mismas dos garantías
que ya prueba `test_impersonation.py` para `require_superadmin`, aplicadas a
esta dependencia nueva y aditiva (plan
`plans/260916-0810-usuarios-y-permisos-plataforma/`, hallazgos S-1/S-2 del
red-team de ese plan).

Unit-level, sin pasar por HTTP: la fase 0 no añade ningún endpoint todavía
(eso es la fase 1), así que se llama a la dependencia directamente con unos
`AccessTokenClaims` construidos a mano.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import update

from app.core.database import SessionMaintenance
from app.core.deps import require_platform_staff
from app.core.security import AccessTokenClaims
from app.modules.users.models import User
from app.shared.errors import AuthenticationError, PermissionDeniedError
from tests.conftest import OrganizacionDePrueba


async def _fijar(
    user_id: uuid.UUID, *, is_superadmin: bool = False, platform_role: str | None = None
) -> None:
    async with SessionMaintenance() as session:
        await session.execute(
            update(User)
            .where(User.id == user_id)
            .values(is_superadmin=is_superadmin, platform_role=platform_role)
        )
        await session.commit()


def _claims(user_id: uuid.UUID, *, impersonated_by: uuid.UUID | None = None) -> AccessTokenClaims:
    return AccessTokenClaims(
        user_id=user_id,
        organization_id=None,
        jti="test",
        is_superadmin=False,
        impersonated_by=impersonated_by,
    )


async def test_acepta_superadmin(organizacion: OrganizacionDePrueba) -> None:
    await _fijar(organizacion.owner_id, is_superadmin=True)
    async with SessionMaintenance() as session:
        actual = await require_platform_staff(_claims(organizacion.owner_id), session)
    assert actual.id == organizacion.owner_id
    assert actual.is_superadmin is True


async def test_acepta_soporte(organizacion: OrganizacionDePrueba) -> None:
    await _fijar(organizacion.owner_id, platform_role="soporte")
    async with SessionMaintenance() as session:
        actual = await require_platform_staff(_claims(organizacion.owner_id), session)
    assert actual.id == organizacion.owner_id
    assert actual.is_superadmin is False


async def test_rechaza_sin_ningun_rol_de_plataforma(organizacion: OrganizacionDePrueba) -> None:
    await _fijar(organizacion.owner_id)
    async with SessionMaintenance() as session:
        with pytest.raises(PermissionDeniedError):
            await require_platform_staff(_claims(organizacion.owner_id), session)


async def test_rechaza_usuario_desactivado_aunque_sea_superadmin(
    organizacion: OrganizacionDePrueba,
) -> None:
    await _fijar(organizacion.owner_id, is_superadmin=True)
    async with SessionMaintenance() as session:
        await session.execute(
            update(User).where(User.id == organizacion.owner_id).values(is_active=False)
        )
        await session.commit()
    async with SessionMaintenance() as session:
        with pytest.raises(AuthenticationError):
            await require_platform_staff(_claims(organizacion.owner_id), session)


@pytest.mark.parametrize("is_superadmin,platform_role", [(True, None), (False, "soporte")])
async def test_rechaza_token_de_impersonacion_aunque_el_suplantado_tenga_rol_de_plataforma(
    organizacion: OrganizacionDePrueba,
    is_superadmin: bool,
    platform_role: str | None,
) -> None:
    """Hallazgo S-1 del red-team: el claim `impersonated_by` es la defensa,
    no la fila de `users` — sin esta comprobación, una sesión de
    suplantación sobre una cuenta con `is_superadmin`/`soporte` pasaría este
    gate."""
    await _fijar(organizacion.owner_id, is_superadmin=is_superadmin, platform_role=platform_role)
    async with SessionMaintenance() as session:
        with pytest.raises(PermissionDeniedError):
            await require_platform_staff(
                _claims(organizacion.owner_id, impersonated_by=uuid.uuid4()), session
            )


async def test_lee_el_rol_en_base_de_datos_no_desde_el_claim(
    organizacion: OrganizacionDePrueba,
) -> None:
    """Hallazgo S-2 del red-team: `AccessTokenClaims.is_superadmin` (el
    claim histórico del token) se ignora a propósito — solo cuenta lo que
    diga la fila `users` en el momento de la petición."""
    await _fijar(organizacion.owner_id, is_superadmin=False, platform_role=None)
    claims = AccessTokenClaims(
        user_id=organizacion.owner_id,
        organization_id=None,
        jti="test",
        is_superadmin=True,  # claim obsoleto/falso: no debe bastar
        impersonated_by=None,
    )
    async with SessionMaintenance() as session:
        with pytest.raises(PermissionDeniedError):
            await require_platform_staff(claims, session)
