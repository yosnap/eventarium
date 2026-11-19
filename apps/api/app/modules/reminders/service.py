"""Selección, reclamación y envío del recordatorio a los inscritos.

Cada 10 minutos se reclaman por lotes las inscripciones a las que ya les toca
(`reminder_claimed_at`), con `SKIP LOCKED` para que dos ejecuciones no se
pisen, y se encola el envío de cada una tras el commit. El envío vuelve a
comprobarlo todo (la inscripción o el evento pueden haber cambiado mientras
esperaba en la cola), manda el correo y marca el recordatorio como enviado
para la fecha actual del evento.

Semántica: como mucho un recordatorio por fecha del evento. Una reclamación
que no llega a enviarse (cola o SMTP caídos) vuelve a ser elegible a los 30
minutos; un correo que el proveedor acepta sin que se llegue a marcar como
enviado puede repetirse (riesgo aceptado, como el resto de correos).
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, text

from app.core.config import get_settings
from app.core.database import maintenance_session
from app.core.email import get_email_provider
from app.core.locale import fijar_idioma, normalizar_locale, ruta_web
from app.core.tenant import base_url_de_organizacion
from app.modules.events.models import Event
from app.modules.payments import refunds_service
from app.modules.registrations.models import EventRegistration
from app.modules.reminders.correo import DatosDelRecordatorio, asunto_y_cuerpo
from app.modules.tickets.service import adjunto_qr, emitir_entrada, generar_token_qr

logger = logging.getLogger(__name__)

TAMANO_DE_LOTE = 200
# Margen para no pisar la siguiente ejecución del cron (cada 10 minutos).
TIEMPO_MAXIMO_POR_EJECUCION = timedelta(minutes=8)
# Una tarea retrasada no avisa a destiempo: con menos de esto no se envía.
MARGEN_MINIMO = timedelta(minutes=60)

# Parte de los eventos (cota indexable de 72 h, el máximo del desplegable) y
# después aplica la ventana exacta de cada uno.
_RECLAMAR = text(
    """
    WITH candidatas AS (
        SELECT r.id
        FROM event_registrations r
        JOIN events e ON e.id = r.event_id AND e.organization_id = r.organization_id
        JOIN organizations o ON o.id = e.organization_id AND o.is_active
        WHERE e.status = 'published'
          AND e.deleted_at IS NULL
          AND e.reminder_enabled
          AND e.starts_at > now() + interval '60 minutes'
          AND e.starts_at <= now() + interval '72 hours'
          AND e.starts_at - make_interval(hours => e.reminder_hours_before) <= now()
          AND r.status = 'confirmed'
          AND COALESCE(r.confirmed_at, r.created_at)
              < e.starts_at - make_interval(hours => e.reminder_hours_before)
          AND r.reminder_sent_for_starts_at IS DISTINCT FROM date_trunc('minute', e.starts_at)
          AND (r.reminder_claimed_at IS NULL
               OR r.reminder_claimed_at < now() - interval '30 minutes')
        ORDER BY e.starts_at
        LIMIT :limite
        FOR UPDATE OF r SKIP LOCKED
    )
    UPDATE event_registrations r
    SET reminder_claimed_at = now()
    FROM candidatas c
    WHERE r.id = c.id
    RETURNING r.id
    """
)


async def reclamar_lote(limite: int | None = None) -> list[uuid.UUID]:
    async with maintenance_session() as session:
        filas = await session.execute(_RECLAMAR, {"limite": limite or TAMANO_DE_LOTE})
        return [fila[0] for fila in filas]


async def procesar_recordatorios() -> int:
    """`dispatch_event_reminders_task`: reclama lotes hasta vaciar o agotar el
    tiempo, y encola el envío de cada inscripción reclamada. Devuelve cuántas."""
    from app.core.tasks import send_event_reminder_task

    total = 0
    limite_de_tiempo = time.monotonic() + TIEMPO_MAXIMO_POR_EJECUCION.total_seconds()
    while True:
        lote = await reclamar_lote()
        # Tras el commit de la reclamación: si encolar falla, la reclamación
        # caduca a los 30 minutos y la inscripción se vuelve a intentar.
        for registration_id in lote:
            try:
                await send_event_reminder_task.kiq(str(registration_id))
            except Exception:
                logger.exception("No se pudo encolar el recordatorio de %s.", registration_id)
        total += len(lote)
        if len(lote) < TAMANO_DE_LOTE or time.monotonic() >= limite_de_tiempo:
            return total


async def enviar_recordatorio(registration_id: uuid.UUID) -> bool:
    """Envía el recordatorio de una inscripción reclamada. Devuelve si se envió.

    No se envía si, mientras esperaba en la cola, la inscripción dejó de estar
    confirmada, el evento dejó de estar publicado o desactivó el recordatorio,
    faltan menos de 60 minutos, o ya se envió para la fecha actual.
    """
    from app.core.tasks import limpiar_asunto
    from app.modules.registrations.avisos import _generar_token_cancelacion  # noqa: SLF001

    async with maintenance_session() as session:
        inscripcion = await session.get(EventRegistration, registration_id)
        evento = await session.get(Event, inscripcion.event_id) if inscripcion else None
        if inscripcion is None or evento is None:
            return False
        inicio_al_minuto = evento.starts_at.replace(second=0, microsecond=0)
        ahora = datetime.now(UTC)
        if (
            inscripcion.status != "confirmed"
            or evento.status != "published"
            or evento.deleted_at is not None
            or not evento.reminder_enabled
            or evento.starts_at - ahora < MARGEN_MINIMO
            # Si se aplazó mientras esperaba en la cola, aún no le toca.
            or evento.starts_at - timedelta(hours=evento.reminder_hours_before) > ahora
            or inscripcion.reminder_sent_for_starts_at == inicio_al_minuto
        ):
            inscripcion.reminder_claimed_at = None
            return False

        # Inscripciones anteriores a las entradas QR: se emite ahora (idempotente).
        ticket = await emitir_entrada(session, inscripcion)
        qr = generar_token_qr(ticket) if ticket.revoked_at is None else None
        cancel_token = await _generar_token_cancelacion(inscripcion.id)
        reembolso = await refunds_service.reembolso_si_se_cancela(
            session,
            organization_id=inscripcion.organization_id,
            event_id=evento.id,
            registration_id=inscripcion.id,
        )
        en_espera = await session.scalar(
            select(func.count())
            .select_from(EventRegistration)
            .where(
                EventRegistration.organization_id == evento.organization_id,
                EventRegistration.event_id == evento.id,
                EventRegistration.status == "waitlisted",
            )
        )
        base = await base_url_de_organizacion(evento.organization_id)
        idioma = normalizar_locale(inscripcion.locale)
        datos = DatosDelRecordatorio(
            titulo=evento.title,
            inicio=evento.starts_at,
            zona=evento.timezone,
            modalidad=evento.location_mode,
            lugar=evento.location_name,
            direccion=evento.location_address,
            ciudad=evento.city,
            # Sin saltos de línea: no puede inventar párrafos en el correo.
            url_online=" ".join(evento.online_url.split()) if evento.online_url else None,
            enlace_mi_entrada=f"{base}{ruta_web(idioma, 'mi-entrada')}?token={cancel_token}",
            enlace_cancelacion=(
                f"{base}{ruta_web(idioma, 'cancelar-inscripcion')}?token={cancel_token}"
            ),
            hay_lista_de_espera=bool(en_espera),
            con_qr=qr is not None,
            reembolso=reembolso,
            limite_de_reembolso=evento.starts_at
            - timedelta(hours=get_settings().payment_refund_cutoff_hours),
            idioma=idioma,
        )
        destinatario = inscripcion.email

    # El pie y el botón de la plantilla salen en el idioma del contexto.
    fijar_idioma(idioma)
    asunto, cuerpo = asunto_y_cuerpo(datos)
    await get_email_provider().send(
        to=destinatario,
        subject=limpiar_asunto(asunto),
        body=cuerpo,
        attachments=[adjunto_qr(qr)] if qr is not None else [],
    )

    async with maintenance_session() as session:
        inscripcion = await session.get(EventRegistration, registration_id, with_for_update=True)
        if inscripcion is not None:
            inscripcion.reminder_sent_at = datetime.now(UTC)
            inscripcion.reminder_sent_for_starts_at = inicio_al_minuto
            inscripcion.reminder_claimed_at = None
    return True
