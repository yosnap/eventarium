"""Cola de tareas asíncronas sobre Redis Streams.

Se usa `RedisStreamBroker` y no `ListQueueBroker` porque el primero confirma los
mensajes (`ack`) y permite reintentos: una tarea perdida por un reinicio del worker
no puede desaparecer sin rastro.
"""

from __future__ import annotations

import uuid

from taskiq import TaskiqEvents, TaskiqState
from taskiq.schedule_sources import LabelScheduleSource
from taskiq.scheduler.scheduler import TaskiqScheduler
from taskiq_redis import RedisAsyncResultBackend, RedisStreamBroker

from app.core.cleanup import sweep_unverified_accounts
from app.core.config import get_settings
from app.core.email import EmailAttachment, get_email_provider
from app.core.tenant import base_url_de_organizacion

# Registro de todas las tablas en `Base.metadata` antes de que cualquier tarea
# haga un `commit`, mismo motivo y mismo patrón que `alembic/env.py`: este
# módulo se ejecuta como punto de entrada propio (`taskiq worker
# app.core.tasks:broker`), así que ningún router de `app.main` llega a
# importarse nunca en el proceso del worker. Sin esto, la primera tarea que
# haga `flush`/`commit` sobre una fila con una FK hacia una tabla cuyo modelo
# no se haya importado todavía en *este* proceso falla con
# `NoReferencedTableError`/`PendingRollbackError` («could not find table
# 'users'»): SQLAlchemy resuelve las FK declaradas por nombre de tabla contra
# `Base.metadata`, que solo se rellena importando la clase del modelo.
from app.modules.events import models as _event_models  # noqa: F401
from app.modules.legal import models as _legal_models  # noqa: F401
from app.modules.organizations import models as _organization_models  # noqa: F401
from app.modules.payments import models as _payment_models  # noqa: F401
from app.modules.registrations import models as _registration_models  # noqa: F401
from app.modules.roles import models as _role_models  # noqa: F401
from app.modules.sponsors import models as _sponsor_models  # noqa: F401
from app.modules.tickets import models as _ticket_models  # noqa: F401
from app.modules.tickets.service import generar_imagen_qr
from app.modules.users import models as _user_models  # noqa: F401

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
    base = await base_url_de_organizacion(uuid.UUID(organization_id))
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
    base = await base_url_de_organizacion(uuid.UUID(organization_id))
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
    base = await base_url_de_organizacion(uuid.UUID(organization_id))
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
async def send_registration_cancelled_email(
    to_email: str, organization_id: str, reembolso: str | None = None
) -> None:
    """Cancelación de una inscripción, por el organizador o por autocancelación.

    `reembolso` (fase 6 del PRD, fase 5 de trabajo, hallazgo #13) distingue
    los dos casos de una cancelación con pago: `"en_curso"` (política
    cumplida, se ha creado la intención de reembolso) o `"sin_reembolso"`
    (había importe pendiente pero la política de plazo lo descarta). `None`
    para un evento gratuito o un pago que nunca llegó a cobrarse — mismo
    correo que antes de esta fase.
    """
    cuerpo = (
        "Hola,\n\n"
        "Tu inscripción a este evento ha quedado cancelada. Si no has sido tú, "
        "contacta con la organización del evento."
    )
    if reembolso == "en_curso":
        cuerpo += (
            "\n\nEstamos tramitando el reembolso de tu pago; lo recibirás en los "
            "próximos días en el mismo medio de pago."
        )
    elif reembolso == "sin_reembolso":
        cuerpo += (
            "\n\nTu pago no se reembolsa automáticamente por la política de plazo de "
            "cancelación de este evento. Contacta con la organización si crees que "
            "debería reembolsarse."
        )
    await get_email_provider().send(
        to=to_email,
        subject="Tu inscripción ha sido cancelada",
        body=cuerpo,
    )


@broker.task(retry_on_error=True, max_retries=5)
async def send_registration_payment_link_email(
    to_email: str, organization_id: str, checkout_url: str, cancel_token: str, expira_el: str
) -> None:
    """Enlace de pago de los caminos 2, 3 y 4 (fase 6 del PRD, fase 4 de
    trabajo): verificación de email, aprobación manual y promoción de lista
    de espera de un evento de pago. Encolado por
    `dispatch_pending_payment_links_task`, nunca dentro de la petición que
    verificó/aprobó/promovió (hallazgo #12: sería una llamada de red a
    Stripe bajo bloqueos de fila)."""
    base = await base_url_de_organizacion(uuid.UUID(organization_id))
    enlace_cancelacion = f"{base}/cancelar-inscripcion?token={cancel_token}"
    await get_email_provider().send(
        to=to_email,
        subject="Completa el pago de tu entrada",
        body=_cuerpo_con_cancelacion(
            "Tu plaza está reservada. Complétala pagando tu entrada antes de "
            f"{expira_el} desde este enlace:\n{checkout_url}",
            enlace_cancelacion,
        ),
    )


@broker.task(schedule=[{"cron": "* * * * *"}])
async def dispatch_pending_payment_links_task() -> None:
    """Cada minuto: crea la Checkout Session de los caminos 2, 3 y 4 y encola
    su correo (`app/modules/payments/checkout_service.py`)."""
    from app.modules.payments.checkout_service import dispatch_pending_payment_links

    await dispatch_pending_payment_links()


@broker.task(schedule=[{"cron": "*/5 * * * *"}])
async def expire_pending_payments_task() -> None:
    """Cada 5 minutos: hermana de `expire_waitlist_promotions_task`. Antes de
    expirar una compra caducada, consulta el estado real en Stripe — un
    webhook perdido no debe cancelar una compra que sí se pagó."""
    from app.modules.payments.checkout_service import expirar_pagos_pendientes

    await expirar_pagos_pendientes()


@broker.task(retry_on_error=True, max_retries=5)
async def process_stripe_webhook_task(event_id: str) -> None:
    """Efecto de dominio de un webhook de Stripe ya registrado como
    `received` (`app/modules/payments/webhooks.py`). Relee el payload de la
    base de datos por `event_id`, nunca del argumento serializado en la cola
    (decisión #9 del plan de la fase 6)."""
    from app.modules.payments.webhooks import procesar_evento

    await procesar_evento(event_id)


@broker.task(schedule=[{"cron": "*/10 * * * *"}])
async def sweep_stuck_webhook_events_task() -> None:
    """Cada 10 minutos: reencola los eventos `received` atascados entre la
    cola y el worker, y los `failed` con reintentos disponibles (hallazgo #9:
    sin esto, un evento perdido deja dinero cobrado sin inscripción
    confirmada, para siempre)."""
    from app.core.database import maintenance_session
    from app.modules.payments import repository as payments_repository

    async with maintenance_session() as session:
        pendientes = await payments_repository.eventos_para_reencolar(session)
    for event_id in pendientes:
        await process_stripe_webhook_task.kiq(event_id)


@broker.task(schedule=[{"cron": "0 3 * * *"}])
async def purge_stripe_webhook_events_task() -> None:
    """Diaria: purga `stripe_webhook_events` más antiguos que
    `stripe_webhook_retention_days` (hallazgo #15)."""
    from app.core.database import maintenance_session
    from app.modules.payments import repository as payments_repository

    async with maintenance_session() as session:
        await payments_repository.purgar_eventos_antiguos(
            session, dias=get_settings().stripe_webhook_retention_days
        )


@broker.task(schedule=[{"cron": "*/2 * * * *"}])
async def process_refunds_task() -> None:
    """Cada 2 minutos, y encolada al vuelo tras cada cancelación con
    reembolso automático (`registrations/service.py::_cancelar_inscripcion`):
    ejecuta contra Stripe las intenciones `pending` del outbox
    `event_payment_refunds` (fase 6 del PRD, fase 5 de trabajo). El mismo
    camino ejecuta tanto el reembolso automático como el manual del panel."""
    from app.modules.payments.refunds_service import procesar_reembolsos_pendientes

    await procesar_reembolsos_pendientes()


@broker.task(schedule=[{"cron": "*/10 * * * *"}])
async def sweep_stuck_refunds_task() -> None:
    """Cada 10 minutos: hermana de `sweep_stuck_webhook_events_task`. Retoma
    un reembolso cuya llamada a Stripe pudo tener éxito pero cuya escritura
    posterior falló (hallazgo #11: sin esto, la fila queda `submitted` para
    siempre y nadie se entera de si el dinero salió o no)."""
    from app.modules.payments.refunds_service import reencolar_reembolsos_atascados

    await reencolar_reembolsos_atascados()


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
    base = await base_url_de_organizacion(uuid.UUID(organization_id))
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
