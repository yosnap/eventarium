"""El catálogo de eventos de demostración es coherente consigo mismo.

Este test existe por un fallo real: el script de siembra declaraba las sesiones
con una convención de duración distinta de la del evento, y **el sistema lo
rechazaba al sembrar** con un 409 («la sesión debe caer dentro del rango del
evento»). No lo cazó nada porque el catálogo no tenía pruebas: el report que
acompañó al script verificó el *resultado* de una ejecución, no el script.

Es una comprobación **de datos, sin base de datos**: replica exactamente las dos
funciones que usa la siembra (`_local_a_utc` y `_inicio_de_sesion`) y comprueba
que cada sesión cae dentro de su evento. Es lo que permite que un cambio de
catálogo falle aquí en medio segundo, en vez de al sembrar contra Postgres.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from scripts.seed_eventos_demo.datos import EVENTOS, PERSONAS
from scripts.seed_eventos_demo.siembra import _inicio_de_sesion, _local_a_utc

CORREOS = {persona["email"] for persona in PERSONAS}


def _en_evento(evento: dict) -> tuple:
    """El evento tal como lo persiste la siembra: fechas ya en UTC real."""
    zona = evento.get("timezone", "Europe/Madrid")
    return _local_a_utc(evento["starts_at"], zona), _local_a_utc(evento["ends_at"], zona), zona


class TestCatalogoCoherente:
    def test_hay_veinte_eventos_y_sus_slugs_no_se_repiten(self) -> None:
        slugs = [evento["slug"] for evento in EVENTOS]
        assert len(slugs) == len(set(slugs)), "dos eventos con el mismo slug"
        assert len(slugs) == 20

    def test_las_fechas_del_evento_estan_en_orden(self) -> None:
        for evento in EVENTOS:
            assert evento["ends_at"] > evento["starts_at"], (
                f"«{evento['slug']}» termina antes de empezar"
            )

    def test_cada_sesion_cae_dentro_de_su_evento(self) -> None:
        """La comprobación que el sistema hace al sembrar, aquí y sin base.

        Si esto falla, la siembra fallará con un 409 y el mensaje no dirá cuál
        de los veinte eventos es el culpable.
        """
        for evento in EVENTOS:
            inicio, fin, zona = _en_evento(evento)
            for sesion in evento.get("sesiones", []):
                dias, hora, minuto, dur_horas, dur_minutos = sesion["starts_offset"]
                empieza = _inicio_de_sesion(inicio, dias, hora, minuto, zona)
                termina = empieza + timedelta(hours=dur_horas, minutes=dur_minutos)
                assert empieza >= inicio, (
                    f"«{evento['slug']}» / «{sesion['title']}» empieza antes que su evento "
                    f"({empieza} < {inicio})"
                )
                assert termina <= fin, (
                    f"«{evento['slug']}» / «{sesion['title']}» termina después que su evento "
                    f"({termina} > {fin})"
                )

    def test_las_sesiones_no_van_hacia_atras_en_el_tiempo(self) -> None:
        """Una duración negativa o cero daría una sesión que acaba antes de
        empezar, y ninguna validación de rango lo cazaría por sí sola."""
        for evento in EVENTOS:
            for sesion in evento.get("sesiones", []):
                _, _, _, dur_horas, dur_minutos = sesion["starts_offset"]
                assert dur_horas * 60 + dur_minutos > 0, (
                    f"«{evento['slug']}» / «{sesion['title']}» no dura nada"
                )

    def test_los_ponentes_de_cada_sesion_existen_en_el_catalogo(self) -> None:
        """Un correo mal escrito no falla al sembrar: revienta con un `KeyError`
        sin decir cuál."""
        for evento in EVENTOS:
            for sesion in evento.get("sesiones", []):
                for correo, rol in sesion.get("ponentes", []):
                    assert correo in CORREOS, (
                        f"«{evento['slug']}» / «{sesion['title']}» menciona a «{correo}», "
                        f"que no está en el catálogo de personas"
                    )
                    # El rol es **texto libre** en el modelo (`role_key`, solo
                    # exige no estar vacío): «panelista» es tan válido como
                    # «speaker». Lo que se comprueba es que venga puesto, no que
                    # esté en una lista que el sistema no tiene.
                    assert rol.strip(), f"participación sin rol en «{sesion['title']}»"

    def test_las_sedes_referidas_por_las_sesiones_existen(self) -> None:
        """`venue_index` apunta por posición: un índice de más revienta al sembrar."""
        for evento in EVENTOS:
            sedes = evento.get("sedes", [])
            for sesion in evento.get("sesiones", []):
                indice = sesion.get("venue_index")
                if indice is not None:
                    assert 0 <= indice < len(sedes), (
                        f"«{evento['slug']}» / «{sesion['title']}» apunta a la sede {indice}, "
                        f"y el evento solo tiene {len(sedes)}"
                    )

    def test_los_eventos_de_pago_tienen_al_menos_un_tipo_de_entrada(self) -> None:
        """Sin tipos de entrada, el sistema **no deja publicar** un evento de pago:
        la siembra fallaría al publicar, no al crear."""
        for evento in EVENTOS:
            if evento["registration_mode"] == "paid":
                assert evento.get("ticket_types"), (
                    f"«{evento['slug']}» es de pago y no declara ningún tipo de entrada"
                )

    @pytest.mark.parametrize("evento", EVENTOS, ids=lambda e: e["slug"])
    def test_cada_evento_declara_lo_minimo(self, evento: dict) -> None:
        assert evento.get("title")
        assert evento.get("location_mode") in {"in_person", "online", "hybrid"}
        assert evento.get("registration_mode") in {"free", "approval", "paid"}
