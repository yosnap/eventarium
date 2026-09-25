"""Proveedor de correo de la plataforma (nivel admin).

En `modules/admin` por la misma razón que `ai_router.py`: la tabla solo la
escribe la sesión de mantenimiento, y `get_maintenance_db` no autentica por
sí solo — la barrera es `Superadmin` en cada ruta (test estático de
`tests/modules/test_admin.py`).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import registrar_auditoria
from app.core.database import maintenance_session
from app.core.deps import SCOPE_SESION, CurrentUser, get_maintenance_db, require_superadmin
from app.core.email import invalidar_configuracion_en_cache
from app.core.ratelimit import EMAIL_TEST_POR_IP, limit_per_ip
from app.modules.email_settings import service
from app.modules.email_settings.schemas import EmailSettingsIn, EmailSettingsOut, EmailTestOut

router = APIRouter(prefix="/admin", tags=["administración"])

MaintenanceDb = Annotated[AsyncSession, Depends(get_maintenance_db, scope=SCOPE_SESION)]
Superadmin = Annotated[CurrentUser, Depends(require_superadmin)]


async def _confirmar_y_refrescar(session: AsyncSession) -> None:
    """Commit explícito y **después** vaciar la caché del envío.

    Al revés, un envío de este mismo proceso entre medias leería la fila aún
    sin confirmar y volvería a cachear la configuración vieja otros 30 s.
    """
    await session.commit()
    invalidar_configuracion_en_cache()


@router.get(
    "/email-settings",
    summary="Proveedor de correo de la plataforma",
    description=(
        "La configuración guardada (`source=database`) o, si no hay, la de las "
        "variables `SMTP_*` (`source=environment`). **Nunca** devuelve la "
        "contraseña: solo si existe y su pista. Incluye el catálogo de "
        "proveedores para el formulario."
    ),
    response_model=EmailSettingsOut,
)
async def get_email_settings(_: Superadmin, session: MaintenanceDb) -> EmailSettingsOut:
    return service.vista(await service.leer_fila(session))


@router.put(
    "/email-settings",
    summary="Configurar el proveedor de correo de la plataforma",
    description=(
        "Guarda la conexión y la cifra en reposo con `AI_SETTINGS_ENCRYPTION_KEY` "
        "(503 si no está configurada). Desde ese momento anula las variables "
        "`SMTP_*`; los procesos que envían lo notan en menos de un minuto. El "
        "modo TLS se deriva del puerto."
    ),
    response_model=EmailSettingsOut,
)
async def put_email_settings(
    datos: EmailSettingsIn, superadmin: Superadmin, session: MaintenanceDb
) -> EmailSettingsOut:
    fila = await service.guardar(session, datos)
    await registrar_auditoria(
        session,
        actor_user_id=superadmin.id,
        organization_id=None,
        action="platform_email_settings.updated",
        entity_type="platform_email_settings",
        entity_id=str(fila.id),
        # Nunca la contraseña ni su pista.
        detail={"provider": fila.provider, "host": fila.host, "port": fila.port},
    )
    vista = service.vista(fila)
    await _confirmar_y_refrescar(session)
    return vista


@router.delete(
    "/email-settings",
    summary="Volver a las variables de entorno SMTP_*",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_email_settings(superadmin: Superadmin, session: MaintenanceDb) -> Response:
    if await service.borrar(session):
        await registrar_auditoria(
            session,
            actor_user_id=superadmin.id,
            organization_id=None,
            action="platform_email_settings.deleted",
            entity_type="platform_email_settings",
            entity_id=None,
            detail={},
        )
        await _confirmar_y_refrescar(session)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/email-settings/test",
    summary="Enviar un correo de prueba sin guardar",
    description=(
        "Envía un correo real **al propio superadmin** con la configuración del "
        "formulario (la contraseña puede omitirse para usar la guardada, si el "
        "proveedor no cambia). Responde 200 con `ok`: un `false` y su `motivo` "
        "son el resultado de la prueba. «Aceptado» significa que el servidor "
        "SMTP lo aceptó, no que haya llegado a la bandeja."
    ),
    response_model=EmailTestOut,
    dependencies=[limit_per_ip("email-test", EMAIL_TEST_POR_IP)],
)
async def post_email_test(datos: EmailSettingsIn, superadmin: Superadmin) -> EmailTestOut:
    # Sesiones cortas propias en vez de `MaintenanceDb`: el envío puede tardar
    # hasta el timeout SMTP y no debe retener una conexión del pool de
    # mantenimiento (pequeño y compartido por todo `/admin`) mientras tanto.
    async with maintenance_session() as session:
        config = await service.config_para_probar(session, datos)
    resultado = await service.probar(config, destinatario=superadmin.email)
    async with maintenance_session() as session:
        await registrar_auditoria(
            session,
            actor_user_id=superadmin.id,
            organization_id=None,
            action="platform_email_settings.tested",
            entity_type="platform_email_settings",
            entity_id=None,
            detail={"provider": datos.provider, "ok": resultado.ok, "motivo": resultado.motivo},
        )
    return resultado
