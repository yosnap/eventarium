"""Fijaciones compartidas de los tests de la pasarela de IA.

Registrado como plugin en `conftest.py` (mismo patrón que
`payments_test_helpers.py`) para que cada módulo de test no tenga que
importar las fijaciones por nombre.

La clave de cifrado la ponen **los tests**, nunca el entorno: el `.env` de
integración continua no define `AI_SETTINGS_ENCRYPTION_KEY`, así que un test
que dependiera de la del entorno pasaría en local y fallaría en CI.

Ningún test de este módulo sale a Internet ni usa una clave real:

- `proveedor_simulado` sustituye el transporte HTTP de LiteLLM por un
  `httpx.MockTransport`, así que la petición se construye entera (URL,
  cabecera `Authorization`, cuerpo) y se inspecciona sin salir de proceso.
  Es el equivalente del cliente simulado de `payments/stripe_client.py`.
- `dns_publico` sustituye la resolución DNS de la validación SSRF: sin ella,
  revalidar `api_base` en cada llamada resolvería de verdad el host del
  proveedor, y la suite dejaría de poder ejecutarse sin red.
- Las claves son literales falsos (`sk-…`), nunca variables de entorno.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import httpx
import pytest
from cryptography.fernet import Fernet
from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import SessionMaintenance
from app.modules.ai_gateway import validacion
from app.modules.ai_gateway.crypto import cifrar_clave, pista_de_clave
from app.modules.ai_gateway.models import (
    ID_FILA_DE_PLATAFORMA,
    OrganizationAiSettings,
    PlatformAiSettings,
)
from app.modules.users.models import User
from tests.conftest import OrganizacionDePrueba, iniciar_sesion

#: Clave Fernet fija de la suite. Generada una vez por ejecución: no es un
#: secreto real y no sale de la base de datos de tests.
CLAVE_DE_CIFRADO = Fernet.generate_key().decode()

#: Clave de proveedor de ejemplo. Formato de NaN (`sk-…`), aunque el backend
#: no valida el prefijo de ningún proveedor a propósito.
CLAVE_DE_PROVEEDOR = "sk-clave-de-prueba-0000-1234"


@pytest.fixture
def cifrado(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """Instalación con cifrado configurado."""
    monkeypatch.setenv("AI_SETTINGS_ENCRYPTION_KEY", CLAVE_DE_CIFRADO)
    get_settings.cache_clear()
    yield CLAVE_DE_CIFRADO
    get_settings.cache_clear()


@pytest.fixture
def sin_cifrado(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Instalación sin `AI_SETTINGS_ENCRYPTION_KEY`."""
    monkeypatch.setenv("AI_SETTINGS_ENCRYPTION_KEY", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def hacer_superadmin(email: str) -> None:
    async with SessionMaintenance() as session:
        usuario = await session.scalar(select(User).where(User.email == email))
        assert usuario is not None
        usuario.is_superadmin = True
        await session.commit()


async def cabeceras_de_superadmin(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> dict[str, str]:
    """Promociona al propietario de la organización y devuelve sus cabeceras."""
    await hacer_superadmin(organizacion.owner_email)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    return cabeceras


# --- Configuración sembrada directamente (fase 2) -----------------------------


async def configurar_plataforma(
    *,
    provider: str = "nan_builders",
    default_model: str = "deepseek-v4-flash",
    clave: str = CLAVE_DE_PROVEEDOR,
    api_base: str | None = None,
    techo_usd: Decimal | None = None,
) -> None:
    """Deja la configuración por defecto de la instalación lista para usar.

    Escribe la fila directamente con el rol de mantenimiento en vez de pasar
    por el `PUT` del admin: los tests de esta fase prueban `completar`, no el
    endpoint de configuración, que ya tiene los suyos en la fase 1.
    """
    async with SessionMaintenance() as session:
        fila = await session.get(PlatformAiSettings, ID_FILA_DE_PLATAFORMA)
        if fila is None:
            fila = PlatformAiSettings(id=ID_FILA_DE_PLATAFORMA)
            session.add(fila)
        fila.provider = provider
        fila.default_model = default_model
        fila.api_base = api_base
        fila.api_key_encrypted = cifrar_clave(clave)
        fila.api_key_hint = pista_de_clave(clave)
        fila.monthly_ceiling_usd = techo_usd
        await session.commit()


async def configurar_organizacion(
    organization_id: uuid.UUID,
    *,
    provider: str = "openrouter",
    default_model: str = "openai/gpt-4o-mini",
    clave: str = CLAVE_DE_PROVEEDOR,
    api_base: str | None = None,
    limite_usd: Decimal | None = None,
) -> None:
    """Crea (o sustituye) el override de configuración de una organización."""
    async with SessionMaintenance() as session:
        fila = await session.get(OrganizationAiSettings, organization_id)
        if fila is None:
            fila = OrganizationAiSettings(
                organization_id=organization_id,
                provider=provider,
                default_model=default_model,
                api_key_encrypted=cifrar_clave(clave),
                api_key_hint=pista_de_clave(clave),
            )
            session.add(fila)
        fila.provider = provider
        fila.default_model = default_model
        fila.api_base = api_base
        fila.api_key_encrypted = cifrar_clave(clave)
        fila.api_key_hint = pista_de_clave(clave)
        fila.monthly_limit_usd = limite_usd
        await session.commit()


# --- Proveedor simulado (mock HTTP, sin red) ----------------------------------


@dataclass(slots=True)
class PeticionCapturada:
    """Lo que habría salido de verdad hacia el proveedor."""

    url: str
    authorization: str | None
    cuerpo: dict[str, Any]


def respuesta_de_chat(
    *,
    contenido: str = "respuesta simulada",
    model: str = "modelo-sin-precio-conocido",
    prompt_tokens: int = 10,
    completion_tokens: int = 3,
) -> dict[str, Any]:
    """Cuerpo de una respuesta OpenAI-compatible correcta.

    El `model` por defecto es uno que **no** está en el mapa de precios de
    LiteLLM a propósito: el coste que calcula LiteLLM sale del modelo que
    devuelve el proveedor, no del que se pidió, así que un nombre conocido
    por defecto haría auditable hasta el gasto de un gateway que en
    producción nunca lo es. Los tests que necesitan un coste real pasan un
    modelo del mapa explícitamente.
    """
    return {
        "id": "chatcmpl-simulada",
        "object": "chat.completion",
        "created": 1,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": contenido},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


@dataclass(slots=True)
class ProveedorSimulado:
    """Transporte HTTP falso: registra lo que sale y decide lo que entra."""

    peticiones: list[PeticionCapturada] = field(default_factory=list)
    estado: int = 200
    cuerpo: dict[str, Any] = field(default_factory=respuesta_de_chat)
    #: Retardo artificial de la «llamada de red», en segundos. Lo usa el test
    #: que comprueba que el bloqueo de la reserva no se retiene durante ella.
    retardo_s: float = 0.0

    async def _manejar(self, peticion: httpx.Request) -> httpx.Response:
        import json

        self.peticiones.append(
            PeticionCapturada(
                url=str(peticion.url),
                authorization=peticion.headers.get("authorization"),
                cuerpo=json.loads(peticion.content or b"{}"),
            )
        )
        if self.retardo_s:
            await asyncio.sleep(self.retardo_s)
        return httpx.Response(self.estado, json=self.cuerpo)

    @property
    def ultima(self) -> PeticionCapturada:
        assert self.peticiones, "el proveedor simulado no recibió ninguna petición"
        return self.peticiones[-1]


@pytest.fixture
def proveedor_simulado(monkeypatch: pytest.MonkeyPatch) -> Iterator[ProveedorSimulado]:
    """Sustituye el transporte HTTP de LiteLLM por un `MockTransport`.

    Hay que interceptar en **dos** sitios porque LiteLLM tiene dos caminos de
    salida: la ruta `openai/...` (que usa el SDK de OpenAI y su
    `litellm.aclient_session`) y las rutas propias como `openrouter/...` (que
    usan su `AsyncHTTPHandler`). Con uno solo, la mitad de los tests de mapeo
    saldría a Internet de verdad.

    La caché de clientes de LiteLLM se vacía antes y después: si no, un test
    reutilizaría el cliente ya construido por el anterior y sus peticiones se
    registrarían en el proveedor simulado equivocado.
    """
    from app.modules.ai_gateway import client as ai_client

    # Primero el cargador del módulo y después cualquier `import litellm`: es
    # ese primer import el que decide si el mapa de precios se descarga de
    # Internet o sale de la copia local, y la suite no sale a la red.
    litellm = ai_client._litellm()

    from litellm.llms.custom_httpx import http_handler

    simulado = ProveedorSimulado()

    def _crear_cliente(*_args: Any, **_kwargs: Any) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(simulado._manejar))

    litellm.in_memory_llm_clients_cache.flush_cache()
    monkeypatch.setattr(http_handler.AsyncHTTPHandler, "create_client", _crear_cliente)
    monkeypatch.setattr(litellm, "aclient_session", _crear_cliente())
    yield simulado
    litellm.in_memory_llm_clients_cache.flush_cache()


@pytest.fixture
def dns_publico(monkeypatch: pytest.MonkeyPatch) -> None:
    """La validación SSRF resuelve a una IP pública, sin consultar DNS real.

    `completar` revalida el `api_base` en cada llamada (el DNS puede cambiar
    entre guardar y usar). Sin esta fijación, la suite necesitaría resolver
    de verdad los hosts de los proveedores.
    """
    monkeypatch.setattr(validacion, "_resolver", lambda _host: ["93.184.216.34"])


@pytest.fixture
def dns_interno(monkeypatch: pytest.MonkeyPatch) -> None:
    """Simula un host de proveedor secuestrado hacia la red interna."""
    monkeypatch.setattr(validacion, "_resolver", lambda _host: ["10.0.0.5"])
