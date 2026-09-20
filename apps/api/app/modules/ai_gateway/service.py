"""Reglas de la configuración de IA: validación, resolución y guardado.

**Una sola** función de resolución (`resolver_config_efectiva`) para todos
los caminos —el `GET` del organizador, el `GET` del admin y, en la fase 2,
`completar`— para que no pueda haber dos lecturas con precedencias
distintas (riesgo S3-1).

Precedencia, todo-o-nada **por fila** (V-5): si la organización tiene fila de
override, se usa **entera** (su proveedor, su modelo, su `api_base` y su
clave). Nunca se mezcla el `api_base` de una con la clave de la otra: sería
exfiltrar la clave compartida de plataforma a un endpoint del organizador.

Servicios (V-7): `activo = global_enabled AND NOT override_off`. Un servicio
apagado globalmente no se reactiva por organización.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.ai_gateway import cache_modelos, repository, servicios
from app.modules.ai_gateway import proveedores as catalogo
from app.modules.ai_gateway.crypto import cifrar_clave, pista_de_clave
from app.modules.ai_gateway.errores import (
    ApiBaseNoPermitido,
    ApiBaseRequerido,
    ClaveRequerida,
    LimitePorEncimaDelTecho,
    ModeloDesconocido,
    ProveedorDesconocido,
    ProveedorRequerido,
    ServicioDesconocido,
)
from app.modules.ai_gateway.models import OrganizationAiSettings, PlatformAiSettings
from app.modules.ai_gateway.schemas import (
    AiUsageErrorOut,
    AiUsageOut,
    AiUsageRecordOut,
    ModeloDelCatalogoOut,
    OrganizationAiSettingsOut,
    OrganizationAiSettingsUpdate,
    OrganizationServiceOut,
    OrigenDeConfig,
    PlatformAiSettingsOut,
    PlatformAiSettingsUpdate,
    PlatformAiUsageOut,
    PlatformAiUsageRecordOut,
    ProveedorDelCatalogoOut,
    ServiceOut,
    ServiceToggle,
)
from app.modules.ai_gateway.validacion import validar_api_base


@dataclass(frozen=True, slots=True)
class ConfigEfectiva:
    """Qué configuración usa de verdad una organización, y de dónde sale.

    `api_key_encrypted` sigue **cifrada**: ninguna función de esta fase la
    descifra, y el `GET` solo expone `has_key` y la pista.
    """

    origen: OrigenDeConfig
    provider: str | None
    default_model: str | None
    #: Base URL efectiva (la del catálogo en los proveedores de base fija).
    api_base: str | None
    api_base_editable: bool
    api_key_encrypted: str | None
    #: Pista de la clave **propia** de la organización. `None` si hereda
    #: (V-11: la pista de la clave de plataforma no se enseña a los tenants).
    api_key_hint: str | None
    monthly_limit_usd: Decimal | None
    monthly_ceiling_usd: Decimal | None
    limite_efectivo_usd: Decimal | None
    updated_at: datetime | None

    @property
    def usable(self) -> bool:
        return self.origen != "sin_configuracion"


def limite_efectivo(
    limite_de_organizacion: Decimal | None, techo_de_plataforma: Decimal | None
) -> Decimal | None:
    """El límite que manda, con la semántica explícita del `NULL` (V-6).

    | límite organización | techo plataforma | efectivo |
    |---|---|---|
    | `NULL` | `NULL` | sin límite (`None`) |
    | valor | `NULL` | el de la organización |
    | `NULL` | valor | el techo |
    | valor | valor | el menor de los dos |

    No se delega en `min()` (revienta con `None`) ni en `LEAST` de SQL (que
    ignora los `NULL` y devolvería el valor en vez de «sin límite»).
    """
    if limite_de_organizacion is None:
        return techo_de_plataforma
    if techo_de_plataforma is None:
        return limite_de_organizacion
    return min(limite_de_organizacion, techo_de_plataforma)


def _plataforma_tiene_credencial(fila: PlatformAiSettings | None) -> bool:
    return (
        fila is not None
        and fila.provider is not None
        and fila.default_model is not None
        and fila.api_key_encrypted is not None
    )


async def resolver_config_efectiva(
    session: AsyncSession, organization_id: uuid.UUID
) -> ConfigEfectiva:
    """La configuración que usa una organización: la suya o la heredada.

    Lee las dos tablas en la **misma** sesión (la de plataforma tiene
    `SELECT` concedido a `app_user`), así que funciona igual desde una
    petición HTTP del organizador y desde el worker (V-3/V-4).
    """
    propia = await repository.get_organization_settings(session, organization_id)
    plataforma = await repository.get_platform_settings(session)
    techo = plataforma.monthly_ceiling_usd if plataforma is not None else None

    if propia is not None:
        proveedor = catalogo.obtener(propia.provider)
        return ConfigEfectiva(
            origen="propia",
            provider=propia.provider,
            default_model=propia.default_model,
            api_base=catalogo.api_base_efectivo(propia.provider, propia.api_base),
            api_base_editable=proveedor.api_base_editable if proveedor else False,
            api_key_encrypted=propia.api_key_encrypted,
            api_key_hint=propia.api_key_hint,
            monthly_limit_usd=propia.monthly_limit_usd,
            monthly_ceiling_usd=techo,
            limite_efectivo_usd=limite_efectivo(propia.monthly_limit_usd, techo),
            updated_at=propia.updated_at,
        )

    if plataforma is not None and _plataforma_tiene_credencial(plataforma):
        clave = plataforma.provider or ""
        proveedor = catalogo.obtener(clave)
        return ConfigEfectiva(
            origen="heredada",
            provider=plataforma.provider,
            default_model=plataforma.default_model,
            api_base=catalogo.api_base_efectivo(clave, plataforma.api_base),
            api_base_editable=proveedor.api_base_editable if proveedor else False,
            api_key_encrypted=plataforma.api_key_encrypted,
            api_key_hint=None,
            monthly_limit_usd=None,
            monthly_ceiling_usd=techo,
            limite_efectivo_usd=techo,
            updated_at=plataforma.updated_at,
        )

    # Sin override propio y sin credencial de plataforma: es el estado al que
    # degrada borrar la configuración de plataforma (V-12). Estado explícito,
    # no una excepción: el `GET` lo pinta y solo `completar` (fase 2) falla.
    return ConfigEfectiva(
        origen="sin_configuracion",
        provider=None,
        default_model=None,
        api_base=None,
        api_base_editable=False,
        api_key_encrypted=None,
        api_key_hint=None,
        monthly_limit_usd=None,
        monthly_ceiling_usd=techo,
        limite_efectivo_usd=techo,
        updated_at=None,
    )


def vista_de_plataforma(fila: PlatformAiSettings | None) -> PlatformAiSettingsOut:
    """Lo que ve el admin: estado, nunca la clave.

    `api_base` es el **efectivo** (el del catálogo en los proveedores de base
    fija, aunque la columna esté a `NULL`), y `api_base_editable` dice si el
    formulario debe pedirlo — solo `custom`.
    """
    if fila is None:
        return PlatformAiSettingsOut(
            provider=None,
            default_model=None,
            api_base=None,
            api_base_editable=False,
            has_key=False,
            api_key_hint=None,
            monthly_ceiling_usd=None,
            updated_at=None,
        )
    proveedor = catalogo.obtener(fila.provider) if fila.provider else None
    return PlatformAiSettingsOut(
        provider=fila.provider,
        default_model=fila.default_model,
        api_base=catalogo.api_base_efectivo(fila.provider or "", fila.api_base),
        api_base_editable=proveedor.api_base_editable if proveedor else False,
        has_key=fila.api_key_encrypted is not None,
        api_key_hint=fila.api_key_hint,
        monthly_ceiling_usd=fila.monthly_ceiling_usd,
        updated_at=fila.updated_at,
    )


async def vista_de_organizacion(
    session: AsyncSession, organization_id: uuid.UUID
) -> OrganizationAiSettingsOut:
    """Lo que ve el organizador: la configuración efectiva y su estado.

    Pasa por `resolver_config_efectiva`, la misma función que usará
    `completar` en la fase 2, para que el panel y la llamada real no puedan
    discrepar.
    """
    config = await resolver_config_efectiva(session, organization_id)
    activo = await servicio_activo(session, organization_id, servicios.SERVICIO_IA)
    return OrganizationAiSettingsOut(
        origen=config.origen,
        provider=config.provider,
        default_model=config.default_model,
        api_base=config.api_base,
        api_base_editable=config.api_base_editable,
        has_key=config.api_key_encrypted is not None,
        api_key_hint=config.api_key_hint,
        monthly_limit_usd=config.monthly_limit_usd,
        monthly_ceiling_usd=config.monthly_ceiling_usd,
        limite_efectivo_usd=config.limite_efectivo_usd,
        servicio_ia_activo=activo,
        updated_at=config.updated_at,
    )


async def vista_de_uso(
    session: AsyncSession, organization_id: uuid.UUID, *, ultimos: int = 20, errores_: int = 10
) -> AiUsageOut:
    """Gasto del periodo, últimas llamadas y últimos `error_code`.

    El límite que se devuelve sale de `resolver_config_efectiva`, igual que
    el del `GET` de configuración y el que aplica `completar`: si el panel
    enseñara un límite calculado aparte, podría contradecir al que de verdad
    corta las llamadas.
    """
    config = await resolver_config_efectiva(session, organization_id)
    periodo = repository.periodo_actual()
    resumen = await repository.resumen_del_periodo(session, organization_id, periodo)
    filas = await repository.ultimos_usos(session, organization_id, limite=ultimos)
    fallos = await repository.ultimos_errores(session, organization_id, limite=errores_)
    activo = await servicio_activo(session, organization_id, servicios.SERVICIO_IA)
    return AiUsageOut(
        periodo=periodo,
        llamadas=resumen.llamadas,
        llamadas_fallidas=resumen.llamadas_fallidas,
        gasto_usd=resumen.gasto_usd,
        gasto_auditable=resumen.gasto_auditable,
        input_tokens=resumen.input_tokens,
        output_tokens=resumen.output_tokens,
        limite_efectivo_usd=config.limite_efectivo_usd,
        servicio_ia_activo=activo,
        ultimos=[
            AiUsageRecordOut(
                id=fila.id,
                use_case=fila.use_case,
                provider=fila.provider,
                model=fila.model,
                status=fila.status,
                input_tokens=fila.input_tokens,
                output_tokens=fila.output_tokens,
                cost_usd=fila.cost_usd,
                cost_auditable=fila.cost_auditable,
                error_code=fila.error_code,
                latency_ms=fila.latency_ms,
                created_at=fila.created_at,
            )
            for fila in filas
        ],
        ultimos_errores=[
            AiUsageErrorOut(
                error_code=fallo.error_code, veces=fallo.veces, ultima_vez=fallo.ultima_vez
            )
            for fallo in fallos
        ],
    )


def catalogo_de_proveedores() -> list[ProveedorDelCatalogoOut]:
    """El catálogo cerrado serializado, en el orden de `proveedores.py`.

    Lo consumen los dos paneles para poblar sus desplegables. No lleva nada
    sensible: claves y etiquetas de proveedores y modelos, las mismas que ya
    publica el `enum` de `provider` en el `openapi.json`.
    """
    return [
        ProveedorDelCatalogoOut(
            clave=proveedor.clave,
            etiqueta=proveedor.etiqueta,
            api_base_editable=proveedor.api_base_editable,
            api_base_fijo=proveedor.api_base_fijo,
            modelos_abiertos=proveedor.modelos_abiertos,
            coste_auditable=proveedor.coste_auditable,
            modelos=[
                ModeloDelCatalogoOut(
                    clave=modelo.clave, etiqueta=modelo.etiqueta, vision=modelo.vision
                )
                for modelo in proveedor.modelos
            ],
        )
        for proveedor in catalogo.PROVEEDORES.values()
    ]


async def vista_de_uso_de_plataforma(
    session: AsyncSession, *, ultimos: int = 20, errores_: int = 10
) -> PlatformAiUsageOut:
    """Gasto agregado de **toda** la instalación en el periodo actual.

    Solo la llama el router de `/admin`, con la sesión de mantenimiento: es
    la única consulta de uso que cruza organizaciones a propósito.
    """
    periodo = repository.periodo_actual()
    resumen = await repository.resumen_del_periodo(session, None, periodo)
    filas = await repository.ultimos_usos(session, None, limite=ultimos)
    fallos = await repository.ultimos_errores(session, None, limite=errores_)
    plataforma = await repository.get_platform_settings(session)
    return PlatformAiUsageOut(
        periodo=periodo,
        llamadas=resumen.llamadas,
        llamadas_fallidas=resumen.llamadas_fallidas,
        gasto_usd=resumen.gasto_usd,
        gasto_auditable=resumen.gasto_auditable,
        input_tokens=resumen.input_tokens,
        output_tokens=resumen.output_tokens,
        monthly_ceiling_usd=plataforma.monthly_ceiling_usd if plataforma else None,
        ultimos=[
            PlatformAiUsageRecordOut(
                id=fila.id,
                organization_id=fila.organization_id,
                use_case=fila.use_case,
                provider=fila.provider,
                model=fila.model,
                status=fila.status,
                input_tokens=fila.input_tokens,
                output_tokens=fila.output_tokens,
                cost_usd=fila.cost_usd,
                cost_auditable=fila.cost_auditable,
                error_code=fila.error_code,
                latency_ms=fila.latency_ms,
                created_at=fila.created_at,
            )
            for fila in filas
        ],
        ultimos_errores=[
            AiUsageErrorOut(
                error_code=fallo.error_code, veces=fallo.veces, ultima_vez=fallo.ultima_vez
            )
            for fallo in fallos
        ],
    )


def _proveedor_del_catalogo(clave: str) -> catalogo.Proveedor:
    proveedor = catalogo.obtener(clave)
    if proveedor is None:
        raise ProveedorDesconocido(
            f"«{clave}» no es un proveedor de IA admitido.",
            extra={"proveedores": list(catalogo.CLAVES_DE_PROVEEDOR)},
        )
    return proveedor


def _validar_modelo(proveedor: catalogo.Proveedor, modelo: str) -> None:
    if not proveedor.acepta_modelo(modelo):
        raise ModeloDesconocido(
            f"«{modelo}» no es un modelo admitido de {proveedor.etiqueta}.",
            extra={"modelos": [entrada.clave for entrada in proveedor.modelos]},
        )


def _api_base_a_guardar(
    proveedor: catalogo.Proveedor, api_base: str | None, *, enviado: bool
) -> str | None:
    """Qué se guarda en la columna `api_base`, y qué se rechaza.

    En los proveedores de base fija la columna queda a `NULL` y la URL sale
    del catálogo: si el proveedor cambia de base URL se cambia en un sitio,
    sin migrar filas. Aceptar un `api_base` de usuario ahí permitiría apuntar
    `nan_builders`/`cheaper_inference` a un host del atacante y quedarse con
    la clave que viaja en la cabecera — de ahí el 422.
    """
    if not proveedor.api_base_editable:
        if enviado and api_base is not None:
            raise ApiBaseNoPermitido(
                f"{proveedor.etiqueta} usa una dirección fija: no admite «api_base».",
                extra={"api_base_efectivo": proveedor.api_base_fijo},
            )
        return None

    if api_base is None:
        raise ApiBaseRequerido(
            f"{proveedor.etiqueta} necesita la dirección del endpoint («api_base»)."
        )
    return validar_api_base(api_base, es_produccion=get_settings().app_env == "production")


def _comprobar_coherencia(enviados: set[str], *, hay_credencial_previa: bool) -> None:
    """Reglas de todo-o-nada del `PUT` (V-5), iguales en los dos niveles."""
    if ("provider" in enviados or "api_base" in enviados) and "api_key" not in enviados:
        raise ClaveRequerida(
            "Cambiar el proveedor o su dirección exige enviar también la clave: "
            "la configuración se guarda entera, nunca a medias."
        )
    if "api_key" in enviados and not {"provider", "default_model"} <= enviados:
        raise ProveedorRequerido(
            "Enviar una clave exige enviar también «provider» y «default_model»."
        )
    if "default_model" in enviados and "api_key" not in enviados and not hay_credencial_previa:
        raise ClaveRequerida(
            "Todavía no hay ninguna clave guardada: envía «provider», «default_model» "
            "y «api_key» juntos."
        )


async def guardar_config_de_plataforma(
    session: AsyncSession, datos: PlatformAiSettingsUpdate
) -> PlatformAiSettings:
    """Aplica el `PUT` del admin sobre la fila única. Sesión de mantenimiento.

    Bajar el techo por debajo de límites de organización ya existentes **no**
    se bloquea: el efectivo es el mínimo, así que el techo manda igualmente
    (riesgo S3-5, decidido: documentar el comportamiento, no frenar al
    admin).
    """
    enviados = set(datos.model_fields_set)
    fila = await repository.get_or_create_platform_settings(session)
    _comprobar_coherencia(enviados, hay_credencial_previa=fila.api_key_encrypted is not None)

    if "api_key" in enviados:
        clave_texto = datos.provider or ""
        proveedor = _proveedor_del_catalogo(clave_texto)
        modelo = datos.default_model or ""
        _validar_modelo(proveedor, modelo)
        api_base = _api_base_a_guardar(proveedor, datos.api_base, enviado="api_base" in enviados)
        if datos.api_key is None:
            raise ClaveRequerida("La clave del proveedor no puede estar vacía.")
        en_claro = datos.api_key.get_secret_value()

        fila.provider = proveedor.clave
        fila.default_model = modelo
        fila.api_base = api_base
        fila.api_key_encrypted = cifrar_clave(en_claro)
        fila.api_key_hint = pista_de_clave(en_claro)
    elif "default_model" in enviados:
        # Cambiar solo el modelo, conservando proveedor y clave.
        if fila.provider is None:
            raise ProveedorRequerido(
                "Todavía no hay proveedor configurado: envía «provider», «default_model» "
                "y «api_key» juntos."
            )
        proveedor = _proveedor_del_catalogo(fila.provider)
        _validar_modelo(proveedor, datos.default_model or "")
        fila.default_model = datos.default_model

    if "monthly_ceiling_usd" in enviados:
        fila.monthly_ceiling_usd = datos.monthly_ceiling_usd

    await session.flush()
    # La credencial de plataforma la comparten todas las organizaciones que
    # heredan: su catálogo en vivo cacheado ya no corresponde a esta clave.
    await cache_modelos.invalidar_ambito(None)
    return fila


async def guardar_override_de_organizacion(
    session: AsyncSession, organization_id: uuid.UUID, datos: OrganizationAiSettingsUpdate
) -> OrganizationAiSettings:
    """Aplica el `PUT` del organizador. Sesión con RLS fijado (`DbDep`).

    Una fila de override sin clave no existe por construcción (V-5): crear
    el override exige proveedor, modelo y clave en la misma petición.
    """
    enviados = set(datos.model_fields_set)
    fila = await repository.get_organization_settings(session, organization_id)
    _comprobar_coherencia(enviados, hay_credencial_previa=fila is not None)

    if fila is None and "api_key" not in enviados:
        raise ClaveRequerida(
            "Esta organización todavía hereda la configuración de la plataforma: para "
            "sobrescribirla hay que enviar «provider», «default_model» y «api_key»."
        )

    plataforma = await repository.get_platform_settings(session)
    techo = plataforma.monthly_ceiling_usd if plataforma is not None else None
    if "monthly_limit_usd" in enviados:
        _comprobar_limite_bajo_el_techo(datos.monthly_limit_usd, techo)

    if "api_key" in enviados:
        proveedor = _proveedor_del_catalogo(datos.provider or "")
        modelo = datos.default_model or ""
        _validar_modelo(proveedor, modelo)
        api_base = _api_base_a_guardar(proveedor, datos.api_base, enviado="api_base" in enviados)
        if datos.api_key is None:
            raise ClaveRequerida("La clave del proveedor no puede estar vacía.")
        en_claro = datos.api_key.get_secret_value()
        cifrada = cifrar_clave(en_claro)

        if fila is None:
            fila = OrganizationAiSettings(
                organization_id=organization_id,
                provider=proveedor.clave,
                default_model=modelo,
                api_base=api_base,
                api_key_encrypted=cifrada,
                api_key_hint=pista_de_clave(en_claro),
            )
            session.add(fila)
        else:
            fila.provider = proveedor.clave
            fila.default_model = modelo
            fila.api_base = api_base
            fila.api_key_encrypted = cifrada
            fila.api_key_hint = pista_de_clave(en_claro)
    elif fila is not None and "default_model" in enviados:
        proveedor = _proveedor_del_catalogo(fila.provider)
        _validar_modelo(proveedor, datos.default_model or "")
        fila.default_model = datos.default_model or fila.default_model

    if fila is None:
        # Inalcanzable: sin fila previa, `ClaveRequerida` ya ha cortado
        # arriba. Se deja explícito en vez de un `assert` (prohibido en
        # código de aplicación) para que mypy vea el tipo estrecho.
        raise ClaveRequerida(
            "No hay configuración propia que actualizar: envía «provider», "
            "«default_model» y «api_key»."
        )
    if "monthly_limit_usd" in enviados:
        fila.monthly_limit_usd = datos.monthly_limit_usd

    await session.flush()
    await cache_modelos.invalidar_ambito(organization_id)
    return fila


def _comprobar_limite_bajo_el_techo(limite: Decimal | None, techo: Decimal | None) -> None:
    """422 si el organizador intenta elevar su límite por encima del techo.

    Con techo `NULL` (sin techo) no hay nada que superar: la tabla de V-6
    dice que el efectivo es entonces el límite de la organización.
    """
    if limite is None or techo is None:
        return
    if limite > techo:
        raise LimitePorEncimaDelTecho(
            "El límite de gasto no puede superar el techo de la plataforma.",
            extra={"techo_usd": str(techo), "limite_usd": str(limite)},
        )


async def borrar_override_de_organizacion(
    session: AsyncSession, organization_id: uuid.UUID
) -> bool:
    """Vuelve a heredar la configuración de plataforma."""
    borrada = await repository.delete_organization_settings(session, organization_id)
    # A partir de ahora la organización usa la clave de plataforma: lo que
    # tuviera cacheado bajo su propio ámbito es de una credencial que ya no
    # existe.
    await cache_modelos.invalidar_ambito(organization_id)
    return borrada


def _servicio_del_catalogo(service_key: str) -> servicios.Servicio:
    servicio = servicios.SERVICIOS.get(service_key)
    if servicio is None:
        raise ServicioDesconocido(
            f"«{service_key}» no es un servicio conmutable de la plataforma.",
            extra={"servicios": list(servicios.CLAVES_DE_SERVICIO)},
        )
    return servicio


async def estado_global_de_servicios(session: AsyncSession) -> list[ServiceOut]:
    """Los interruptores globales, en el orden del catálogo.

    El catálogo manda: un servicio sin fila todavía se muestra como activo
    (es el estado por defecto), y una fila de un servicio retirado del
    catálogo no se muestra.
    """
    filas = {fila.service_key: fila for fila in await repository.list_platform_services(session)}
    salida: list[ServiceOut] = []
    for clave, servicio in servicios.SERVICIOS.items():
        fila = filas.get(clave)
        salida.append(
            ServiceOut(
                service_key=clave,
                etiqueta=servicio.etiqueta,
                descripcion=servicio.descripcion,
                enabled=fila.enabled if fila is not None else True,
            )
        )
    return salida


async def aplicar_interruptores_globales(
    session: AsyncSession, cambios: list[ServiceToggle]
) -> list[ServiceOut]:
    for cambio in cambios:
        _servicio_del_catalogo(cambio.service_key)
        await repository.set_platform_service(session, cambio.service_key, enabled=cambio.enabled)
    return await estado_global_de_servicios(session)


async def estado_de_servicios_de_organizacion(
    session: AsyncSession, organization_id: uuid.UUID
) -> list[OrganizationServiceOut]:
    globales = {
        fila.service_key: fila.enabled for fila in await repository.list_platform_services(session)
    }
    forzados_off = {
        fila.service_key
        for fila in await repository.list_organization_service_overrides(session, organization_id)
    }
    salida: list[OrganizationServiceOut] = []
    for clave, servicio in servicios.SERVICIOS.items():
        global_enabled = globales.get(clave, True)
        overridden_off = clave in forzados_off
        salida.append(
            OrganizationServiceOut(
                service_key=clave,
                etiqueta=servicio.etiqueta,
                global_enabled=global_enabled,
                overridden_off=overridden_off,
                enabled=global_enabled and not overridden_off,
            )
        )
    return salida


async def aplicar_override_de_servicios(
    session: AsyncSession, organization_id: uuid.UUID, cambios: list[ServiceToggle]
) -> list[OrganizationServiceOut]:
    """Override por organización, que **solo** puede desactivar (V-7/V-8).

    `enabled=false` fuerza el apagado; `enabled=true` borra el override y
    vuelve a heredar — nunca enciende por encima de la decisión global.

    Antes de forzar el apagado se garantiza la fila global del servicio: un
    servicio del catálogo cuya fila no se sembró todavía (clave añadida en
    código sin migración que la siembre) haría reventar la FK de
    `organization_services.service_key` con un `IntegrityError` — un 500 en
    vez del 422 de dominio que exige el catálogo cerrado. Se siembra activa,
    que es el estado por defecto que ya asume la lectura.
    """
    for cambio in cambios:
        _servicio_del_catalogo(cambio.service_key)
        if cambio.enabled:
            await repository.clear_organization_service_override(
                session, organization_id, cambio.service_key
            )
        else:
            if await repository.get_platform_service(session, cambio.service_key) is None:
                await repository.set_platform_service(session, cambio.service_key, enabled=True)
            await repository.force_organization_service_off(
                session, organization_id, cambio.service_key
            )
    return await estado_de_servicios_de_organizacion(session, organization_id)


async def servicio_activo(
    session: AsyncSession, organization_id: uuid.UUID, service_key: str
) -> bool:
    """`activo = global_enabled AND NOT override_off`.

    Funciona con la sesión de la organización: `platform_services` tiene
    `SELECT` concedido a `app_user`.
    """
    global_ = await repository.get_platform_service(session, service_key)
    if global_ is not None and not global_.enabled:
        return False
    overrides = await repository.list_organization_service_overrides(session, organization_id)
    return not any(fila.service_key == service_key for fila in overrides)
