"""Las respuestas públicas sirven el contenido traducido, con caída al original,
y dicen en qué idiomas está al día cada página."""

from __future__ import annotations

import json
import re
import uuid
from datetime import timedelta
from pathlib import Path

from httpx import AsyncClient
from sqlalchemy import update

from app.core.database import SessionApp, SessionMaintenance, set_organization_context
from app.modules.organizations.models import Organization
from app.modules.translations import service
from app.modules.translations.campos import TIPOS, TipoDeEntidad
from tests.conftest import OrganizacionDePrueba, iniciar_sesion
from tests.test_events_public import AHORA, EVENTOS_DE_ACME, EVENTS, _crear_evento, _publicar

INGLES = {"Accept-Language": "en-US"}
RAIZ_APP = Path(__file__).resolve().parents[1] / "app"


async def _traducir(
    organizacion: OrganizacionDePrueba,
    event_id: str,
    tipo: TipoDeEntidad,
    entity_id: str,
    campo: str,
    original: str,
    valor: str,
) -> None:
    async with SessionApp() as session, session.begin():
        await set_organization_context(session, organizacion.id)
        await service.guardar_manual(
            session,
            organization_id=organizacion.id,
            event_id=uuid.UUID(event_id),
            tipo=tipo,
            entity_id=uuid.UUID(entity_id),
            campo=campo,
            locale="en-US",
            valor=valor,
            original=original,
            origen_del_contenido="es-ES",
            idiomas_activos=("es-ES", "en-US"),
            user_id=organizacion.owner_id,
        )


async def _evento_con_contenido(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> tuple[dict[str, str], dict, dict, dict]:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_evento(
        cliente, cabeceras, slug="bilingue", title="Jornada de IA", summary="Un día entero"
    )
    sesion = (
        await cliente.post(
            f"{EVENTS}/{evento['id']}/sessions",
            headers=cabeceras,
            json={
                "session_type": "talk",
                "title": "Charla inaugural",
                "starts_at": (AHORA + timedelta(hours=1)).isoformat(),
                "ends_at": (AHORA + timedelta(hours=2)).isoformat(),
            },
        )
    ).json()
    pregunta = (
        await cliente.post(
            f"{EVENTS}/{evento['id']}/registration-questions",
            headers=cabeceras,
            json={
                "type": "single_choice",
                "label": "¿Talla?",
                "options": ["Pequeña", "Grande"],
                "required": False,
                "sort_order": 0,
            },
        )
    ).json()
    await _publicar(cliente, cabeceras, evento["id"])
    async with SessionMaintenance() as session, session.begin():
        await session.execute(
            update(Organization)
            .where(Organization.id == organizacion.id)
            .values(content_locales=["es-ES", "en-US"])
        )
    return cabeceras, evento, sesion, pregunta


async def test_sin_traducir_se_sirve_el_original_con_canonical_al_espanol(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    await _evento_con_contenido(cliente, organizacion)

    ficha = (await cliente.get(f"{EVENTOS_DE_ACME}/bilingue", headers=INGLES)).json()

    assert ficha["title"] == "Jornada de IA"
    assert ficha["source_locale"] == "es-ES"
    assert ficha["served_locale"] == "es-ES"
    assert ficha["up_to_date_locales"] == ["es-ES"]
    assert ficha["pending_fields"] >= 3


async def test_traducido_entero_se_sirve_en_ingles_y_queda_al_dia_en_los_dos(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, evento, sesion, pregunta = await _evento_con_contenido(cliente, organizacion)
    for campo, original, valor in (
        ("title", "Jornada de IA", "AI Day"),
        ("summary", "Un día entero", "A whole day"),
    ):
        await _traducir(organizacion, evento["id"], "event", evento["id"], campo, original, valor)
    await _traducir(
        organizacion, evento["id"], "session", sesion["id"], "title", "Charla inaugural", "Keynote"
    )
    # El tipo de sesión es de la organización y su nombre también sale en la ficha.
    tipo = (await cliente.get(f"{EVENTOS_DE_ACME}/bilingue")).json()["sessions"][0]["type"]
    await _traducir(
        organizacion, evento["id"], "session_type", tipo["id"], "name", tipo["name"], "Talk"
    )

    ficha = (await cliente.get(f"{EVENTOS_DE_ACME}/bilingue", headers=INGLES)).json()
    espanol = (await cliente.get(f"{EVENTOS_DE_ACME}/bilingue")).json()

    assert ficha["title"] == "AI Day"
    assert ficha["sessions"][0]["title"] == "Keynote"
    assert ficha["sessions"][0]["type"]["name"] == "Talk"
    assert ficha["served_locale"] == "en-US"
    assert ficha["up_to_date_locales"] == ["es-ES", "en-US"]
    assert ficha["pending_fields"] == 0
    assert espanol["title"] == "Jornada de IA"
    assert espanol["up_to_date_locales"] == ["es-ES", "en-US"]

    listado = (await cliente.get("/api/v1/public/events", headers=INGLES)).json()
    assert [e["title"] for e in listado if e["slug"] == "bilingue"] == ["AI Day"]

    # Las opciones de la pregunta: el valor sigue siendo el original.
    await _traducir(
        organizacion,
        evento["id"],
        "question",
        pregunta["id"],
        "options",
        json.dumps(["Pequeña", "Grande"]),
        json.dumps({"Pequeña": "Small", "Grande": "Large"}),
    )
    preguntas = (
        await cliente.get(f"{EVENTOS_DE_ACME}/bilingue/registration-questions", headers=INGLES)
    ).json()
    assert preguntas[0]["options"] == ["Pequeña", "Grande"]
    assert preguntas[0]["choices"] == [
        {"value": "Pequeña", "label": "Small"},
        {"value": "Grande", "label": "Large"},
    ]
    assert preguntas[0]["label"] == "¿Talla?"


async def test_si_cambia_el_original_la_traduccion_vieja_deja_de_servirse(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    cabeceras, evento, _, _ = await _evento_con_contenido(cliente, organizacion)
    await _traducir(
        organizacion, evento["id"], "event", evento["id"], "title", "Jornada de IA", "AI Day"
    )

    editado = await cliente.patch(
        f"{EVENTS}/{evento['id']}", headers=cabeceras, json={"title": "Jornada de IA 2027"}
    )
    assert editado.status_code == 200, editado.text

    ficha = (await cliente.get(f"{EVENTOS_DE_ACME}/bilingue", headers=INGLES)).json()
    assert ficha["title"] == "Jornada de IA 2027"


async def test_con_el_ingles_desactivado_en_la_organizacion_no_se_sirve(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, evento, _, _ = await _evento_con_contenido(cliente, organizacion)
    await _traducir(
        organizacion, evento["id"], "event", evento["id"], "title", "Jornada de IA", "AI Day"
    )
    async with SessionMaintenance() as session, session.begin():
        await session.execute(
            update(Organization)
            .where(Organization.id == organizacion.id)
            .values(content_locales=["es-ES"])
        )

    ficha = (await cliente.get(f"{EVENTOS_DE_ACME}/bilingue", headers=INGLES)).json()
    assert ficha["title"] == "Jornada de IA"
    assert ficha["up_to_date_locales"] == ["es-ES"]
    assert ficha["pending_fields"] == 0


def test_todos_los_tipos_se_superponen_en_alguna_respuesta() -> None:
    """Si se añade un tipo traducible y ninguna respuesta lo usa, su traducción
    no se vería nunca."""
    codigo = "\n".join(
        ruta.read_text(encoding="utf-8")
        for ruta in RAIZ_APP.rglob("*.py")
        if "translations" not in ruta.parts
    )
    usados = set(re.findall(r'(?:campo|opciones)\(\s*"([a-z_]+)"', codigo))
    usados |= {"question"} if "tr.opciones(" in codigo else set()
    usados |= {"tag"} if "tr.etiqueta(" in codigo else set()
    assert set(TIPOS) <= usados, set(TIPOS) - usados
