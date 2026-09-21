"""`GET /organizations/me/ai-usage` y la purga por retención (fase 2)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import update

from app.core.database import SessionApp, SessionMaintenance, set_organization_context
from app.modules.ai_gateway import client as ai_client
from app.modules.ai_gateway import repository
from app.modules.ai_gateway.models import AiUsageRecord
from tests.ai_gateway_test_helpers import (
    ProveedorSimulado,
    configurar_organizacion,
    configurar_plataforma,
)
from tests.conftest import (
    OrganizacionDePrueba,
    crear_miembro,
    iniciar_sesion,
    iniciar_sesion_con,
)

MENSAJES = [{"role": "user", "content": "hola"}]


async def _llamar(organizacion: OrganizacionDePrueba) -> None:
    await ai_client.completar(
        organization_id=organizacion.id, use_case="accounting_ocr", messages=MENSAJES
    )


async def test_el_resumen_refleja_el_gasto_y_el_limite(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    cifrado: str,
    proveedor_simulado: ProveedorSimulado,
    dns_publico: None,
) -> None:
    await configurar_plataforma(techo_usd=Decimal("10"))
    await _llamar(organizacion)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    respuesta = await cliente.get("/api/v1/organizations/me/ai-usage", headers=cabeceras)

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["periodo"] == repository.periodo_actual()
    assert cuerpo["llamadas"] == 1
    assert cuerpo["llamadas_fallidas"] == 0
    assert Decimal(cuerpo["gasto_usd"]) == ai_client.COSTE_DE_SEGURIDAD_USD
    # `nan_builders` está fuera del mapa de precios: el total es orientativo.
    assert cuerpo["gasto_auditable"] is False
    assert Decimal(cuerpo["limite_efectivo_usd"]) == Decimal("10")
    assert cuerpo["servicio_ia_activo"] is True
    assert cuerpo["input_tokens"] == 10
    assert cuerpo["output_tokens"] == 3
    assert len(cuerpo["ultimos"]) == 1
    assert cuerpo["ultimos"][0]["use_case"] == "accounting_ocr"
    assert cuerpo["ultimos"][0]["provider"] == "nan_builders"
    assert cuerpo["ultimos"][0]["status"] == "liquidado"
    assert cuerpo["ultimos_errores"] == []


async def test_el_resumen_agrupa_los_codigos_de_error(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    cifrado: str,
    proveedor_simulado: ProveedorSimulado,
    dns_publico: None,
) -> None:
    """Sin vista de detalle (no-objetivo del PRD), los `error_code` agrupados
    son la única pista de diagnóstico del panel."""
    await configurar_plataforma()
    proveedor_simulado.estado = 500
    proveedor_simulado.cuerpo = {"error": {"message": "caído"}}
    for _ in range(2):
        try:
            await _llamar(organizacion)
        except Exception:  # noqa: BLE001, S110 - el fallo es lo que se prueba
            pass
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    cuerpo = (await cliente.get("/api/v1/organizations/me/ai-usage", headers=cabeceras)).json()

    assert cuerpo["llamadas"] == 2
    assert cuerpo["llamadas_fallidas"] == 2
    # Las fallidas no suman al gasto del periodo.
    assert Decimal(cuerpo["gasto_usd"]) == Decimal("0")
    assert cuerpo["ultimos_errores"] == [
        {
            "error_code": "proveedor_error",
            "veces": 2,
            "ultima_vez": cuerpo["ultimos_errores"][0]["ultima_vez"],
        }
    ]


async def test_el_resumen_solo_ve_el_uso_propio(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    otra_organizacion: OrganizacionDePrueba,
    cifrado: str,
    proveedor_simulado: ProveedorSimulado,
    dns_publico: None,
) -> None:
    await configurar_plataforma()
    await _llamar(organizacion)
    _, cabeceras = await iniciar_sesion(cliente, otra_organizacion)

    cuerpo = (await cliente.get("/api/v1/organizations/me/ai-usage", headers=cabeceras)).json()

    assert cuerpo["llamadas"] == 0
    assert cuerpo["ultimos"] == []


async def test_el_resumen_lo_ve_solo_el_propietario(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, cifrado: str
) -> None:
    """Mismo gate que `/me/ai-settings`: `organizer` tiene permisos amplios,
    pero el gasto de la organización es exclusivo de `owner`."""
    miembro = await crear_miembro(organizacion, "organizer")
    _, cabeceras = await iniciar_sesion_con(cliente, organizacion, miembro.email, miembro.password)

    respuesta = await cliente.get("/api/v1/organizations/me/ai-usage", headers=cabeceras)

    assert respuesta.status_code == 403


async def test_el_resumen_devuelve_el_limite_propio_cuando_es_menor(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    cifrado: str,
    proveedor_simulado: ProveedorSimulado,
    dns_publico: None,
) -> None:
    await configurar_plataforma(techo_usd=Decimal("50"))
    await configurar_organizacion(organizacion.id, limite_usd=Decimal("5"))
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    cuerpo = (await cliente.get("/api/v1/organizations/me/ai-usage", headers=cabeceras)).json()

    assert Decimal(cuerpo["limite_efectivo_usd"]) == Decimal("5")


async def test_la_purga_respeta_la_retencion_y_no_borra_reservas(
    organizacion: OrganizacionDePrueba,
    cifrado: str,
    proveedor_simulado: ProveedorSimulado,
    dns_publico: None,
) -> None:
    """Una fila liquidada antigua se purga; una reserva sin cerrar no, por
    antigua que sea: borrarla escondería gasto en vez de registrarlo."""
    await configurar_plataforma()
    await _llamar(organizacion)
    periodo = repository.periodo_actual()
    async with SessionApp() as session, session.begin():
        await set_organization_context(session, organizacion.id)
        await repository.asegurar_periodo(session, organizacion.id, periodo)
        await repository.reservar_uso(
            session,
            organization_id=organizacion.id,
            periodo=periodo,
            use_case="accounting_ocr",
            provider="nan_builders",
            model="deepseek-v4-flash",
            coste_estimado_usd=Decimal("0.05"),
            limite_usd=None,
        )

    antiguo = datetime.now(UTC) - timedelta(days=200)
    async with SessionMaintenance() as session:
        await session.execute(update(AiUsageRecord).values(created_at=antiguo))
        await session.commit()

    async with SessionMaintenance() as session:
        borradas = await repository.purgar_usos_antiguos(session, dias=90)
        await session.commit()

    assert borradas == 1
    async with SessionApp() as session, session.begin():
        await set_organization_context(session, organizacion.id)
        restantes = list(await session.scalars(AiUsageRecord.__table__.select()))
    assert len(restantes) == 1
