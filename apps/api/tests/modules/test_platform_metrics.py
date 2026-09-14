"""Escritorio de la plataforma.

Aquí lo que se prueba no es que los números salgan, sino que **no salga ningún
importe**. El endpoint corre con el motor de mantenimiento (`BYPASSRLS`), así que
ve todas las organizaciones y todo lo que hay dentro: la frontera del producto
—el administrador de la instalación no ve el negocio de nadie— no la protege
ninguna política, la protege el esquema de respuesta.

Por eso el test central de este fichero no comprueba una respuesta concreta:
recorre el **esquema** buscando claves monetarias. Un `sum(amount_cents)` añadido
mañana a estos modelos falla aquí, que es la única red que hay.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.database import SessionMaintenance
from app.modules.admin import metrics_schemas
from app.modules.payments.models import OrganizationStripeAccount
from app.modules.users.models import User
from tests.conftest import OrganizacionDePrueba, iniciar_sesion

METRICS = "/api/v1/admin/metrics"
EVENTS = "/api/v1/events"

#: Nombres de campo que, si aparecieran en la respuesta, serían un importe. La
#: lista es por sufijo y por nombre exacto, igual que la redacción del registro
#: de auditoría (`app/core/audit_redaction.py`), para que las dos fronteras se
#: lean igual.
SUFIJOS_MONETARIOS = ("_cents", "amount", "_refunded")
NOMBRES_MONETARIOS = frozenset(
    {"amount", "importe", "precio", "price", "budget", "budgeted", "total_cents", "ingresos"}
)


def _claves_de(modelo: type) -> set[str]:
    """Todas las claves del esquema, incluidas las de los modelos anidados."""
    claves: set[str] = set()
    for nombre, campo in modelo.model_fields.items():
        claves.add(nombre)
        anotacion = campo.annotation
        for posible in _modelos_anidados(anotacion):
            claves |= _claves_de(posible)
    return claves


def _modelos_anidados(anotacion: object) -> list[type]:
    """Los modelos Pydantic que aparecen dentro de una anotación, si hay."""
    candidatos: list[type] = []
    origen = getattr(anotacion, "__origin__", None)
    args = getattr(anotacion, "__args__", ())
    for arg in args or (anotacion,):
        if isinstance(arg, type) and hasattr(arg, "model_fields"):
            candidatos.append(arg)
    if origen is not None and isinstance(origen, type) and hasattr(origen, "model_fields"):
        candidatos.append(origen)
    return candidatos


async def _hacer_superadmin(email: str) -> None:
    async with SessionMaintenance() as session:
        usuario = await session.scalar(select(User).where(User.email == email))
        assert usuario is not None
        usuario.is_superadmin = True
        await session.commit()


class TestElEsquemaNoAdmiteImportes:
    def test_ninguna_clave_del_esquema_es_monetaria(self) -> None:
        """La red que sostiene toda la frontera del producto.

        Si alguien añade un campo de dinero a las métricas de plataforma, este
        test falla — que es exactamente lo que se quiere: la decisión de que el
        administrador vea importes es de producto, no un descuido que pasa CI.
        """
        claves = _claves_de(metrics_schemas.MetricasDePlataformaOut)

        sospechosas = {
            clave
            for clave in claves
            if clave.lower() in NOMBRES_MONETARIOS or clave.lower().endswith(SUFIJOS_MONETARIOS)
        }
        assert not sospechosas, (
            f"El esquema del escritorio de plataforma no puede tener campos "
            f"monetarios, y tiene: {sorted(sospechosas)}. Si el administrador "
            f"debe ver importes, es un cambio de producto: actualiza el esquema "
            f"y este test a conciencia."
        )


class TestMetricasDePlataforma:
    async def test_sin_superadmin_no_se_puede_consultar(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        respuesta = await cliente.get(METRICS, headers=cabeceras)
        assert respuesta.status_code == 403

    async def test_sin_sesion_devuelve_401(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        respuesta = await cliente.get(METRICS)
        assert respuesta.status_code == 401

    async def test_el_superadmin_ve_la_salud_y_las_cifras_de_la_instalacion(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        await _hacer_superadmin(organizacion.owner_email)
        _, cabeceras = await iniciar_sesion(cliente, organizacion)

        respuesta = await cliente.get(METRICS, headers=cabeceras)
        assert respuesta.status_code == 200, respuesta.text
        cuerpo = respuesta.json()

        # Las tres dependencias se comprueban de verdad: en el entorno de test
        # están todas levantadas.
        assert cuerpo["salud"] == {"database": "ok", "storage": "ok", "redis": "ok"}
        assert cuerpo["cifras"]["organizaciones_totales"] >= 1
        assert cuerpo["cifras"]["usuarios"] >= 1

    async def test_ve_la_actividad_de_cada_organizacion_sin_importes(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        _, cabeceras_admin = await iniciar_sesion(cliente, organizacion)
        creado = await cliente.post(
            EVENTS,
            headers=cabeceras_admin,
            json={
                "slug": "plataforma-actividad",
                "title": "Evento de plataforma",
                "starts_at": "2026-10-01T09:00:00Z",
                "ends_at": "2026-10-02T18:00:00Z",
                "location_mode": "in_person",
                "location_name": "Sala",
            },
        )
        assert creado.status_code == 201, creado.text

        await _hacer_superadmin(organizacion.owner_email)
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        respuesta = await cliente.get(METRICS, headers=cabeceras)

        fila = next(o for o in respuesta.json()["organizaciones"] if o["slug"] == organizacion.slug)
        assert fila["eventos"] >= 1
        assert fila["miembros"] >= 1
        assert fila["eventos_publicados"] == 0, "el evento se ha creado en borrador"
        assert fila["ultimo_evento_creado"] is not None
        # Y ninguna clave de dinero en la fila, que es lo que se está protegiendo.
        assert not any("cents" in clave or "amount" in clave for clave in fila)

    async def test_las_banderas_de_no_arranca_detectan_una_cuenta_atascada(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        """Una organización que publica eventos de pago sin conectar Stripe no
        puede cobrar: es el caso que el admin tiene que poder ver sin mirar una
        sola cifra.

        Se publica un evento **gratuito** y se deja otro `paid` en borrador, no
        un `paid` publicado: el sistema **no deja publicar un evento de pago sin
        cuenta que cobre** (`_asegurar_venta_posible`, 409). Eso está bien y este
        test lo respeta; la bandera mira los publicados en modo pago porque es
        hasta donde el negocio puede llegar.
        """
        _, cabeceras_admin = await iniciar_sesion(cliente, organizacion)

        # Un evento gratuito sí se publica.
        gratuito = await cliente.post(
            EVENTS,
            headers=cabeceras_admin,
            json={
                "slug": "plataforma-gratuito",
                "title": "Evento gratuito",
                "starts_at": "2026-10-01T09:00:00Z",
                "ends_at": "2026-10-02T18:00:00Z",
                "location_mode": "in_person",
                "location_name": "Sala",
            },
        )
        publicado = await cliente.patch(
            f"{EVENTS}/{gratuito.json()['id']}",
            headers=cabeceras_admin,
            json={"status": "published", "visibility": "public"},
        )
        assert publicado.status_code == 200, publicado.text

        await _hacer_superadmin(organizacion.owner_email)
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        respuesta = await cliente.get(METRICS, headers=cabeceras)

        fila = next(o for o in respuesta.json()["organizaciones"] if o["slug"] == organizacion.slug)
        assert fila["stripe_conectada"] is False
        # Publicó y no ha recibido ni una inscripción: está publicada y parada,
        # que es exactamente lo que el admin necesita ver.
        assert fila["eventos_publicados"] >= 1
        assert fila["publicados_sin_inscripciones"] is True
        # No hay eventos **de pago** publicados (no se pueden publicar sin
        # cuenta), así que esta bandera no aplica todavía.
        assert fila["tiene_stripe_pendiente_con_eventos_de_pago"] is False

    async def test_la_bandera_de_stripe_salta_al_perder_la_cuenta(
        self,
        cliente: AsyncClient,
        organizacion: OrganizacionDePrueba,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """El caso real que la bandera existe para cazar.

        Un evento de pago **sí** se puede publicar con la cuenta conectada; si la
        cuenta se cae después (desautorizada, o `charges_enabled` a `False`), el
        evento se queda publicado y vendiendo sin poder cobrar. El sistema no
        puede impedir eso —la desconexión ocurre en Stripe—, así que el admin
        tiene que poder verlo, y para eso está la bandera.

        Publicar un evento de pago exige tres cosas (ver `_asegurar_venta_posible`):
        que la instalación tenga Stripe configurado, una cuenta con
        `charges_enabled`, y al menos un tipo de entrada vigente. Aquí se dan las
        tres para llegar a un estado que el producto permite de verdad.
        """
        from app.core.config import Settings
        from app.modules.events import service as events_service

        def _settings_con_stripe() -> Settings:
            return Settings(
                stripe_secret_key="sk_test_" + "a" * 40,
                stripe_webhook_secret="whsec_" + "b" * 40,
            )

        monkeypatch.setattr(events_service, "get_settings", _settings_con_stripe)

        async with SessionMaintenance() as session:
            session.add(
                OrganizationStripeAccount(
                    organization_id=organizacion.id,
                    stripe_account_id=f"acct_{organizacion.slug}",
                    charges_enabled=True,
                )
            )
            await session.commit()

        _, cabeceras_admin = await iniciar_sesion(cliente, organizacion)
        creado = await cliente.post(
            EVENTS,
            headers=cabeceras_admin,
            json={
                "slug": "plataforma-pago-desconectado",
                "title": "Evento de pago",
                "starts_at": "2026-10-01T09:00:00Z",
                "ends_at": "2026-10-02T18:00:00Z",
                "location_mode": "in_person",
                "location_name": "Sala",
                "registration_mode": "paid",
            },
        )
        evento = creado.json()

        # Un tipo de entrada vigente: sin él tampoco se puede publicar.
        tipo = await cliente.post(
            f"{EVENTS}/{evento['id']}/ticket-types",
            headers=cabeceras_admin,
            json={"name": "General", "price_cents": 2500, "is_active": True},
        )
        assert tipo.status_code in (200, 201), tipo.text

        publicado = await cliente.patch(
            f"{EVENTS}/{evento['id']}",
            headers=cabeceras_admin,
            json={"status": "published", "visibility": "public"},
        )
        assert publicado.status_code == 200, publicado.text

        # Y ahora se pierde la cuenta, que es lo que el sistema no puede evitar.
        async with SessionMaintenance() as session:
            cuenta = await session.scalar(
                select(OrganizationStripeAccount).where(
                    OrganizationStripeAccount.organization_id == organizacion.id
                )
            )
            assert cuenta is not None
            cuenta.deauthorized_at = datetime.now(UTC)
            await session.commit()

        await _hacer_superadmin(organizacion.owner_email)
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        respuesta = await cliente.get(METRICS, headers=cabeceras)

        fila = next(o for o in respuesta.json()["organizaciones"] if o["slug"] == organizacion.slug)
        assert fila["stripe_conectada"] is False
        assert fila["tiene_stripe_pendiente_con_eventos_de_pago"] is True, (
            "publicado y de pago, con la cuenta caída: el admin tiene que verlo"
        )

    async def test_una_organizacion_sin_actividad_no_tiene_marcas(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        """`None` es «no consta», no una fecha inventada."""
        await _hacer_superadmin(organizacion.owner_email)
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        respuesta = await cliente.get(METRICS, headers=cabeceras)

        fila = next(o for o in respuesta.json()["organizaciones"] if o["slug"] == organizacion.slug)
        assert fila["evento_mas_reciente"] is None
        assert fila["ultima_inscripcion"] is None
        # El acceso sí consta: acaba de entrar para hacer esta petición.
        assert fila["ultimo_acceso"] is not None
