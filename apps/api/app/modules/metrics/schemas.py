"""Esquemas de las métricas del escritorio de un evento.

Es una **vista de lectura**: no hay modelo propio ni tabla. Todo lo que devuelve
sale de contar lo que ya existe (inscripciones, entradas, pagos, contabilidad,
patrocinadores, agenda, ponentes), y por eso el módulo vive aparte en vez de
colgarse de uno de los módulos que consulta: no pertenece a ninguno.

Dos reglas de diseño, decididas en el PRD y verificadas contra el código:

- **Cada bloque lleva su permiso.** El escritorio junta datos de seis recursos
  distintos, y quien mira no tiene por qué poder verlos todos: un miembro con
  `events:read` y sin `registrations:read` no debe recibir conteos de
  inscripciones, aunque la pantalla sea la misma. Los bloques se **omiten en el
  servidor**, no se esconden en la interfaz.
- **Los importes solo existen si hay permiso económico.** El dinero va en su
  propio bloque, para que omitirlo no deje huecos en los demás.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

#: Estado de cada pieza del evento: si está lista, si le falta algo, o si no
#: aplica (una sección que el evento no usa no debe salir como un aviso).
EstadoDePieza = Literal["lista", "pendiente", "no_aplica"]


class EmbudoOut(BaseModel):
    """Los cuatro escalones del embudo de inscripción.

    `formulario` cuenta toda inscripción iniciada; `verificado`, `aprobado` y
    `emitido` son los hitos que la persona fue superando. Son **acumulativos y
    monótonos** salvo por las bajas posteriores (alguien puede haberse
    verificado y luego cancelar), así que la interfaz no debe dibujarlos como
    una cuenta atrás estricta.
    """

    formulario: int
    verificado: int
    aprobado: int
    emitido: int
    #: `True` cuando el evento no exige verificación de correo: entonces
    #: `verificado` es igual a `formulario` por construcción y la interfaz lo
    #: etiqueta como tal, en vez de pintar un 100 % que no ocurrió.
    sin_verificacion_exigida: bool


class OcupacionOut(BaseModel):
    """Cuánto del aforo está tomado.

    `reservadas` es lo que el propio sistema considera ocupado —no solo las
    confirmadas: también las promociones de lista de espera y los pagos dentro
    de su ventana—, porque es el número con el que decide si cabe una persona
    más. Pintar solo las confirmadas daría un aforo que no coincide con el que
    la aplicación aplica.
    """

    reservadas: int
    #: `None` cuando el evento no fija aforo: no es «0 plazas», es «sin límite».
    aforo: int | None


class PiezaOut(BaseModel):
    """Una de las piezas del evento, con su estado y cuánto tiene."""

    clave: str
    estado: EstadoDePieza
    cantidad: int


class CifrasOut(BaseModel):
    """Los conteos por estado de inscripción, y la lista de espera."""

    por_estado: dict[str, int]
    lista_de_espera: int
    #: Solicitudes esperando decisión. Es el dato más accionable del escritorio.
    por_aprobar: int
    #: Inscripciones confirmadas que además tienen entrada emitida y sin usar:
    #: las personas que aún no han entrado.
    sin_entrar: int


class DineroOut(BaseModel):
    """Los importes del evento.

    Va en su propio bloque y **solo se incluye con permiso económico**: así,
    omitirlo no deja huecos en el resto de la vista.
    """

    ingresos_cobrados_cents: int
    presupuesto_cents: int
    ejecutado_cents: int
    moneda: str


class MetricasDelEventoOut(BaseModel):
    """Todo lo que el escritorio de un evento necesita, en una sola llamada.

    Los bloques de permiso opcional (`dinero`) son `None` cuando quien pide no
    puede verlos. Los demás van siempre: si un miembro alcanza el evento, puede
    ver cómo va.
    """

    event_id: str
    embudo: EmbudoOut | None
    ocupacion: OcupacionOut | None
    cifras: CifrasOut | None
    piezas: list[PiezaOut]
    dinero: DineroOut | None
