"""Límites de peticiones sobre Redis.

Ventana fija con `INCR` + `EXPIRE`: la primera petición de la ventana crea la clave y
le pone caducidad, y las siguientes solo incrementan. Basta para frenar fuerza bruta
contra el login y no necesita estructuras de datos adicionales.

La identificación del cliente usa la IP real solo cuando la petición llega por un
proxy de confianza; si no, cualquiera podría rotar `X-Forwarded-For` y saltarse el
límite.

Fail-closed: si Redis no responde no se puede contar, así que se rechaza con 503 en
lugar de dejar pasar la petición sin control.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import Depends, Request

from app.core.redis_client import require_redis
from app.core.tenant import is_trusted_proxy
from app.shared.errors import DomainError

# Límites iniciales (peticiones por minuto).
LOGIN_POR_IP = 5
REFRESH_POR_IP = 30
PUBLICO_POR_IP = 120
# El registro es de un solo uso por persona: algo más permisivo que el login.
REGISTRO_POR_IP = 10
# El reenvío es reutilizable y encola correo: más estricto, además de exigir Turnstile.
REENVIO_VERIFICACION_POR_IP = 3
# El token tiene 256 bits de entropía (no es adivinable), pero el endpoint sigue
# necesitando un tope propio para no quedar como el único público sin ninguno.
VERIFICACION_CORREO_POR_IP = 20
# Creación de organización: de un solo uso legítimo por persona, como el registro.
CREAR_ORGANIZACION_POR_IP = 10
# check-slug es solo ayuda de UX (debounce en el cliente), pero necesita su propio
# tope: sin Turnstile ni cuenta detrás, es el candidato más fácil a escaneo.
CHECK_SLUG_POR_IP = 30
# Mismo riesgo de *email bombing* que el reenvío de verificación: reutilizable y
# encola correo, con Turnstile obligatorio delante.
FORGOT_PASSWORD_POR_IP = 3
# «Pedir bio» a un ponente es una acción manual de panel que encola correo:
# un bucle de cliente sobre ella sería la vía más directa a email bombing.
PEDIR_BIO_POR_IP = 5
# El token tiene 256 bits de entropía, pero el endpoint necesita su propio tope, igual
# que verify-email.
RESET_PASSWORD_POR_IP = 20
# Inscripción a un evento: de un solo uso legítimo por persona y evento, como el
# registro de cuentas.
INSCRIPCION_POR_IP = 10
# Mismo razonamiento que verify-email: el token tiene entropía de sobra, pero el
# endpoint necesita su propio tope por ser público.
VERIFICACION_INSCRIPCION_POR_IP = 20
# Confirmación de una promoción de lista de espera: mismo razonamiento que
# verify-email, token con entropía de sobra pero tope propio por ser público.
CONFIRMACION_PROMOCION_POR_IP = 20
# Autocancelación: mismo razonamiento que confirm-waitlist-promotion.
CANCELACION_INSCRIPCION_POR_IP = 20
# Invitación de equipo (fase 2 del plan de invitaciones): mismo razonamiento
# que verify-email/reset-password, un tope propio para el GET (consulta el
# estado) y otro para el POST (consume el token).
INVITACION_CONSULTA_POR_IP = 30
INVITACION_ACEPTAR_POR_IP = 20
# `/mi-entrada` (fase 4 del PRD): a diferencia de verify/cancel, es un enlace
# pensado para volver a visitarlo varias veces, no de un solo uso — mismo
# tope que el resto de endpoints públicos con token de sobra entropía.
MI_ENTRADA_POR_IP = 20
# Páginas legales (fase 5 del PRD): lectura pública sin token, mismo tope que
# el resto de contenido público de solo lectura.
LEGAL_PAGES_POR_IP = PUBLICO_POR_IP
# Identificadores públicos de analítica (fase 1 del plan de cookies):
# mismo nivel de exposición que el propio HTML que los cargaría.
ANALITICA_POR_IP = PUBLICO_POR_IP
# El banner de cookies llama a este endpoint como mucho una vez por decisión
# real (aceptar/rechazar/personalizar); más permisivo que el registro porque
# no encola correo ni consume ningún recurso escaso, pero sigue necesitando
# su propio tope por ser público y sin Turnstile delante.
COOKIE_CONSENT_POR_IP = 30
# Superadministración (fase 5 del PRD): `admin/router.py` era el único módulo
# de la API sin ningún límite de peticiones — un token de superadmin robado
# sin tope permitiría iterar la exportación RGPD sobre todos los eventos de
# todas las organizaciones sin fricción.
AUDIT_LOG_POR_IP = 30
RGPD_EXPORT_POR_IP = 10
RGPD_DELETE_POR_IP = 10
# Impersonación: abre acceso a la cuenta y los datos de otra persona, así que
# lleva tope propio y bajo — una sesión de administrador robada no debe poder
# suplantar en masa. Va junto a los de RGPD, que son la operación más parecida
# en sensibilidad.
IMPERSONATION_POR_IP = 5
# Sincronización manual de Stripe (fase 6 del PRD): es la única ruta del
# panel que provoca una llamada de red a Stripe por petición, así que lleva
# un tope propio distinto del resto de escrituras de pagos.
STRIPE_SYNC_POR_IP = 20
# Presupuesto público de compra (fase 6 del PRD, fase 3 de trabajo): sin
# Turnstile ni cuenta detrás, es el candidato más fácil a enumerar códigos de
# descuento por fuerza bruta — mismo tope que `check-slug`, otro endpoint de
# solo lectura sin más protección que este límite y Turnstile.
CHECKOUT_QUOTE_POR_IP = 30
# Catálogo de modelos en vivo: provoca una llamada saliente al proveedor por
# cada entrada que no esté en caché, así que necesita tope propio aunque la
# caché absorba la mayoría. Permisivo porque el panel lo pide cada vez que se
# cambia el desplegable de proveedor, y son siete.
AI_MODELOS_EN_VIVO_POR_IP = 30
# Prueba de conexión: cada petición es sí o sí una llamada saliente (no se
# cachea: comprueba la credencial de ahora mismo) y, en `custom`, hacia un
# host que escribe quien la pide. Tope bajo, del orden de `IMPERSONATION`:
# pulsar «Probar conexión» es una acción manual, no un bucle.
AI_TEST_CONNECTION_POR_IP = 10
# Prueba del proveedor de correo: cada una es un correo real saliente. Más
# bajo que el de IA: basta para corregir una credencial, no para usar la
# instalación de relay.
EMAIL_TEST_POR_IP = 3
# Cambio de organización activa (fase 1 del plan de organización sin
# dominio): emite un token nuevo tras comprobar pertenencia, mismo orden de
# magnitud que el propio login — no hay ningún motivo legítimo para cambiar
# de organización muchas veces por minuto.
SWITCH_ORGANIZATION_POR_IP = 20
# Plan «mis-eventos-asistente»: encola correo, mismo perfil de riesgo que
# `forgot-password` (email bombing) — mismo tope, con Turnstile obligatorio
# delante igual que allí (hallazgo de code-review, Fase 3: la primera
# redacción de este límite no llevaba Turnstile pese al comentario, lo que
# hacía el ataque mucho más barato que contra `forgot-password`).
MIS_EVENTOS_SOLICITAR_POR_IP = FORGOT_PASSWORD_POR_IP
# Consulta del listado: el token tiene entropía de sobra, pero el endpoint
# necesita su propio tope por ser público, igual que verify-email.
MIS_EVENTOS_VER_POR_IP = 20

# Servidor MCP: se cuenta **cada uso de herramienta** de una conexión, no
# cada petición HTTP (una sola petición Streamable HTTP puede llevar varias
# llamadas). Holgado para un asistente que prepara un evento completo, corto
# para uno que ha entrado en bucle.
MCP_HERRAMIENTAS_POR_CONEXION = 120
# Y por IP antes de autenticar, para que nadie pueda probar claves sin tope.
# Holgado a propósito: Claude y ChatGPT conectan desde las IP de su nube,
# compartidas por muchas personas; el límite fino es el de cada conexión.
MCP_POR_IP = 600

VENTANA_SEGUNDOS = 60


class TooManyRequestsError(DomainError):
    status_code = 429
    title = "Demasiadas peticiones"


def client_ip(request: Request) -> str:
    """IP real del cliente, teniendo en cuenta el proxy de confianza."""
    directa = request.client.host if request.client else "desconocida"
    if is_trusted_proxy(directa):
        reenviada = request.headers.get("x-forwarded-for")
        if reenviada:
            return reenviada.split(",")[0].strip()
    return directa


def identify_by_ip(request: Request) -> str:
    return f"ip:{client_ip(request)}"


async def _consumir(clave: str, veces: int, segundos: int) -> None:
    redis = await require_redis()
    async with redis.pipeline(transaction=True) as tuberia:
        tuberia.incr(clave)
        tuberia.expire(clave, segundos, nx=True)
        resultado = await tuberia.execute()

    consumidas = int(resultado[0])
    if consumidas > veces:
        restante = await redis.ttl(clave)
        raise TooManyRequestsError(
            "Has superado el límite de peticiones. Inténtalo de nuevo en unos instantes.",
            extra={"retry_after": max(1, restante)},
        )


def _limite(
    nombre: str,
    identificador: Callable[[Request], str],
    veces: int,
    segundos: int,
) -> Callable[[Request], Awaitable[None]]:
    async def dependencia(request: Request) -> None:
        await _consumir(f"ratelimit:{nombre}:{identificador(request)}", veces, segundos)

    return dependencia


# `Depends(...)` devuelve un marcador de FastAPI que no es utilizable como anotación
# de tipo, así que estas fábricas se declaran como `Any`.
def limit_per_ip(nombre: str, veces: int, segundos: int = VENTANA_SEGUNDOS) -> Any:
    """Límite por IP de origen."""
    return Depends(_limite(nombre, identify_by_ip, veces, segundos))


async def consumir_por_conexion_mcp(connection_id: str) -> None:
    """Límite por conexión MCP, llamado por cada uso de herramienta."""
    await _consumir(
        f"ratelimit:mcp:conexion:{connection_id}", MCP_HERRAMIENTAS_POR_CONEXION, VENTANA_SEGUNDOS
    )


async def consumir_mcp_por_ip(request: Request) -> None:
    """Límite por IP de `/mcp`, antes de autenticar (ver `main.py`)."""
    await _consumir(f"ratelimit:mcp:{identify_by_ip(request)}", MCP_POR_IP, VENTANA_SEGUNDOS)
