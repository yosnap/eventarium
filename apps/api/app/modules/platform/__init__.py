"""Identidad y páginas legales de la plataforma, mantenidas por el superadmin.

La web de la instalación (Eventarium) tiene su propia identidad y sus propias
páginas legales, separadas de las de cada organización. `host.py` decide si un
host es de plataforma o de organización; `repository.py` da lectura para los
endpoints públicos, y la escritura vive en `modules/admin` con la sesión de
mantenimiento.
"""

from __future__ import annotations

from app.modules.platform.host import ResolvedHost, resolve_host

__all__ = ["ResolvedHost", "resolve_host"]
