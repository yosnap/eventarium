"""Cola de tareas asíncronas sobre Redis Streams.

Se usa `RedisStreamBroker` y no `ListQueueBroker` porque el primero confirma los
mensajes (`ack`) y permite reintentos: una tarea perdida por un reinicio del worker
no puede desaparecer sin rastro.
"""

from __future__ import annotations

import logging
import uuid

from taskiq import TaskiqEvents, TaskiqState
from taskiq.schedule_sources import LabelScheduleSource
from taskiq.scheduler.scheduler import TaskiqScheduler
from taskiq_redis import RedisAsyncResultBackend, RedisStreamBroker

from app.core.cleanup import sweep_unverified_accounts
from app.core.config import get_settings
from app.core.email import EmailAttachment, get_email_provider
from app.core.email_template import neutralizar_texto_de_usuario
from app.core.locale import Locale, fijar_idioma, normalizar_locale, ruta_web
from app.core.mensajes import marcar, t
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
from app.modules.accounting import models as _accounting_models  # noqa: F401
from app.modules.events import models as _event_models  # noqa: F401
from app.modules.legal import models as _legal_models  # noqa: F401
from app.modules.media import models as _media_models  # noqa: F401
from app.modules.nearby import models as _nearby_models  # noqa: F401
from app.modules.organizations import models as _organization_models  # noqa: F401
from app.modules.payments import models as _payment_models  # noqa: F401
from app.modules.policies import models as _policy_models  # noqa: F401
from app.modules.registrations import models as _registration_models  # noqa: F401
from app.modules.roles import models as _role_models  # noqa: F401
from app.modules.sponsors import models as _sponsor_models  # noqa: F401
from app.modules.tickets import models as _ticket_models  # noqa: F401
from app.modules.tickets.service import adjunto_qr
from app.modules.translations import models as _translation_models  # noqa: F401
from app.modules.translations.cola import instalar_encolado_automatico
from app.modules.users import models as _user_models  # noqa: F401

_settings = get_settings()

# El worker también guarda textos (p. ej. al cerrar procesos): sus cambios piden
# traducción igual que los de la API.
instalar_encolado_automatico()

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


#: Los asuntos llevan nombres que escribe el usuario (organización, evento):
#: se acotan para que no ocupen la bandeja entera.
LONGITUD_MAXIMA_DEL_ASUNTO = 150


def limpiar_asunto(asunto: str) -> str:
    """El asunto en una sola línea y con longitud acotada.

    Un salto de línea en un nombre escrito por un usuario no puede llegar a la
    cabecera `Subject`: la partiría o, en el peor caso, añadiría cabeceras.
    """
    return " ".join(asunto.split())[:LONGITUD_MAXIMA_DEL_ASUNTO]


def _idioma_del_envio(locale: str | None) -> Locale:
    """Fija el idioma de la tarea para `t()` y la plantilla, y lo devuelve.

    Sin `locale` (mensajes encolados antes de que existiera el argumento), español.
    """
    idioma = normalizar_locale(locale)
    fijar_idioma(idioma)
    return idioma


def _enlace(base: str, idioma: Locale, ruta: str, token: str) -> str:
    """Enlace a una página pública de la web, con la ruta traducida al idioma."""
    return f"{base}{ruta_web(idioma, ruta)}?token={token}"


async def _enviar(
    to_email: str, asunto: str, cuerpo: str, attachments: list[EmailAttachment] | None = None
) -> None:
    await get_email_provider().send(
        to=to_email, subject=limpiar_asunto(asunto), body=cuerpo, attachments=attachments or []
    )


@broker.task(retry_on_error=True, max_retries=5)
async def send_verification_email(to_email: str, token: str, *, locale: str | None = None) -> None:
    """Envía el enlace de verificación de correo tras el registro."""
    idioma = _idioma_del_envio(locale)
    enlace = _enlace(get_settings().web_base_url, idioma, "verificar-correo", token)
    await _enviar(
        to_email,
        t("Verifica tu correo"),
        t(
            "Hola,\n\n"
            "Confirma tu correo para completar el registro:\n"
            "{enlace}\n\n"
            "El enlace caduca en 24 horas. Si no has sido tú, ignora este mensaje.",
            enlace=enlace,
        ),
    )


@broker.task()
async def sweep_unverified_accounts_task() -> None:
    """Aviso a los 5 días, borrado a los 7 (`core/cleanup.py`).

    Sin `schedule`: el barrido automático horario se desactivó a petición
    expresa (borraba cuentas de desarrollo sin aviso visible). La tarea sigue
    aquí por si se quiere volver a programar o invocar a mano más adelante,
    pero no se dispara sola."""
    await sweep_unverified_accounts()


@broker.task(retry_on_error=True, max_retries=5)
async def send_invitation_email(
    to_email: str,
    token: str,
    organization_id: str,
    organization_name: str,
    role_name: str,
    *,
    locale: str | None = None,
) -> None:
    """Envía el enlace de invitación de equipo (fase 2 del plan de invitaciones).

    El asunto y el cuerpo dicen «te han invitado», nunca «recupera tu
    contraseña»: el mecanismo es el mismo que `send_password_reset_email`
    (Redis + huella + TTL) pero el mensaje no puede serlo, o la persona
    invitada cree que le han hackeado la cuenta (hallazgo S-1 del red-team).
    El enlace va a la ruta propia `/invitacion`, nunca a
    `/recuperar-contrasena/nueva`.
    """
    idioma = _idioma_del_envio(locale)
    base = await base_url_de_organizacion(uuid.UUID(organization_id))
    enlace = _enlace(base, idioma, "invitacion", token)
    # Nombre escrito por un usuario: sin URLs que se conviertan en el botón del correo.
    organizacion = neutralizar_texto_de_usuario(organization_name)
    await _enviar(
        to_email,
        t("Te han invitado a «{organizacion}»", organizacion=organizacion),
        t(
            "Hola,\n\n"
            "Te han invitado a unirte a «{organizacion}» con el rol «{rol}».\n"
            "Para aceptar la invitación y crear tu contraseña, entra aquí:\n"
            "{enlace}\n\n"
            "El enlace caduca en 7 días. Si no esperabas esta invitación, puedes "
            "ignorar este mensaje.",
            organizacion=organizacion,
            rol=role_name,
            enlace=enlace,
        ),
    )


@broker.task(retry_on_error=True, max_retries=5)
async def send_password_reset_email(
    to_email: str, token: str, *, locale: str | None = None
) -> None:
    """Envía el enlace de recuperación de contraseña."""
    idioma = _idioma_del_envio(locale)
    enlace = _enlace(get_settings().web_base_url, idioma, "recuperar-contrasena/nueva", token)
    await _enviar(
        to_email,
        t("Recupera tu contraseña"),
        t(
            "Hola,\n\n"
            "Alguien ha pedido restablecer la contraseña de esta cuenta. Si has sido "
            "tú, elige una nueva desde este enlace:\n"
            "{enlace}\n\n"
            "El enlace caduca en 24 horas. Si no has sido tú, ignora este mensaje: tu "
            "contraseña actual sigue siendo válida.",
            enlace=enlace,
        ),
    )


@broker.task(retry_on_error=True, max_retries=5)
async def send_mis_eventos_access_email(
    to_email: str, token: str, *, locale: str | None = None
) -> None:
    """Envía el magic-link de «Mis eventos» (listado de inscripciones por email).

    Mismo mecanismo que `send_password_reset_email` (Redis + huella + TTL
    propio de 30 min, ver `verification.py`), pero el enlace no cambia nada:
    solo lista. El asunto y el cuerpo lo dicen explícitamente para no sonar a
    aviso de seguridad de cuenta.
    """
    idioma = _idioma_del_envio(locale)
    enlace = _enlace(get_settings().web_base_url, idioma, "mis-eventos/ver", token)
    await _enviar(
        to_email,
        t("Tus inscripciones a eventos"),
        t(
            "Hola,\n\n"
            "Alguien ha pedido ver el listado de inscripciones a eventos de este "
            "correo. Si has sido tú, entra aquí:\n"
            "{enlace}\n\n"
            "El enlace caduca en 30 minutos y solo sirve una vez. Si no has sido "
            "tú, ignora este mensaje.",
            enlace=enlace,
        ),
    )


@broker.task(retry_on_error=True, max_retries=5)
async def send_email_change_warning(
    to_email: str, new_email: str, *, locale: str | None = None
) -> None:
    """Avisa al correo **actual** de que se ha solicitado cambiarlo. Sin enlace ni token."""
    _idioma_del_envio(locale)
    await _enviar(
        to_email,
        t("Se ha solicitado cambiar el correo de tu cuenta"),
        t(
            "Hola,\n\n"
            "Alguien ha solicitado cambiar el correo de esta cuenta a {correo}. El "
            "cambio no se aplicará hasta que se confirme desde esa dirección.\n\n"
            "Si no has sido tú, cambia tu contraseña cuanto antes: alguien con acceso "
            "a tu sesión está intentando llevarse la cuenta a otro correo.",
            correo=new_email,
        ),
    )


@broker.task(retry_on_error=True, max_retries=5)
async def send_impersonation_notice(
    to_email: str, *, reason: str, minutos: int, organizacion: str, locale: str | None = None
) -> None:
    """Avisa a la persona de que el equipo de la plataforma ha entrado a su cuenta.

    Sin enlace y sin token: es un aviso, no una acción que la persona tenga que
    hacer. Va al suplantado y no al administrador porque suplantar da acceso a
    datos personales de alguien que, sin este correo, no tendría forma de
    enterarse (el registro de auditoría está restringido al personal de
    plataforma).
    """
    _idioma_del_envio(locale)
    await _enviar(
        to_email,
        t("El equipo de la plataforma ha accedido a tu cuenta"),
        t(
            "Hola,\n\n"
            "El equipo de soporte ha accedido a tu cuenta de {organizacion} durante "
            "unos {minutos} minutos para revisar una incidencia. El motivo indicado "
            "es: «{motivo}».\n\n"
            "El acceso es de solo lectura: durante ese tiempo no se ha modificado "
            "nada de tu cuenta ni de tus eventos. Queda registrado quién lo hizo y "
            "cuándo.\n\n"
            "Si no esperabas este acceso, responde a este correo para que lo "
            "revisemos.",
            organizacion=organizacion,
            minutos=minutos,
            motivo=reason,
        ),
    )


@broker.task(retry_on_error=True, max_retries=5)
async def send_email_change_confirmation(
    to_email: str, token: str, *, locale: str | None = None
) -> None:
    """Envía el enlace de confirmación al correo **nuevo**."""
    idioma = _idioma_del_envio(locale)
    enlace = _enlace(get_settings().web_base_url, idioma, "cuenta/confirmar-correo", token)
    await _enviar(
        to_email,
        t("Confirma tu nuevo correo"),
        t(
            "Hola,\n\n"
            "Confirma que quieres usar este correo para tu cuenta:\n"
            "{enlace}\n\n"
            "El enlace caduca en 24 horas. Si no has sido tú, ignora este mensaje.",
            enlace=enlace,
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
    to_email: str, token: str, organization_id: str, *, locale: str | None = None
) -> None:
    """Envía el enlace de verificación de una inscripción a un evento."""
    idioma = _idioma_del_envio(locale)
    base = await base_url_de_organizacion(uuid.UUID(organization_id))
    enlace = _enlace(base, idioma, "verificar-inscripcion", token)
    await _enviar(
        to_email,
        t("Verifica tu inscripción"),
        t(
            "Hola,\n\n"
            "Confirma tu correo para completar la inscripción:\n"
            "{enlace}\n\n"
            "El enlace caduca en 24 horas. Si no has sido tú, ignora este mensaje.",
            enlace=enlace,
        ),
    )


def _cuerpo_con_cancelacion(intro: str, enlace_cancelacion: str) -> str:
    """Cuerpo común a las plantillas que ofrecen autocancelación
    (confirmación, lista de espera, enlace de pago) — evita repetir el mismo
    párrafo de cancelación en cada tarea. `intro` llega ya traducida."""
    return t(
        "Hola,\n\n{intro}\n\n"
        "Si no puedes asistir, cancela tu inscripción desde este enlace:\n"
        "{enlace}",
        intro=intro,
        enlace=enlace_cancelacion,
    )


@broker.task(retry_on_error=True, max_retries=5)
async def send_registration_confirmed_email(
    to_email: str,
    organization_id: str,
    cancel_token: str,
    qr_token: str | None = None,
    *,
    locale: str | None = None,
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
    idioma = _idioma_del_envio(locale)
    base = await base_url_de_organizacion(uuid.UUID(organization_id))
    enlace_cancelacion = _enlace(base, idioma, "cancelar-inscripcion", cancel_token)
    enlace_mi_entrada = _enlace(base, idioma, "mi-entrada", cancel_token)
    await _enviar(
        to_email,
        t("Tu inscripción está confirmada"),
        _cuerpo_con_cancelacion(
            t(
                "Tu inscripción ha quedado confirmada. ¡Te esperamos! Tu entrada es el "
                "código QR de este correo: muéstrala en la puerta el día del evento.\n\n"
                "Si pierdes este correo o no ves la imagen, puedes volver a verla aquí:\n"
                "{enlace}",
                enlace=enlace_mi_entrada,
            ),
            enlace_cancelacion,
        ),
        attachments=[adjunto_qr(qr_token)] if qr_token is not None else [],
    )


@broker.task(retry_on_error=True, max_retries=5)
async def send_registration_waitlisted_email(
    to_email: str, organization_id: str, cancel_token: str, *, locale: str | None = None
) -> None:
    """Entrada en lista de espera (alta directa, verificación o aprobación)."""
    idioma = _idioma_del_envio(locale)
    base = await base_url_de_organizacion(uuid.UUID(organization_id))
    enlace_cancelacion = _enlace(base, idioma, "cancelar-inscripcion", cancel_token)
    await _enviar(
        to_email,
        t("Estás en la lista de espera"),
        _cuerpo_con_cancelacion(
            t(
                "El aforo está completo; te hemos añadido a la lista de espera. Te "
                "avisaremos por correo si se libera una plaza."
            ),
            enlace_cancelacion,
        ),
    )


@broker.task(retry_on_error=True, max_retries=5)
async def send_registration_rejected_email(
    to_email: str, organization_id: str, reason: str | None = None, *, locale: str | None = None
) -> None:
    """Rechazo de una inscripción `pending_approval` por el organizador.

    `reason` es el mensaje que el organizador escribe en el diálogo de
    rechazo; no se guarda en ninguna tabla (solo viaja aquí), así que un
    reenvío posterior del mismo rechazo (alta duplicada sobre una
    inscripción ya `rejected`) no puede reconstruirlo. Parámetro opcional al
    final: la tarea puede tener mensajes en cola con la firma antigua
    (2 posicionales) — un worker desplegado antes que la API que ya encola
    3 fallaría con `TypeError`, así que en un despliegue continuo los
    workers se actualizan primero.

    Nota de retención: el `reason` no llega a Postgres, pero `broker`
    (`RedisStreamBroker`) no fija `maxlen` — un mensaje ya `XACK`eado no se
    borra del stream de Redis por sí solo. Acota la retención del dato en la
    base de datos de negocio, no en la infraestructura de mensajería
    compartida por todas las tareas del sistema (ajustar eso es una decisión
    de infraestructura aparte, no específica de este correo).
    """
    _idioma_del_envio(locale)
    cuerpo = t(
        "Hola,\n\n"
        "El organizador del evento no ha aprobado tu inscripción. Si crees que "
        "es un error, contacta directamente con la organización."
    )
    # Texto libre del organizador: sin URLs que se conviertan en el botón del correo.
    motivo = neutralizar_texto_de_usuario(reason) if reason else None
    if motivo:
        cuerpo += "\n\n" + t("Mensaje del organizador:\n{motivo}", motivo=motivo)
    await _enviar(to_email, t("Tu inscripción no ha sido aprobada"), cuerpo)


@broker.task(retry_on_error=True, max_retries=5)
async def send_registration_pending_approval_email(
    to_email: str, organization_id: str, *, locale: str | None = None
) -> None:
    """Inscripción recibida en un evento con aprobación: queda a la espera de
    que el organizador la acepte o la rechace (ambos casos tienen su correo)."""
    _idioma_del_envio(locale)
    await _enviar(
        to_email,
        t("Hemos recibido tu inscripción"),
        t(
            "Hola,\n\n"
            "Hemos recibido tu inscripción. El organizador del evento la revisará y te "
            "avisaremos por correo en cuanto la apruebe o la rechace."
        ),
    )


_ESTADO_PARA_EL_ORGANIZADOR = {
    "confirmed": marcar("confirmada"),
    "waitlisted": marcar("en lista de espera (el aforo está completo)"),
    "pending_approval": marcar("pendiente de tu aprobación"),
}


@broker.task(retry_on_error=True, max_retries=5)
async def send_registration_received_organizer_email(
    to_email: str,
    organization_id: str,
    event_id: str,
    registration_id: str,
    event_title: str,
    participant_name: str,
    participant_email: str,
    status: str,
    paid: bool = False,
    *,
    locale: str | None = None,
) -> None:
    """Aviso a quien gestiona las inscripciones de una organización: alguien
    se ha inscrito (o ha pagado su entrada). Un destinatario por tarea, para
    que un reintento no reenvíe a quien ya lo recibió.

    El enlace al panel va en la **primera** línea: es la URL que la plantilla
    convierte en botón (`detectar_accion`), y el nombre del participante lo
    escribe un anónimo — se neutraliza para que no pueda ocupar ese lugar.
    """
    _idioma_del_envio(locale)
    base = await base_url_de_organizacion(uuid.UUID(organization_id))
    # El panel no lleva prefijo de idioma: sale en el idioma de la cuenta.
    enlace = f"{base}/dashboard/events/{event_id}/registrations/{registration_id}"
    titulo = neutralizar_texto_de_usuario(event_title)
    pendiente = status == "pending_approval"
    if pendiente:
        asunto = t("Inscripción pendiente de aprobar en {titulo}", titulo=titulo)
        entrada = t(
            "Alguien quiere inscribirse en «{titulo}» y necesita tu aprobación.", titulo=titulo
        )
    elif paid:
        asunto = t("Entrada pagada en {titulo}", titulo=titulo)
        entrada = t("Se ha pagado una entrada de «{titulo}».", titulo=titulo)
    else:
        asunto = t("Nueva inscripción en {titulo}", titulo=titulo)
        entrada = t("Hay una inscripción nueva en «{titulo}».", titulo=titulo)
    estado = _ESTADO_PARA_EL_ORGANIZADOR.get(status)
    cuerpo = f"{enlace}\n\n{entrada}\n\n" + t(
        "Nombre: {nombre}\nCorreo: {correo}\nEstado: {estado}",
        nombre=neutralizar_texto_de_usuario(participant_name),
        # El correo llega validado como dirección (sin espacios ni esquema):
        # se deja tal cual para que se pueda copiar o pulsar.
        correo=participant_email,
        estado=t(estado) if estado is not None else status,  # mensaje marcado
    )
    if pendiente:
        cuerpo += "\n\n" + t("Abre la inscripción para aprobarla o rechazarla.")
    await _enviar(to_email, asunto, cuerpo)


@broker.task(retry_on_error=True, max_retries=5)
async def send_registration_cancelled_email(
    to_email: str, organization_id: str, reembolso: str | None = None, *, locale: str | None = None
) -> None:
    """Cancelación de una inscripción, por el organizador o por autocancelación.

    `reembolso` (fase 6 del PRD, fase 5 de trabajo) distingue
    los dos casos de una cancelación con pago: `"en_curso"` (política
    cumplida, se ha creado la intención de reembolso) o `"sin_reembolso"`
    (había importe pendiente pero la política de plazo lo descarta). `None`
    para un evento gratuito o un pago que nunca llegó a cobrarse — mismo
    correo que antes de esta fase.
    """
    _idioma_del_envio(locale)
    cuerpo = t(
        "Hola,\n\n"
        "Tu inscripción a este evento ha quedado cancelada. Si no has sido tú, "
        "contacta con la organización del evento."
    )
    if reembolso == "en_curso":
        cuerpo += "\n\n" + t(
            "Estamos tramitando el reembolso de tu pago; lo recibirás en los "
            "próximos días en el mismo medio de pago."
        )
    elif reembolso == "reembolsado":
        cuerpo += "\n\n" + t(
            "Se te ha devuelto el importe completo de tu pago; lo verás en los "
            "próximos días en el mismo medio de pago."
        )
    elif reembolso == "sin_reembolso":
        cuerpo += "\n\n" + t(
            "Tu pago no se reembolsa automáticamente por la política de plazo de "
            "cancelación de este evento. Contacta con la organización si crees que "
            "debería reembolsarse."
        )
    await _enviar(to_email, t("Tu inscripción ha sido cancelada"), cuerpo)


@broker.task(retry_on_error=True, max_retries=5)
async def send_event_cancelled_email(
    to_email: str,
    organization_id: str,
    titulo: str,
    motivo: str | None,
    con_reembolso: bool,
    *,
    locale: str | None = None,
) -> None:
    """La organización ha cancelado el evento. Lo encola el barrido de
    `events/cancelacion.py`, una vez por inscripción cancelada con el evento."""
    _idioma_del_envio(locale)
    # Textos escritos por el organizador: sin URLs que se conviertan en el botón.
    titulo = neutralizar_texto_de_usuario(titulo)
    motivo = neutralizar_texto_de_usuario(motivo) if motivo else None
    cuerpo = t("Hola,\n\nLa organización ha cancelado el evento «{titulo}».", titulo=titulo)
    if motivo:
        cuerpo += "\n\n" + t("Motivo:\n{motivo}", motivo=motivo)
    cuerpo += "\n\n" + t("Tu inscripción queda cancelada y tu entrada deja de ser válida.")
    if con_reembolso:
        cuerpo += "\n\n" + t(
            "Te devolvemos el importe íntegro de tu pago; lo recibirás en los "
            "próximos días en el mismo medio de pago."
        )
    await _enviar(to_email, t("Evento cancelado: {titulo}", titulo=titulo), cuerpo)


@broker.task(retry_on_error=True, max_retries=5)
async def sweep_event_cancellation_task(organization_id: str, event_id: str) -> None:
    """Barrido de una cancelación recién confirmada: cancela inscripciones,
    pide reembolsos y avisa, por lotes. Lo encola el router tras el `commit`."""
    from app.modules.events.cancelacion import barrer_cancelacion

    await barrer_cancelacion(uuid.UUID(organization_id), uuid.UUID(event_id))


@broker.task(schedule=[{"cron": "*/10 * * * *"}])
async def resume_event_cancellations_task() -> None:
    """Cada 10 minutos: retoma las cancelaciones de evento con trabajo
    pendiente, por si el barrido encolado murió a medias."""
    from app.modules.events.cancelacion import reanudar_cancelaciones_pendientes

    await reanudar_cancelaciones_pendientes()


@broker.task(retry_on_error=True, max_retries=5)
async def send_registration_payment_link_email(
    to_email: str,
    organization_id: str,
    checkout_url: str,
    cancel_token: str,
    expira_el: str,
    *,
    locale: str | None = None,
) -> None:
    """Enlace de pago de los caminos 2, 3 y 4 (fase 6 del PRD, fase 4 de
    trabajo): verificación de email, aprobación manual y promoción de lista
    de espera de un evento de pago. Encolado por
    `dispatch_pending_payment_links_task`, nunca dentro de la petición que
    verificó/aprobó/promovió: sería una llamada de red a
    Stripe bajo bloqueos de fila."""
    idioma = _idioma_del_envio(locale)
    base = await base_url_de_organizacion(uuid.UUID(organization_id))
    enlace_cancelacion = _enlace(base, idioma, "cancelar-inscripcion", cancel_token)
    await _enviar(
        to_email,
        t("Completa el pago de tu entrada"),
        _cuerpo_con_cancelacion(
            t(
                "Tu plaza está reservada. Complétala pagando tu entrada antes de "
                "{expira_el} desde este enlace:\n{enlace}",
                expira_el=expira_el,
                enlace=checkout_url,
            ),
            enlace_cancelacion,
        ),
    )


@broker.task(schedule=[{"cron": "*/10 * * * *"}])
async def dispatch_event_reminders_task() -> None:
    """Cada 10 minutos: reclama las inscripciones a las que ya les toca el
    recordatorio y encola su envío (`app/modules/reminders/service.py`)."""
    from app.modules.reminders.service import procesar_recordatorios

    await procesar_recordatorios()


@broker.task
async def send_event_reminder_task(registration_id: str) -> None:
    """Recordatorio de una inscripción ya reclamada: vuelve a comprobarla y lo
    envía. Si falla, su reclamación caduca a los 30 minutos y se reintenta
    entonces (sin reintento inmediato: el correo podría haber salido ya)."""
    from app.modules.reminders.service import enviar_recordatorio

    await enviar_recordatorio(uuid.UUID(registration_id))


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
    cola y el worker, y los `failed` con reintentos disponibles: sin esto, un
    evento perdido deja dinero cobrado sin inscripción confirmada, para
    siempre."""
    from app.core.database import maintenance_session
    from app.modules.payments import repository as payments_repository

    async with maintenance_session() as session:
        pendientes = await payments_repository.eventos_para_reencolar(session)
    for event_id in pendientes:
        await process_stripe_webhook_task.kiq(event_id)


@broker.task(schedule=[{"cron": "0 3 * * *"}])
async def purge_stripe_webhook_events_task() -> None:
    """Diaria: purga `stripe_webhook_events` más antiguos que
    `stripe_webhook_retention_days`."""
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
    posterior falló: sin esto, la fila queda `submitted` para siempre y nadie
    se entera de si el dinero salió o no."""
    from app.modules.payments.refunds_service import reencolar_reembolsos_atascados

    await reencolar_reembolsos_atascados()


@broker.task(schedule=[{"cron": "*/10 * * * *"}])
async def sweep_stuck_ai_reservations_task() -> None:
    """Cada 10 minutos: cierra las reservas de gasto de IA que nadie liquidó.

    Una llamada a un proveedor aparta su coste estimado (`reservado`) antes
    de salir a la red y lo liquida al volver. Si el proceso muere en medio,
    la fila se queda apartando gasto para siempre y el límite del periodo se
    va estrechando sin que nadie sepa por qué. El barrido la marca `fallido`
    con `reserva_abandonada`: el gasto se cuenta como potencialmente
    consumido —nunca se ignora— y queda dicho que nadie confirmó qué pasó."""
    from app.modules.ai_gateway.client import cerrar_reservas_abandonadas

    await cerrar_reservas_abandonadas(minutos=get_settings().ai_reservation_stuck_minutes)


@broker.task(retry_on_error=False)
async def extraer_campos_task(draft_id: str, organization_id: str) -> None:
    """Extrae los campos de un justificante ya subido.

    `retry_on_error=False` a propósito, a diferencia de las tareas de correo:
    el reintento no lo decide taskiq sino el dominio. El cuerpo no propaga
    nunca —traduce el fallo a `error_code` en el propio borrador— y es esa
    columna la que decide si el barrido lo reencola, si espera una acción
    manual o si se queda a la vista. Un reintento ciego de taskiq encima de
    eso podría quemar cuota de IA con el límite ya agotado.

    `organization_id` viaja en la firma porque el worker no tiene petición
    HTTP y necesita fijar el contexto de RLS antes de leer nada; si no
    coincidiera con el del borrador, RLS simplemente no lo encontraría."""
    from app.modules.accounting.drafts_service import extraer_campos

    await extraer_campos(uuid.UUID(draft_id), uuid.UUID(organization_id))


@broker.task(schedule=[{"cron": "*/10 * * * *"}])
async def sweep_stuck_extractions_task() -> None:
    """Cada 10 minutos: rescata extracciones de justificantes atascadas.

    Reencola lo que lleva demasiado tiempo en `pending_extraction` (el worker
    murió entre el encolado y la escritura) y lo que falló con
    `proveedor_error`, el único código transitorio. **Nunca** reencola un
    borrador con `limite_superado`: con el presupuesto de IA todavía agotado,
    cada pasada consumiría una reserva, fallaría y llenaría
    `ai_usage_records` de filas fallidas; ese estado lo recupera el
    organizador desde el panel tras ampliar el límite. Lo que agotó sus
    intentos se escala a log `ERROR`, que es el único aviso de que hay
    justificantes esperando una acción humana."""
    from app.modules.accounting.drafts_service import reencolar_extracciones_atascadas

    await reencolar_extracciones_atascadas()


@broker.task(schedule=[{"cron": "30 3 * * *"}])
async def purge_ai_usage_records_task() -> None:
    """Diaria: purga `ai_usage_records` más antiguos que
    `ai_usage_retention_days`. Nunca borra una reserva sin cerrar: eso lo
    resuelve el barrido, y borrarla aquí escondería el gasto."""
    from app.core.database import maintenance_session
    from app.modules.ai_gateway import repository as ai_repository

    async with maintenance_session() as session:
        await ai_repository.purgar_usos_antiguos(
            session, dias=get_settings().ai_usage_retention_days
        )


@broker.task(retry_on_error=False)
async def traducir_contenido_task(organization_id: str, event_id: str | None, locale: str) -> None:
    """Traduce con IA lo pendiente de un ámbito (un evento, o lo de la
    organización si `event_id` es `None`) a un idioma.

    Sin reintentos de taskiq: los decide el dominio (`error` con espera en cada
    campo). Un reintento ciego podría gastar presupuesto de IA de más."""
    from app.core.locale import normalizar_locale
    from app.core.redis_client import get_redis
    from app.modules.translations import cola

    ambito = cola.Ambito(
        uuid.UUID(organization_id),
        uuid.UUID(event_id) if event_id else None,
        normalizar_locale(locale),
    )
    try:
        await cola.procesar(ambito)
    finally:
        # La web deja de esperar en cuanto termina, haya salido bien o no.
        try:
            await get_redis().delete(cola.marca_en_cola(ambito))
        except Exception:
            logging.getLogger(__name__).warning(
                "No se ha podido borrar la marca de traducción en cola."
            )


@broker.task(schedule=[{"cron": "* * * * *"}])
async def barrer_traducciones_task() -> None:
    """Cada minuto: encola las peticiones de traducción que llevan un rato
    quietas, con un tope por barrido para mantener un ritmo asumible."""
    from app.modules.translations import cola

    async def encolar(ambito: cola.Ambito) -> None:
        await traducir_contenido_task.kiq(
            str(ambito.organization_id),
            str(ambito.event_id) if ambito.event_id else None,
            ambito.locale,
        )

    await cola.barrer(encolar)


@broker.task(schedule=[{"cron": "45 3 * * *"}])
async def purge_unused_tag_translations_task() -> None:
    """Diaria: borra las traducciones de etiquetas que ya no lleva ningún evento
    de su organización. Las demás traducciones se borran con su fila."""
    from app.core.database import maintenance_session
    from app.modules.translations import service as translations_service

    async with maintenance_session() as session:
        await translations_service.borrar_etiquetas_sin_uso(session)


@broker.task(retry_on_error=True, max_retries=5)
async def send_waitlist_promotion_email(
    to_email: str,
    organization_id: str,
    confirm_token: str,
    cancel_token: str,
    expira_el: str,
    *,
    locale: str | None = None,
) -> None:
    """Promoción desde la lista de espera: hay que confirmar antes de `expira_el`
    (ya formateado en texto legible) o la plaza pasa a la siguiente persona."""
    idioma = _idioma_del_envio(locale)
    base = await base_url_de_organizacion(uuid.UUID(organization_id))
    enlace_confirmar = _enlace(base, idioma, "confirmar-promocion", confirm_token)
    enlace_cancelacion = _enlace(base, idioma, "cancelar-inscripcion", cancel_token)
    await _enviar(
        to_email,
        t("Se ha liberado una plaza: confirma tu inscripción"),
        t(
            "Hola,\n\n"
            "Se ha liberado una plaza y te toca a ti. Confirma tu inscripción antes "
            "del {expira_el} (hora del evento) desde este enlace:\n{enlace_confirmar}\n\n"
            "Si no confirmas a tiempo, pasaremos a la siguiente persona en la lista "
            "de espera.\n\n"
            "Si ya no quieres asistir, cancela tu inscripción aquí:\n{enlace_cancelacion}",
            expira_el=expira_el,
            enlace_confirmar=enlace_confirmar,
            enlace_cancelacion=enlace_cancelacion,
        ),
    )


@broker.task(retry_on_error=True, max_retries=5)
async def send_speaker_bio_request_email(
    to_email: str, organization_id: str, event_name: str, *, locale: str | None = None
) -> None:
    """Aviso al ponente de que el organizador necesita su ficha completa.

    El destino es su cuenta (`/dashboard/account`), donde rellena su perfil
    de ponente; no hay un formulario por evento ni un token de un solo uso.
    La persona destinataria ya tiene cuenta en la organización: el mensaje
    no crea credenciales ni enlaces de acceso, solo recuerda la tarea.
    """
    _idioma_del_envio(locale)
    base = await base_url_de_organizacion(uuid.UUID(organization_id))
    # El ancla lleva directo a la ficha de ponente dentro de la cuenta (el panel
    # no lleva prefijo de idioma).
    enlace = f"{base}/dashboard/account#ficha"
    # Nombre escrito por el organizador: sin URLs que se conviertan en el botón.
    evento = neutralizar_texto_de_usuario(event_name)
    await _enviar(
        to_email,
        t("Falta tu ficha para «{evento}»", evento=evento),
        t(
            "Hola,\n\n"
            "Para publicar el programa de «{evento}» falta completar tu ficha "
            "de ponente (biografía, titular y demás datos de perfil).\n\n"
            "Puedes completarla desde tu cuenta:\n"
            "{enlace}\n\n"
            "Si tienes cualquier duda, responde directamente a la organización.",
            evento=evento,
            enlace=enlace,
        ),
    )
