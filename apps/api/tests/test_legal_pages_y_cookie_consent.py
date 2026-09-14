"""Páginas legales de plataforma y `POST /public/cookie-consent`.

Eventarium es una SaaS centralizada: las cuatro páginas legales (aviso legal,
privacidad, cookies, condiciones de inscripción) son siempre las de
plataforma, sirvan desde el host que sirvan — no hay contenido legal propio
de organización (decisión del usuario, 2026-09-14; antes sí lo había,
editable desde `/organizations/me/legal-pages`, retirado en este cambio).

Cubre: plantilla por defecto, edición desde el panel de plataforma,
restauración de plantilla, que un `<script>` guardado como contenido legal
no se ejecuta al servirse, y que `cookie_consents` (que sigue siendo por
organización: es el registro de qué aceptó cada visitante, no el texto
legal) se escribe sin ningún dato personal.
"""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy import func, select

from app.core.database import SessionMaintenance
from app.modules.legal.models import CookieConsent
from app.modules.users.models import User
from tests.conftest import OrganizacionDePrueba, iniciar_sesion

PLATFORM_LEGAL_ADMIN = "/api/v1/admin/legal-pages"
PUBLIC_LEGAL = "/api/v1/public/legal"
COOKIE_CONSENT = "/api/v1/public/cookie-consent"


async def _sesion_superadmin(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> dict[str, str]:
    """Un `owner` promovido a superadmin: mismo patrón que `test_platform_identity.py`."""
    async with SessionMaintenance() as session:
        usuario = await session.scalar(select(User).where(User.email == organizacion.owner_email))
        assert usuario is not None
        usuario.is_superadmin = True
        await session.commit()
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    return cabeceras


async def test_las_cuatro_paginas_resuelven_con_la_plantilla_por_defecto(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    for ruta in ("aviso-legal", "privacidad", "cookies", "condiciones-de-inscripcion"):
        respuesta = await cliente.get(f"{PUBLIC_LEGAL}/{ruta}", headers={"Host": organizacion.host})
        assert respuesta.status_code == 200, respuesta.text
        assert respuesta.json()["content"]


async def test_las_cuatro_paginas_son_iguales_en_dos_organizaciones_distintas(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    otra_organizacion: OrganizacionDePrueba,
) -> None:
    """No hay contenido legal por organización: da igual desde qué host se pida."""
    for ruta in ("aviso-legal", "privacidad", "cookies", "condiciones-de-inscripcion"):
        de_una = await cliente.get(f"{PUBLIC_LEGAL}/{ruta}", headers={"Host": organizacion.host})
        de_otra = await cliente.get(
            f"{PUBLIC_LEGAL}/{ruta}", headers={"Host": otra_organizacion.host}
        )
        assert de_una.json()["content"] == de_otra.json()["content"]


async def test_la_pagina_de_cookies_declara_turnstile_como_necesario(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    respuesta = await cliente.get(f"{PUBLIC_LEGAL}/cookies", headers={"Host": organizacion.host})
    assert respuesta.status_code == 200, respuesta.text
    contenido = respuesta.json()["content"].lower()
    assert "turnstile" in contenido


async def test_host_desconocido_tambien_sirve_las_paginas_legales(cliente: AsyncClient) -> None:
    """Sin contenido por organización que proteger, no hay nada que un host
    desconocido pudiera filtrar: las cuatro páginas responden igual que en
    cualquier otro host, plataforma incluida."""
    respuesta = await cliente.get(f"{PUBLIC_LEGAL}/aviso-legal", headers={"Host": "no-existe.test"})
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["content"]


async def test_editar_y_restaurar_una_pagina_legal(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    cabeceras = await _sesion_superadmin(cliente, organizacion)

    editar = await cliente.patch(
        PLATFORM_LEGAL_ADMIN,
        headers=cabeceras,
        json={"privacy_policy_content": "Texto editado a mano por la plataforma."},
    )
    assert editar.status_code == 200, editar.text
    assert editar.json()["privacy_policy"]["is_custom"] is True
    assert editar.json()["privacy_policy"]["content"] == "Texto editado a mano por la plataforma."

    publica = await cliente.get(f"{PUBLIC_LEGAL}/privacidad", headers={"Host": "localhost"})
    assert publica.json()["content"] == "Texto editado a mano por la plataforma."

    restaurar = await cliente.patch(
        PLATFORM_LEGAL_ADMIN, headers=cabeceras, json={"privacy_policy_content": None}
    )
    assert restaurar.status_code == 200, restaurar.text
    assert restaurar.json()["privacy_policy"]["is_custom"] is False

    tras_restaurar = await cliente.get(f"{PUBLIC_LEGAL}/privacidad", headers={"Host": "localhost"})
    assert tras_restaurar.json()["content"] != "Texto editado a mano por la plataforma."


async def test_un_script_guardado_no_se_ejecuta_al_servirse(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    """El backend nunca interpreta el contenido como HTML: lo sirve como texto
    en un campo JSON `content`. La ejecución solo podría ocurrir si el
    frontend lo inyectase sin sanear (cubierto en `apps/web`, ver
    `sanitize-markdown.spec.ts`)."""
    cabeceras = await _sesion_superadmin(cliente, organizacion)
    carga = "<script>alert(1)</script>"

    respuesta = await cliente.patch(
        PLATFORM_LEGAL_ADMIN, headers=cabeceras, json={"legal_notice_content": carga}
    )
    assert respuesta.status_code == 200, respuesta.text

    publica = await cliente.get(f"{PUBLIC_LEGAL}/aviso-legal", headers={"Host": "localhost"})
    assert publica.status_code == 200
    # El backend lo devuelve tal cual dentro de un string JSON: nunca como HTML
    # ejecutable de la propia respuesta (`content-type: application/json`).
    assert publica.headers["content-type"].startswith("application/json")
    assert publica.json()["content"] == carga

    # Restaura la plantilla para no dejar el aviso legal de la instalación
    # con el contenido de esta prueba de por vida.
    await cliente.patch(
        PLATFORM_LEGAL_ADMIN, headers=cabeceras, json={"legal_notice_content": None}
    )


async def test_un_organizador_no_puede_editar_las_paginas_legales(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    """Son de plataforma: ni el `owner` de una organización llega al endpoint."""
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    respuesta = await cliente.patch(
        PLATFORM_LEGAL_ADMIN, headers=cabeceras, json={"privacy_policy_content": "x"}
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
