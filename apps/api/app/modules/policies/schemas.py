"""Schemas de las políticas y condiciones propias de cada organizador."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field

#: Tope por texto. Es una barrera contra abusos, no una regla de negocio: un
#: documento legal largo cabe de sobra y cambiarlo no toca el esquema.
LIMITE_CARACTERES = 50_000

TipoDePolitica = Literal["condiciones", "reembolsos", "privacidad", "otras"]
OrigenDePolitica = Literal["evento", "organizacion", "ninguno"]


class PolicyVersionOut(BaseModel):
    """Una versión concreta de un texto."""

    version_id: str
    kind: TipoDePolitica
    version: int
    content: str
    created_at: datetime


class OrganizationPolicyItem(BaseModel):
    """Texto por defecto de la organización para un tipo."""

    kind: TipoDePolitica
    #: `None` si nunca se escribió o está retirado.
    current: PolicyVersionOut | None
    #: Número de la última versión guardada, también si está retirada: el
    #: panel lo usa para distinguir «sin escribir» de «retirado».
    last_version: int | None


class EventPolicyItem(BaseModel):
    """Texto vigente de un evento para un tipo, y de dónde sale."""

    kind: TipoDePolitica
    origin: OrigenDePolitica
    #: El texto que se muestra y se acepta en este evento (`None` = ninguno).
    current: PolicyVersionOut | None
    #: El texto de la organización, para enseñarlo como «heredado» aunque el
    #: evento tenga uno propio.
    organization: PolicyVersionOut | None


class PolicyUpdate(BaseModel):
    """Guardar un texto nuevo.

    En la organización, `content` es obligatorio (`""` = retirar). En un
    evento, `None` = volver a heredar el de la organización.
    """

    content: Annotated[str, Field(max_length=LIMITE_CARACTERES)] | None
