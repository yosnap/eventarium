"""Catálogo de idiomas soportados por la cuenta de usuario.

Vive en `app.core`, no en `app.modules.users.schemas` (dueño natural de la columna
`users.locale`): `users.schemas` ya importa de `organizations.schemas`
(`SLUG_PATTERN`, `PublicOrganizationRef`), así que si el alias viviera en `users.schemas`,
que `organizations.schemas` lo importara de vuelta (`InvitationAcceptRequest`)
cerraría un ciclo. `app.core` es el único punto neutral que `auth`, `organizations` y
`users` ya pueden importar sin crear una dependencia nueva entre módulos de dominio —
mismo patrón que `Environment` en `app.core.config`.

Espejo en el frontend: `apps/web/src/app/core/i18n/locale-de-cuenta.ts`
(`LOCALES_DE_CUENTA`). Ampliar los dos a la vez.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Annotated, Final, Literal, cast, get_args

from fastapi import Depends
from starlette.types import ASGIApp, Receive, Scope, Send

Locale = Literal["es-ES", "en-US"]
DEFAULT_LOCALE: Locale = "es-ES"
LOCALES: Final[tuple[Locale, ...]] = get_args(Locale)

#: Idioma de la petición en curso. Fuera de una petición (tareas, scripts) vale el
#: idioma por defecto: quien envía un correo o genera un documento en segundo plano
#: debe pasar el idioma del destinatario de forma explícita.
_idioma_actual: ContextVar[Locale] = ContextVar("idioma_actual", default=DEFAULT_LOCALE)


def buscar_locale(valor: str | None) -> Locale | None:
    """Idioma del catálogo que corresponde a `valor`, o `None` si no hay ninguno.

    Acepta el código completo (`en-US`) en cualquier capitalización y también el
    idioma sin región (`en`), que es lo que mandan muchos navegadores.
    """
    if not valor:
        return None
    buscado = valor.strip().lower()
    for locale in LOCALES:
        if buscado == locale.lower():
            return locale
    idioma = buscado.split("-", 1)[0]
    for locale in LOCALES:
        if locale.split("-", 1)[0].lower() == idioma:
            return locale
    return None


def normalizar_locale(valor: str | None) -> Locale:
    """Como `buscar_locale`, pero con el idioma por defecto si no hay coincidencia."""
    return buscar_locale(valor) or DEFAULT_LOCALE


def resolver_accept_language(cabecera: str | None) -> Locale:
    """Elige el idioma del catálogo con mayor peso `q` en `Accept-Language`.

    Sin cabecera, o sin ningún idioma del catálogo en ella, el de por defecto. Los
    clientes que no la mandan (el servidor MCP, integraciones) reciben español.
    """
    if not cabecera:
        return DEFAULT_LOCALE
    candidatos: list[tuple[float, int, Locale]] = []
    for posicion, parte in enumerate(cabecera.split(",")[:20]):
        trozos = [t.strip() for t in parte.split(";")]
        etiqueta = trozos[0]
        if not etiqueta or etiqueta == "*":
            continue
        peso = 1.0
        for parametro in trozos[1:]:
            if parametro.startswith("q="):
                try:
                    peso = float(parametro[2:])
                except ValueError:
                    peso = 0.0
        locale = buscar_locale(etiqueta)
        if locale is not None and peso > 0:
            # A igual peso gana el que aparece antes: se ordena por posición.
            candidatos.append((-peso, posicion, locale))
    if not candidatos:
        return DEFAULT_LOCALE
    return min(candidatos)[2]


def idioma_actual() -> Locale:
    return _idioma_actual.get()


def fijar_idioma(locale: Locale) -> None:
    """Fija el idioma del contexto actual (tareas en segundo plano y tests)."""
    _idioma_actual.set(locale)


def resolver_idioma_de_peticion(parametro: str | None, accept_language: str | None) -> Locale:
    """`?idioma=` (enlaces y depuración) manda sobre `Accept-Language`."""
    return buscar_locale(parametro) or resolver_accept_language(accept_language)


class IdiomaMiddleware:
    """Resuelve el idioma de cada petición HTTP y lo deja en el contexto.

    Middleware ASGI puro (no `BaseHTTPMiddleware`): el `ContextVar` se fija en el
    mismo contexto en el que se ejecutan las dependencias, el endpoint y los
    manejadores de errores, que así responden en el idioma de quien pregunta.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        accept_language: str | None = None
        for nombre, valor in scope.get("headers", []):
            if nombre == b"accept-language":
                accept_language = valor.decode("latin-1")
                break
        parametro: str | None = None
        consulta = cast(bytes, scope.get("query_string", b"")).decode("latin-1")
        for par in consulta.split("&"):
            clave, _, valor_param = par.partition("=")
            if clave == "idioma":
                parametro = valor_param
                break
        token = _idioma_actual.set(resolver_idioma_de_peticion(parametro, accept_language))
        try:
            await self.app(scope, receive, send)
        finally:
            _idioma_actual.reset(token)


def _idioma_de_la_peticion() -> Locale:
    return idioma_actual()


#: Idioma de la petición para los endpoints que lo necesitan de forma explícita.
IdiomaDep = Annotated[Locale, Depends(_idioma_de_la_peticion)]
