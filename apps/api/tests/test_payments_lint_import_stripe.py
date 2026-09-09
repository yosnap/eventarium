"""`import stripe` está confinado a `app/modules/payments/stripe_client.py`
(fase 6 del PRD, decisión #7 del plan): ninguna otra función de servicio
importa el SDK directamente, así que el `acct_id` de destino siempre pasa por
la resolución de ese único fichero. Verificado ejecutando `ruff` sobre un
fichero de prueba con ese import, no solo por revisión.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[1]


def _ejecutar_ruff_sobre(contenido: str, ruta_relativa: str) -> subprocess.CompletedProcess[str]:
    """Pasa `contenido` a `ruff check` por `stdin`, con `--stdin-filename
    <ruta_relativa>` para que el `per-file-ignores` de `TID251` empareje por
    esa ruta exacta — sin escribir nunca sobre el fichero real (hallazgo S1
    del code review de la fase 6, ronda 3): la versión anterior escribía
    sobre `app/modules/payments/stripe_client.py` de verdad y lo restauraba
    en el `finally`, así que un crash a mitad del `subprocess.run` (o de la
    propia sesión de pruebas) podía dejarlo corrupto en disco. Verificado que
    `ruff` soporta este modo (`ruff check --stdin-filename <ruta> -`, rc=0
    para un import permitido por `per-file-ignores`, rc=1 con `TID251` para
    cualquier otra ruta).
    """
    return subprocess.run(  # noqa: S603 — argv fijo, sin entrada externa
        [sys.executable, "-m", "ruff", "check", "--stdin-filename", ruta_relativa, "-"],
        cwd=API_DIR,
        input=contenido,
        capture_output=True,
        text=True,
    )


def test_import_stripe_fuera_del_wrapper_falla_el_lint() -> None:
    resultado = _ejecutar_ruff_sobre(
        "import stripe\n\nprint(stripe)\n",
        "app/modules/payments/_probeta_lint.py",
    )
    assert resultado.returncode != 0
    assert "TID251" in resultado.stdout


def test_import_stripe_dentro_del_wrapper_no_falla_el_lint() -> None:
    """`stripe_client.py` es el único fichero con `per-file-ignores` para
    `TID251` — la fase 2 de trabajo lo crea con contenido real; aquí solo se
    confirma que la regla de lint no bloquearía ese fichero en concreto."""
    resultado = _ejecutar_ruff_sobre(
        "import stripe\n\nprint(stripe)\n",
        "app/modules/payments/stripe_client.py",
    )
    assert "TID251" not in resultado.stdout
