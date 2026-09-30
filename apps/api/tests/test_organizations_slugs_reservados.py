"""Los identificadores reservados cubren las rutas del frontend y del proxy."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.core.database import SessionMaintenance
from app.modules.organizations import service as organization_service
from app.modules.organizations.schemas import RESERVED_SLUGS
from app.shared.errors import ConflictError

RAIZ = Path(__file__).resolve().parents[3]
RUTAS_DEL_FRONTEND = RAIZ / "apps" / "web" / "src" / "app" / "app.routes.ts"
CADDYFILE = RAIZ / "infra" / "caddy" / "Caddyfile"


def _primer_segmento(ruta: str) -> str:
    return ruta.split("/", 1)[0]


@pytest.mark.skipif(not RUTAS_DEL_FRONTEND.exists(), reason="falta apps/web en este checkout")
def test_todo_primer_segmento_de_ruta_del_frontend_esta_reservado() -> None:
    rutas = re.findall(r"path:\s*'([^']*)'", RUTAS_DEL_FRONTEND.read_text(encoding="utf-8"))
    segmentos = {
        _primer_segmento(ruta) for ruta in rutas if ruta and not ruta.startswith((":", "*"))
    }
    assert segmentos, "no se ha leído ninguna ruta: ¿cambió el formato de app.routes.ts?"
    assert segmentos - RESERVED_SLUGS == set()


@pytest.mark.skipif(not CADDYFILE.exists(), reason="falta infra/caddy en este checkout")
def test_las_rutas_del_proxy_estan_reservadas() -> None:
    caddy = CADDYFILE.read_text(encoding="utf-8")
    segmentos = {
        m.strip(".") if m.startswith("..") else m
        for m in re.findall(r"(?:handle\s+|path\s+)/([\w.-]+)", caddy)
    }
    assert segmentos - RESERVED_SLUGS == set()


async def test_crear_organizacion_rechaza_un_identificador_reservado() -> None:
    async with SessionMaintenance() as session:
        with pytest.raises(ConflictError):
            await organization_service.create_organization(
                session, slug="eventos", name="Reservada"
            )
