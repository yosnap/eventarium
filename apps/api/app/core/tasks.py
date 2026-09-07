"""Cola de tareas asíncronas sobre Redis Streams.

Se usa `RedisStreamBroker` y no `ListQueueBroker` porque el primero confirma los
mensajes (`ack`) y permite reintentos: una tarea perdida por un reinicio del worker
no puede desaparecer sin rastro.
"""

from __future__ import annotations

from taskiq import TaskiqEvents, TaskiqState
from taskiq.schedule_sources import LabelScheduleSource
from taskiq.scheduler.scheduler import TaskiqScheduler
from taskiq_redis import RedisAsyncResultBackend, RedisStreamBroker

from app.core.cleanup import sweep_unverified_accounts
from app.core.config import get_settings
from app.core.email import get_email_provider

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
