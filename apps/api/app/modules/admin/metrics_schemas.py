"""Esquemas del escritorio de la plataforma.

**Este fichero es un allowlist, y esa es su razón de ser.** El endpoint que los
sirve corre con el motor de mantenimiento (`BYPASSRLS`), así que ve todas las
organizaciones y todo lo que hay dentro. La promesa del producto —que el
administrador de la instalación **no ve las cifras de nadie**— no la protege
ningún mecanismo automático: la protege que estos esquemas no tengan ningún campo
donde quepan importes.

Un `sum(event_payments.amount_cents)` añadido más tarde compilaría, pasaría el
test estático que vigila dónde se usa el motor, y filtraría economía de terceros.
Por eso hay además un test que recorre estos modelos buscando claves monetarias:
añadir una aquí falla en CI, y esa es la red.

Si algún día el administrador necesita ver importes, es que la decisión de
producto cambió — y entonces se cambia aquí y en su test, a conciencia, no por
descuido.
"""

from __future__ import annotations

from pydantic import BaseModel


class SaludDeLaInstalacionOut(BaseModel):
    """Estado de las dependencias críticas, tal como lo da `GET /health`."""

    database: str
    storage: str
    redis: str


class CifrasDeLaInstalacionOut(BaseModel):
    """Los totales de la instalación entera."""

    organizaciones_activas: int
    organizaciones_totales: int
    eventos_totales: int
    eventos_publicados: int
    usuarios: int
    miembros: int


class ActividadDeOrganizacionOut(BaseModel):
    """Qué hace una organización, sin ningún importe.

    Las cuatro marcas de tiempo responden a preguntas distintas y por eso van
    separadas, no fundidas en un «última actividad»: una cuenta que crea eventos
    pero no recibe inscripciones está rota, y una que recibe inscripciones sin
    accesos nuevos puede estar abandonada.

    `evento_mas_reciente` es `updated_at` («última vez que se tocó un evento») y
    `ultimo_evento_creado` es `created_at` («último dado de alta»): editar un
    evento existente es trabajar, y con una sola marca se leería como parada.
    """

    id: str
    name: str
    slug: str
    is_active: bool
    eventos: int
    eventos_publicados: int
    inscripciones: int
    miembros: int
    #: `None` cuando no consta, que no es lo mismo que «hace mucho».
    evento_mas_reciente: str | None
    ultimo_evento_creado: str | None
    ultima_inscripcion: str | None
    ultimo_acceso: str | None
    stripe_conectada: bool
    #: Banderas de «no arranca»: convierten cuatro datos sueltos en una alerta.
    tiene_stripe_pendiente_con_eventos_de_pago: bool
    publicados_sin_inscripciones: bool


class MetricasDePlataformaOut(BaseModel):
    """Todo lo que necesita el escritorio de plataforma en una llamada."""

    salud: SaludDeLaInstalacionOut
    cifras: CifrasDeLaInstalacionOut
    organizaciones: list[ActividadDeOrganizacionOut]
