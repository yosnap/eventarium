"""Nivel organización de la pasarela de IA: herencia, override, techo y gates."""

from __future__ import annotations

import json
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import delete, select

from app.core.audit import AuditLog
from app.core.database import SessionApp, SessionMaintenance, set_organization_context
from app.modules.ai_gateway.models import OrganizationAiSettings, PlatformAiSettings
from app.modules.ai_gateway.service import limite_efectivo
from app.modules.organizations.models import OrganizationMember
from tests.ai_gateway_test_helpers import (
    CLAVE_DE_PROVEEDOR,
    cabeceras_de_superadmin,
    hacer_superadmin,
)
from tests.conftest import (
    OrganizacionDePrueba,
    crear_miembro,
    iniciar_sesion,
    iniciar_sesion_con,
)

MIS_AJUSTES = "/api/v1/organizations/me/ai-settings"
AJUSTES_DE_PLATAFORMA = "/api/v1/admin/ai-settings"

CLAVE_PROPIA = "ci_live_clave-propia-de-la-org-9876"

CONFIG_PROPIA = {
    "provider": "cheaper_inference",
    "default_model": "gpt-5.4",
    "api_key": CLAVE_PROPIA,
}


async def _configurar_plataforma(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, *, techo: str | None = "50.000000"
) -> None:
    """Deja configurada la plataforma con un superadmin aparte.

    El superadmin es una persona **distinta** del propietario de la
    organización que luego hereda: así el test no puede pasar por accidente
    gracias a un privilegio cruzado.
    """
    admin = await crear_miembro(organizacion, "organizer", email="admin-plataforma@acme.com")
    await hacer_superadmin(admin.email)
    _, cabeceras = await iniciar_sesion_con(cliente, organizacion, admin.email, admin.password)
    cuerpo: dict[str, object] = {
        "provider": "nan_builders",
        "default_model": "deepseek-v4-flash",
        "api_key": CLAVE_DE_PROVEEDOR,
    }
    if techo is not None:
        cuerpo["monthly_ceiling_usd"] = techo
    respuesta = await cliente.put(AJUSTES_DE_PLATAFORMA, headers=cabeceras, json=cuerpo)
    assert respuesta.status_code == 200, respuesta.text


async def test_sin_nada_configurado_el_estado_es_sin_configuracion(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, cifrado: str
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    respuesta = await cliente.get(MIS_AJUSTES, headers=cabeceras)
    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["origen"] == "sin_configuracion"
    assert cuerpo["has_key"] is False
    assert cuerpo["servicio_ia_activo"] is True


async def test_la_organizacion_hereda_la_configuracion_de_plataforma(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, cifrado: str
) -> None:
    await _configurar_plataforma(cliente, organizacion)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    respuesta = await cliente.get(MIS_AJUSTES, headers=cabeceras)
    cuerpo = respuesta.json()
    assert cuerpo["origen"] == "heredada"
    assert cuerpo["provider"] == "nan_builders"
    assert cuerpo["has_key"] is True
    # V-11: la pista de la clave de plataforma no se enseña a ningún tenant.
    assert cuerpo["api_key_hint"] is None
    assert cuerpo["monthly_ceiling_usd"] == "50.000000"
    assert cuerpo["limite_efectivo_usd"] == "50.000000"
    assert CLAVE_DE_PROVEEDOR not in respuesta.text


async def test_el_owner_sobrescribe_con_su_configuracion(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, cifrado: str
) -> None:
    await _configurar_plataforma(cliente, organizacion)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    guardado = await cliente.put(
        MIS_AJUSTES, headers=cabeceras, json={**CONFIG_PROPIA, "monthly_limit_usd": "10.000000"}
    )
    assert guardado.status_code == 200, guardado.text
    cuerpo = guardado.json()
    assert cuerpo["origen"] == "propia"
    assert cuerpo["provider"] == "cheaper_inference"
    assert cuerpo["api_base"] == "https://api.cheaperinference.com/v1"
    # La pista sí se ve cuando la clave es suya.
    assert cuerpo["api_key_hint"] == CLAVE_PROPIA[-4:]
    assert cuerpo["limite_efectivo_usd"] == "10.000000"
    assert "api_key" not in cuerpo
    assert CLAVE_PROPIA not in guardado.text

    leido = await cliente.get(MIS_AJUSTES, headers=cabeceras)
    assert leido.json()["origen"] == "propia"
    assert CLAVE_PROPIA not in leido.text


async def test_la_clave_de_la_organizacion_se_guarda_cifrada(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, cifrado: str
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    await cliente.put(MIS_AJUSTES, headers=cabeceras, json=CONFIG_PROPIA)

    async with SessionMaintenance() as session:
        fila = await session.scalar(select(OrganizationAiSettings))
    assert fila is not None
    assert CLAVE_PROPIA not in fila.api_key_encrypted
    assert fila.api_key_hint == CLAVE_PROPIA[-4:]


async def test_borrar_el_override_vuelve_a_heredar(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, cifrado: str
) -> None:
    await _configurar_plataforma(cliente, organizacion)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    await cliente.put(MIS_AJUSTES, headers=cabeceras, json=CONFIG_PROPIA)

    borrado = await cliente.delete(MIS_AJUSTES, headers=cabeceras)
    assert borrado.status_code == 204

    despues = await cliente.get(MIS_AJUSTES, headers=cabeceras)
    assert despues.json()["origen"] == "heredada"
    assert despues.json()["provider"] == "nan_builders"


async def test_un_limite_por_encima_del_techo_se_rechaza_y_no_se_persiste(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, cifrado: str
) -> None:
    await _configurar_plataforma(cliente, organizacion, techo="20.000000")
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    respuesta = await cliente.put(
        MIS_AJUSTES, headers=cabeceras, json={**CONFIG_PROPIA, "monthly_limit_usd": "99.000000"}
    )
    assert respuesta.status_code == 422, respuesta.text
    assert respuesta.json()["code"] == "limite_por_encima_del_techo"

    async with SessionMaintenance() as session:
        assert await session.scalar(select(OrganizationAiSettings)) is None


async def test_bajar_el_techo_por_debajo_del_limite_manda_sin_bloquear_al_admin(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, cifrado: str
) -> None:
    """Riesgo S3-5: el efectivo es el mínimo, no se frena al admin."""
    await _configurar_plataforma(cliente, organizacion, techo="50.000000")
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    await cliente.put(
        MIS_AJUSTES, headers=cabeceras, json={**CONFIG_PROPIA, "monthly_limit_usd": "40.000000"}
    )

    cabeceras_admin = await cabeceras_de_superadmin(cliente, organizacion)
    bajada = await cliente.put(
        AJUSTES_DE_PLATAFORMA, headers=cabeceras_admin, json={"monthly_ceiling_usd": "5.000000"}
    )
    assert bajada.status_code == 200

    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    cuerpo = (await cliente.get(MIS_AJUSTES, headers=cabeceras)).json()
    assert cuerpo["monthly_limit_usd"] == "40.000000"
    assert cuerpo["limite_efectivo_usd"] == "5.000000"


def test_semantica_del_nulo_en_el_limite_efectivo() -> None:
    """V-6: los cuatro casos, explícitos."""
    assert limite_efectivo(None, None) is None
    assert limite_efectivo(Decimal("10"), None) == Decimal("10")
    assert limite_efectivo(None, Decimal("30")) == Decimal("30")
    assert limite_efectivo(Decimal("40"), Decimal("30")) == Decimal("30")


async def test_un_override_sin_clave_se_rechaza(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, cifrado: str
) -> None:
    """V-5: una fila de override sin clave no existe por construcción."""
    await _configurar_plataforma(cliente, organizacion)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    respuesta = await cliente.put(
        MIS_AJUSTES, headers=cabeceras, json={"monthly_limit_usd": "10.000000"}
    )
    assert respuesta.status_code == 422, respuesta.text
    assert respuesta.json()["code"] == "clave_requerida"

    async with SessionMaintenance() as session:
        assert await session.scalar(select(OrganizationAiSettings)) is None


async def test_un_api_base_enviado_a_un_proveedor_de_base_fija_se_rechaza(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, cifrado: str
) -> None:
    """Evita robar la clave apuntando el proveedor a un host del atacante."""
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    respuesta = await cliente.put(
        MIS_AJUSTES,
        headers=cabeceras,
        json={**CONFIG_PROPIA, "api_base": "https://host-del-atacante.example/v1"},
    )
    assert respuesta.status_code == 422
    assert respuesta.json()["code"] == "api_base_no_permitido"

    async with SessionMaintenance() as session:
        assert await session.scalar(select(OrganizationAiSettings)) is None


async def test_un_miembro_sin_rol_owner_recibe_403(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, cifrado: str
) -> None:
    """`organizer` tiene permisos amplios, pero esto es exclusivo de `owner`."""
    miembro = await crear_miembro(organizacion, "organizer")
    _, cabeceras = await iniciar_sesion_con(cliente, organizacion, miembro.email, miembro.password)

    assert (await cliente.get(MIS_AJUSTES, headers=cabeceras)).status_code == 403
    assert (
        await cliente.put(MIS_AJUSTES, headers=cabeceras, json=CONFIG_PROPIA)
    ).status_code == 403
    assert (await cliente.delete(MIS_AJUSTES, headers=cabeceras)).status_code == 403


async def test_varias_membresias_con_una_owner_no_reciben_403(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, cifrado: str
) -> None:
    """El gate mira **todas** las membresías, no la primera."""
    miembro = await crear_miembro(organizacion, "organizer", email="doble@acme.com")
    async with SessionMaintenance() as session:
        session.add(
            OrganizationMember(
                organization_id=organizacion.id,
                user_id=miembro.user_id,
                role_id=organizacion.owner_role_id,
                profile_data={},
            )
        )
        await session.commit()

    _, cabeceras = await iniciar_sesion_con(cliente, organizacion, miembro.email, miembro.password)
    assert (await cliente.get(MIS_AJUSTES, headers=cabeceras)).status_code == 200


async def test_el_organizador_no_tiene_endpoint_de_servicios(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    """V-8: el override de servicios lo escribe solo el admin."""
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    respuesta = await cliente.put(
        "/api/v1/organizations/me/services",
        headers=cabeceras,
        json={"services": [{"service_key": "ai", "enabled": True}]},
    )
    assert respuesta.status_code in {404, 405}


async def test_un_servicio_apagado_para_la_organizacion_se_ve_en_su_get(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, cifrado: str
) -> None:
    cabeceras_admin = await cabeceras_de_superadmin(cliente, organizacion)
    await cliente.put(
        f"/api/v1/admin/organizations/{organizacion.id}/services",
        headers=cabeceras_admin,
        json={"services": [{"service_key": "ai", "enabled": False}]},
    )

    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    assert (await cliente.get(MIS_AJUSTES, headers=cabeceras)).json()["servicio_ia_activo"] is False


async def test_borrar_la_config_de_plataforma_degrada_a_sin_configuracion(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, cifrado: str
) -> None:
    """V-12: degrada con un estado de dominio claro, nunca con un 500."""
    await _configurar_plataforma(cliente, organizacion)
    async with SessionMaintenance() as session:
        await session.execute(delete(PlatformAiSettings))
        await session.commit()

    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    respuesta = await cliente.get(MIS_AJUSTES, headers=cabeceras)
    assert respuesta.status_code == 200
    assert respuesta.json()["origen"] == "sin_configuracion"


async def test_la_configuracion_de_una_organizacion_no_la_ve_otra(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    otra_organizacion: OrganizacionDePrueba,
    cifrado: str,
) -> None:
    """RLS: aunque el repositorio olvidara el filtro, la política corta."""
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    await cliente.put(MIS_AJUSTES, headers=cabeceras, json=CONFIG_PROPIA)

    async with SessionApp() as session, session.begin():
        await set_organization_context(session, otra_organizacion.id, otra_organizacion.owner_id)
        filas = (await session.scalars(select(OrganizationAiSettings))).all()
    assert filas == []


async def _auditoria_de_ia(accion: str) -> list[AuditLog]:
    async with SessionMaintenance() as session:
        filas = await session.scalars(select(AuditLog).where(AuditLog.action == accion))
        return list(filas)


async def test_guardar_el_override_queda_auditado_sin_la_clave(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, cifrado: str
) -> None:
    """Una credencial con gasto asociado no se guarda sin dejar rastro."""
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    respuesta = await cliente.put(MIS_AJUSTES, headers=cabeceras, json=CONFIG_PROPIA)
    assert respuesta.status_code == 200, respuesta.text

    filas = await _auditoria_de_ia("organization_ai_settings.updated")
    assert len(filas) == 1
    fila = filas[0]
    assert fila.actor_user_id == organizacion.owner_id
    assert fila.organization_id == organizacion.id
    assert fila.entity_type == "organization_ai_settings"
    assert fila.detail["provider"] == "cheaper_inference"
    assert fila.detail["default_model"] == "gpt-5.4"
    assert fila.detail["has_key"] is True
    # Ni en claro ni cifrada ni su pista: la auditoría es otro sitio donde
    # una credencial no debe acabar.
    serializada = json.dumps(fila.detail)
    assert CLAVE_PROPIA not in serializada
    assert CLAVE_PROPIA[-4:] not in serializada


async def test_volver_a_heredar_queda_auditado(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, cifrado: str
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    await cliente.put(MIS_AJUSTES, headers=cabeceras, json=CONFIG_PROPIA)

    borrado = await cliente.delete(MIS_AJUSTES, headers=cabeceras)
    assert borrado.status_code == 204

    filas = await _auditoria_de_ia("organization_ai_settings.deleted")
    assert len(filas) == 1
    assert filas[0].actor_user_id == organizacion.owner_id
    assert filas[0].organization_id == organizacion.id
    assert filas[0].detail == {"habia_configuracion": True}
