"""Ficha de una membresía (p. ej. la biografía de un ponente): la edita su
titular o quien gestiona miembros y podría conceder ese rol."""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy import func, select, text

from app.core.database import SessionMaintenance
from app.modules.translations.campos import huella
from app.modules.translations.models import ContentTranslation
from tests.conftest import (
    OrganizacionDePrueba,
    crear_miembro,
    iniciar_sesion,
    iniciar_sesion_con,
)

BIO = "Investigadora en IA aplicada a la salud."


def _url(member_id: object) -> str:
    return f"/api/v1/organizations/me/members/{member_id}/profile"


async def test_un_ponente_completa_su_biografia(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    ponente = await crear_miembro(organizacion, "speaker")
    _, cabeceras = await iniciar_sesion_con(cliente, organizacion, ponente.email, ponente.password)

    respuesta = await cliente.patch(
        _url(ponente.member_id), headers=cabeceras, json={"profile_data": {"bio": BIO}}
    )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["profile_data"] == {"bio": BIO}
    perfil = await cliente.get("/api/v1/users/me/public-profile", headers=cabeceras)
    membresia = perfil.json()["eligible_memberships"][0]
    assert membresia["profile_data"]["bio"] == BIO
    assert any(campo["key"] == "bio" for campo in membresia["profile_fields"])


async def test_el_titular_debe_rellenar_la_biografia_obligatoria(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    ponente = await crear_miembro(organizacion, "speaker")
    _, cabeceras = await iniciar_sesion_con(cliente, organizacion, ponente.email, ponente.password)

    respuesta = await cliente.patch(
        _url(ponente.member_id), headers=cabeceras, json={"profile_data": {"empresa": "Acme"}}
    )

    assert respuesta.status_code == 422


async def test_un_ponente_no_edita_la_ficha_de_otra_persona(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    ponente = await crear_miembro(organizacion, "speaker")
    otro = await crear_miembro(organizacion, "speaker", email="otro-ponente@example.com")
    _, cabeceras = await iniciar_sesion_con(cliente, organizacion, ponente.email, ponente.password)

    respuesta = await cliente.patch(
        _url(otro.member_id), headers=cabeceras, json={"profile_data": {"bio": BIO}}
    )

    assert respuesta.status_code == 403


async def test_el_organizador_completa_la_ficha_por_partes_y_queda_auditado(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    ponente = await crear_miembro(organizacion, "speaker")
    organizador = await crear_miembro(organizacion, "organizer")
    _, cabeceras = await iniciar_sesion_con(
        cliente, organizacion, organizador.email, organizador.password
    )

    respuesta = await cliente.patch(
        _url(ponente.member_id), headers=cabeceras, json={"profile_data": {"empresa": "Acme"}}
    )

    assert respuesta.status_code == 200, respuesta.text
    async with SessionMaintenance() as session:
        fila = (
            await session.execute(
                text(
                    "SELECT detail FROM audit_log WHERE action = 'member.profile_updated' "
                    "AND entity_id = :id"
                ),
                {"id": str(ponente.member_id)},
            )
        ).scalar_one()
    assert fila["campos"] == ["empresa"]
    assert "Acme" not in str(fila)


async def test_un_organizador_no_reescribe_la_ficha_del_propietario(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    organizador = await crear_miembro(organizacion, "organizer")
    _, cabeceras = await iniciar_sesion_con(
        cliente, organizacion, organizador.email, organizador.password
    )
    async with SessionMaintenance() as session:
        member_id_owner = await session.scalar(
            text("SELECT id FROM organization_members WHERE user_id = :u AND organization_id = :o"),
            {"u": organizacion.owner_id, "o": organizacion.id},
        )

    respuesta = await cliente.patch(
        _url(member_id_owner), headers=cabeceras, json={"profile_data": {"cargo": "Otro"}}
    )

    assert respuesta.status_code == 403


async def test_claves_desconocidas_y_tamano_maximo(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    ponente = await crear_miembro(organizacion, "speaker")
    _, cabeceras = await iniciar_sesion_con(cliente, organizacion, ponente.email, ponente.password)

    desconocida = await cliente.patch(
        _url(ponente.member_id),
        headers=cabeceras,
        json={"profile_data": {"bio": BIO, "twitter": "@x"}},
    )
    larga = await cliente.patch(
        _url(ponente.member_id), headers=cabeceras, json={"profile_data": {"bio": "a" * 5001}}
    )

    assert desconocida.status_code == 422
    assert larga.status_code == 422
    assert "5000" in larga.text


async def test_una_clave_heredada_guardada_se_descarta_sin_bloquear(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    ponente = await crear_miembro(organizacion, "speaker")
    async with SessionMaintenance() as session:
        await session.execute(
            text(
                "UPDATE organization_members SET profile_data = "
                '\'{"bio": "vieja", "twitter": "@antiguo"}\' WHERE id = :id'
            ),
            {"id": ponente.member_id},
        )
        await session.commit()
    _, cabeceras = await iniciar_sesion_con(cliente, organizacion, ponente.email, ponente.password)

    respuesta = await cliente.patch(
        _url(ponente.member_id), headers=cabeceras, json={"profile_data": {"bio": BIO}}
    )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["profile_data"] == {"bio": BIO}


async def test_si_la_ficha_cambio_entre_medias_da_409(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    ponente = await crear_miembro(organizacion, "speaker")
    _, cabeceras = await iniciar_sesion_con(cliente, organizacion, ponente.email, ponente.password)
    primera = await cliente.patch(
        _url(ponente.member_id), headers=cabeceras, json={"profile_data": {"bio": BIO}}
    )
    leida = primera.json()["updated_at"]
    await cliente.patch(
        _url(ponente.member_id),
        headers=cabeceras,
        json={"profile_data": {"bio": "Otra versión"}, "expected_updated_at": leida},
    )

    respuesta = await cliente.patch(
        _url(ponente.member_id),
        headers=cabeceras,
        json={"profile_data": {"bio": "La mía"}, "expected_updated_at": leida},
    )

    assert respuesta.status_code == 409


async def test_una_membresia_de_otra_organizacion_no_existe(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    otra_organizacion: OrganizacionDePrueba,
) -> None:
    ajeno = await crear_miembro(otra_organizacion, "speaker")
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    respuesta = await cliente.patch(
        _url(ajeno.member_id), headers=cabeceras, json={"profile_data": {"bio": BIO}}
    )

    assert respuesta.status_code == 404


async def test_un_correo_de_contacto_tiene_tope(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    ponente = await crear_miembro(organizacion, "speaker")
    _, cabeceras = await iniciar_sesion_con(cliente, organizacion, ponente.email, ponente.password)

    respuesta = await cliente.patch(
        _url(ponente.member_id),
        headers=cabeceras,
        json={"profile_data": {"bio": BIO, "contacto": f"{'a' * 250}@acme.example"}},
    )

    assert respuesta.status_code == 422
    assert "254" in respuesta.text


async def test_vaciar_un_campo_de_la_ficha_borra_su_traduccion(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    ponente = await crear_miembro(organizacion, "speaker")
    _, cabeceras = await iniciar_sesion_con(cliente, organizacion, ponente.email, ponente.password)
    titular = "Investigadora"
    await cliente.patch(
        _url(ponente.member_id),
        headers=cabeceras,
        json={"profile_data": {"bio": BIO, "titular": titular}},
    )
    async with SessionMaintenance() as session, session.begin():
        session.add(
            ContentTranslation(
                organization_id=organizacion.id,
                event_id=None,
                entity_type="member_profile",
                entity_id=ponente.member_id,
                field="titular",
                locale="en-US",
                value="Researcher",
                origin="manual",
                status="al_dia",
                source_hash=huella(titular),
            )
        )

    vaciada = await cliente.patch(
        _url(ponente.member_id),
        headers=cabeceras,
        json={"profile_data": {"bio": BIO, "titular": ""}},
    )

    assert vaciada.status_code == 200, vaciada.text
    async with SessionMaintenance() as session:
        quedan = await session.scalar(
            select(func.count())
            .select_from(ContentTranslation)
            .where(ContentTranslation.entity_id == ponente.member_id)
        )
    assert quedan == 0
