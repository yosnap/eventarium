"""CRUD HTTP de niveles de patrocinio y patrocinadores, y bloque público
agrupado por nivel (Fase 5 del PRD, fase 2 de trabajo).

Mismo patrón que `test_events_public.py`/`test_registrations_organizer.py`:
cliente HTTP real, `Host` para resolver la organización, `iniciar_sesion` para
un `owner` autenticado.
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient

from app.core.permissions import Permission
from tests.conftest import OrganizacionDePrueba, crear_rol, iniciar_sesion, iniciar_sesion_con

EVENTS = "/api/v1/events"
SPONSOR_TIERS = "/api/v1/organizations/me/sponsor-tiers"
PUBLIC_EVENTS = "/api/v1/public/events"

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

AHORA = datetime.now(UTC).replace(microsecond=0)


def _payload_evento(slug: str, **overrides: object) -> dict:
    payload = {
        "slug": slug,
        "title": f"Evento {slug}",
        "starts_at": AHORA.isoformat(),
        "ends_at": (AHORA + timedelta(days=2)).isoformat(),
        "location_mode": "in_person",
    }
    payload.update(overrides)
    return payload


async def _crear_evento(cliente: AsyncClient, cabeceras: dict[str, str], slug: str) -> dict:
    respuesta = await cliente.post(EVENTS, headers=cabeceras, json=_payload_evento(slug))
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


async def _publicar(cliente: AsyncClient, cabeceras: dict[str, str], event_id: str) -> None:
    respuesta = await cliente.patch(
        f"{EVENTS}/{event_id}",
        headers=cabeceras,
        json={"status": "published", "visibility": "public"},
    )
    assert respuesta.status_code == 200, respuesta.text


async def _crear_tier(
    cliente: AsyncClient, cabeceras: dict[str, str], name: str, display_order: int
) -> dict:
    respuesta = await cliente.post(
        SPONSOR_TIERS,
        headers=cabeceras,
        json={"name": name, "display_order": display_order, "logo_size": "large"},
    )
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


async def test_crear_reordenar_y_listar_niveles(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    oro = await _crear_tier(cliente, cabeceras, "Oro", 1)
    plata = await _crear_tier(cliente, cabeceras, "Plata", 2)
    bronce = await _crear_tier(cliente, cabeceras, "Bronce", 3)

    listado = await cliente.get(SPONSOR_TIERS, headers=cabeceras)
    assert listado.status_code == 200
    assert [n["name"] for n in listado.json()["items"]] == ["Oro", "Plata", "Bronce"]

    # Reordenar: Bronce pasa a ser el primero.
    respuesta = await cliente.patch(
        f"{SPONSOR_TIERS}/{bronce['id']}", headers=cabeceras, json={"display_order": 0}
    )
    assert respuesta.status_code == 200, respuesta.text

    listado = await cliente.get(SPONSOR_TIERS, headers=cabeceras)
    assert [n["name"] for n in listado.json()["items"]] == ["Bronce", "Oro", "Plata"]
    assert oro["display_order"] == 1 and plata["display_order"] == 2


async def test_borrar_nivel_con_patrocinadores_da_409_con_mensaje_claro(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    nivel = await _crear_tier(cliente, cabeceras, "Oro", 1)
    evento = await _crear_evento(cliente, cabeceras, "con-patrocinio")

    alta = await cliente.post(
        f"{EVENTS}/{evento['id']}/sponsors",
        headers=cabeceras,
        json={
            "tier_id": nivel["id"],
            "name": "Acme Corp",
            "contribution_type": "monetaria",
            "contribution_amount": "500.00",
        },
    )
    assert alta.status_code == 201, alta.text

    borrado = await cliente.delete(f"{SPONSOR_TIERS}/{nivel['id']}", headers=cabeceras)
    assert borrado.status_code == 409
    assert "reasígnalos" in borrado.json()["detail"]


async def test_patch_de_nivel_con_name_null_devuelve_422_no_409(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    """Regresión: `name`/`logo_size` son `NOT NULL` en BD; un `null` explícito
    en el `PATCH` no debe llegar a la BD ni reportarse como 409 de nombre
    duplicado (`sponsors/service.py:53`), sino como 422 de validación."""
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    nivel = await _crear_tier(cliente, cabeceras, "Oro", 1)

    respuesta = await cliente.patch(
        f"{SPONSOR_TIERS}/{nivel['id']}", headers=cabeceras, json={"name": None}
    )
    assert respuesta.status_code == 422, respuesta.text

    respuesta_logo = await cliente.patch(
        f"{SPONSOR_TIERS}/{nivel['id']}", headers=cabeceras, json={"logo_size": None}
    )
    assert respuesta_logo.status_code == 422, respuesta_logo.text

    # El nivel no ha cambiado.
    listado = await cliente.get(SPONSOR_TIERS, headers=cabeceras)
    assert listado.json()["items"][0]["name"] == "Oro"


async def test_no_se_puede_asignar_un_patrocinador_a_un_nivel_ajeno(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    otra_organizacion: OrganizacionDePrueba,
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    _, cabeceras_ajenas = await iniciar_sesion(cliente, otra_organizacion)

    nivel_ajeno = await _crear_tier(cliente, cabeceras_ajenas, "Oro ajeno", 1)
    evento = await _crear_evento(cliente, cabeceras, "evento-propio")

    respuesta = await cliente.post(
        f"{EVENTS}/{evento['id']}/sponsors",
        headers=cabeceras,
        json={
            "tier_id": nivel_ajeno["id"],
            "name": "Intruso",
            "contribution_type": "monetaria",
            "contribution_amount": "10.00",
        },
    )
    assert respuesta.status_code == 422
    assert "no existe" in respuesta.json()["detail"]


async def test_aportacion_monetaria_y_en_especie_son_mutuamente_excluyentes(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    nivel = await _crear_tier(cliente, cabeceras, "Colaborador", 1)
    evento = await _crear_evento(cliente, cabeceras, "evento-aportaciones")

    sin_importe = await cliente.post(
        f"{EVENTS}/{evento['id']}/sponsors",
        headers=cabeceras,
        json={"tier_id": nivel["id"], "name": "Sin importe", "contribution_type": "monetaria"},
    )
    assert sin_importe.status_code == 422

    con_ambos = await cliente.post(
        f"{EVENTS}/{evento['id']}/sponsors",
        headers=cabeceras,
        json={
            "tier_id": nivel["id"],
            "name": "Con ambos",
            "contribution_type": "en_especie",
            "contribution_amount": "10.00",
            "contribution_description": "Catering",
        },
    )
    assert con_ambos.status_code == 422


async def test_patch_de_patrocinador_con_tier_id_null_devuelve_422_no_500(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    """Regresión: `tier_id: null` explícito llegaba hasta `uuid.UUID(None)`
    (`sponsors/router.py:198`), un `TypeError` no capturado que el handler
    genérico convertía en 500. Debe ser un 422 de validación."""
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    nivel = await _crear_tier(cliente, cabeceras, "Oro", 1)
    evento = await _crear_evento(cliente, cabeceras, "evento-tier-null")

    alta = await cliente.post(
        f"{EVENTS}/{evento['id']}/sponsors",
        headers=cabeceras,
        json={
            "tier_id": nivel["id"],
            "name": "Acme Corp",
            "contribution_type": "monetaria",
            "contribution_amount": "500.00",
        },
    )
    assert alta.status_code == 201, alta.text

    respuesta = await cliente.patch(
        f"{EVENTS}/{evento['id']}/sponsors/{alta.json()['id']}",
        headers=cabeceras,
        json={"tier_id": None},
    )
    assert respuesta.status_code == 422, respuesta.text

    respuesta_nombre = await cliente.patch(
        f"{EVENTS}/{evento['id']}/sponsors/{alta.json()['id']}",
        headers=cabeceras,
        json={"name": None},
    )
    assert respuesta_nombre.status_code == 422, respuesta_nombre.text


async def test_permisos_organizador_puede_leer_y_escribir_sin_permiso_da_403(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    solo_lectura_role_id = await crear_rol(
        organizacion, key="solo_lectura_sponsors", permisos=[Permission.SPONSORS_READ]
    )
    del solo_lectura_role_id
    # Un rol sin ningún permiso de sponsors: 403 tanto en lectura como en escritura.
    sin_permisos_role_id = await crear_rol(organizacion, key="sin_sponsors", permisos=[])
    del sin_permisos_role_id

    from tests.conftest import crear_miembro

    persona = await crear_miembro(organizacion, "sin_sponsors")
    _, cabeceras = await iniciar_sesion_con(cliente, organizacion, persona.email, persona.password)

    lectura = await cliente.get(SPONSOR_TIERS, headers=cabeceras)
    assert lectura.status_code == 403

    escritura = await cliente.post(
        SPONSOR_TIERS, headers=cabeceras, json={"name": "Oro", "display_order": 0}
    )
    assert escritura.status_code == 403


async def test_bloque_publico_agrupa_por_nivel_muestra_el_logo_y_oculta_aportacion(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    oro = await _crear_tier(cliente, cabeceras, "Oro", 1)
    plata = await _crear_tier(cliente, cabeceras, "Plata", 2)
    evento = await _crear_evento(cliente, cabeceras, "publico-con-patrocinio")
    await _publicar(cliente, cabeceras, evento["id"])

    monetario = (
        await cliente.post(
            f"{EVENTS}/{evento['id']}/sponsors",
            headers=cabeceras,
            json={
                "tier_id": oro["id"],
                "name": "Patrocinador monetario",
                "website": "https://example.com",
                "contribution_type": "monetaria",
                "contribution_amount": "1000.00",
            },
        )
    ).json()
    subida_logo = await cliente.put(
        f"{EVENTS}/{evento['id']}/sponsors/{monetario['id']}/logo",
        headers=cabeceras,
        files={"fichero": ("logo.png", PNG, "image/png")},
    )
    assert subida_logo.status_code == 200, subida_logo.text
    assert subida_logo.json()["logo_url"]

    await cliente.post(
        f"{EVENTS}/{evento['id']}/sponsors",
        headers=cabeceras,
        json={
            "tier_id": plata["id"],
            "name": "Colaborador en especie",
            "contribution_type": "en_especie",
            "contribution_description": "Cesión de espacio",
        },
    )

    detalle = await cliente.get(
        f"{PUBLIC_EVENTS}/{evento['slug']}", headers={"Host": organizacion.host}
    )
    assert detalle.status_code == 200
    cuerpo = detalle.json()
    assert [nivel["name"] for nivel in cuerpo["sponsor_tiers"]] == ["Oro", "Plata"]
    primer_patrocinador = cuerpo["sponsor_tiers"][0]["sponsors"][0]
    assert primer_patrocinador["name"] == "Patrocinador monetario"
    assert primer_patrocinador["logo_url"]
    assert primer_patrocinador["contribution_type"] == "monetaria"
    assert "contribution_amount" not in primer_patrocinador
    # La descripción de una aportación en especie sí es pública: describe qué
    # se aporta, no cuánto vale (a diferencia del importe monetario, que
    # nunca se expone).
    segundo_patrocinador = cuerpo["sponsor_tiers"][1]["sponsors"][0]
    assert segundo_patrocinador["contribution_type"] == "en_especie"
    assert segundo_patrocinador["contribution_description"] == "Cesión de espacio"


async def test_ficha_publica_de_patrocinador_incluye_nivel_e_historial_por_nombre(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    oro = await _crear_tier(cliente, cabeceras, "Oro", 1)
    plata = await _crear_tier(cliente, cabeceras, "Plata", 2)

    evento_anterior = await _crear_evento(cliente, cabeceras, "ficha-patrocinador-2025")
    await _publicar(cliente, cabeceras, evento_anterior["id"])
    await cliente.post(
        f"{EVENTS}/{evento_anterior['id']}/sponsors",
        headers=cabeceras,
        json={"tier_id": plata["id"], "name": "Empresa Repetida", "contribution_type": "en_especie",
              "contribution_description": "Catering"},
    )

    evento_actual = await _crear_evento(cliente, cabeceras, "ficha-patrocinador-2026")
    await _publicar(cliente, cabeceras, evento_actual["id"])
    patrocinador = (
        await cliente.post(
            f"{EVENTS}/{evento_actual['id']}/sponsors",
            headers=cabeceras,
            json={
                "tier_id": oro["id"],
                "name": "Empresa Repetida",
                "website": "https://example.com",
                "contribution_type": "monetaria",
                "contribution_amount": "1000.00",
            },
        )
    ).json()

    respuesta = await cliente.get(
        f"{PUBLIC_EVENTS}/{evento_actual['slug']}/sponsors/{patrocinador['id']}",
        headers={"Host": organizacion.host},
    )
    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["name"] == "Empresa Repetida"
    assert cuerpo["tier_name"] == "Oro"
    assert cuerpo["contribution_type"] == "monetaria"
    assert "contribution_amount" not in cuerpo
    assert cuerpo["event_slug"] == "ficha-patrocinador-2026"
    assert len(cuerpo["history"]) == 1
    assert cuerpo["history"][0]["event_slug"] == "ficha-patrocinador-2025"
    assert cuerpo["history"][0]["tier_name"] == "Plata"


async def test_ficha_publica_de_patrocinador_404_si_el_evento_no_es_publico(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    nivel = await _crear_tier(cliente, cabeceras, "Oro", 1)
    evento = await _crear_evento(cliente, cabeceras, "ficha-patrocinador-borrador")
    patrocinador = (
        await cliente.post(
            f"{EVENTS}/{evento['id']}/sponsors",
            headers=cabeceras,
            json={"tier_id": nivel["id"], "name": "Sin publicar", "contribution_type": "en_especie",
                  "contribution_description": "Material"},
        )
    ).json()

    respuesta = await cliente.get(
        f"{PUBLIC_EVENTS}/{evento['slug']}/sponsors/{patrocinador['id']}",
        headers={"Host": organizacion.host},
    )
    assert respuesta.status_code == 404


async def test_evento_en_borrador_no_expone_su_bloque_de_patrocinadores(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    nivel = await _crear_tier(cliente, cabeceras, "Oro", 1)
    evento = await _crear_evento(cliente, cabeceras, "evento-borrador-patrocinio")
    await cliente.post(
        f"{EVENTS}/{evento['id']}/sponsors",
        headers=cabeceras,
        json={
            "tier_id": nivel["id"],
            "name": "Patrocinador oculto",
            "contribution_type": "monetaria",
            "contribution_amount": "10.00",
        },
    )

    respuesta = await cliente.get(
        f"{PUBLIC_EVENTS}/{evento['slug']}", headers={"Host": organizacion.host}
    )
    assert respuesta.status_code == 404
