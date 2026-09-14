"""Identidad y páginas legales de la plataforma, mantenidas por el superadmin.

La web de la instalación (Eventarium) tiene una única identidad y unas
únicas páginas legales, sin organización ni host de por medio.
`repository.py` da lectura para los endpoints públicos, y la escritura vive
en `modules/admin` con la sesión de mantenimiento.
"""

from __future__ import annotations
