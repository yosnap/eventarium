"""Categorías (catálogo de instalación) y etiquetas de los eventos."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.core.database import SessionApp, SessionMaintenance
from app.modules.events.categories import normalizar_etiquetas
from app.modules.users.models import User
from tests.conftest import OrganizacionDePrueba, iniciar_sesion
from tests.test_events_public import _crear_evento, _publicar

ADMIN = "/api/v1/admin/event-categories"
ASIGNABLES = "/api/v1/event-categories"
PUBLICAS = "/api/v1/public/event-categories"
EVENTS = "/api/v1/events"
PUBLICO = "/api/v1/public"


async def _superadmin(cliente: AsyncClient, organizacion: OrganizacionDePrueba) -> dict[str, str]:
    async with SessionMaintenance() as session:
        usuario = await session.scalar(select(User).where(User.email == organizacion.owner_email))
        assert usuario is not None
        usuario.is_superadmin = True
        await session.commit()
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    return cabeceras


async def _crear_categoria(
    cliente: AsyncClient, cabeceras: dict[str, str], slug: str, **campos: object
) -> dict:
    respuesta = await cliente.post(
        ADMIN, headers=cabeceras, json={"slug": slug, "name": slug.title(), **campos}
    )
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


# --- Etiquetas -------------------------------------------------------------


def test_las_etiquetas_se_normalizan_en_minusculas_sin_repetidas() -> None:
    assert normalizar_etiquetas(["  IA ", "Machine   Learning", "ia", "Diseño-UX"]) == [
        "ia",
        "machine learning",
        "diseño-ux",
    ]


@pytest.mark.parametrize(
    "etiquetas",
    [
        ["a"],
        ["x" * 31],
        ["#ia"],
        ["ia!"],
        ["ia_ok"],
        ["🙂ia"],
        ["-ia"],
        ["a"] * 1 + ["b1", "c2", "d3", "e4", "f5"],
    ],
)
def test_las_etiquetas_invalidas_se_rechazan(etiquetas: list[str]) -> None:
    with pytest.raises(ValueError):
        normalizar_etiquetas(etiquetas)


def test_repetir_una_etiqueta_no_cuenta_dos_veces_para_el_maximo() -> None:
    assert len(normalizar_etiquetas(["ia", "ia", "ia", "ia", "ia", "ia", "datos"])) == 2


# --- Catálogo ---------------------------------------------------------------


async def test_solo_el_superadmin_gestiona_el_catalogo(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    otra_organizacion: OrganizacionDePrueba,
) -> None:
    en_uso = await _crear_categoria(cliente, await _superadmin(cliente, organizacion), "existente")
    _, sin_permiso = await iniciar_sesion(cliente, otra_organizacion)
    for metodo, ruta, cuerpo in (
        ("get", ADMIN, None),
        ("post", ADMIN, {"slug": "taller", "name": "Taller"}),
        ("patch", f"{ADMIN}/{en_uso['id']}", {"is_active": False}),
    ):
        respuesta = await cliente.request(metodo, ruta, headers=sin_permiso, json=cuerpo)
        assert respuesta.status_code in (401, 403), (metodo, respuesta.status_code)


async def test_el_superadmin_crea_edita_y_desactiva_sin_borrar(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    cabeceras = await _superadmin(cliente, organizacion)
    categoria = await _crear_categoria(cliente, cabeceras, "taller", display_order=2)

    repetida = await cliente.post(ADMIN, headers=cabeceras, json={"slug": "taller", "name": "Otro"})
    assert repetida.status_code == 409

    editada = await cliente.patch(
        f"{ADMIN}/{categoria['id']}",
        headers=cabeceras,
        json={"name": "Talleres", "is_active": False, "slug": "cambiado"},
    )
    assert editada.status_code == 200, editada.text
    assert editada.json()["name"] == "Talleres"
    assert editada.json()["is_active"] is False
    assert editada.json()["slug"] == "taller"  # el identificador no cambia

    # No hay borrado.
    assert (await cliente.delete(f"{ADMIN}/{categoria['id']}", headers=cabeceras)).status_code in (
        404,
        405,
    )


async def test_la_aplicacion_no_puede_escribir_en_el_catalogo() -> None:
    async with SessionApp() as session:
        with pytest.raises(DBAPIError):
            await session.execute(
                text(
                    "INSERT INTO event_categories (id, slug, name) "
                    "VALUES (gen_random_uuid(), 'x', 'X')"
                )
            )


async def test_el_panel_solo_ofrece_categorias_activas_y_el_publico_tambien(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    cabeceras = await _superadmin(cliente, organizacion)
    await _crear_categoria(cliente, cabeceras, "taller", display_order=2)
    await _crear_categoria(cliente, cabeceras, "charla", display_order=1)
    await _crear_categoria(cliente, cabeceras, "vieja", is_active=False)

    panel = (await cliente.get(ASIGNABLES, headers=cabeceras)).json()
    publico = (await cliente.get(PUBLICAS)).json()

    assert [c["slug"] for c in panel] == ["charla", "taller"]
    assert publico == [{"slug": "charla", "name": "Charla"}, {"slug": "taller", "name": "Taller"}]


# --- Asignación a un evento -------------------------------------------------


async def test_asignar_categoria_activa_y_etiquetas_a_un_evento(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    cabeceras = await _superadmin(cliente, organizacion)
    categoria = await _crear_categoria(cliente, cabeceras, "taller")

    evento = await _crear_evento(
        cliente,
        cabeceras,
        slug="con-categoria",
        category_id=categoria["id"],
        tags=[" IA ", "Datos"],
    )

    assert evento["category"]["slug"] == "taller"
    assert evento["tags"] == ["ia", "datos"]


async def test_no_se_asigna_una_categoria_desactivada_ni_inexistente(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    cabeceras = await _superadmin(cliente, organizacion)
    vieja = await _crear_categoria(cliente, cabeceras, "vieja", is_active=False)
    for valor in (vieja["id"], "00000000-0000-0000-0000-000000000000", "no-es-un-id"):
        respuesta = await cliente.post(
            EVENTS,
            headers=cabeceras,
            json={
                "slug": "x1",
                "title": "X",
                "starts_at": "2030-01-01T10:00:00+00:00",
                "ends_at": "2030-01-02T10:00:00+00:00",
                "location_mode": "in_person",
                "category_id": valor,
            },
        )
        assert respuesta.status_code == 422, (valor, respuesta.text)


async def test_una_categoria_desactivada_no_se_pierde_al_guardar_otros_cambios(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    cabeceras = await _superadmin(cliente, organizacion)
    categoria = await _crear_categoria(cliente, cabeceras, "taller")
    evento = await _crear_evento(cliente, cabeceras, slug="conserva", category_id=categoria["id"])
    await cliente.patch(f"{ADMIN}/{categoria['id']}", headers=cabeceras, json={"is_active": False})

    # Editar otra cosa: la categoría se queda.
    otro = await cliente.patch(
        f"{EVENTS}/{evento['id']}", headers=cabeceras, json={"title": "Nuevo"}
    )
    assert otro.status_code == 200, otro.text
    assert otro.json()["category"]["slug"] == "taller"
    assert otro.json()["category"]["is_active"] is False
    # Reenviar la misma categoría (el panel lo hace) tampoco falla.
    igual = await cliente.patch(
        f"{EVENTS}/{evento['id']}", headers=cabeceras, json={"category_id": categoria["id"]}
    )
    assert igual.status_code == 200, igual.text
    # Pero no se puede asignar a otro evento.
    nuevo = await cliente.post(
        EVENTS,
        headers=cabeceras,
        json={
            "slug": "otro",
            "title": "Otro",
            "starts_at": "2030-01-01T10:00:00+00:00",
            "ends_at": "2030-01-02T10:00:00+00:00",
            "location_mode": "in_person",
            "category_id": categoria["id"],
        },
    )
    assert nuevo.status_code == 422


async def test_null_explicito_quita_la_categoria_y_la_ausencia_no_cambia(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    cabeceras = await _superadmin(cliente, organizacion)
    categoria = await _crear_categoria(cliente, cabeceras, "taller")
    evento = await _crear_evento(
        cliente, cabeceras, slug="quita", category_id=categoria["id"], tags=["ia"]
    )

    sin_tocar = await cliente.patch(
        f"{EVENTS}/{evento['id']}", headers=cabeceras, json={"title": "T"}
    )
    assert sin_tocar.json()["category"]["slug"] == "taller"
    assert sin_tocar.json()["tags"] == ["ia"]

    quitada = await cliente.patch(
        f"{EVENTS}/{evento['id']}", headers=cabeceras, json={"category_id": None, "tags": []}
    )
    assert quitada.status_code == 200, quitada.text
    assert quitada.json()["category"] is None
    assert quitada.json()["tags"] == []

    nula = await cliente.patch(f"{EVENTS}/{evento['id']}", headers=cabeceras, json={"tags": None})
    assert nula.status_code == 422


async def test_etiquetas_invalidas_dan_422(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_evento(cliente, cabeceras, slug="etiquetas")
    for etiquetas in (
        ["a"],
        ["x" * 31],
        ["#ia"],
        ["uno", "dos", "tres", "cuatro", "cinco", "seis"],
    ):
        respuesta = await cliente.patch(
            f"{EVENTS}/{evento['id']}", headers=cabeceras, json={"tags": etiquetas}
        )
        assert respuesta.status_code == 422, etiquetas


# --- Contratos y filtros públicos -------------------------------------------


async def _publicado(
    cliente: AsyncClient, cabeceras: dict[str, str], slug: str, **campos: object
) -> dict:
    evento = await _crear_evento(cliente, cabeceras, slug=slug, **campos)
    await _publicar(cliente, cabeceras, evento["id"])
    return evento


async def test_los_contratos_publicos_llevan_categoria_y_etiquetas(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    cabeceras = await _superadmin(cliente, organizacion)
    categoria = await _crear_categoria(cliente, cabeceras, "taller")
    await _publicado(cliente, cabeceras, "ficha", category_id=categoria["id"], tags=["ia"])

    detalle = (
        await cliente.get(f"{PUBLICO}/organizations/{organizacion.slug}/events/ficha")
    ).json()
    listado = (await cliente.get(f"{PUBLICO}/events")).json()

    assert detalle["category"] == {"slug": "taller", "name": "Taller"}
    assert detalle["tags"] == ["ia"]
    assert listado[0]["category"] == {"slug": "taller", "name": "Taller"}
    assert listado[0]["tags"] == ["ia"]

    # Desactivada: deja de mostrarse en público, aunque el evento la conserva.
    await cliente.patch(f"{ADMIN}/{categoria['id']}", headers=cabeceras, json={"is_active": False})
    assert (await cliente.get(f"{PUBLICO}/events")).json()[0]["category"] is None


async def test_el_filtro_por_categoria_y_etiquetas_va_en_la_consulta_y_cruza_organizaciones(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    otra_organizacion: OrganizacionDePrueba,
) -> None:
    cabeceras = await _superadmin(cliente, organizacion)
    taller = await _crear_categoria(cliente, cabeceras, "taller")
    charla = await _crear_categoria(cliente, cabeceras, "charla")
    await _publicado(
        cliente, cabeceras, "a-taller-ia", category_id=taller["id"], tags=["ia", "datos"]
    )
    await _publicado(cliente, cabeceras, "a-charla-ia", category_id=charla["id"], tags=["ia"])
    _, cabeceras_b = await iniciar_sesion(cliente, otra_organizacion)
    await _publicado(cliente, cabeceras_b, "b-taller", category_id=taller["id"], tags=["datos"])
    await _publicado(cliente, cabeceras_b, "b-sin-nada")

    def slugs(respuesta) -> list[str]:  # noqa: ANN001
        return sorted(e["slug"] for e in respuesta.json())

    todos = await cliente.get(f"{PUBLICO}/events")
    assert len(todos.json()) == 4
    assert todos.headers["X-Total-Count"] == "4"

    por_categoria = await cliente.get(f"{PUBLICO}/events", params={"categoria": "taller"})
    assert slugs(por_categoria) == ["a-taller-ia", "b-taller"]

    por_etiqueta = await cliente.get(f"{PUBLICO}/events", params={"etiqueta": "ia"})
    assert slugs(por_etiqueta) == ["a-charla-ia", "a-taller-ia"]

    # Varias etiquetas = «y».
    ambas = await cliente.get(
        f"{PUBLICO}/events", params=[("etiqueta", "ia"), ("etiqueta", "DATOS")]
    )
    assert slugs(ambas) == ["a-taller-ia"]

    combinado = await cliente.get(
        f"{PUBLICO}/events", params={"categoria": "taller", "etiqueta": "datos"}
    )
    assert slugs(combinado) == ["a-taller-ia", "b-taller"]

    # Una categoría inexistente o desactivada no da error: no hay resultados.
    assert (await cliente.get(f"{PUBLICO}/events", params={"categoria": "no-existe"})).json() == []
    await cliente.patch(f"{ADMIN}/{taller['id']}", headers=cabeceras, json={"is_active": False})
    assert (await cliente.get(f"{PUBLICO}/events", params={"categoria": "taller"})).json() == []


async def test_maximo_tres_etiquetas_por_filtro_y_etiquetas_invalidas(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    demasiadas = await cliente.get(
        f"{PUBLICO}/events", params=[("etiqueta", t) for t in ("aa", "bb", "cc", "dd")]
    )
    assert demasiadas.status_code == 422
    invalida = await cliente.get(f"{PUBLICO}/events", params={"etiqueta": "#mal"})
    assert invalida.status_code == 422
    tres = await cliente.get(
        f"{PUBLICO}/events", params=[("etiqueta", t) for t in ("aa", "bb", "cc")]
    )
    assert tres.status_code == 200


async def test_la_paginacion_global_corta_el_conjunto_ordenado_y_da_el_total(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    otra_organizacion: OrganizacionDePrueba,
) -> None:
    _, cabeceras_a = await iniciar_sesion(cliente, organizacion)
    _, cabeceras_b = await iniciar_sesion(cliente, otra_organizacion)
    fechas = {
        "e1": ("2030-01-01", cabeceras_a),
        "e2": ("2030-01-02", cabeceras_b),
        "e3": ("2030-01-03", cabeceras_a),
        "e4": ("2030-01-04", cabeceras_b),
        "e5": ("2030-01-05", cabeceras_a),
    }
    for slug, (dia, cab) in fechas.items():
        await _publicado(
            cliente,
            cab,
            slug,
            starts_at=f"{dia}T10:00:00+00:00",
            ends_at=f"{dia}T12:00:00+00:00",
        )

    pagina_1 = await cliente.get(f"{PUBLICO}/events", params={"limit": 2})
    pagina_2 = await cliente.get(f"{PUBLICO}/events", params={"limit": 2, "offset": 2})
    pagina_3 = await cliente.get(f"{PUBLICO}/events", params={"limit": 2, "offset": 4})

    assert [e["slug"] for e in pagina_1.json()] == ["e1", "e2"]
    assert [e["slug"] for e in pagina_2.json()] == ["e3", "e4"]
    assert [e["slug"] for e in pagina_3.json()] == ["e5"]
    assert pagina_1.headers["X-Total-Count"] == pagina_3.headers["X-Total-Count"] == "5"
    assert (await cliente.get(f"{PUBLICO}/events", params={"limit": 101})).status_code == 422


async def test_paginacion_combinada_con_filtro_y_empate_de_fecha_entre_organizaciones(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    otra_organizacion: OrganizacionDePrueba,
) -> None:
    cabeceras = await _superadmin(cliente, organizacion)
    taller = await _crear_categoria(cliente, cabeceras, "taller")
    _, cabeceras_b = await iniciar_sesion(cliente, otra_organizacion)
    misma_hora = {"starts_at": "2030-02-01T10:00:00+00:00", "ends_at": "2030-02-01T12:00:00+00:00"}
    # Tres del filtro con la MISMA hora entre dos organizaciones y uno fuera del filtro.
    for slug, cab in (("t1", cabeceras), ("t2", cabeceras_b), ("t3", cabeceras)):
        await _publicado(cliente, cab, slug, category_id=taller["id"], **misma_hora)
    await _publicado(cliente, cabeceras, "fuera", **misma_hora)

    vistos: list[str] = []
    for offset in (0, 1, 2):
        pagina = await cliente.get(
            f"{PUBLICO}/events", params={"categoria": "taller", "limit": 1, "offset": offset}
        )
        assert pagina.headers["X-Total-Count"] == "3"
        vistos += [e["slug"] for e in pagina.json()]

    # Con el mismo `starts_at` el desempate por id mantiene un orden estable: cada
    # evento aparece exactamente una vez, sin saltos ni repeticiones entre páginas.
    assert sorted(vistos) == ["t1", "t2", "t3"]
    completa = await cliente.get(f"{PUBLICO}/events", params={"categoria": "taller"})
    assert [e["slug"] for e in completa.json()] == vistos
    assert (
        await cliente.get(f"{PUBLICO}/events", params={"limit": 1, "offset": 10001})
    ).status_code == 422
