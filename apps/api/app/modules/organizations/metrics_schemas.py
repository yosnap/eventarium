"""Esquemas del escritorio de la organización.

Una **vista de lectura**: no hay tabla propia. Todo sale de contar lo que la
organización ya tiene —eventos, inscripciones, pagos, contabilidad, miembros,
roles y patrocinadores—, y por eso vive aparte de `schemas.py` en vez de
mezclarse con los esquemas de escritura del branding y los miembros.

Dos reglas, las mismas que en las métricas de un evento:

- **Cada bloque lleva su permiso y se omite en el servidor** si falta, en vez de
  mandarse y esconderse en la interfaz.
- **Los importes van en su propio bloque**, para que omitirlos no deje huecos en
  los demás.
"""

from __future__ import annotations

from pydantic import BaseModel

#: Cuánto ocupa un evento, para la tabla del escritorio.
EstadoDeEvento = str


class EventoDelEscritorioOut(BaseModel):
    """Una fila de la tabla de eventos, con sus cifras ya contadas.

    Las cifras por evento se agregan en la misma consulta que la lista, no en una
    por fila: un organizador con veinte eventos no debe provocar veinte viajes a
    la base para pintar su escritorio.
    """

    id: str
    title: str
    slug: str
    status: str
    starts_at: str
    #: `None` cuando el evento no fija aforo.
    aforo: int | None
    #: `None` cuando quien mira no tiene `registrations:read`: se omite en la
    #: consulta, no se manda y se esconde.
    confirmadas: int | None
    #: Solicitudes esperando decisión: lo accionable de cada evento.
    por_aprobar: int | None
    #: `None` cuando quien mira no tiene permiso económico.
    ingresos_cents: int | None


class CifrasDeOrganizacionOut(BaseModel):
    """Los conteos de la organización entera."""

    eventos_por_estado: dict[str, int]
    inscripciones_por_estado: dict[str, int]
    #: Suma de aforos de los eventos que lo fijan, y plazas reservadas en ellos.
    reservadas: int
    aforo_total: int | None
    por_aprobar: int
    lista_de_espera: int


class EstructuraOut(BaseModel):
    """Cuántas personas y roles tiene la organización, y cuántos patrocinadores."""

    miembros: int
    roles: int
    patrocinadores: int


class DineroDeOrganizacionOut(BaseModel):
    """Los importes de la organización, sumados por moneda.

    Se agrupa por moneda en vez de dar un total único: una organización puede
    tener eventos en euros y en dólares, y sumarlos daría una cifra que no
    significa nada. El caso normal es una sola entrada.
    """

    por_moneda: dict[str, int]
    presupuesto_por_moneda: dict[str, int]
    ejecutado_por_moneda: dict[str, int]


class EstadoDeStripeOut(BaseModel):
    """Si la organización puede cobrar, que es lo que decide si vende entradas."""

    conectada: bool
    charges_enabled: bool
    payouts_enabled: bool
    details_submitted: bool


class MetricasDeOrganizacionOut(BaseModel):
    """Todo lo que necesita el escritorio de la organización en una llamada."""

    #: Solicitudes por aprobar en toda la organización: el dato más accionable.
    eventos_en_borrador: int
    eventos: list[EventoDelEscritorioOut]
    cifras: CifrasDeOrganizacionOut | None
    estructura: EstructuraOut
    dinero: DineroDeOrganizacionOut | None
    stripe: EstadoDeStripeOut
