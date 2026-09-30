"""Regla de «añadir al calendario»: solo con la plaza confirmada.

Pruebas del helper puro, sin base de datos: la regla vive en una función que
recibe el evento ya cargado, y es lo que comparten verificación, promoción de
lista de espera, `/mi-entrada` y la vuelta de pago.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.modules.events.models import Event
from app.modules.organizations.schemas import PublicOrganizationRef
from app.modules.registrations.calendar import calendario_de_evento

INICIO = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
FIN = datetime(2026, 10, 1, 18, 0, tzinfo=UTC)
ORGANIZACION = PublicOrganizationRef(slug="acme", name="Acme")


def _evento(**campos: object) -> Event:
    base: dict[str, object] = {
        "slug": "congreso",
        "title": "Congreso",
        "starts_at": INICIO,
        "ends_at": FIN,
        "timezone": "Europe/Madrid",
        "location_name": None,
        "location_address": None,
        "online_url": None,
    }
    base.update(campos)
    return Event(**base)


def test_confirmada_devuelve_los_datos_del_evento() -> None:
    info = calendario_de_evento(
        _evento(location_name="Palacio", location_address="Calle Mayor 1"),
        ORGANIZACION,
        estado_inscripcion="confirmed",
    )

    assert info is not None
    assert info.slug == "congreso"
    assert info.organization == ORGANIZACION
    assert info.title == "Congreso"
    assert info.starts_at == INICIO
    assert info.ends_at == FIN
    assert info.timezone == "Europe/Madrid"
    assert info.location == "Palacio, Calle Mayor 1"


@pytest.mark.parametrize(
    "estado",
    ["pending_verification", "pending_approval", "pending_payment", "waitlisted", "cancelled"],
)
def test_sin_plaza_confirmada_no_se_ofrece(estado: str) -> None:
    assert calendario_de_evento(_evento(), ORGANIZACION, estado_inscripcion=estado) is None


def test_un_evento_cancelado_no_se_ofrece_aunque_la_inscripcion_siga_confirmada() -> None:
    """Las inscripciones se cancelan por lotes tras cancelar el evento."""
    assert (
        calendario_de_evento(
            _evento(status="cancelled"), ORGANIZACION, estado_inscripcion="confirmed"
        )
        is None
    )


@pytest.mark.parametrize(
    ("campos", "esperado"),
    [
        ({"location_address": "Calle Mayor 1"}, "Calle Mayor 1"),
        ({"location_name": "  Palacio  "}, "Palacio"),
        (
            {"location_name": "   ", "online_url": "https://meet.example/x"},
            "https://meet.example/x",
        ),
        ({"online_url": "https://meet.example/x"}, "https://meet.example/x"),
        ({}, None),
    ],
)
def test_el_lugar_prefiere_sede_y_direccion_y_cae_al_enlace_en_linea(
    campos: dict[str, object], esperado: str | None
) -> None:
    info = calendario_de_evento(_evento(**campos), ORGANIZACION, estado_inscripcion="confirmed")

    assert info is not None
    assert info.location == esperado
