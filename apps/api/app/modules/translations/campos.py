"""Qué se traduce: tipos de entidad, sus campos y las transiciones de estado.

`TIPOS` es el mismo conjunto cerrado que la restricción `entity_type` de la tabla.
"""

from __future__ import annotations

import hashlib
from typing import Final, Literal, get_args

TipoDeEntidad = Literal[
    "event",
    "session",
    "session_type",
    "venue",
    "ticket_type",
    "question",
    "sponsor_tier",
    "sponsor",
    "member_profile",
    "organization",
    "policy_version",
    "nearby_place",
    "tag",
]
TIPOS: Final[tuple[TipoDeEntidad, ...]] = get_args(TipoDeEntidad)

#: Campos traducibles de cada tipo. En `member_profile` son claves de
#: `organization_members.profile_data`; `tag` tiene campo abierto (la etiqueta
#: normalizada) y se valida aparte.
CAMPOS: Final[dict[TipoDeEntidad, frozenset[str]]] = {
    "event": frozenset({"title", "summary", "description", "location_name", "cancellation_reason"}),
    "session": frozenset({"title", "description", "room"}),
    "session_type": frozenset({"name", "description"}),
    "venue": frozenset({"name"}),
    "ticket_type": frozenset({"name", "description"}),
    "question": frozenset({"label"}),
    "sponsor_tier": frozenset({"name", "benefits"}),
    "sponsor": frozenset({"name", "contribution_description"}),
    "member_profile": frozenset({"bio", "titular", "curriculum"}),
    "organization": frozenset({"description"}),
    "policy_version": frozenset({"content"}),
    "nearby_place": frozenset({"name", "notes"}),
    "tag": frozenset(),
}

#: Tipos que no cuelgan de un evento: su traducción tiene `event_id` nulo. Las
#: versiones de políticas pueden ser de un evento o de toda la organización.
TIPOS_DE_ORGANIZACION: Final[frozenset[TipoDeEntidad]] = frozenset(
    {"member_profile", "organization", "tag", "session_type", "sponsor_tier"}
)

#: Tabla de cada tipo con fila propia. Un trigger en cada una borra las
#: traducciones de la fila en la misma transacción que la borra (migración
#: `0074`). `event` y `organization` no lo necesitan: la FK de
#: `content_translations` ya borra en cascada. `tag` no tiene tabla.
TABLAS: Final[dict[TipoDeEntidad, str]] = {
    "session": "event_sessions",
    "session_type": "session_types",
    "venue": "event_venues",
    "ticket_type": "event_ticket_types",
    "question": "event_registration_questions",
    "sponsor_tier": "sponsor_tiers",
    "sponsor": "sponsors",
    "member_profile": "organization_members",
    "policy_version": "organization_policy_versions",
    "nearby_place": "event_nearby_places",
}

Estado = Literal["pendiente", "en_curso", "al_dia", "error", "desactualizada"]
Origen = Literal["ia", "manual", "revisada"]

#: Transiciones permitidas. Cualquier estado pasa a `desactualizada` cuando cambia
#: el original; `error` vuelve a `en_curso` cuando vence su espera.
TRANSICIONES: Final[dict[Estado, frozenset[Estado]]] = {
    "pendiente": frozenset({"en_curso", "desactualizada"}),
    "en_curso": frozenset({"al_dia", "error", "desactualizada"}),
    "al_dia": frozenset({"desactualizada", "en_curso"}),
    "error": frozenset({"en_curso", "desactualizada"}),
    "desactualizada": frozenset({"en_curso", "al_dia"}),
}

#: Orígenes que la IA no puede sobrescribir.
ORIGENES_PROTEGIDOS: Final[frozenset[Origen]] = frozenset({"manual", "revisada"})


#: Las opciones de una pregunta se traducen una a una: `option:<valor original>`.
PREFIJO_OPCION: Final = "option:"


def campo_valido(tipo: TipoDeEntidad, campo: str) -> bool:
    """`campo` es traducible en `tipo`."""
    if tipo == "question" and campo.startswith(PREFIJO_OPCION):
        return len(campo) > len(PREFIJO_OPCION) and len(campo) <= 200
    if tipo == "tag":
        return 0 < len(campo) <= 200 and campo == campo.strip().lower()
    return campo in CAMPOS[tipo]


def puede_pasar(desde: Estado, hacia: Estado) -> bool:
    """La tabla de transiciones admite pasar de `desde` a `hacia`."""
    return hacia in TRANSICIONES[desde]


def huella(original: str) -> str:
    """Huella del texto original (SHA-256 en hexadecimal)."""
    return hashlib.sha256(original.encode("utf-8")).hexdigest()
