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
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Response, status

from app.core.audit import registrar_auditoria
from app.core.database import maintenance_session
from app.core.deps import DbDep, OrgOwnerDep
from app.modules.ai_gateway import service
from app.modules.ai_gateway.schemas import (
    OrganizationAiSettingsOut,
    OrganizationAiSettingsUpdate,
)

router = APIRouter(prefix="/organizations", tags=["organizaciones"])


async def _auditar(
    *,
    actor_user_id: uuid.UUID,
    organization_id: uuid.UUID,
    action: str,
    detail: dict[str, Any],
) -> None:
    """Auditoría de los cambios de credencial de la organización.

    Se encola como `BackgroundTask` —Starlette la corre tras enviar la
    respuesta, y por tanto tras el `commit` real de la transacción de la
    petición— y abre su propia sesión de mantenimiento, porque `audit_log`
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
