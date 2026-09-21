"""Caché del listado de modelos consultado en vivo a cada proveedor.

Sin caché, cada apertura del panel de configuración dispararía una llamada
saliente al proveedor por cada cambio del desplegable. El listado de modelos
de un proveedor cambia como mucho unas pocas veces al mes, así que casi todas
esas llamadas serían repetidas.

**Redis y no memoria de proceso** (mismo criterio que `ratelimit.py`): en
desarrollo la API corre con `--reload` y en producción con varios workers, así
que una caché en el proceso se invalidaría sola de forma impredecible y cada
worker llamaría al proveedor por su cuenta.

**Ámbito de la clave**: `(organización | plataforma, proveedor)`. Dos
organizaciones con clave propia distinta pueden ver catálogos distintos del
mismo proveedor (planes y modelos habilitados dependen de la cuenta), así que
compartir entrada filtraría el catálogo de una cuenta a otra. La entrada de
`plataforma` la comparten todas las organizaciones que heredan, que es
exactamente el caso en el que la clave también es la misma.

**Fail-open, a propósito**: si Redis no responde, esto devuelve «no hay nada
cacheado» y sigue adelante en vez de un 503. La caché es una optimización, no
un control de seguridad — lo que sí es fail-closed es el límite de peticiones
que protege estos endpoints, y ese sigue siendo `require_redis`.

**Nunca se cachea la clave del proveedor**, solo el listado de modelos que
devolvió: `clave`, `etiqueta` y la marca de visión.
"""

from __future__ import annotations

import json
import logging
import uuid

from app.core.redis_client import get_redis
from app.modules.ai_gateway.proveedores import PROVEEDORES, Modelo

logger = logging.getLogger(__name__)

#: 10 minutos. El catálogo de un proveedor cambia en días o semanas, no en
#: minutos, así que la ventana la marca el otro lado del compromiso: cuánto
#: tarda en aparecer en el desplegable un modelo recién habilitado en la
#: cuenta del proveedor. Diez minutos es corto para una persona que acaba de
#: cambiar su plan y quiere verlo reflejado, y largo para que un panel abierto
#: y recargado varias veces seguidas no llame al proveedor más de una vez.
TTL_SEGUNDOS = 600

#: Prefijo propio: `ratelimit:` y este no pueden colisionar.
_PREFIJO = "ai:modelos"


def clave_de_cache(organization_id: uuid.UUID | None, provider: str) -> str:
    """`None` = la entrada compartida de quien usa la clave de plataforma."""
    ambito = str(organization_id) if organization_id is not None else "plataforma"
    return f"{_PREFIJO}:{ambito}:{provider}"


async def leer(organization_id: uuid.UUID | None, provider: str) -> list[Modelo] | None:
    """Los modelos cacheados, o `None` si no hay entrada válida."""
    try:
        crudo = await get_redis().get(clave_de_cache(organization_id, provider))
    except Exception:
        # Sin `exc_info`: el error de Redis no lleva nada sensible, pero
        # tampoco aporta nada en un camino que degrada solo.
        logger.warning("No se ha podido leer la caché de modelos de IA de %s", provider)
        return None

    if not crudo:
        return None

    try:
        entradas = json.loads(crudo)
        return [
            Modelo(
                clave=str(entrada["clave"]),
                etiqueta=str(entrada["etiqueta"]),
                vision=bool(entrada["vision"]),
            )
            for entrada in entradas
        ]
    except (ValueError, TypeError, KeyError):
        # Entrada de un formato anterior o corrupta: se trata como ausencia.
        logger.warning("Entrada de caché de modelos de IA ilegible para %s", provider)
        return None


async def guardar(organization_id: uuid.UUID | None, provider: str, modelos: list[Modelo]) -> None:
    """Guarda el listado con el TTL del módulo. Nunca lanza."""
    carga = json.dumps(
        [
            {"clave": modelo.clave, "etiqueta": modelo.etiqueta, "vision": modelo.vision}
            for modelo in modelos
        ]
    )
    try:
        await get_redis().set(clave_de_cache(organization_id, provider), carga, ex=TTL_SEGUNDOS)
    except Exception:
        logger.warning("No se ha podido cachear el listado de modelos de IA de %s", provider)


async def invalidar_ambito(organization_id: uuid.UUID | None) -> None:
    """Borra las entradas de un ámbito entero, proveedor a proveedor.

    La llaman los tres caminos que cambian qué credencial se usa: guardar la
    configuración de plataforma, guardar el override de una organización y
    borrarlo. Una clave nueva puede dar acceso a un catálogo distinto del que
    se cacheó con la anterior, así que dejar la entrada viva enseñaría durante
    hasta diez minutos los modelos de la credencial anterior.

    Se borran las claves una a una y **sin `SCAN`**: el catálogo tiene siete
    proveedores, así que la lista de claves exactas es conocida, y recorrer el
    espacio de claves de Redis por patrón es caro y no es atómico.
    """
    claves = [clave_de_cache(organization_id, provider) for provider in PROVEEDORES]
    try:
        await get_redis().delete(*claves)
    except Exception:
        logger.warning("No se ha podido invalidar la caché de modelos de IA del ámbito")
