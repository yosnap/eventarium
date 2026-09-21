"""Catálogo cerrado de servicios conmutables de la instalación.

Separado de `proveedores.py` porque es otro dominio: qué funciones de la
plataforma se pueden apagar, no qué proveedor de IA se usa. El estado vive en
base de datos (`platform_services` / `organization_services`); la **lista** de
claves válidas vive aquí, para que un `service_key` inventado se rechace con
un 422 y no con un error de integridad (V-10).

Semántica del interruptor (V-7, binaria, nunca tri-estado):

    activo = global_enabled AND NOT (la organización lo tiene forzado a off)

Un servicio apagado globalmente **no** se puede reactivar por organización, y
el override por organización lo escribe **solo el admin** (V-8): el
organizador no tiene ningún endpoint de servicios.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Clave del servicio de IA. La usan la pasarela y sus consumidores.
SERVICIO_IA = "ai"

#: Longitud máxima de `service_key` en base de datos.
LONGITUD_SERVICE_KEY = 40


@dataclass(frozen=True, slots=True)
class Servicio:
    clave: str
    etiqueta: str
    descripcion: str


SERVICIOS: dict[str, Servicio] = {
    SERVICIO_IA: Servicio(
        clave=SERVICIO_IA,
        etiqueta="Pasarela de IA",
        descripcion=(
            "Permite que las funciones que usan IA (OCR de justificantes, y las que "
            "se añadan) llamen al proveedor configurado."
        ),
    ),
}

#: Claves válidas, en el orden del catálogo.
CLAVES_DE_SERVICIO: tuple[str, ...] = tuple(SERVICIOS)


def existe(service_key: str) -> bool:
    return service_key in SERVICIOS
