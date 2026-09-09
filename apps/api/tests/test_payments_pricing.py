"""Funciones puras de precio y vigencia (fase 6 del PRD, fase 3 de trabajo).

Sin base de datos ni fixtures: `calcular_precio_final`, `validar_tipo_vigente`
y `validar_codigo_vigente` no tocan la sesión, así que se testean con
`SimpleNamespace` en vez de instancias reales del ORM.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.modules.payments.service import (
    calcular_precio_final,
    validar_codigo_vigente,
    validar_tipo_vigente,
)

AHORA = datetime.now(UTC)


def test_sin_codigo_devuelve_el_precio_intacto() -> None:
    assert calcular_precio_final(1500, None, None) == 1500


def test_porcentaje_redondea_a_la_baja_al_centimo() -> None:
    # 999 * 33 // 100 = 329 (329.67 truncado), total 670.
    assert calcular_precio_final(999, "percentage", 33) == 670


def test_porcentaje_100_da_cero() -> None:
    assert calcular_precio_final(1500, "percentage", 100) == 0


def test_importe_fijo_mayor_que_el_precio_da_cero_nunca_negativo() -> None:
    assert calcular_precio_final(500, "fixed_amount", 10_000) == 0


def test_importe_fijo_menor_que_el_precio_resta_exacto() -> None:
    assert calcular_precio_final(1500, "fixed_amount", 300) == 1200


def test_discount_type_desconocido_lanza_value_error() -> None:
    with pytest.raises(ValueError, match="discount_type desconocido"):
        calcular_precio_final(1000, "otro", 10)


def _tipo(**overrides: object) -> SimpleNamespace:
    base = dict(is_active=True, sales_start_at=None, sales_end_at=None, id=uuid.uuid4())
    base.update(overrides)
    return SimpleNamespace(**base)


def test_tipo_inactivo_no_esta_vigente() -> None:
    assert validar_tipo_vigente(_tipo(is_active=False), AHORA) is False


def test_tipo_antes_de_su_ventana_de_venta_no_esta_vigente() -> None:
    tipo = _tipo(sales_start_at=AHORA + timedelta(days=1))
    assert validar_tipo_vigente(tipo, AHORA) is False


def test_tipo_despues_de_su_ventana_de_venta_no_esta_vigente() -> None:
    tipo = _tipo(sales_end_at=AHORA - timedelta(days=1))
    assert validar_tipo_vigente(tipo, AHORA) is False


def test_tipo_sin_ventana_y_activo_esta_vigente() -> None:
    assert validar_tipo_vigente(_tipo(), AHORA) is True


def test_tipo_dentro_de_su_ventana_esta_vigente() -> None:
    tipo = _tipo(sales_start_at=AHORA - timedelta(days=1), sales_end_at=AHORA + timedelta(days=1))
    assert validar_tipo_vigente(tipo, AHORA) is True


def _codigo(**overrides: object) -> SimpleNamespace:
    base = dict(valid_from=None, valid_until=None, max_uses=None, ticket_type_id=None)
    base.update(overrides)
    return SimpleNamespace(**base)


def test_codigo_antes_de_su_vigencia_no_es_valido() -> None:
    tipo = _tipo()
    codigo = _codigo(valid_from=AHORA + timedelta(days=1))
    assert validar_codigo_vigente(codigo, tipo, 0, AHORA) is False


def test_codigo_tras_su_vigencia_no_es_valido() -> None:
    tipo = _tipo()
    codigo = _codigo(valid_until=AHORA - timedelta(days=1))
    assert validar_codigo_vigente(codigo, tipo, 0, AHORA) is False


def test_codigo_agotado_por_usos_derivados_no_es_valido() -> None:
    tipo = _tipo()
    codigo = _codigo(max_uses=3)
    assert validar_codigo_vigente(codigo, tipo, 3, AHORA) is False
    assert validar_codigo_vigente(codigo, tipo, 2, AHORA) is True


def test_codigo_de_otro_tipo_de_entrada_no_es_valido() -> None:
    tipo = _tipo()
    codigo = _codigo(ticket_type_id=uuid.uuid4())
    assert validar_codigo_vigente(codigo, tipo, 0, AHORA) is False


def test_codigo_sin_tipo_restringido_aplica_a_cualquier_tipo() -> None:
    tipo = _tipo()
    codigo = _codigo(ticket_type_id=None)
    assert validar_codigo_vigente(codigo, tipo, 0, AHORA) is True


def test_codigo_vigente_sin_restricciones_es_valido() -> None:
    tipo = _tipo()
    codigo = _codigo()
    assert validar_codigo_vigente(codigo, tipo, 0, AHORA) is True
