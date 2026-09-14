"""Páginas legales de plataforma y aislamiento de sus tablas.

Fase 6 (cierre) del plan de organización sin dominio: sin `organization_domains`
ni `platform_domains`, nada de esto resuelve ya por host. Cubre que las
páginas legales se sirven sin necesitar ninguna organización resuelta, que
las tablas de plataforma no son escribibles por una sesión de organización, y
que una sesión sin contexto RLS no ve datos de ninguna organización.
"""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy import text

from app.core.database import SessionApp

# `GET /tenant/branding` (identidad de plataforma sin ningún host que
# resolver) ya tiene su cobertura dedicada en `tests/test_tenant.py`; este
# fichero se centra en las páginas legales y en el aislamiento de las tablas
# de plataforma.


async def test_legal_de_plataforma_se_sirve_sin_organizacion_resuelta(
    cliente: AsyncClient,
) -> None:
    """Las legales de plataforma no dependen de ningún host: no hace falta
    registrar ninguno de plataforma ni de organización para que respondan."""
    respuesta = await cliente.get("/api/v1/public/legal/aviso-legal")
    assert respuesta.status_code == 200, respuesta.text
    contenido = respuesta.json()["content"]
    assert "Eventarium" in contenido


async def test_condiciones_de_inscripcion_tambien_sirven_sin_organizacion_resuelta(
    cliente: AsyncClient,
) -> None:
    """Eventarium es una SaaS centralizada: las condiciones son siempre las de
    plataforma, sin depender de ningún host (decisión del usuario,
    2026-09-14; antes eran un contrato de cada organización y 404 aquí)."""
    respuesta = await cliente.get("/api/v1/public/legal/condiciones-de-inscripcion")
    assert respuesta.status_code == 200, respuesta.text
    assert "Eventarium" in respuesta.json()["content"]


async def test_una_sesion_de_organizacion_no_puede_escribir_las_tablas_de_plataforma() -> None:
    """La barrera real de la identidad de plataforma: la fila no es escribible por un tenant.

    Sin el `REVOKE` de la migración, `ALTER DEFAULT PRIVILEGES` dejaría a
    cualquier sesión de organización reescribir el logo y los textos legales que
    se sirven a toda la instalación (y borrar la identidad).
    """
    async with SessionApp() as session:
        for sentencia in (
            "UPDATE platform_branding SET name = 'secuestrado'",
            "DELETE FROM platform_branding",
            "UPDATE platform_legal_pages SET content = 'secuestrado'",
        ):
            try:
                await session.execute(text(sentencia))
                await session.commit()
            except Exception:  # noqa: BLE001 — cualquier denegación de permiso vale
                await session.rollback()
            else:
                raise AssertionError(f"una sesión de organización pudo ejecutar: {sentencia}")


async def test_una_sesion_sin_contexto_rls_no_ve_datos_de_ninguna_organizacion() -> None:
    """La sesión de plataforma no puede leer datos de nadie.

    Las políticas RLS comparan contra `app_current_organization()`, que sin
    contexto es NULL y por tanto no devuelve ninguna fila. Se verifica aquí
    para que un cambio futuro en las políticas no convierta esa sesión en una
    lectura global silenciosa.
    """
    # Consultas literales, una por tabla: el nombre de la tabla nunca se
    # interpola desde una variable.
    consultas = (
        "SELECT count(*) FROM organizations",
        "SELECT count(*) FROM events",
        "SELECT count(*) FROM users",
        "SELECT count(*) FROM organization_members",
    )
    async with SessionApp() as session:
        for consulta in consultas:
            total = await session.scalar(text(consulta))
            assert total == 0, f"sin contexto RLS, «{consulta}» devolvió {total} filas"
