"""Endpoints de superadministración y su aislamiento del resto de la API."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from httpx import AsyncClient
from sqlalchemy import select

from app.core.database import SessionMaintenance
from app.main import app
from app.modules.users.models import User
from tests.conftest import OrganizacionDePrueba, iniciar_sesion

ADMIN = "/api/v1/admin/organizations"


async def _hacer_superadmin(email: str) -> None:
    async with SessionMaintenance() as session:
        usuario = await session.scalar(select(User).where(User.email == email))
        assert usuario is not None
        usuario.is_superadmin = True
        await session.commit()


async def test_sin_token_devuelve_401(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    respuesta = await cliente.get(ADMIN)
    assert respuesta.status_code == 401


async def test_un_usuario_normal_devuelve_403(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    """El propietario de una organización no es superadministrador de la instalación."""
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    respuesta = await cliente.get(ADMIN, headers=cabeceras)
    assert respuesta.status_code == 403


async def test_un_superadmin_crea_una_organizacion_completa(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    """Fase 6 (cierre) del plan de organización sin dominio: crear una
    organización ya no admite ni exige ningún `host` — sin dominio propio,
    queda operativa solo con su slug, branding y roles clonados."""
    await _hacer_superadmin(organizacion.owner_email)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    respuesta = await cliente.post(
        ADMIN,
        headers=cabeceras,
        json={"slug": "nueva", "name": "Organización Nueva"},
    )
    assert respuesta.status_code == 201
    nueva = respuesta.json()
    assert nueva["slug"] == "nueva"
    assert nueva["name"] == "Organización Nueva"

    listado = await cliente.get(ADMIN, headers=cabeceras)
    assert "nueva" in {o["slug"] for o in listado.json()}


async def test_no_se_puede_repetir_el_slug(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    await _hacer_superadmin(organizacion.owner_email)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    repetido_slug = await cliente.post(
        ADMIN,
        headers=cabeceras,
        json={"slug": organizacion.slug, "name": "Copia"},
    )
    assert repetido_slug.status_code == 409


def test_solo_el_modulo_admin_usa_el_motor_de_mantenimiento() -> None:
    """El rol con BYPASSRLS no debe filtrarse a ningún otro módulo de la API.

    Es una comprobación estática deliberada: si alguien añade `get_maintenance_db` a
    otro router, RLS dejaría de proteger ese camino y ningún test funcional lo notaría.
    """
    modules = Path(__file__).resolve().parents[2] / "app" / "modules"
    infractores = [
        str(fichero.relative_to(modules.parent))
        for fichero in modules.rglob("*.py")
        if fichero.parent.name != "admin" and "get_maintenance_db" in fichero.read_text()
    ]
    assert not infractores, f"get_maintenance_db usado fuera de modules/admin: {infractores}"


def _rutas_de_app() -> list[Any]:
    """Todas las rutas de la aplicación, incluidas las de los routers incluidos.

    `app.routes` del proyecto monta los routers como `_IncludedRouter`, que no
    expone `.routes` sino `.original_router`; un recorrido que solo mirara
    `app.routes` (o solo `.routes`) devolvería cero rutas y el test pasaría sin
    comprobar nada.
    """
    from fastapi.routing import APIRoute

    encontradas: list[Any] = []
    pendientes: list[Any] = list(app.routes)
    vistos: set[int] = set()
    while pendientes:
        objeto = pendientes.pop()
        if id(objeto) in vistos:
            continue
        vistos.add(id(objeto))

        if isinstance(objeto, APIRoute):
            encontradas.append(objeto)
            continue

        for atributo in ("routes", "original_router", "router", "app"):
            hijo = getattr(objeto, atributo, None)
            if hijo is None:
                continue
            pendientes.extend(getattr(hijo, "routes", []) or [hijo])
    return encontradas


def test_todas_las_rutas_de_admin_exigen_superadmin() -> None:
    """Recorre las rutas del router de administración y exige su dependencia de gate.

    `get_maintenance_db` (BYPASSRLS) no autentica por sí solo: la única barrera
    de los endpoints de administración es el `Depends(require_superadmin)` que
    cada función declara a mano. Un endpoint nuevo que lo olvide quedaría
    expuesto con permisos de mantenimiento y sin autenticar, y ningún test
    funcional de otro camino lo detectaría.
    """
    # El prefijo `/api/v1` lo aplica el `include_router` de `main.py`, no la ruta
    # en sí: filtrar por `/api/v1/admin` devolvería vacío y el test pasaría sin
    # comprobar nada. Las rutas del módulo llevan `/admin` en su propio path.
    #
    # Excepción documentada: `impersonate/stop` se llama **con el token de
    # suplantación**, no con el del administrador, así que no puede exigir
    # `require_superadmin` (lo rechazaría por ser un token de impersonación).
    # Su propia barrera es exigir que el token sea de suplantación.
    rutas = [
        ruta
        for ruta in _rutas_de_app()
        if ruta.path.startswith("/admin") and not ruta.path.endswith("/impersonate/stop")
    ]
    assert rutas, "el recorrido no encontró ninguna ruta de /admin: el test no comprobaría nada"

    sin_gate = []
    for ruta in rutas:
        nombres = {
            dependencia.call.__name__
            for dependencia in ruta.dependant.dependencies
            if dependencia.call is not None
        }
        # El gate se declara como `Depends(require_superadmin)`, directo o como
        # alias `Superadmin`; en ambos casos la dependencia resuelta es la misma.
        if "require_superadmin" not in nombres:
            sin_gate.append(ruta.path)

    assert not sin_gate, f"rutas de /admin sin require_superadmin: {sin_gate}"
