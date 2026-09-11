"""Endpoints y aislamiento de la identidad de plataforma.

Cubre los criterios de éxito de la fase: un host de plataforma sirve la web de
la instalación **sin** organización (antes era imposible: cualquier host sin
organización daba 404), el fail-closed para hosts de organización no
registrados se conserva, y las tablas de plataforma no son escribibles por una
sesión de organización.
"""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy import text

from app.core.database import SessionApp, SessionMaintenance
from tests.conftest import OrganizacionDePrueba

HOST_PLATAFORMA = "eventarium.test"


async def _registrar_host_de_plataforma(host: str) -> None:
    async with SessionMaintenance() as session:
        await session.execute(
            text("INSERT INTO platform_domains (id, host) VALUES (gen_random_uuid(), :host)"),
            {"host": host},
        )
        await session.commit()


async def _limpiar_hosts_de_plataforma() -> None:
    async with SessionMaintenance() as session:
        await session.execute(text("DELETE FROM platform_domains"))
        await session.commit()


async def test_host_de_plataforma_sirve_el_branding_sin_organizacion(
    cliente: AsyncClient,
) -> None:
    """El bloque `platform` llega aunque el host no resuelva a ninguna organización."""
    await _registrar_host_de_plataforma(HOST_PLATAFORMA)
    try:
        respuesta = await cliente.get("/api/v1/tenant/branding", headers={"Host": HOST_PLATAFORMA})
        assert respuesta.status_code == 200, respuesta.text

        cuerpo = respuesta.json()
        assert cuerpo["platform"]["name"] == "Eventarium"
        # Sin organización: los campos de raíz van nulos, no ausentes.
        assert cuerpo["organization_id"] is None
        assert cuerpo["organization_slug"] is None
    finally:
        await _limpiar_hosts_de_plataforma()


async def test_host_de_organizacion_trae_los_dos_bloques(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    """Un host de organización sigue sirviendo su identidad, además de la de plataforma."""
    respuesta = await cliente.get("/api/v1/tenant/branding", headers={"Host": organizacion.host})
    assert respuesta.status_code == 200, respuesta.text

    cuerpo = respuesta.json()
    assert cuerpo["organization_slug"] == organizacion.slug
    assert cuerpo["platform"]["name"] == "Eventarium"


async def test_host_desconocido_sigue_devolviendo_404(cliente: AsyncClient) -> None:
    """El fail-closed no se relaja: un host que no es de plataforma ni de organización falla."""
    respuesta = await cliente.get(
        "/api/v1/tenant/branding", headers={"Host": "no-existe-en-ningun-sitio.test"}
    )
    assert respuesta.status_code == 404, respuesta.text


async def test_legal_de_plataforma_en_host_de_plataforma(cliente: AsyncClient) -> None:
    """Las legales de plataforma se sirven sin organización resuelta."""
    await _registrar_host_de_plataforma(HOST_PLATAFORMA)
    try:
        respuesta = await cliente.get(
            "/api/v1/public/legal/aviso-legal", headers={"Host": HOST_PLATAFORMA}
        )
        assert respuesta.status_code == 200, respuesta.text
        contenido = respuesta.json()["content"]
        assert "Eventarium" in contenido
    finally:
        await _limpiar_hosts_de_plataforma()


async def test_condiciones_de_inscripcion_no_existen_para_la_plataforma(
    cliente: AsyncClient,
) -> None:
    """Las condiciones son de la organización que inscribe, no de la plataforma."""
    await _registrar_host_de_plataforma(HOST_PLATAFORMA)
    try:
        respuesta = await cliente.get(
            "/api/v1/public/legal/condiciones-de-inscripcion", headers={"Host": HOST_PLATAFORMA}
        )
        assert respuesta.status_code == 404, respuesta.text
    finally:
        await _limpiar_hosts_de_plataforma()


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
            "INSERT INTO platform_domains (id, host) VALUES (gen_random_uuid(), 'malo.test')",
            "UPDATE platform_legal_pages SET content = 'secuestrado'",
        ):
            try:
                await session.execute(text(sentencia))
                await session.commit()
            except Exception:  # noqa: BLE001 — cualquier denegación de permiso vale
                await session.rollback()
            else:
                raise AssertionError(f"una sesión de organización pudo ejecutar: {sentencia}")
