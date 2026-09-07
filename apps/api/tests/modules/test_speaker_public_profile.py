"""Perfil público de ponente: autoservicio y lista blanca (fase 3 del PRD)."""

from __future__ import annotations

from httpx import AsyncClient

from app.modules.users.schemas import filter_public_profile_fields
from tests.conftest import OrganizacionDePrueba, crear_miembro, iniciar_sesion_con

PUBLIC_PROFILE = "/api/v1/users/me/public-profile"
CHECK_SLUG = f"{PUBLIC_PROFILE}/check-slug"


def test_la_lista_blanca_descarta_un_campo_a_medida_sensible() -> None:
    profile_data = {
        "bio": "Biografía pública",
        "web": "https://ejemplo.com",
        "telefono": "600000000",
        "dni": "12345678A",
    }
    filtrado = filter_public_profile_fields(profile_data)
    assert filtrado == {"bio": "Biografía pública", "web": "https://ejemplo.com"}
    assert "telefono" not in filtrado
    assert "dni" not in filtrado


async def test_una_persona_activa_su_propio_perfil_publico(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    ponente = await crear_miembro(organizacion, "speaker")
    _, cabeceras = await iniciar_sesion_con(cliente, organizacion, ponente.email, ponente.password)

    estado_inicial = await cliente.get(PUBLIC_PROFILE, headers=cabeceras)
    assert estado_inicial.status_code == 200
    assert estado_inicial.json()["profile"]["active"] is False
    elegibles = estado_inicial.json()["eligible_memberships"]
    assert any(m["organization_member_id"] == str(ponente.member_id) for m in elegibles)

    activacion = await cliente.patch(
        PUBLIC_PROFILE,
        headers=cabeceras,
        json={
            "public_slug": "la-ponente",
            "source_organization_member_id": str(ponente.member_id),
        },
    )
    assert activacion.status_code == 200, activacion.text
    assert activacion.json()["profile"] == {
        "active": True,
        "public_slug": "la-ponente",
        "source_organization_member_id": str(ponente.member_id),
    }

    disponibilidad = await cliente.get(CHECK_SLUG, headers=cabeceras, params={"slug": "la-ponente"})
    assert disponibilidad.json()["available"] is False


async def test_activar_sobre_una_membresia_ajena_falla_con_422(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    ponente = await crear_miembro(organizacion, "speaker")
    otra_persona = await crear_miembro(organizacion, "volunteer")
    _, cabeceras = await iniciar_sesion_con(
        cliente, organizacion, otra_persona.email, otra_persona.password
    )

    respuesta = await cliente.patch(
        PUBLIC_PROFILE,
        headers=cabeceras,
        json={
            "public_slug": "suplantando",
            "source_organization_member_id": str(ponente.member_id),
        },
    )
    assert respuesta.status_code == 422


async def test_activar_sobre_un_rol_sin_campos_publicables_falla_con_422(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    voluntario = await crear_miembro(organizacion, "volunteer")
    _, cabeceras = await iniciar_sesion_con(
        cliente, organizacion, voluntario.email, voluntario.password
    )

    respuesta = await cliente.patch(
        PUBLIC_PROFILE,
        headers=cabeceras,
        json={
            "public_slug": "voluntario-publico",
            "source_organization_member_id": str(voluntario.member_id),
        },
    )
    assert respuesta.status_code == 422


async def test_el_slug_es_unico_por_organizacion(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    ponente_a = await crear_miembro(
        organizacion, "speaker", email=f"ponente-a@{organizacion.slug}.com"
    )
    ponente_b = await crear_miembro(
        organizacion, "speaker", email=f"ponente-b@{organizacion.slug}.com"
    )
    _, cabeceras_a = await iniciar_sesion_con(
        cliente, organizacion, ponente_a.email, ponente_a.password
    )
    _, cabeceras_b = await iniciar_sesion_con(
        cliente, organizacion, ponente_b.email, ponente_b.password
    )

    await cliente.patch(
        PUBLIC_PROFILE,
        headers=cabeceras_a,
        json={
            "public_slug": "mismo-slug",
            "source_organization_member_id": str(ponente_a.member_id),
        },
    )
    repetido = await cliente.patch(
        PUBLIC_PROFILE,
        headers=cabeceras_b,
        json={
            "public_slug": "mismo-slug",
            "source_organization_member_id": str(ponente_b.member_id),
        },
    )
    assert repetido.status_code == 409


async def test_desactivar_libera_el_slug(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    ponente = await crear_miembro(organizacion, "speaker")
    _, cabeceras = await iniciar_sesion_con(cliente, organizacion, ponente.email, ponente.password)

    await cliente.patch(
        PUBLIC_PROFILE,
        headers=cabeceras,
        json={
            "public_slug": "slug-liberable",
            "source_organization_member_id": str(ponente.member_id),
        },
    )
    desactivacion = await cliente.patch(
        PUBLIC_PROFILE, headers=cabeceras, json={"public_slug": None}
    )
    assert desactivacion.status_code == 200
    assert desactivacion.json()["profile"]["active"] is False

    disponibilidad = await cliente.get(
        CHECK_SLUG, headers=cabeceras, params={"slug": "slug-liberable"}
    )
    assert disponibilidad.json()["available"] is True
