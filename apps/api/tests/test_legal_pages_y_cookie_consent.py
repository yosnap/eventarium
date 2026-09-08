"""Páginas legales (fase 5 del PRD, fase 3 de trabajo) y `POST /public/cookie-consent`.

Cubre: plantilla por defecto, edición desde el panel, restauración de
plantilla, que un `<script>` guardado como contenido legal no se ejecuta al
servirse, y que `cookie_consents` se escribe sin ningún dato personal.
"""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy import func, select

from app.core.database import SessionMaintenance
from app.modules.legal.models import CookieConsent
from tests.conftest import OrganizacionDePrueba, iniciar_sesion

LEGAL_PAGES_ADMIN = "/api/v1/organizations/me/legal-pages"
PUBLIC_LEGAL = "/api/v1/public/legal"
COOKIE_CONSENT = "/api/v1/public/cookie-consent"


async def test_las_cuatro_paginas_resuelven_con_la_plantilla_por_defecto(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    async with SessionMaintenance() as session:
        from app.modules.organizations import repository as organizations_repository

        entidad = await organizations_repository.get_organization(session, organizacion.id)
        assert entidad is not None
        entidad.legal_name = "Acme Legal SL"
        entidad.contact_email = "legal@acme.example"
        entidad.legal_address = "Calle Falsa 123, Valencia"
        entidad.tax_id = "B12345678"
        await session.commit()

    for ruta in ("aviso-legal", "privacidad", "cookies", "condiciones-de-inscripcion"):
        respuesta = await cliente.get(f"{PUBLIC_LEGAL}/{ruta}", headers={"Host": organizacion.host})
        assert respuesta.status_code == 200, respuesta.text
        contenido = respuesta.json()["content"]
        assert "Acme Legal SL" in contenido
        assert "legal@acme.example" in contenido


async def test_la_pagina_de_cookies_declara_turnstile_como_necesario(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    respuesta = await cliente.get(f"{PUBLIC_LEGAL}/cookies", headers={"Host": organizacion.host})
    assert respuesta.status_code == 200, respuesta.text
    contenido = respuesta.json()["content"].lower()
    assert "turnstile" in contenido
    assert "interés legítimo" in contenido or "interes legitimo" in contenido


async def test_host_desconocido_devuelve_404(cliente: AsyncClient) -> None:
    respuesta = await cliente.get(f"{PUBLIC_LEGAL}/aviso-legal", headers={"Host": "no-existe.test"})
    assert respuesta.status_code == 404


async def test_editar_y_restaurar_una_pagina_legal(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    editar = await cliente.patch(
        LEGAL_PAGES_ADMIN,
        headers=cabeceras,
        json={"privacy_policy_content": "Texto editado a mano por la organización."},
    )
    assert editar.status_code == 200, editar.text
    assert editar.json()["privacy_policy"]["is_custom"] is True
    assert editar.json()["privacy_policy"]["content"] == "Texto editado a mano por la organización."

    publica = await cliente.get(f"{PUBLIC_LEGAL}/privacidad", headers={"Host": organizacion.host})
    assert publica.json()["content"] == "Texto editado a mano por la organización."

    restaurar = await cliente.patch(
        LEGAL_PAGES_ADMIN, headers=cabeceras, json={"privacy_policy_content": None}
    )
    assert restaurar.status_code == 200, restaurar.text
    assert restaurar.json()["privacy_policy"]["is_custom"] is False

    tras_restaurar = await cliente.get(
        f"{PUBLIC_LEGAL}/privacidad", headers={"Host": organizacion.host}
    )
    assert tras_restaurar.json()["content"] != "Texto editado a mano por la organización."


async def test_un_script_guardado_no_se_ejecuta_al_servirse(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    """El backend nunca interpreta el contenido como HTML: lo sirve como texto
    en un campo JSON `content`. La ejecución solo podría ocurrir si el
    frontend lo inyectase sin sanear (cubierto en `apps/web`, ver
    `sanitize-markdown.spec.ts`)."""
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    carga = "<script>alert(1)</script>"

    respuesta = await cliente.patch(
        LEGAL_PAGES_ADMIN, headers=cabeceras, json={"legal_notice_content": carga}
    )
    assert respuesta.status_code == 200, respuesta.text

    publica = await cliente.get(f"{PUBLIC_LEGAL}/aviso-legal", headers={"Host": organizacion.host})
    assert publica.status_code == 200
    # El backend lo devuelve tal cual dentro de un string JSON: nunca como HTML
    # ejecutable de la propia respuesta (`content-type: application/json`).
    assert publica.headers["content-type"].startswith("application/json")
    assert publica.json()["content"] == carga


async def test_un_organizador_sin_permiso_no_puede_editar(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    from app.core.permissions import Permission
    from tests.conftest import crear_miembro, crear_rol, iniciar_sesion_con

    await crear_rol(organizacion, key="solo-lectura", permisos=[Permission.ORGANIZATIONS_READ])
    miembro = await crear_miembro(organizacion, "solo-lectura")
    _, cabeceras = await iniciar_sesion_con(cliente, organizacion, miembro.email, miembro.password)

    respuesta = await cliente.patch(
        LEGAL_PAGES_ADMIN, headers=cabeceras, json={"privacy_policy_content": "x"}
    )
    assert respuesta.status_code == 403


async def test_cookie_consent_se_guarda_sin_ningun_dato_personal(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    respuesta = await cliente.post(
        COOKIE_CONSENT,
        headers={"Host": organizacion.host},
        json={"categories": ["necessary", "analytics"]},
    )
    assert respuesta.status_code == 204

    async with SessionMaintenance() as session:
        fila = (await session.execute(select(CookieConsent))).scalar_one()
        assert fila.organization_id == organizacion.id
        assert set(fila.categories_accepted) == {"necessary", "analytics"}
        assert not hasattr(fila, "user_id")
        assert not hasattr(fila, "ip_hash")
        assert not hasattr(fila, "ip_address")

        total = await session.scalar(select(func.count()).select_from(CookieConsent))
        assert total == 1


async def test_cookie_consent_anade_necessary_si_falta(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    """El banner nunca debería omitirla, pero si llega sin ella el backend no
    guarda una fila que no refleje que las cookies necesarias siempre están
    activas."""
    respuesta = await cliente.post(
        COOKIE_CONSENT,
        headers={"Host": organizacion.host},
        json={"categories": ["marketing"]},
    )
    assert respuesta.status_code == 204

    async with SessionMaintenance() as session:
        fila = (await session.execute(select(CookieConsent))).scalar_one()
        assert set(fila.categories_accepted) == {"necessary", "marketing"}


async def test_cookie_consent_rechaza_categoria_desconocida(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    respuesta = await cliente.post(
        COOKIE_CONSENT,
        headers={"Host": organizacion.host},
        json={"categories": ["necessary", "algo-no-valido"]},
    )
    assert respuesta.status_code == 422


async def test_cookie_consent_aislado_por_organizacion(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    otra_organizacion: OrganizacionDePrueba,
) -> None:
    await cliente.post(
        COOKIE_CONSENT,
        headers={"Host": organizacion.host},
        json={"categories": ["necessary"]},
    )
    await cliente.post(
        COOKIE_CONSENT,
        headers={"Host": otra_organizacion.host},
        json={"categories": ["necessary", "marketing"]},
    )

    async with SessionMaintenance() as session:
        de_la_primera = await session.scalar(
            select(func.count())
            .select_from(CookieConsent)
            .where(CookieConsent.organization_id == organizacion.id)
        )
        de_la_segunda = await session.scalar(
            select(func.count())
            .select_from(CookieConsent)
            .where(CookieConsent.organization_id == otra_organizacion.id)
        )
        assert de_la_primera == 1
        assert de_la_segunda == 1
