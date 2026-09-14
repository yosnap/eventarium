"""Datos y branding de la organización actual."""

from __future__ import annotations

import base64

from httpx import AsyncClient

from tests.conftest import OrganizacionDePrueba, iniciar_sesion, iniciar_sesion_como

ORGANIZACION = "/api/v1/organizations/me"
BRANDING = "/api/v1/organizations/me/branding"

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


async def test_leer_y_actualizar_la_organizacion(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    lectura = await cliente.get(ORGANIZACION, headers=cabeceras)
    assert lectura.status_code == 200
    assert lectura.json()["slug"] == organizacion.slug

    escritura = await cliente.patch(
        ORGANIZACION,
        headers=cabeceras,
        json={"name": "Nombre nuevo", "website": "https://ejemplo.com"},
    )
    assert escritura.status_code == 200
    assert escritura.json()["name"] == "Nombre nuevo"


async def test_un_asistente_no_puede_modificar_la_organizacion(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion_como(cliente, organizacion, "attendee")
    respuesta = await cliente.patch(ORGANIZACION, headers=cabeceras, json={"name": "Secuestro"})
    assert respuesta.status_code == 403


async def test_actualizar_el_branding_y_verlo_al_releerlo(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    """Fase 6 (cierre) del plan de organización sin dominio: `GET
    /tenant/branding` ya no lleva ningún bloque `organization` (retirado con
    `organization_domains`) — la única fuente de lectura del branding propio
    es esta misma familia de endpoints autenticados."""
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    respuesta = await cliente.put(
        BRANDING,
        headers=cabeceras,
        json={
            "social_links": [{"kind": "linkedin", "url": "https://linkedin.com/company/x"}],
            "organizer_blurb": "Comunidad de IA en Valencia",
        },
    )
    assert respuesta.status_code == 200

    releido = await cliente.get(BRANDING, headers=cabeceras)
    cuerpo = releido.json()
    assert cuerpo["social_links"][0]["kind"] == "linkedin"


async def test_actualizar_el_branding_con_una_plantilla_de_tema(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    catalogo = await cliente.get("/api/v1/organizations/me/theme-templates", headers=cabeceras)
    assert catalogo.status_code == 200
    claro = next(p for p in catalogo.json() if p["key"] == "claro")

    respuesta = await cliente.put(
        BRANDING,
        headers=cabeceras,
        json={
            "theme_template_id": claro["id"],
            "social_links": [],
            "organizer_blurb": "Comunidad de IA en Valencia",
        },
    )
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["theme_template_id"] == claro["id"]
    # El resto de campos vivos del branding se conserva.
    assert respuesta.json()["organizer_blurb"] == "Comunidad de IA en Valencia"

    releido = await cliente.get(BRANDING, headers=cabeceras)
    assert releido.json()["theme_template_id"] == claro["id"]


async def test_actualizar_el_branding_con_una_plantilla_de_tema_inexistente(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    respuesta = await cliente.put(
        BRANDING,
        headers=cabeceras,
        json={
            "theme_template_id": "00000000-0000-0000-0000-000000000000",
            "social_links": [],
        },
    )
    assert respuesta.status_code == 422


async def test_subir_el_logotipo_devuelve_una_url_publica(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    respuesta = await cliente.put(
        f"{BRANDING}/logo",
        headers=cabeceras,
        files={"fichero": ("logo.png", PNG, "image/png")},
    )
    assert respuesta.status_code == 200
    url = respuesta.json()["logo_url"]
    assert url and f"orgs/{organizacion.id}/branding/logo/" in url

    releido = await cliente.get(BRANDING, headers=cabeceras)
    assert releido.json()["logo_url"] == url


async def test_no_se_puede_subir_un_svg_como_logotipo(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    respuesta = await cliente.put(
        f"{BRANDING}/logo",
        headers=cabeceras,
        files={
            "fichero": (
                "logo.svg",
                b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
                "image/svg+xml",
            )
        },
    )
    assert respuesta.status_code == 422


async def test_users_me_devuelve_roles_y_permisos(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    respuesta = await cliente.get("/api/v1/users/me", headers=cabeceras)
    assert respuesta.status_code == 200

    cuerpo = respuesta.json()
    assert cuerpo["email"] == organizacion.owner_email
    assert cuerpo["roles"] == ["owner"]
    assert "organizations:write" in cuerpo["permissions"]
