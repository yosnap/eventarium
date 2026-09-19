"""Marca de último acceso por membresía.

`organization_members.last_seen_at` es la señal que el escritorio de plataforma
usa para saber si alguien sigue entrando. Dos cosas que se comprueban aquí y que
son fáciles de romper sin que se note:

- La marca va **por membresía**, no en `users`: una persona en dos
  organizaciones no debe hacer saltar la marca de las dos al entrar en una.
- La escribe el **login**, y solo el login: el refresh no (mide acceso
  explícito) ni la impersonación (quien entra no es la persona).
"""

from __future__ import annotations

from datetime import UTC, datetime

from httpx import AsyncClient
from sqlalchemy import select

from app.core.database import SessionMaintenance
from app.modules.organizations.models import OrganizationMember
from tests.conftest import OrganizacionDePrueba, iniciar_sesion


async def _marca(organizacion: OrganizacionDePrueba, user_id: str | None = None) -> datetime | None:
    async with SessionMaintenance() as session:
        consulta = select(OrganizationMember.last_seen_at).where(
            OrganizationMember.organization_id == organizacion.id
        )
        if user_id:
            consulta = consulta.where(OrganizationMember.user_id == user_id)
        return await session.scalar(consulta)


async def test_recien_creada_no_tiene_marca(
    organizacion: OrganizacionDePrueba,
) -> None:
    """`None` es «no consta», no «hace mucho»: rellenarla al migrar diría que
    todo el mundo entró justo cuando se aplicó la migración."""
    assert await _marca(organizacion) is None


async def test_el_login_escribe_la_marca(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    assert await _marca(organizacion) is None

    await iniciar_sesion(cliente, organizacion)

    marca = await _marca(organizacion)
    assert marca is not None, "el login deja constancia del acceso"
    assert marca <= datetime.now(UTC)


async def test_un_login_fallido_no_escribe_la_marca(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    """Quien no entra no ha accedido: dejar marca sería un dato falso."""
    respuesta = await cliente.post(
        "/api/v1/auth/login",
        json={"email": organizacion.owner_email, "password": "contraseña-incorrecta"},
    )
    assert respuesta.status_code == 401
    assert await _marca(organizacion) is None


async def test_la_marca_es_de_la_organizacion_en_la_que_se_entra(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    otra_organizacion: OrganizacionDePrueba,
) -> None:
    """El dato es «si alguien de *esta* organización sigue entrando».

    Si la marca viviera en `users`, entrar en una organización la haría saltar en
    todas las demás sin que nadie de ellas hubiera entrado — que es justo el
    error que la columna por membresía evita.
    """
    await iniciar_sesion(cliente, organizacion)

    assert await _marca(organizacion) is not None
    assert await _marca(otra_organizacion) is None
