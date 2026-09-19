"""Redacción de importes en la lectura del registro de auditoría.

El registro de auditoría guarda, en su columna `detail`, el detalle completo de
cada acción sensible — incluidos los importes de contabilidad (`amount_cents`,
`budgeted_cents`, `total_cents` y compañía). Guardarlos es correcto: la
auditoría debe poder reconstruir qué se hizo, y para eso hace falta el número.

Servirlos por la API es otra cosa. El administrador de la plataforma gobierna la
instalación, **no** el negocio de las organizaciones: la decisión de producto es
que no vea las cifras de nadie, y que si necesita verlas entre suplantando una
cuenta. Un endpoint que devolviera el `detail` en crudo rompía esa frontera sin
que nadie lo notara, porque el dato viajaba dentro de una estructura que no se
lee a simple vista (`{"antes": {...}, "despues": {"total_cents": ...}}`).

Por eso la redacción se aplica **al serializar la respuesta**, no al escribir:
la fila en base queda íntegra —el registro de auditoría conserva su valor
probatorio— y solo se recorta lo que sale por la API. Es una barrera de
servidor, no de interfaz: protege también a quien llame al endpoint a mano.

El nombre de la clave es lo único que se mira, y se recorta por **sufijo y por
nombre exacto**, no por coincidencia parcial: `amount_cents` se recorta,
`amount_verified` no existe hoy pero tampoco se tocaría. Se recorre el detalle en
profundidad porque las estructuras anidadas son el caso real (`antes`/`despues`
de una edición), no una hipótesis.
"""

from __future__ import annotations

from typing import Any

#: Sufijos que identifican un importe en céntimos o una cuantía económica.
#: `_cents` cubre `amount_cents`, `budgeted_cents`, `total_cents`,
#: `price_cents`, `discount_cents`, `contingency_fund_cents` y
#: `total_budgeted_cents`; las otras dos entradas existen ya en el detalle de
#: contabilidad (`amount_refunded`, `valoracion_cents`).
_SUFIJOS_MONETARIOS: tuple[str, ...] = ("_cents", "_refunded")

#: Nombres exactos que son económicos sin llevar sufijo reconocible.
#: `contingency_fund_percent` no es un importe, pero es un parámetro de cálculo
#: presupuestario: se recorta con los demás y se revisa si algún día se decide
#: que el admin sí debe conocerlo.
_CLAVES_MONETARIAS_EXACTAS: frozenset[str] = frozenset({"amount", "contingency_fund_percent"})

#: Marca que sustituye al valor recortado. No se omite la clave: dejar la clave
#: con un valor explícito permite distinguir «esta acción no tocaba dinero» de
#: «esta acción tocaba dinero y no se te muestra», que es información de
#: auditoría legítima.
REDACTADO = "[redactado]"


def _es_clave_monetaria(clave: str) -> bool:
    return clave in _CLAVES_MONETARIAS_EXACTAS or clave.endswith(_SUFIJOS_MONETARIOS)


def _redactar(valor: Any) -> Any:
    if isinstance(valor, dict):
        return {clave: _redactar_recursivo(clave, hijo) for clave, hijo in valor.items()}
    if isinstance(valor, list):
        return [_redactar(hijo) for hijo in valor]
    return valor


def _redactar_recursivo(clave: str, valor: Any) -> Any:
    if _es_clave_monetaria(clave):
        return REDACTADO
    return _redactar(valor)


def redactar_importes(detail: dict[str, Any]) -> dict[str, Any]:
    """Devuelve una copia del detalle con los importes sustituidos.

    No muta la entrada: la fila que se acaba de leer de la base conserva sus
    valores tal cual, por si el llamante los necesita para otra cosa.
    """
    return {clave: _redactar_recursivo(clave, valor) for clave, valor in detail.items()}
