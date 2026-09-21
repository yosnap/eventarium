"""Invariante de las dependencias de sesión: `commit` antes que las tareas de fondo.

Todo el backend da por supuesto que una `BackgroundTask` corre sobre una
transacción **ya confirmada**: el borrado del objeto anterior en
`events/router.py:upload_cover`, el del logo en `sponsors/router.py`, el del
justificante en `accounting/drafts_service.py`, y todas las auditorías que se
encolan como tarea (`roles`, `accounting`, `ai_gateway`).

Ese supuesto no lo da el `BackgroundTask`: una dependencia con `yield`
declarada sin `scope` termina *después* de enviar la respuesta, y por tanto
después de las tareas de fondo. Lo da el `scope="function"` con el que
`core/deps.py` declara la sesión. Estos tests fallan si alguien lo revierte.
"""

# Sin `from __future__ import annotations` a propósito: estos tests declaran
# endpoints dentro de la propia función de test, y con las anotaciones
# aplazadas FastAPI resolvería sus firmas contra los globales del módulo, donde
# las dependencias locales no existen (el `Depends` se perdería y el parámetro
# pasaría a leerse como query, devolviendo 422).

from collections.abc import AsyncIterator, Iterator
from typing import Annotated, Any

from fastapi import BackgroundTasks, Depends, FastAPI
from fastapi.dependencies.models import Dependant
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import SCOPE_SESION, SessionDep, get_maintenance_db, get_session
from app.main import create_app

#: Dependencias generadoras que envuelven una transacción de base de datos. Son
#: las únicas del proyecto: el resto de sesiones (`maintenance_session()`,
#: `SessionApp()` en servicios y tareas) se abren con un gestor de contexto
#: propio, fuera del grafo de dependencias de FastAPI.
GENERADORAS_DE_SESION = (get_session, get_maintenance_db)


async def test_la_sesion_confirma_antes_de_ejecutar_las_tareas_de_fondo() -> None:
    """Orden real observado en una petición: `handler` → `commit` → tarea.

    Se escucha el evento `after_commit` de la propia sesión que inyecta
    `SessionDep`, así que mide el `commit` de verdad, no una aproximación.
    """
    orden: list[str] = []
    app = FastAPI()

    @app.post("/orden")
    async def endpoint(session: SessionDep, tareas: BackgroundTasks) -> dict[str, bool]:
        orden.append("handler")
        event.listen(
            session.sync_session,
            "after_commit",
            lambda _sesion: orden.append("commit"),
        )
        tareas.add_task(orden.append, "tarea")
        return {"ok": True}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://deps.test") as http:
        respuesta = await http.post("/orden")

    assert respuesta.status_code == 200, respuesta.text
    assert orden == ["handler", "commit", "tarea"], orden


async def test_una_peticion_abre_una_sola_sesion() -> None:
    """Dos puntos de uso de la sesión en la misma petición dan la misma sesión.

    FastAPI mete el `scope` calculado en la clave de caché de la dependencia:
    declarar `get_session` con `scope` en un sitio y sin él en otro abriría
    **dos** sesiones distintas, es decir dos transacciones, y la segunda sin el
    contexto de RLS que fijó la primera.
    """
    app = FastAPI()

    async def a_traves_de_otra_dependencia(session: SessionDep) -> AsyncSession:
        return session

    @app.get("/una-sola")
    async def endpoint(
        session: SessionDep,
        indirecta: Annotated[AsyncSession, Depends(a_traves_de_otra_dependencia)],
    ) -> dict[str, bool]:
        return {"misma_sesion": session is indirecta}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://deps.test") as http:
        respuesta = await http.get("/una-sola")

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json() == {"misma_sesion": True}


def _dependencias(dependant: Dependant, vistas: set[int] | None = None) -> list[Dependant]:
    """Aplana el árbol de dependencias de una ruta."""
    vistas = set() if vistas is None else vistas
    if id(dependant) in vistas:
        return []
    vistas.add(id(dependant))
    encontradas = [dependant]
    for hija in dependant.dependencies:
        encontradas.extend(_dependencias(hija, vistas))
    return encontradas


def _rutas_con_dependant(routes: Any, vistas: set[int] | None = None) -> Iterator[Any]:
    """Recorre el árbol de rutas y devuelve las que tienen `dependant`.

    Recursivo a propósito: FastAPI ya no aplana los routers incluidos, los
    envuelve en un `_IncludedRouter` que guarda el suyo en `original_router`.
    Quedarse en el primer nivel de `app.routes` no encontraría ni una sola ruta
    de la API — de ahí la comprobación de que el recorrido ve algo.
    """
    vistas = set() if vistas is None else vistas
    for ruta in routes:
        if id(ruta) in vistas:
            continue
        vistas.add(id(ruta))
        if getattr(ruta, "dependant", None) is not None:
            yield ruta
        anidadas = getattr(ruta, "routes", None) or getattr(
            getattr(ruta, "original_router", None), "routes", None
        )
        if anidadas:
            yield from _rutas_con_dependant(anidadas, vistas)


def test_toda_dependencia_de_sesion_de_la_api_declara_scope_de_funcion() -> None:
    """Comprobación estática sobre la aplicación real, ruta por ruta.

    Cubre los alias `MaintenanceDb` que cada módulo de `admin` declara por su
    cuenta (los declara por separado a propósito, para que el test estático de
    `tests/modules/test_admin.py` siga siendo el único camino de entrada), y
    cualquier punto de uso nuevo que aparezca en el futuro.
    """
    aplicacion = create_app()
    sin_scope: list[str] = []
    revisadas = 0

    for ruta in _rutas_con_dependant(aplicacion.routes):
        for sub in _dependencias(ruta.dependant):
            if sub.call not in GENERADORAS_DE_SESION:
                continue
            revisadas += 1
            if sub.scope != SCOPE_SESION:
                nombre = getattr(sub.call, "__name__", repr(sub.call))
                sin_scope.append(f"{getattr(ruta, 'path', ruta)} → {nombre} (scope={sub.scope!r})")

    # Sin esto, el test pasaría también si dejara de encontrar rutas (por
    # ejemplo si FastAPI vuelve a cambiar cómo anida los routers incluidos).
    assert revisadas > 400, f"solo {revisadas} dependencias de sesión: el recorrido no ve la API"

    assert not sin_scope, (
        "Estas dependencias de sesión no declaran scope='function', así que sus "
        "tareas de fondo correrían antes del commit (y abrirían una segunda "
        "sesión en la misma petición):\n" + "\n".join(sorted(set(sin_scope)))
    )


def _orden_observado(scope: Any) -> list[str]:
    """Orden `handler` / salida de la dependencia / tarea de fondo, con ese `scope`.

    Usa una dependencia con `yield` de mentira, sin base de datos: lo que se
    mide es el orden que impone FastAPI, no nada de la sesión real.
    """
    orden: list[str] = []

    async def sesion_falsa() -> AsyncIterator[None]:
        try:
            yield None
        finally:
            orden.append("salida")

    app = FastAPI()

    @app.post("/x")
    async def endpoint(
        tareas: BackgroundTasks,
        _sesion: Annotated[None, Depends(sesion_falsa, scope=scope)],
    ) -> dict[str, bool]:
        orden.append("handler")
        tareas.add_task(orden.append, "tarea")
        return {"ok": True}

    with TestClient(app) as http:
        assert http.post("/x").status_code == 200
    return orden


def test_el_scope_de_funcion_es_lo_que_cambia_el_orden() -> None:
    """Falsación: sin `scope`, el orden se invierte.

    Documenta por qué existe el resto de este módulo. Si una versión futura de
    FastAPI dejara de invertir el orden, este test fallaría y avisaría de que
    los comentarios del backend sobre el `scope` ya no describen la realidad.
    """
    for scope, esperado in (
        (None, ["handler", "tarea", "salida"]),
        (SCOPE_SESION, ["handler", "salida", "tarea"]),
    ):
        assert _orden_observado(scope) == esperado, scope
