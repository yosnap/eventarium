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
    """Escribe `contenido` en `ruta_relativa` para que ruff lo analice por su
    ruta real (el `per-file-ignores` de `TID251` empareja por ruta exacta), y
    restaura el estado previo del fichero al terminar. `stripe_client.py` es
    un fichero real del repo, no un fichero de prueba desechable: borrarlo con
    `unlink` en el `finally` (como hacía antes) lo eliminaba del disco de
    verdad en cada ejecución de la suite.
    """
    ruta = API_DIR / ruta_relativa
    ruta.parent.mkdir(parents=True, exist_ok=True)
    contenido_previo = ruta.read_text(encoding="utf-8") if ruta.exists() else None
    ruta.write_text(contenido, encoding="utf-8")
    try:
        return subprocess.run(  # noqa: S603 — argv fijo, sin entrada externa
            [sys.executable, "-m", "ruff", "check", str(ruta)],
            cwd=API_DIR,
            capture_output=True,
            text=True,
        )
    finally:
        if contenido_previo is None:
            ruta.unlink(missing_ok=True)
        else:
            ruta.write_text(contenido_previo, encoding="utf-8")


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
