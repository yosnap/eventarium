"""Políticas y condiciones propias del organizador: versionado, resolución del
texto vigente, permisos, inmutabilidad y aislamiento entre organizaciones."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.core.database import SessionApp, SessionMaintenance, set_organization_context
from app.core.permissions import Permission
from app.modules.events.models import Event
from app.modules.policies import service
from app.modules.policies.models import OrganizationPolicyVersion
from app.shared.errors import ConflictError
from tests.conftest import (
    OrganizacionDePrueba,
    crear_miembro,
    crear_rol,
    iniciar_sesion,
    iniciar_sesion_con,
)

ORGANIZACION = "/api/v1/organizations/me/policies"
AHORA = datetime.now(UTC)


def _evento_url(event_id: uuid.UUID) -> str:
    return f"/api/v1/events/{event_id}/policies"


async def _crear_evento(organizacion: OrganizacionDePrueba) -> uuid.UUID:
    async with SessionMaintenance() as session:
        evento = Event(
            organization_id=organizacion.id,
            slug=f"evento-politicas-{uuid.uuid4().hex[:8]}",
            title="Evento con políticas",
            status="published",
            visibility="public",
            starts_at=AHORA,
            ends_at=AHORA + timedelta(days=1),
            location_mode="online",
        )
        session.add(evento)
        await session.commit()
        return evento.id


def _por_tipo(respuesta: dict) -> dict[str, dict]:  # type: ignore[type-arg]
    return {item["kind"]: item for item in respuesta["items"]}


async def test_guardar_crea_versiones_nuevas_sin_tocar_las_anteriores(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    for numero in (1, 2, 3):
        respuesta = await cliente.put(
            f"{ORGANIZACION}/reembolsos", json={"content": f"Texto {numero}"}, headers=cabeceras
        )
        assert respuesta.status_code == 200, respuesta.text

    reembolsos = _por_tipo(respuesta.json())["reembolsos"]
    assert reembolsos["current"]["version"] == 3
    assert reembolsos["current"]["content"] == "Texto 3"

    async with SessionMaintenance() as session:
        filas = (
            await session.scalars(
                select(OrganizationPolicyVersion)
                .where(OrganizationPolicyVersion.kind == "reembolsos")
                .order_by(OrganizationPolicyVersion.version)
            )
        ).all()
    assert [(fila.version, fila.content) for fila in filas] == [
        (1, "Texto 1"),
        (2, "Texto 2"),
        (3, "Texto 3"),
    ]


async def test_retirar_un_texto_de_organizacion_lo_deja_sin_texto_vigente(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    await cliente.put(f"{ORGANIZACION}/privacidad", json={"content": "Hola"}, headers=cabeceras)
    respuesta = await cliente.put(
        f"{ORGANIZACION}/privacidad", json={"content": "   "}, headers=cabeceras
    )
    privacidad = _por_tipo(respuesta.json())["privacidad"]
    assert privacidad["current"] is None
    assert privacidad["last_version"] == 2


async def test_un_texto_de_organizacion_nulo_es_invalido(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    respuesta = await cliente.put(
        f"{ORGANIZACION}/condiciones", json={"content": None}, headers=cabeceras
    )
    assert respuesta.status_code == 422


async def test_mas_de_cincuenta_mil_caracteres_es_invalido(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    respuesta = await cliente.put(
        f"{ORGANIZACION}/condiciones", json={"content": "x" * 50_001}, headers=cabeceras
    )
    assert respuesta.status_code == 422


async def test_un_tipo_desconocido_es_invalido(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    respuesta = await cliente.put(
        f"{ORGANIZACION}/cookies", json={"content": "x"}, headers=cabeceras
    )
    assert respuesta.status_code == 422


async def test_resolucion_evento_propio_organizacion_o_ninguno(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    event_id = await _crear_evento(organizacion)
    await cliente.put(
        f"{ORGANIZACION}/condiciones", json={"content": "De la organización"}, headers=cabeceras
    )
    await cliente.put(
        f"{ORGANIZACION}/reembolsos", json={"content": "Reembolsos generales"}, headers=cabeceras
    )
    respuesta = await cliente.put(
        f"{_evento_url(event_id)}/reembolsos",
        json={"content": "Reembolsos de este evento"},
        headers=cabeceras,
    )
    assert respuesta.status_code == 200, respuesta.text
    items = _por_tipo(respuesta.json())

    assert items["condiciones"]["origin"] == "organizacion"
    assert items["condiciones"]["current"]["content"] == "De la organización"
    assert items["reembolsos"]["origin"] == "evento"
    assert items["reembolsos"]["current"]["content"] == "Reembolsos de este evento"
    # El texto de la organización se sigue enseñando aunque el evento lo sustituya.
    assert items["reembolsos"]["organization"]["content"] == "Reembolsos generales"
    assert items["privacidad"]["origin"] == "ninguno"
    assert items["privacidad"]["current"] is None
    assert items["otras"]["origin"] == "ninguno"


async def test_volver_a_heredar_usa_la_version_de_la_organizacion(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    event_id = await _crear_evento(organizacion)
    general = await cliente.put(
        f"{ORGANIZACION}/condiciones", json={"content": "General"}, headers=cabeceras
    )
    version_general = _por_tipo(general.json())["condiciones"]["current"]["version_id"]
    await cliente.put(
        f"{_evento_url(event_id)}/condiciones", json={"content": "Propio"}, headers=cabeceras
    )
    respuesta = await cliente.put(
        f"{_evento_url(event_id)}/condiciones", json={"content": None}, headers=cabeceras
    )
    condiciones = _por_tipo(respuesta.json())["condiciones"]
    assert condiciones["origin"] == "organizacion"
    # Invariante: el id vigente es el de la fila cuyo texto se muestra, nunca
    # el de la fila de evento vacía que marca «vuelve a heredar».
    assert condiciones["current"]["version_id"] == version_general


async def test_un_texto_propio_de_evento_vacio_es_invalido(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    event_id = await _crear_evento(organizacion)
    respuesta = await cliente.put(
        f"{_evento_url(event_id)}/condiciones", json={"content": "  "}, headers=cabeceras
    )
    assert respuesta.status_code == 422


async def test_escribir_textos_exige_permiso_de_organizacion_tambien_en_un_evento(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    """Un rol a medida con `events:write` pero sin `organizations:write` no
    puede sustituir los textos de un evento: obligan a toda la organización."""
    event_id = await _crear_evento(organizacion)
    await crear_rol(
        organizacion,
        key="editor-de-eventos",
        permisos=[Permission.EVENTS_READ, Permission.EVENTS_WRITE, Permission.ORGANIZATIONS_READ],
    )
    miembro = await crear_miembro(organizacion, "editor-de-eventos")
    _, cabeceras = await iniciar_sesion_con(cliente, organizacion, miembro.email, miembro.password)

    evento = await cliente.put(
        f"{_evento_url(event_id)}/privacidad", json={"content": "x"}, headers=cabeceras
    )
    assert evento.status_code == 403
    organizacion_put = await cliente.put(
        f"{ORGANIZACION}/privacidad", json={"content": "x"}, headers=cabeceras
    )
    assert organizacion_put.status_code == 403
    # Leer sí puede, y el panel sabe que debe mostrarlo en solo lectura.
    lectura = await cliente.get(_evento_url(event_id), headers=cabeceras)
    assert lectura.status_code == 200
    assert lectura.json()["can_edit"] is False
    de_organizacion = await cliente.get(ORGANIZACION, headers=cabeceras)
    assert de_organizacion.json()["can_edit"] is False


async def test_consultar_una_version_antigua_devuelve_su_contenido_exacto(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    event_id = await _crear_evento(organizacion)
    primera = await cliente.put(
        f"{_evento_url(event_id)}/otras", json={"content": "Versión uno"}, headers=cabeceras
    )
    version_id = _por_tipo(primera.json())["otras"]["current"]["version_id"]
    await cliente.put(
        f"{_evento_url(event_id)}/otras", json={"content": "Versión dos"}, headers=cabeceras
    )

    respuesta = await cliente.get(
        f"{_evento_url(event_id)}/versions/{version_id}", headers=cabeceras
    )
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["content"] == "Versión uno"
    assert respuesta.json()["version"] == 1


async def test_una_version_de_otro_evento_no_se_devuelve(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    un_evento = await _crear_evento(organizacion)
    otro_evento = await _crear_evento(organizacion)
    respuesta = await cliente.put(
        f"{_evento_url(un_evento)}/otras", json={"content": "Solo del primero"}, headers=cabeceras
    )
    version_id = _por_tipo(respuesta.json())["otras"]["current"]["version_id"]
    cruzada = await cliente.get(
        f"{_evento_url(otro_evento)}/versions/{version_id}", headers=cabeceras
    )
    assert cruzada.status_code == 404


async def test_otra_organizacion_no_ve_ni_escribe_los_textos_ajenos(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    otra_organizacion: OrganizacionDePrueba,
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    event_id = await _crear_evento(organizacion)
    respuesta = await cliente.put(
        f"{ORGANIZACION}/privacidad", json={"content": "Privada de acme"}, headers=cabeceras
    )
    version_id = _por_tipo(respuesta.json())["privacidad"]["current"]["version_id"]

    _, ajenas = await iniciar_sesion(cliente, otra_organizacion)
    propias = _por_tipo((await cliente.get(ORGANIZACION, headers=ajenas)).json())
    assert all(item["current"] is None for item in propias.values())
    assert (await cliente.get(_evento_url(event_id), headers=ajenas)).status_code == 404
    escritura = await cliente.put(
        f"{_evento_url(event_id)}/privacidad", json={"content": "x"}, headers=ajenas
    )
    assert escritura.status_code == 404
    version = await cliente.get(f"{_evento_url(event_id)}/versions/{version_id}", headers=ajenas)
    assert version.status_code == 404


async def test_rls_oculta_los_textos_de_organizacion_ajenos(
    organizacion: OrganizacionDePrueba, otra_organizacion: OrganizacionDePrueba
) -> None:
    async with SessionMaintenance() as session:
        session.add(
            OrganizationPolicyVersion(
                organization_id=organizacion.id, kind="condiciones", content="Acme", version=1
            )
        )
        await session.commit()

    async with SessionApp() as session, session.begin():
        await set_organization_context(session, otra_organizacion.id)
        visibles = (await session.scalars(select(OrganizationPolicyVersion))).all()
    assert visibles == []


@pytest.mark.parametrize(
    "sentencia",
    [
        "UPDATE organization_policy_versions SET content = 'reescrito'",
        "DELETE FROM organization_policy_versions",
    ],
)
async def test_la_aplicacion_no_puede_reescribir_ni_borrar_versiones(
    organizacion: OrganizacionDePrueba, sentencia: str
) -> None:
    """La prueba de lo aceptado no se puede reescribir desde el rol de la API."""
    async with SessionMaintenance() as session:
        session.add(
            OrganizationPolicyVersion(
                organization_id=organizacion.id, kind="condiciones", content="Original", version=1
            )
        )
        await session.commit()

    with pytest.raises(DBAPIError, match="permission denied"):
        async with SessionApp() as session, session.begin():
            await set_organization_context(session, organizacion.id)
            await session.execute(text(sentencia))


async def test_borrar_el_evento_borra_sus_versiones_y_conserva_las_de_la_organizacion(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    event_id = await _crear_evento(organizacion)
    await cliente.put(f"{ORGANIZACION}/condiciones", json={"content": "Org"}, headers=cabeceras)
    await cliente.put(
        f"{_evento_url(event_id)}/condiciones", json={"content": "Evento"}, headers=cabeceras
    )

    async with SessionMaintenance() as session:
        await session.execute(text("DELETE FROM events WHERE id = :id"), {"id": event_id})
        await session.commit()
        filas = (await session.scalars(select(OrganizationPolicyVersion))).all()
    assert [(fila.event_id, fila.content) for fila in filas] == [(None, "Org")]


async def test_guardar_el_mismo_texto_no_crea_version(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    """Un «Guardar» sin cambios no debe obligar a volver a aceptar las
    condiciones a quien tenga el formulario de inscripción abierto."""
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    event_id = await _crear_evento(organizacion)
    for _ in range(2):
        await cliente.put(
            f"{ORGANIZACION}/condiciones", json={"content": "Igual"}, headers=cabeceras
        )
        await cliente.put(
            f"{_evento_url(event_id)}/otras", json={"content": "Propio"}, headers=cabeceras
        )
        await cliente.put(
            f"{_evento_url(event_id)}/reembolsos", json={"content": None}, headers=cabeceras
        )
    async with SessionMaintenance() as session:
        versiones = sorted(
            (fila.kind, fila.version)
            for fila in (await session.scalars(select(OrganizationPolicyVersion))).all()
        )
    assert versiones == [("condiciones", 1), ("otras", 1), ("reembolsos", 1)]


async def test_sin_escribir_no_hay_ultima_version(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    items = _por_tipo((await cliente.get(ORGANIZACION, headers=cabeceras)).json())
    assert all(item["current"] is None and item["last_version"] is None for item in items.values())


async def test_la_fila_de_volver_a_heredar_no_se_consulta_como_version(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    event_id = await _crear_evento(organizacion)
    await cliente.put(
        f"{_evento_url(event_id)}/otras", json={"content": "Propio"}, headers=cabeceras
    )
    await cliente.put(f"{_evento_url(event_id)}/otras", json={"content": None}, headers=cabeceras)
    async with SessionMaintenance() as session:
        heredar = await session.scalar(
            select(OrganizationPolicyVersion).where(OrganizationPolicyVersion.content.is_(None))
        )
    assert heredar is not None
    respuesta = await cliente.get(
        f"{_evento_url(event_id)}/versions/{heredar.id}", headers=cabeceras
    )
    assert respuesta.status_code == 404


async def test_un_guardado_simultaneo_da_conflicto_y_no_un_error(
    organizacion: OrganizacionDePrueba, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Si otra persona guarda entre la lectura de la última versión y la
    inserción, el índice único choca y el servicio responde 409 legible."""
    async with SessionMaintenance() as session:
        session.add(
            OrganizationPolicyVersion(
                organization_id=organizacion.id, kind="condiciones", content="De otra", version=1
            )
        )
        await session.commit()

    async with SessionApp() as session, session.begin():
        await set_organization_context(session, organizacion.id)

        # La lectura de la última versión «no ve» la que acaba de guardar la
        # otra persona, así que se intenta insertar la versión 1 otra vez.
        async def sin_ultima(*_args: object, **_kwargs: object) -> None:
            return None

        monkeypatch.setattr(session, "scalar", sin_ultima)
        with pytest.raises(ConflictError):
            await service.guardar_version(
                session,
                organization_id=organizacion.id,
                event_id=None,
                kind="condiciones",
                content="Mío",
                user_id=None,
            )
        monkeypatch.undo()
        # La transacción sigue viva tras el SAVEPOINT fallido.
        filas = (await session.scalars(select(OrganizationPolicyVersion))).all()
    assert [fila.content for fila in filas] == ["De otra"]
