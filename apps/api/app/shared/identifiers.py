"""Identificadores primarios.

Se usa UUID v7 en lugar de v4: incluye una marca temporal en los bits altos, así que
los identificadores nuevos se insertan al final del índice B-tree en vez de dispersos,
lo que evita la fragmentación de los índices en tablas que crecen mucho.
"""

from __future__ import annotations

import uuid

import uuid_utils


def new_uuid7() -> uuid.UUID:
    """Nuevo UUID v7 como `uuid.UUID` de la biblioteca estándar."""
    return uuid.UUID(str(uuid_utils.uuid7()))
