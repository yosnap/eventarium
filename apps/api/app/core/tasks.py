"""Cola de tareas asíncronas sobre Redis Streams.

Se usa `RedisStreamBroker` y no `ListQueueBroker` porque el primero confirma los
mensajes (`ack`) y permite reintentos: una tarea perdida por un reinicio del worker
no puede desaparecer sin rastro.
"""

from __future__ import annotations

import uuid

from sqlalchemy import text
from taskiq import TaskiqEvents, TaskiqState
from taskiq.schedule_sources import LabelScheduleSource
from taskiq.scheduler.scheduler import TaskiqScheduler
from taskiq_redis import RedisAsyncResultBackend, RedisStreamBroker

from app.core.cleanup import sweep_unverified_accounts
from app.core.config import get_settings
from app.core.database import maintenance_session
from app.core.email import EmailAttachment, get_email_provider
from app.modules.tickets.service import generar_imagen_qr

_settings = get_settings()

result_backend: RedisAsyncResultBackend[object] = RedisAsyncResultBackend(
    redis_url=_settings.redis_url,
    result_ex_time=60 * 60,
)

broker = RedisStreamBroker(url=_settings.redis_url).with_result_backend(result_backend)

# `TaskiqScheduler` corre en su propio proceso (`taskiq scheduler app.core.tasks:scheduler`),
# distinto de `taskiq worker`. `LabelScheduleSource` lee el `schedule=[...]` declarado
# en cada tarea con `@broker.task`, no hace falta registrarlas aparte.
scheduler = TaskiqScheduler(broker=broker, sources=[LabelScheduleSource(broker)])


@broker.on_event(TaskiqEvents.WORKER_STARTUP)
async def _al_arrancar(state: TaskiqState) -> None:
    state.entorno = _settings.app_env


@broker.task(retry_on_error=True, max_retries=5)
async def ping(mensaje: str = "pong") -> str:
    """Tarea mínima de verificación de la cola."""
    return mensaje


@broker.task(retry_on_error=True, max_retries=5)
async def send_verification_email(to_email: str, token: str) -> None:
    """Envía el enlace de verificación de correo tras el registro."""
    settings = get_settings()
    enlace = f"{settings.web_base_url}/verificar-correo?token={token}"
    await get_email_provider().send(
        to=to_email,
        subject="Verifica tu correo",
        body=(
            "Hola,\n\n"
            "Confirma tu correo para completar el registro:\n"
            f"{enlace}\n\n"
            "El enlace caduca en 24 horas. Si no has sido tú, ignora este mensaje."
        ),
    )


@broker.task(schedule=[{"cron": "0 * * * *"}])
async def sweep_unverified_accounts_task() -> None:
    """Cada hora: aviso a los 5 días, borrado a los 7 (`core/cleanup.py`)."""
    await sweep_unverified_accounts()


@broker.task(retry_on_error=True, max_retries=5)
async def send_password_reset_email(to_email: str, token: str) -> None:
    """Envía el enlace de recuperación de contraseña."""
    settings = get_settings()
    enlace = f"{settings.web_base_url}/recuperar-contrasena/nueva?token={token}"
    await get_email_provider().send(
        to=to_email,
        subject="Recupera tu contraseña",
        body=(
            "Hola,\n\n"
            "Alguien ha pedido restablecer la contraseña de esta cuenta. Si has sido "
            "tú, elige una nueva desde este enlace:\n"
            f"{enlace}\n\n"
            "El enlace caduca en 24 horas. Si no has sido tú, ignora este mensaje: tu "
            "contraseña actual sigue siendo válida."
        ),
    )


@broker.task(retry_on_error=True, max_retries=5)
async def send_email_change_warning(to_email: str, new_email: str) -> None:
    """Avisa al correo **actual** de que se ha solicitado cambiarlo. Sin enlace ni token."""
    await get_email_provider().send(
        to=to_email,
        subject="Se ha solicitado cambiar el correo de tu cuenta",
        body=(
            "Hola,\n\n"
            f"Alguien ha solicitado cambiar el correo de esta cuenta a {new_email}. El "
            "cambio no se aplicará hasta que se confirme desde esa dirección.\n\n"
            "Si no has sido tú, cambia tu contraseña cuanto antes: alguien con acceso "
            "a tu sesión está intentando llevarse la cuenta a otro correo."
        ),
    )


@broker.task(retry_on_error=True, max_retries=5)
async def send_email_change_confirmation(to_email: str, token: str) -> None:
    """Envía el enlace de confirmación al correo **nuevo**."""
    settings = get_settings()
    enlace = f"{settings.web_base_url}/cuenta/confirmar-correo?token={token}"
    await get_email_provider().send(
        to=to_email,
        subject="Confirma tu nuevo correo",
        body=(
            "Hola,\n\n"
            "Confirma que quieres usar este correo para tu cuenta:\n"
            f"{enlace}\n\n"
            "El enlace caduca en 24 horas. Si no has sido tú, ignora este mensaje."
        ),
    )


async def _base_url_de_organizacion(organization_id: uuid.UUID) -> str:
    """URL pública de la organización, por su dominio primario.

    A diferencia de los correos de cuenta (transversales a toda la instalación,
    de ahí `settings.web_base_url`), un correo de inscripción llega a alguien
    sin sesión ni contexto de organización: el enlace tiene que apuntar al
    dominio propio de esa organización — la instalación resuelve el tenant por
    `Host`, así que un enlace al dominio equivocado no encontraría la
    inscripción al volver. Usa `maintenance_session` porque una tarea de fondo
    no tiene una petición HTTP de la que resolver la organización.
    """
    settings = get_settings()
    async with maintenance_session() as session:
        host = await session.scalar(
            text(
                "SELECT host FROM organization_domains "
                "WHERE organization_id = :id ORDER BY is_primary DESC LIMIT 1"
            ),
            {"id": organization_id},
        )
    if not host:
        return settings.web_base_url
    esquema = "https" if settings.app_env == "production" else "http"
    return f"{esquema}://{host}"


@broker.task(schedule=[{"cron": "*/15 * * * *"}])
async def expire_waitlist_promotions_task() -> None:
    """Cada 15 minutos: devuelve al final de la cola las promociones de lista
    de espera caducadas sin confirmar y promueve a la siguiente persona
    (`app/modules/registrations/service.py`).

    Importado dentro de la tarea, no a nivel de módulo: `registrations.service`
    importa `send_registration_verification_email` de este mismo archivo, y un
    `import` a nivel de módulo en ambos sentidos sería una importación circular.
    """
    from app.modules.registrations.service import expire_waitlist_promotions

    await expire_waitlist_promotions()


@broker.task(retry_on_error=True, max_retries=5)
async def send_registration_verification_email(
    to_email: str, token: str, organization_id: str
) -> None:
    """Envía el enlace de verificación de una inscripción a un evento."""
    base = await _base_url_de_organizacion(uuid.UUID(organization_id))
    enlace = f"{base}/verificar-inscripcion?token={token}"
    await get_email_provider().send(
        to=to_email,
        subject="Verifica tu inscripción",
        body=(
            "Hola,\n\n"
            "Confirma tu correo para completar la inscripción:\n"
            f"{enlace}\n\n"
            "El enlace caduca en 24 horas. Si no has sido tú, ignora este mensaje."
        ),
    )


def _cuerpo_con_cancelacion(intro: str, enlace_cancelacion: str) -> str:
    """Cuerpo común a las tres plantillas que ofrecen autocancelación
    (confirmación, lista de espera, promoción) — evita triplicar el mismo
    párrafo de cancelación en cada tarea."""
    return (
        f"Hola,\n\n{intro}\n\n"
        "Si no puedes asistir, cancela tu inscripción desde este enlace:\n"
        f"{enlace_cancelacion}"
    )


@broker.task(retry_on_error=True, max_retries=5)
async def send_registration_confirmed_email(
    to_email: str, organization_id: str, cancel_token: str, qr_token: str | None = None
) -> None:
    """Confirmación de inscripción (alta directa, verificación o aprobación),
    con la entrada QR incrustada (fase 4 del PRD, fase 4 de trabajo).

    `qr_token` es el JWT ya firmado de la entrada (`tickets.service.generar_token_qr`),
    generado en `_enviar_email_por_estado` — la imagen PNG se genera aquí, en
    el worker, no en el camino de la petición HTTP que confirma la inscripción.

    Opcional con valor por defecto (no un cuarto argumento obligatorio): un
    despliegue con reinicio escalonado podría dejar un mensaje ya encolado
    por un productor con la firma antigua (de tres argumentos) esperando a
    ser procesado por un worker ya actualizado — con un valor por defecto ese
    mensaje se entrega igual, sin el QR incrustado, en vez de fallar.
    """
    base = await _base_url_de_organizacion(uuid.UUID(organization_id))
    enlace_cancelacion = f"{base}/cancelar-inscripcion?token={cancel_token}"
    enlace_mi_entrada = f"{base}/mi-entrada?token={cancel_token}"
    await get_email_provider().send(
        to=to_email,
        subject="Tu inscripción está confirmada",
        body=_cuerpo_con_cancelacion(
            "Tu inscripción ha quedado confirmada. ¡Te esperamos! Adjuntamos tu "
            "entrada con el código QR: muéstrala en la puerta el día del evento.\n\n"
            f"Si pierdes este correo, puedes volver a verla aquí:\n{enlace_mi_entrada}",
            enlace_cancelacion,
        ),
        attachments=(
            [
                EmailAttachment(
                    filename="entrada.png",
                    content=generar_imagen_qr(qr_token),
                    maintype="image",
                    subtype="png",
                )
            ]
            if qr_token is not None
            else []
        ),
    )


@broker.task(retry_on_error=True, max_retries=5)
async def send_registration_waitlisted_email(
    to_email: str, organization_id: str, cancel_token: str
) -> None:
    """Entrada en lista de espera (alta directa, verificación o aprobación)."""
    base = await _base_url_de_organizacion(uuid.UUID(organization_id))
    enlace_cancelacion = f"{base}/cancelar-inscripcion?token={cancel_token}"
    await get_email_provider().send(
        to=to_email,
        subject="Estás en la lista de espera",
        body=_cuerpo_con_cancelacion(
            "El aforo está completo; te hemos añadido a la lista de espera. Te "
            "avisaremos por correo si se libera una plaza.",
            enlace_cancelacion,
        ),
    )


@broker.task(retry_on_error=True, max_retries=5)
async def send_registration_rejected_email(to_email: str, organization_id: str) -> None:
    """Rechazo de una inscripción `pending_approval` por el organizador."""
    await get_email_provider().send(
        to=to_email,
        subject="Tu inscripción no ha sido aprobada",
        body=(
            "Hola,\n\n"
            "El organizador del evento no ha aprobado tu inscripción. Si crees que "
            "es un error, contacta directamente con la organización."
        ),
    )


@broker.task(retry_on_error=True, max_retries=5)
async def send_registration_cancelled_email(to_email: str, organization_id: str) -> None:
    """Cancelación de una inscripción, por el organizador o por autocancelación."""
    await get_email_provider().send(
        to=to_email,
        subject="Tu inscripción ha sido cancelada",
        body=(
            "Hola,\n\n"
            "Tu inscripción a este evento ha quedado cancelada. Si no has sido tú, "
            "contacta con la organización del evento."
        ),
    )


@broker.task(retry_on_error=True, max_retries=5)
async def send_waitlist_promotion_email(
    to_email: str,
    organization_id: str,
    confirm_token: str,
    cancel_token: str,
    expira_el: str,
) -> None:
    """Promoción desde la lista de espera: hay que confirmar antes de `expira_el`
    (ya formateado en texto legible) o la plaza pasa a la siguiente persona."""
    base = await _base_url_de_organizacion(uuid.UUID(organization_id))
    enlace_confirmar = f"{base}/confirmar-promocion?token={confirm_token}"
    enlace_cancelacion = f"{base}/cancelar-inscripcion?token={cancel_token}"
    await get_email_provider().send(
        to=to_email,
        subject="Se ha liberado una plaza: confirma tu inscripción",
        body=(
            "Hola,\n\n"
            "Se ha liberado una plaza y te toca a ti. Confirma tu inscripción antes "
            f"de {expira_el} desde este enlace:\n{enlace_confirmar}\n\n"
            "Si no confirmas a tiempo, pasaremos a la siguiente persona en la lista "
            "de espera.\n\n"
            f"Si ya no quieres asistir, cancela tu inscripción aquí:\n{enlace_cancelacion}"
        ),
    )
