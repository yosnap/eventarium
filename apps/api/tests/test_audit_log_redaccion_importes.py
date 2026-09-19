"""La lectura del registro de auditoría no sirve los importes de las organizaciones.

El administrador de la instalación gobierna la plataforma, no el negocio de las
organizaciones: si necesita ver las cifras de una, suplanta una cuenta. El
`detail` de `audit_log` guarda los importes completos (es correcto: la auditoría
debe poder reconstruir qué se hizo), así que hay que recortarlos **al servirlos**.

La fila en base no se toca — se comprueba aquí explícitamente, porque es la
mitad de la garantía: el registro de auditoría conserva su valor probatorio.
"""

from __future__ import annotations

from sqlalchemy import select

from app.core.audit import AuditLog
from app.core.audit_redaction import REDACTADO, redactar_importes
from app.core.database import SessionMaintenance
from tests.conftest import OrganizacionDePrueba, iniciar_sesion

AUDIT_LOG = "/api/v1/admin/audit-log"


async def _hacer_superadmin(email: str) -> None:
    from app.modules.users.models import User

    async with SessionMaintenance() as session:
        usuario = await session.scalar(select(User).where(User.email == email))
        assert usuario is not None
        usuario.is_superadmin = True
        await session.commit()


# --- Redacción, en unitario -------------------------------------------------


def test_recorta_los_importes_por_sufijo() -> None:
    entrada = {
        "amount_cents": 5000,
        "budgeted_cents": 120000,
        "total_cents": 300,
        "price_cents": 2500,
        "discount_cents": 0,
        "contingency_fund_cents": 10000,
        "total_budgeted_cents": 500000,
    }
    salida = redactar_importes(entrada)
    assert all(valor == REDACTADO for valor in salida.values())
    assert set(salida) == set(entrada), "no se omiten claves: se marca el valor"


def test_recorta_los_nombres_exactos_economicos() -> None:
    salida = redactar_importes({"amount": 42, "amount_refunded": 10, "contingency_fund_percent": 5})
    assert salida == {
        "amount": REDACTADO,
        "amount_refunded": REDACTADO,
        "contingency_fund_percent": REDACTADO,
    }


def test_no_recorta_lo_que_no_es_economico() -> None:
    """El nombre es lo único que se mira, y por sufijo: `amount_verified` no es
    un importe y no debe recortarse por parecerse a `amount`."""
    entrada = {
        "slug": "iawic",
        "name": "IAWIC",
        "host": "eventos.example",
        "campos": ["name", "city"],
        "amount_verified": True,
        "is_default": False,
    }
    assert redactar_importes(entrada) == entrada


def test_recorta_en_profundidad_las_estructuras_anidadas() -> None:
    """El caso real de una edición: `antes`/`despues`. Un recorrido que solo
    mirara el primer nivel dejaría pasar el importe."""
    entrada = {
        "antes": {"name": "Escenario", "total_cents": 1000},
        "despues": {"name": "Escenario principal", "total_cents": 1200},
    }
    salida = redactar_importes(entrada)
    assert salida["antes"] == {"name": "Escenario", "total_cents": REDACTADO}
    assert salida["despues"] == {"name": "Escenario principal", "total_cents": REDACTADO}


def test_recorta_dentro_de_listas() -> None:
    entrada = {"lineas": [{"budgeted_cents": 100}, {"budgeted_cents": 200, "name": "Catering"}]}
    salida = redactar_importes(entrada)
    assert salida["lineas"] == [
        {"budgeted_cents": REDACTADO},
        {"budgeted_cents": REDACTADO, "name": "Catering"},
    ]


def test_no_muta_la_entrada() -> None:
    """La fila que se acaba de leer de la base conserva sus valores."""
    entrada = {"total_cents": 777, "antes": {"amount_cents": 10}}
    redactar_importes(entrada)
    assert entrada == {"total_cents": 777, "antes": {"amount_cents": 10}}


# --- Por el endpoint, de extremo a extremo ----------------------------------


async def _sembrar_ingreso_auditado(organizacion: OrganizacionDePrueba) -> None:
    async with SessionMaintenance() as session:
        session.add(
            AuditLog(
                actor_user_id=organizacion.owner_id,
                organization_id=organizacion.id,
                action="accounting_income.created",
                entity_type="accounting_income",
                entity_id="00000000-0000-0000-0000-000000000001",
                detail={"origin": "manual", "amount_cents": 45000},
            )
        )
        await session.commit()


async def test_el_endpoint_no_sirve_el_importe_pero_si_la_accion(
    cliente, organizacion: OrganizacionDePrueba
) -> None:
    await _sembrar_ingreso_auditado(organizacion)
    await _hacer_superadmin(organizacion.owner_email)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    respuesta = await cliente.get(AUDIT_LOG, headers=cabeceras)
    assert respuesta.status_code == 200

    entrada = next(
        fila for fila in respuesta.json()["items"] if fila["action"] == "accounting_income.created"
    )
    assert entrada["detail"]["amount_cents"] == REDACTADO
    # Lo no económico sigue visible: la redacción no vacía el detalle.
    assert entrada["detail"]["origin"] == "manual"


async def test_la_fila_en_base_conserva_el_importe(
    cliente, organizacion: OrganizacionDePrueba
) -> None:
    """La otra mitad de la garantía: se recorta al servir, no al escribir."""
    await _sembrar_ingreso_auditado(organizacion)
    await _hacer_superadmin(organizacion.owner_email)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    await cliente.get(AUDIT_LOG, headers=cabeceras)

    async with SessionMaintenance() as session:
        fila = await session.scalar(
            select(AuditLog).where(AuditLog.action == "accounting_income.created")
        )
    assert fila is not None
    assert fila.detail["amount_cents"] == 45000, "la auditoría en base no se altera"
