"""Catálogo de modelos en vivo y prueba de conexión, ya con contexto.

Encima de `descubrimiento.py` (que solo habla HTTP) y de `cache_modelos.py`
(que solo guarda), esto es lo que decide **con qué clave** se llama y **qué
pasa cuando falla**:

- `modelos_de_proveedor` sirve el desplegable de los dos paneles. Usa la
  credencial que ya resuelve `service.resolver_config_efectiva` —la propia de
  la organización si tiene override, la de plataforma si hereda— y **nunca**
  la de otra organización: esa regla la impone esa función, que es la misma
  que aplica la llamada de generación, así que no se puede reimplementar aquí
  con otro criterio.
- `probar_conexion` sirve el botón «Probar conexión». Ahí la clave llega en el
  cuerpo de la petición porque el caso que importa es justo el contrario: una
  clave recién escrita que **todavía no está guardada**. Por eso no basta con
  `resolver_config_efectiva`.

**Degradar, no vaciar.** Si la llamada en vivo falla por lo que sea (sin
clave, clave rechazada, proveedor caído, respuesta ilegible), el desplegable
recibe el catálogo estático de `proveedores.py` con `en_vivo=false` y el
motivo. Una pantalla vacía sería peor que la lista que ya funcionaba.

**La caché no se aplica a la prueba de conexión**: su propósito es
precisamente comprobar la credencial de ahora mismo.

**La clave nunca sale de aquí.** Se descifra en memoria justo para la llamada
saliente y no viaja ni a la respuesta, ni a la caché, ni a los logs.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai_gateway import cache_modelos, descubrimiento, service
from app.modules.ai_gateway import proveedores as catalogo
from app.modules.ai_gateway.crypto import descifrar_clave
from app.modules.ai_gateway.descubrimiento import ListadoNoDisponible
from app.modules.ai_gateway.errores import (
    CredencialIlegible,
    ProveedorDesconocido,
)
from app.modules.ai_gateway.proveedores import Modelo
from app.modules.ai_gateway.schemas import (
    ModeloDelCatalogoOut,
    ModelosDelProveedorOut,
    PruebaDeConexionOut,
)


@dataclass(frozen=True, slots=True)
class _Credencial:
    """Con qué se llama al proveedor, y bajo qué ámbito se cachea."""

    api_key: str | None
    api_base: str | None
    #: `None` = la organización hereda, así que comparte la entrada de caché
    #: de plataforma con todas las demás que heredan.
    ambito: uuid.UUID | None


def _exigir_proveedor(provider: str) -> catalogo.Proveedor:
    entrada = catalogo.obtener(provider)
    if entrada is None or descubrimiento.adaptador(provider) is None:
        raise ProveedorDesconocido(f"El proveedor «{provider}» no existe en el catálogo.")
    return entrada


def _modelos_estaticos(provider: str) -> list[Modelo]:
    entrada = catalogo.obtener(provider)
    return list(entrada.modelos) if entrada is not None else []


def _salida(modelos: list[Modelo]) -> list[ModeloDelCatalogoOut]:
    return [
        ModeloDelCatalogoOut(clave=modelo.clave, etiqueta=modelo.etiqueta, vision=modelo.vision)
        for modelo in modelos
    ]


async def _credencial_para(
    session: AsyncSession, organization_id: uuid.UUID, provider: str
) -> _Credencial:
    """La clave utilizable para este proveedor, o ninguna.

    Solo sirve si la configuración efectiva **es de ese mismo proveedor**: una
    clave de OpenAI no lista los modelos de Anthropic, y mandarla lo único que
    conseguiría es exponerla a un tercero. Cuando no coincide se devuelve sin
    clave, y el listado saldrá del catálogo estático (salvo en OpenRouter, que
    lo publica sin autenticar).
    """
    config = await service.resolver_config_efectiva(session, organization_id)
    ambito = organization_id if config.origen == "propia" else None

    if config.provider != provider or config.api_key_encrypted is None:
        return _Credencial(api_key=None, api_base=None, ambito=ambito)

    return _Credencial(
        api_key=descifrar_clave(config.api_key_encrypted),
        api_base=config.api_base,
        ambito=ambito,
    )


async def modelos_de_proveedor(
    session: AsyncSession, organization_id: uuid.UUID, provider: str
) -> ModelosDelProveedorOut:
    """El listado del desplegable: en vivo si se puede, estático si no."""
    _exigir_proveedor(provider)
    credencial = await _credencial_para(session, organization_id, provider)

    cacheados = await cache_modelos.leer(credencial.ambito, provider)
    if cacheados is not None:
        return ModelosDelProveedorOut(
            proveedor=provider, en_vivo=True, motivo=None, modelos=_salida(cacheados)
        )

    try:
        modelos = await descubrimiento.listar_modelos(
            provider, api_key=credencial.api_key, api_base=credencial.api_base
        )
    except CredencialIlegible:
        # La clave guardada no descifra: es un estado de la instalación, no un
        # fallo del proveedor, y tiene su propio aviso en el panel.
        raise
    except ListadoNoDisponible as fallo:
        return ModelosDelProveedorOut(
            proveedor=provider,
            en_vivo=False,
            motivo=fallo.motivo,
            modelos=_salida(_modelos_estaticos(provider)),
        )

    await cache_modelos.guardar(credencial.ambito, provider, modelos)
    return ModelosDelProveedorOut(
        proveedor=provider, en_vivo=True, motivo=None, modelos=_salida(modelos)
    )


async def probar_conexion(
    provider: str, *, api_key: str, api_base: str | None
) -> PruebaDeConexionOut:
    """Comprueba una credencial **sin gastar cuota de generación**.

    El listado de modelos es la llamada autenticada más barata que ofrecen los
    siete proveedores: si responde 200 con al menos un modelo, la credencial
    sirve. Una llamada de generación real costaría dinero y contaminaría el
    histórico de uso con una llamada que nadie pidió.

    El resultado incluye los modelos encontrados: el panel los usa para
    rellenar el desplegable con la clave recién escrita, que es la única forma
    de verlos antes de guardarla.
    """
    _exigir_proveedor(provider)

    try:
        modelos = await descubrimiento.listar_modelos(provider, api_key=api_key, api_base=api_base)
    except ListadoNoDisponible as fallo:
        return PruebaDeConexionOut(ok=False, motivo=fallo.motivo, modelos=[])

    return PruebaDeConexionOut(ok=True, motivo=None, modelos=_salida(modelos))
