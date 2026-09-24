"""Herramientas de escritura del MCP: crear en borrador, editar sin tocar el
estado, publicar, despublicar y cancelar en dos pasos, con auditoría.

Reutiliza el montaje de `test_mcp_conexiones_y_lectura.py` (app con su propio
servidor MCP en marcha y llamadas JSON-RPC directas a `/mcp`).
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text

from app.core.database import SessionMaintenance
from app.core.tasks import sweep_event_cancellation_task
from app.modules.events.models import Event
from tests.conftest import OrganizacionDePrueba, iniciar_sesion
from tests.mcp_test_helpers import _crear_clave, _datos, _evento, _herramienta

EVENTS = "/api/v1/events"
AHORA = datetime.now(UTC).replace(microsecond=0)
TODOS = [
    "eventos:leer",
    "eventos:editar",
    "eventos:publicar",
    "eventos:cancelar",
    "patrocinadores:editar",
    "inscripciones:cifras",
]


@pytest.fixture(autouse=True)
def barrido_mockeado():
    with patch.object(sweep_event_cancellation_task, "kiq", new_callable=AsyncMock) as mock:
        yield mock


async def _clave(cliente: AsyncClient, cabeceras: dict[str, str], ambitos: list[str]) -> str:
    return (await _crear_clave(cliente, cabeceras, scopes=ambitos))["api_key"]


async def _estado(event_id: str) -> str:
    async with SessionMaintenance() as session:
        return (await session.get(Event, uuid.UUID(event_id))).status


class TestCrearYEditar:
    async def test_crear_evento_lo_deja_siempre_en_borrador_y_lo_audita(
        self, cliente: AsyncClient, cliente_mcp: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        clave = await _clave(cliente, cabeceras, ["eventos:editar"])

        creado = _datos(
            await _herramienta(
                cliente_mcp,
                clave,
                "crear_evento",
                slug="creado-por-mcp",
                titulo="Creado por un asistente",
                inicio=(AHORA + timedelta(days=5)).isoformat(),
                fin=(AHORA + timedelta(days=6)).isoformat(),
            )
        )

        assert creado["estado"] == "draft"
        async with SessionMaintenance() as session:
            accion = await session.scalar(
                text(
                    "SELECT detail FROM audit_log WHERE action = 'mcp.crear_evento' "
                    "AND entity_id = :id"
                ),
                {"id": creado["id"]},
            )
        assert accion["via"] == "mcp"

    async def test_editar_evento_no_acepta_el_estado(
        self, cliente: AsyncClient, cliente_mcp: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _evento(cliente, cabeceras, "mcp-editar-estado")
        clave = await _clave(cliente, cabeceras, ["eventos:editar"])

        resultado = await _herramienta(
            cliente_mcp, clave, "editar_evento", event_id=evento["id"], status="published"
        )
        editado = _datos(
            await _herramienta(
                cliente_mcp, clave, "editar_evento", event_id=evento["id"], titulo="Nuevo título"
            )
        )

        assert resultado["isError"] is True
        assert editado["titulo"] == "Nuevo título"
        assert await _estado(evento["id"]) == "draft"

    async def test_sin_ambito_de_publicar_no_publica(
        self, cliente: AsyncClient, cliente_mcp: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _evento(cliente, cabeceras, "mcp-sin-publicar")
        clave = await _clave(cliente, cabeceras, ["eventos:editar"])

        resultado = await _herramienta(cliente_mcp, clave, "publicar_evento", event_id=evento["id"])

        assert resultado["isError"] is True
        assert await _estado(evento["id"]) == "draft"

    async def test_la_agenda_respeta_las_reglas_del_panel(
        self, cliente: AsyncClient, cliente_mcp: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _evento(cliente, cabeceras, "mcp-agenda")
        clave = await _clave(cliente, cabeceras, ["eventos:editar"])
        inicio = datetime.fromisoformat(evento["starts_at"])

        dentro = _datos(
            await _herramienta(
                cliente_mcp,
                clave,
                "anadir_sesion",
                event_id=evento["id"],
                titulo="Apertura",
                inicio=(inicio + timedelta(hours=1)).isoformat(),
                fin=(inicio + timedelta(hours=2)).isoformat(),
            )
        )
        fuera = await _herramienta(
            cliente_mcp,
            clave,
            "anadir_sesion",
            event_id=evento["id"],
            titulo="Fuera de fechas",
            inicio=(inicio - timedelta(days=3)).isoformat(),
            fin=(inicio - timedelta(days=3, hours=-1)).isoformat(),
        )

        assert dentro["titulo"] == "Apertura"
        assert fuera["isError"] is True
        assert "rango de fechas" in json.dumps(fuera, ensure_ascii=False)


class TestPublicarYCancelar:
    async def test_publicar_y_despublicar_sin_inscripciones(
        self, cliente: AsyncClient, cliente_mcp: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _evento(cliente, cabeceras, "mcp-publicar")
        clave = await _clave(cliente, cabeceras, ["eventos:publicar"])

        _datos(await _herramienta(cliente_mcp, clave, "publicar_evento", event_id=evento["id"]))
        assert await _estado(evento["id"]) == "published"
        _datos(await _herramienta(cliente_mcp, clave, "despublicar_evento", event_id=evento["id"]))
        assert await _estado(evento["id"]) == "draft"

    async def test_cancelar_pide_confirmacion_y_solo_vale_el_codigo_devuelto(
        self,
        cliente: AsyncClient,
        cliente_mcp: AsyncClient,
        organizacion: OrganizacionDePrueba,
        barrido_mockeado,
    ) -> None:
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _evento(cliente, cabeceras, "mcp-cancelar")
        await cliente.patch(
            f"{EVENTS}/{evento['id']}",
            headers=cabeceras,
            json={"status": "published", "visibility": "public"},
        )
        clave = await _clave(cliente, cabeceras, TODOS)

        resumen = _datos(
            await _herramienta(cliente_mcp, clave, "cancelar_evento", event_id=evento["id"])
        )
        assert await _estado(evento["id"]) == "published"
        malo = await _herramienta(
            cliente_mcp,
            clave,
            "cancelar_evento",
            event_id=evento["id"],
            codigo_de_confirmacion="x" * 16,
        )
        hecho = _datos(
            await _herramienta(
                cliente_mcp,
                clave,
                "cancelar_evento",
                event_id=evento["id"],
                codigo_de_confirmacion=resumen["codigo_de_confirmacion"],
                motivo="Temporal",
            )
        )

        assert resumen["confirmacion_pendiente"] is True
        assert malo["isError"] is True
        assert hecho["cancelado"] is True
        assert await _estado(evento["id"]) == "cancelled"
        barrido_mockeado.assert_awaited_once()

    async def test_el_ambito_de_cancelar_es_aparte(
        self, cliente: AsyncClient, cliente_mcp: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _evento(cliente, cabeceras, "mcp-sin-cancelar")
        clave = await _clave(cliente, cabeceras, ["eventos:editar", "eventos:publicar"])

        resultado = await _herramienta(cliente_mcp, clave, "cancelar_evento", event_id=evento["id"])

        assert resultado["isError"] is True


async def test_una_conexion_limitada_no_toca_otros_eventos(
    cliente: AsyncClient, cliente_mcp: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    permitido = await _evento(cliente, cabeceras, "mcp-limitada-si")
    ajeno = await _evento(cliente, cabeceras, "mcp-limitada-no")
    clave = (
        await _crear_clave(
            cliente, cabeceras, scopes=["eventos:editar"], event_ids=[permitido["id"]]
        )
    )["api_key"]

    editar = await _herramienta(
        cliente_mcp, clave, "editar_evento", event_id=ajeno["id"], titulo="Intruso"
    )
    crear = await _herramienta(
        cliente_mcp,
        clave,
        "crear_evento",
        slug="mcp-limitada-nuevo",
        titulo="Nuevo",
        inicio=(AHORA + timedelta(days=5)).isoformat(),
        fin=(AHORA + timedelta(days=6)).isoformat(),
    )

    assert editar["isError"] is True and crear["isError"] is True
    async with SessionMaintenance() as session:
        titulo = await session.scalar(select(Event.title).where(Event.id == uuid.UUID(ajeno["id"])))
    assert titulo == "Evento mcp-limitada-no"
