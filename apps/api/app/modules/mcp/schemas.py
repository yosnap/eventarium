"""Lo que devuelven las herramientas MCP: una lista cerrada de campos.

No se reutilizan los schemas de la web a propósito: los del panel llevan
correos de miembros y participantes (`events/schemas.py`) e importes de
patrocinio, y todo lo que se devuelve aquí acaba en el historial de un
asistente de terceros. Los tests del MCP comprueban que ninguna respuesta
lleva correos ni teléfonos.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


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
    # Slug de la categoría del catálogo (ver `listar_categorias`), si tiene.
    categoria: str | None = None
    etiquetas: list[str] = Field(default_factory=list)
    enlace_panel: str
    # Idioma en que está escrito el evento y, si se pidió otro con `idioma`, el
    # del título que se devuelve (el pedido si está traducido; si no, el original).
    idioma_original: str = "es-ES"
    idioma_servido: str | None = None


class EstadoDeTraduccion(BaseModel):
    evento_id: str
    idioma_original: str
    idioma: str
    # Textos del evento (y de su agenda, sedes, entradas, preguntas…) que hay que
    # traducir a `idioma`, y cuántos están ya al día.
    textos: int
    al_dia: int
    # Se ha puesto en la cola de traducción automática en esta llamada.
    en_cola: bool
    # La organización tiene su propia clave de IA: se puede traducir con IA.
    traduccion_automatica: bool


class Categoria(BaseModel):
    slug: str
    nombre: str


class SitioCercano(BaseModel):
    id: str
    # hotel, restaurant, bar, parking, transport, pharmacy u other.
    tipo: str
    # Solo con `tipo` other: el tipo con nombre libre.
    tipo_libre: str | None
    nombre: str
    direccion: str | None
    telefono: str | None
    web: str | None
    nota: str | None


class Sede(BaseModel):
    id: str
    nombre: str
    direccion: str | None
    # Solo en las respuestas de escritura: dónde revisar el cambio en el panel.
    enlace_panel: str | None = None


class TipoDeSesion(BaseModel):
    """Un tipo de sesión de la organización (ver `listar_tipos_de_sesion`)."""

    id: str
    nombre: str
    descripcion: str | None
    es_pausa: bool
    clave_base: str | None


class Sesion(BaseModel):
    id: str
    titulo: str
    # Nombre del tipo de la organización (p. ej. «Mesa redonda»).
    tipo: str
    inicio: datetime
    fin: datetime
    sala: str | None
    sede_id: str | None
    enlace_panel: str | None = None


class Portada(BaseModel):
    """Respuesta de `asignar_portada_evento`."""

    event_id: str
    portada_url: str
    enlace_panel: str | None = None


class Patrocinador(BaseModel):
    id: str
    nombre: str
    nivel: str | None
    web: str | None
    tipo_aportacion: str
    enlace_panel: str | None = None


class EventoDetalle(EventoResumen):
    resumen: str | None
    descripcion: str | None
    zona_horaria: str
    # Sin enlace si el evento es privado: no se abre por URL.
    enlace_publico: str | None
    # Recordatorio por correo a los inscritos: si se envía y cuántas horas antes.
    recordatorio: bool
    recordatorio_horas: int
    sitios_cercanos: list[SitioCercano] = []
    motivo_cancelacion: str | None
    # Con `idioma`: idiomas en que todo el evento está al día y cuántos textos se
    # devuelven en el original porque aún no están traducidos al pedido.
    idiomas_al_dia: list[str] = Field(default_factory=list)
    textos_sin_traducir: int = 0
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


class ConfirmacionDeCancelacion(BaseModel):
    """Primer paso de `cancelar_evento`: lo que implica, para confirmarlo con
    la persona. El importe es el total a devolver del propio evento, nunca de
    una persona concreta."""

    confirmacion_pendiente: bool = True
    inscripciones_afectadas: int
    pagos_a_reembolsar: int
    importe_a_reembolsar_cents: int
    moneda: str | None
    codigo_de_confirmacion: str
    aviso: str


class CancelacionHecha(BaseModel):
    cancelado: bool = True
    inscripciones_afectadas: int
    pagos_a_reembolsar: int
    enlace_panel: str
