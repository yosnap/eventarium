"""Cola de tareas asíncronas sobre Redis Streams.

Se usa `RedisStreamBroker` y no `ListQueueBroker` porque el primero confirma los
mensajes (`ack`) y permite reintentos: una tarea perdida por un reinicio del worker
no puede desaparecer sin rastro.
"""

from __future__ import annotations

from taskiq import TaskiqEvents, TaskiqState
from taskiq_redis import RedisAsyncResultBackend, RedisStreamBroker

from app.core.config import get_settings

_settings = get_settings()

result_backend: RedisAsyncResultBackend[object] = RedisAsyncResultBackend(
    redis_url=_settings.redis_url,
    result_ex_time=60 * 60,
)

broker = RedisStreamBroker(url=_settings.redis_url).with_result_backend(result_backend)


@broker.on_event(TaskiqEvents.WORKER_STARTUP)
async def _al_arrancar(state: TaskiqState) -> None:
    state.entorno = _settings.app_env


@broker.task(retry_on_error=True, max_retries=5)
async def ping(mensaje: str = "pong") -> str:
    """Tarea mínima de verificación de la cola."""
    return mensaje
