"""Las horas de los correos van en la zona del evento, también al cambiar la hora."""

from __future__ import annotations

from datetime import UTC, date, datetime

from app.core.fechas import fecha, fecha_y_hora


def test_respeta_el_cambio_de_hora_de_octubre() -> None:
    # El 25-oct-2026 Madrid pasa de UTC+2 a UTC+1.
    assert fecha_y_hora(datetime(2026, 10, 24, 16, 0, tzinfo=UTC), "Europe/Madrid") == (
        "24/10/2026 18:00"
    )
    assert fecha_y_hora(datetime(2026, 10, 26, 16, 0, tzinfo=UTC), "Europe/Madrid") == (
        "26/10/2026 17:00"
    )


def test_una_zona_desconocida_no_rompe_y_usa_madrid() -> None:
    assert fecha_y_hora(datetime(2026, 11, 1, 12, 0, tzinfo=UTC), "Madrid") == "01/11/2026 13:00"


def test_en_ingles_mes_dia_y_hora_de_doce_horas() -> None:
    # 17:30 UTC del 18-nov es 18:30 en Madrid (UTC+1).
    instante = datetime(2026, 11, 18, 17, 30, tzinfo=UTC)
    assert fecha_y_hora(instante, "Europe/Madrid", "es-ES") == "18/11/2026 18:30"
    assert fecha_y_hora(instante, "Europe/Madrid", "en-US") == "11/18/2026 6:30 PM"


def test_en_ingles_medianoche_y_mediodia() -> None:
    assert fecha_y_hora(datetime(2026, 1, 5, 0, 5, tzinfo=UTC), "UTC", "en-US") == (
        "01/05/2026 12:05 AM"
    )
    assert fecha_y_hora(datetime(2026, 1, 5, 12, 0, tzinfo=UTC), "UTC", "en-US") == (
        "01/05/2026 12:00 PM"
    )


def test_conserva_la_zona_del_evento_en_ingles() -> None:
    instante = datetime(2026, 11, 18, 17, 30, tzinfo=UTC)
    assert fecha_y_hora(instante, "America/Mexico_City", "en-US") == "11/18/2026 11:30 AM"


def test_solo_fecha_segun_el_idioma() -> None:
    assert fecha(date(2026, 11, 18), "es-ES") == "18/11/2026"
    assert fecha(date(2026, 11, 18), "en-US") == "11/18/2026"
