"""Lo que devuelven las herramientas MCP: una lista cerrada de campos.

No se reutilizan los schemas de la web a propósito: los del panel llevan
correos de miembros y participantes (`events/schemas.py`) e importes de
patrocinio, y todo lo que se devuelve aquí acaba en el historial de un
asistente de terceros. Un test serializa cada respuesta y falla si aparece un
correo o un teléfono.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class EventoResumen(BaseModel):
    id: str
    slug: str
    titulo: str
    estado: str
    visibilidad: str
    inicio: datetime
    fin: datetime
    formato: str
    lugar: str | None
    ciudad: str | None
    aforo: int | None
    modo_inscripcion: str
    enlace_panel: str


class Sede(BaseModel):
    id: str
    nombre: str
    direccion: str | None


class Sesion(BaseModel):
    id: str
    titulo: str
    tipo: str
    inicio: datetime
    fin: datetime
    sala: str | None
    sede_id: str | None


class Patrocinador(BaseModel):
    id: str
    nombre: str
    nivel: str | None
    web: str | None
    tipo_aportacion: str


class EventoDetalle(EventoResumen):
    resumen: str | None
    descripcion: str | None
    zona_horaria: str
    enlace_publico: str
    motivo_cancelacion: str | None
    sedes: list[Sede]
    sesiones: list[Sesion]
    patrocinadores: list[Patrocinador]


class CifrasDeInscripcion(BaseModel):
    """Solo cifras: ninguna herramienta devuelve datos de asistentes."""

    evento_id: str
    confirmadas: int
    pendientes_de_aprobar: int
    pendientes_de_verificar: int
    pendientes_de_pago: int
    en_lista_de_espera: int
    canceladas: int
    rechazadas: int
    plazas_reservadas: int
    aforo: int | None
    plazas_libres: int | None
