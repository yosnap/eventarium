"""Endpoints de configuración de IA de la organización (nivel organizador).

Patrón self-scoped real (`/organizations/me/...`), igual que `/me/branding`:
la organización sale del token, nunca de la URL. El gate es
`require_org_owner` (rol `owner`), no un `Permission` del enum — el porqué
está en `core/deps.py`.

El nivel plataforma vive en `modules/admin/ai_router.py`: es el único módulo
autorizado a usar la sesión de mantenimiento, y `platform_ai_settings` solo
se escribe desde ahí.

Aquí **no** hay endpoints de servicios: el override por organización lo
escribe solo el admin (V-8). El organizador ve en su `GET` si el servicio
está activo, pero no puede encenderlo.

Sí vive aquí el catálogo de proveedores (`GET /ai/catalog`), en un router
aparte: es de lectura, no depende de ninguna organización y lo consumen por
igual los dos paneles de la fase 3.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, Response, status

from app.core.audit import registrar_auditoria
from app.core.database import maintenance_session
from app.core.deps import (
    CurrentUser,
    CurrentUserDep,
    DbDep,
    OrgOwnerDep,
    require_org_owner,
)
from app.core.ratelimit import (
    AI_MODELOS_EN_VIVO_POR_IP,
    AI_TEST_CONNECTION_POR_IP,
    limit_per_ip,
)
from app.modules.ai_gateway import catalogo_dinamico, service
from app.modules.ai_gateway.errores import ClaveRequerida
from app.modules.ai_gateway.schemas import (
    AiUsageOut,
    ModelosDelProveedorOut,
    OrganizationAiSettingsOut,
    OrganizationAiSettingsUpdate,
    ProveedorDelCatalogoOut,
    PruebaDeConexionIn,
    PruebaDeConexionOut,
)

router = APIRouter(prefix="/organizations", tags=["organizaciones"])

#: Catálogo de proveedores: lo necesitan **los dos** paneles (el del admin y
#: el del organizador), así que no puede colgar ni de `/admin` ni de
#: `/organizations/me` —cada uno de esos gates dejaría fuera al otro panel—.
#: Router propio: el catálogo estático basta con estar autenticado; los dos
#: endpoints que salen a Internet con una clave exigen `require_owner_o_plataforma`.
catalogo_router = APIRouter(prefix="/ai", tags=["ia"])


async def require_owner_o_plataforma(usuario: CurrentUserDep, session: DbDep) -> CurrentUser:
    """Propietario de la organización activa **o** personal de plataforma.

    Los dos endpoints que salen a Internet con una clave (`/catalog/{p}/models`
    y `/test-connection`) los usan dos formularios distintos: el de la
    organización, gateado con `require_org_owner`, y el de plataforma, gateado
    con `is_superadmin`. Estar autenticado no basta: con `provider=custom`
    cualquier miembro podría hacer que la instalación emitiera peticiones
    salientes a un host elegido por él, con la cabecera `Authorization` que
    quisiera y viendo la respuesta, además de gastar la clave ya guardada de
    su organización sin ser su propietario.

    El nivel de confianza es el mismo que ya tiene un `owner`, que puede
    guardar un `api_base` arbitrario por el `PUT` de sus ajustes; por eso
    `custom` no se reserva a plataforma.

    `is_superadmin` sale de `get_current_user`, que lo lee de `users` en cada
    petición: un token antiguo no conserva el privilegio si se revocó.
    """
    if usuario.is_superadmin:
        return usuario
    return await require_org_owner(usuario, session)


#: Gate de los endpoints de catálogo en vivo. Ver `require_owner_o_plataforma`.
OwnerOPlataformaDep = Annotated[CurrentUser, Depends(require_owner_o_plataforma)]


@catalogo_router.get(
    "/catalog",
    summary="Catálogo cerrado de proveedores y modelos de IA",
    description=(
        "Los proveedores válidos y, por cada uno, sus modelos con la marca de "
        "visión (`vision`), si su dirección la escribe quien configura "
        "(`api_base_editable`) y si su gasto es auditable. Es la **única** "
        "fuente del desplegable de los dos paneles: no hay una segunda lista en "
        "el cliente que pudiera quedarse desfasada.\n\n"
        "No lleva nada sensible —claves y etiquetas del catálogo, las mismas que "
        "ya publica el `enum` de `provider`—, así que basta con estar "
        "autenticado."
    ),
    response_model=list[ProveedorDelCatalogoOut],
)
async def get_ai_catalog(_: CurrentUserDep) -> list[ProveedorDelCatalogoOut]:
    return service.catalogo_de_proveedores()


@catalogo_router.get(
    "/catalog/{provider}/models",
    summary="Modelos de un proveedor, consultados en vivo",
    description=(
        "Pregunta al proveedor qué modelos tiene disponibles **ahora**, con la "
        "clave que ya usa esta organización (la suya si tiene configuración "
        "propia, la de la plataforma si hereda). La clave nunca viaja en la "
        "respuesta.\n\n"
        "Si la consulta no sale —no hay clave para ese proveedor, la rechaza, no "
        "responde o contesta algo ilegible— devuelve el catálogo conocido con "
        "`en_vivo: false` y el `motivo`, en vez de una lista vacía.\n\n"
        "El resultado se cachea unos minutos por organización y proveedor, así "
        "que abrir el panel varias veces no repite la llamada saliente.\n\n"
        "Solo lo puede pedir el propietario de la organización o el personal de "
        "plataforma: gasta la credencial guardada en una llamada saliente."
    ),
    response_model=ModelosDelProveedorOut,
    dependencies=[limit_per_ip("ai-modelos-en-vivo", AI_MODELOS_EN_VIVO_POR_IP)],
)
async def get_ai_provider_models(
    provider: str, usuario: OwnerOPlataformaDep, session: DbDep
) -> ModelosDelProveedorOut:
    return await catalogo_dinamico.modelos_de_proveedor(session, usuario.organization_id, provider)


@catalogo_router.post(
    "/test-connection",
    summary="Probar una clave de proveedor sin guardarla",
    description=(
        "Comprueba que la clave enviada sirve contra el proveedor indicado. Usa "
        "su listado de modelos, que es la llamada autenticada más barata: no "
        "consume cuota de generación ni deja rastro en el histórico de uso.\n\n"
        "La clave viaja en el cuerpo porque lo normal es probar la que acaba de "
        "escribirse en el formulario y todavía no está guardada. Es `writeOnly`: "
        "no se almacena, no se registra en ningún log y no vuelve en la "
        "respuesta. Se puede omitir para probar la clave YA guardada de este "
        "mismo nivel, si su proveedor coincide con el indicado.\n\n"
        "Responde siempre 200 con `ok`: un `false` con su `motivo` "
        "(`clave_rechazada`, `tiempo_agotado`, `proveedor_error`, "
        "`respuesta_inesperada`) es un resultado de la prueba, no un error de la "
        "petición. Sí da 422 lo que sí es entrada inválida: un proveedor fuera "
        "del catálogo, una dirección de endpoint no permitida, o ninguna clave "
        "escrita ni guardada que probar.\n\n"
        "Solo lo puede pedir el propietario de la organización o el personal de "
        "plataforma: provoca una llamada saliente con datos escritos por quien "
        "la pide."
    ),
    response_model=PruebaDeConexionOut,
    dependencies=[limit_per_ip("ai-test-connection", AI_TEST_CONNECTION_POR_IP)],
)
async def post_ai_test_connection(
    datos: PruebaDeConexionIn, usuario: OwnerOPlataformaDep, session: DbDep
) -> PruebaDeConexionOut:
    api_key = datos.api_key.get_secret_value() if datos.api_key is not None else None
    api_base = datos.api_base
    if api_key is None:
        credencial = await service.resolver_credencial_guardada_para_prueba(
            session,
            is_superadmin=usuario.is_superadmin,
            organization_id=usuario.organization_id,
            provider=datos.provider,
        )
        if credencial is None:
            raise ClaveRequerida(
                "Escribe la clave para probarla, o guarda una antes de probar sin escribirla."
            )
        api_key, api_base_guardada = credencial
        if api_base is None:
            api_base = api_base_guardada
    return await catalogo_dinamico.probar_conexion(
        datos.provider,
        api_key=api_key,
        api_base=api_base,
    )


async def _auditar(
    *,
    actor_user_id: uuid.UUID,
    organization_id: uuid.UUID,
    action: str,
    detail: dict[str, Any],
) -> None:
    """Auditoría de los cambios de credencial de la organización.

    Se encola como `BackgroundTask` —verificado: corre tras el `commit` real
    de la transacción de la petición, gracias al `scope="function"` con el que
    `core/deps.py` declara la sesión— y abre su propia sesión de
    mantenimiento, porque `audit_log`
    tiene `REVOKE ALL … FROM app_user`. Mismo patrón que
    `roles/service.py:_registrar_cambio_de_permisos`: la auditoría no puede
    sobrevivir a un rollback del cambio que describe.

    `detail` nunca lleva la clave, ni en claro ni cifrada, ni su pista: solo
    metadatos, igual que en el nivel plataforma.
    """
    async with maintenance_session() as auditoria:
        await registrar_auditoria(
            auditoria,
            actor_user_id=actor_user_id,
            organization_id=organization_id,
            action=action,
            entity_type="organization_ai_settings",
            entity_id=str(organization_id),
            detail=detail,
        )


@router.get(
    "/me/ai-settings",
    summary="Configuración de IA de la organización (propia o heredada)",
    description=(
        "Devuelve la configuración que usa de verdad esta organización: la suya "
        "si la ha guardado, o la heredada de la plataforma. **Nunca** devuelve la "
        "clave: solo `has_key`, la pista de sus últimos caracteres y la fecha. La "
        "pista solo aparece cuando la clave es propia — la de plataforma es "
        "compartida por toda la instalación y sus últimos caracteres no se "
        "enseñan a ningún tenant."
    ),
    response_model=OrganizationAiSettingsOut,
)
async def get_my_ai_settings(usuario: OrgOwnerDep, session: DbDep) -> OrganizationAiSettingsOut:
    return await service.vista_de_organizacion(session, usuario.organization_id)


@router.get(
    "/me/ai-usage",
    summary="Gasto y actividad de IA de la organización en el periodo actual",
    description=(
        "Resumen del mes en curso (llamadas, tokens y gasto en USD frente al "
        "límite efectivo), las últimas llamadas y los últimos códigos de error. "
        "El gasto suma las llamadas liquidadas y las reservas en vuelo, nunca las "
        "fallidas. `gasto_auditable` es `false` cuando alguna llamada del periodo "
        "lleva un importe solo estimado, porque su modelo no está en el mapa de "
        "precios del proveedor: ese total es orientativo."
    ),
    response_model=AiUsageOut,
)
async def get_my_ai_usage(usuario: OrgOwnerDep, session: DbDep) -> AiUsageOut:
    return await service.vista_de_uso(session, usuario.organization_id)


@router.put(
    "/me/ai-settings",
    summary="Sobrescribir la configuración de IA de la organización",
    description=(
        "Guarda la configuración propia (proveedor, modelo, clave y, en un "
        "proveedor personalizado, su dirección) y el límite de gasto propio, que "
        "no puede superar el techo de la plataforma (422). La configuración se "
        "guarda **entera**: enviar proveedor o dirección exige enviar también la "
        "clave, y enviar la clave exige proveedor y modelo."
    ),
    response_model=OrganizationAiSettingsOut,
)
async def update_my_ai_settings(
    datos: OrganizationAiSettingsUpdate,
    usuario: OrgOwnerDep,
    session: DbDep,
    background_tasks: BackgroundTasks,
) -> OrganizationAiSettingsOut:
    fila = await service.guardar_override_de_organizacion(session, usuario.organization_id, datos)
    background_tasks.add_task(
        _auditar,
        actor_user_id=usuario.id,
        organization_id=usuario.organization_id,
        action="organization_ai_settings.updated",
        detail={
            "provider": fila.provider,
            "default_model": fila.default_model,
            "has_key": fila.api_key_encrypted is not None,
            "monthly_limit_usd": (
                str(fila.monthly_limit_usd) if fila.monthly_limit_usd is not None else None
            ),
        },
    )
    return await service.vista_de_organizacion(session, usuario.organization_id)


@router.delete(
    "/me/ai-settings",
    summary="Volver a heredar la configuración de IA de la plataforma",
    description=(
        "Borra la configuración propia, incluida su clave cifrada. A partir de "
        "ese momento la organización vuelve a usar la de la plataforma; si la "
        "plataforma no tiene ninguna, queda «sin configuración»."
    ),
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_my_ai_settings(
    usuario: OrgOwnerDep, session: DbDep, background_tasks: BackgroundTasks
) -> Response:
    habia_configuracion = await service.borrar_override_de_organizacion(
        session, usuario.organization_id
    )
    background_tasks.add_task(
        _auditar,
        actor_user_id=usuario.id,
        organization_id=usuario.organization_id,
        action="organization_ai_settings.deleted",
        detail={"habia_configuracion": habia_configuracion},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
