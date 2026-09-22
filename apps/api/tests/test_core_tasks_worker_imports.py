"""`app/core/tasks.py` es el punto de entrada de un proceso propio (`taskiq
worker app.core.tasks:broker`), distinto del de la API: ningún router de
`app.main` llega a importarse nunca ahí. SQLAlchemy resuelve las FK
declaradas por nombre de tabla contra `Base.metadata`, que solo se rellena
importando la clase del modelo — así que si un modelo con una FK hacia otra
tabla no está entre los imports explícitos de `tasks.py`, la primera vez que
el worker configure los mapeadores revienta con `NoReferencedTableError`.

Regresión reproducida (2026-09-22): a `tasks.py` le faltaba
`app.modules.media.models` — `Event.cover_media_id` referencia `media`, así
que CUALQUIER tarea que tocara la tabla `events` (incluida
`extraer_campos_task`, la del OCR de justificantes) reventaba en cuanto
SQLAlchemy configuraba los mapeadores. El borrador se quedaba en
`pending_extraction` para siempre: la tarea se confirmaba (`ack`) en la cola
de todos modos, así que no había ni reintento ni aviso visible.

**Por qué esto no lo detecta un test normal de la suite**: `conftest.py`
importa `app.main` (que a su vez importa todos los routers, y con ellos todos
los modelos) antes de que corra ningún test, así que `Base.metadata` ya
tiene todo registrado dentro del propio proceso de pytest — la misma
comprobación ahí nunca fallaría, esté `tasks.py` bien o mal. Por eso este
test lanza un subproceso de Python que importa **solo** `app.core.tasks`,
igual que hace de verdad `taskiq worker app.core.tasks:broker`.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[1]


def test_el_proceso_del_worker_configura_los_mapeadores_sin_reventar() -> None:
    resultado = subprocess.run(  # noqa: S603 — argv fijo, sin entrada externa
        [
            sys.executable,
            "-c",
            "import app.core.tasks\n"
            "from sqlalchemy.orm import configure_mappers\n"
            "configure_mappers()\n",
        ],
        cwd=API_DIR,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert resultado.returncode == 0, resultado.stderr
