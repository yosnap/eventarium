"""Ámbitos que una persona puede conceder a una conexión MCP.

Cada ámbito exige un permiso de su rol: el permiso efectivo de una llamada es
la intersección de lo concedido y lo que su rol le deja hacer **hoy**, así que
una conexión nunca da más de lo que la persona puede hacer en la web.
"""

from __future__ import annotations

from enum import StrEnum

from app.core.permissions import Permission


class Ambito(StrEnum):
    EVENTOS_LEER = "eventos:leer"
    EVENTOS_EDITAR = "eventos:editar"
    EVENTOS_PUBLICAR = "eventos:publicar"
    EVENTOS_CANCELAR = "eventos:cancelar"
    PATROCINADORES_EDITAR = "patrocinadores:editar"
    INSCRIPCIONES_CIFRAS = "inscripciones:cifras"


PERMISO_REQUERIDO: dict[Ambito, Permission] = {
    Ambito.EVENTOS_LEER: Permission.EVENTS_READ,
    Ambito.EVENTOS_EDITAR: Permission.EVENTS_WRITE,
    Ambito.EVENTOS_PUBLICAR: Permission.EVENTS_WRITE,
    # Si el evento tiene cobros, cancelar exige además `payments:write`; se
    # comprueba en la propia herramienta, igual que en el panel.
    Ambito.EVENTOS_CANCELAR: Permission.EVENTS_WRITE,
    Ambito.PATROCINADORES_EDITAR: Permission.SPONSORS_WRITE,
    Ambito.INSCRIPCIONES_CIFRAS: Permission.REGISTRATIONS_READ,
}

# Lo que se marca por defecto al crear una conexión. `eventos:cancelar` nunca:
# reembolsa dinero y es lo primero que pediría una instrucción inyectada.
AMBITOS_POR_DEFECTO: tuple[Ambito, ...] = (Ambito.EVENTOS_LEER, Ambito.INSCRIPCIONES_CIFRAS)


def ambitos_efectivos(concedidos: list[str], permisos: set[Permission]) -> frozenset[Ambito]:
    """Ámbitos concedidos que el rol actual de la persona todavía respalda."""
    resultado: set[Ambito] = set()
    for valor in concedidos:
        try:
            ambito = Ambito(valor)
        except ValueError:
            continue
        if PERMISO_REQUERIDO[ambito] in permisos:
            resultado.add(ambito)
    return frozenset(resultado)
