---
phase: 4
title: "Fase 4: Email de entrada, página pública y cierre de fase"
status: pending
priority: P1
effort: "1-1.5d"
dependencies: [3]
---

# Fase 4: Email de entrada, página pública y cierre de fase

## Overview

El último tramo: la persona confirmada recibe su entrada con el QR por
correo, puede volver a verla si la pierde, y se cierra la fase con una
pasada end-to-end del flujo completo (confirmar → recibir entrada → escanear
→ intentar duplicar → cancelar y comprobar que la entrada queda revocada).

## Requirements

- Functional:
  - Generación de la imagen del QR: comprobar primero si `qrcode`/`Pillow` (o
    equivalente) ya está entre las dependencias de `apps/api` antes de
    añadir una nueva — si no lo está, añadir la más ligera que cubra
    PNG a partir de una cadena, sin más funciones.
  - `send_registration_confirmed_email` (fase 3) pasa a incluir el QR como
    adjunto/imagen incrustada cuando la inscripción tiene entrada emitida —
    decidir en la implementación si merece una tarea nueva
    (`send_ticket_email`) o basta con extender la existente, según cuánto
    diverjan sus argumentos (la tarea actual no conoce el `ticket_id`
    todavía, habrá que pasárselo).
  - Página pública `/mi-entrada?token=...`: reutiliza el token de
    autocancelación (`registration_cancel`) ya existente de la fase 4 del
    trabajo anterior — **no** genera un token nuevo — para mostrar el QR de
    nuevo sin exponer un enlace adicional de un solo uso; si el token ya fue
    consumido (la persona canceló), la página debe decir con claridad que la
    inscripción está cancelada, no mostrar un QR revocado como si fuera
    válido.
  - Actualizar `docs/prd.md` si el alcance real difiere del redactado (por
    ejemplo, el margen de 48h tras el fin del evento, si termina siendo otro
    valor).
- Non-functional:
  - Igual que el resto de emails del proyecto: sin revelar datos de otras
    inscripciones, mismo remitente/dominio de organización
    (`_base_url_de_organizacion`).

## Validation

- Test end-to-end: confirmar una inscripción → se emite la entrada y se
  encola el email con el QR → escanear ese QR → `valid` → escanear otra vez
  → `duplicate` → cancelar la inscripción → la entrada queda `revoked_at` no
  nulo → un tercer escaneo del mismo QR → `revoked`, no `duplicate`.
- Test: `/mi-entrada` con el token de autocancelación de una inscripción
  `confirmed` muestra el QR; con el de una ya `cancelled` muestra el estado
  cancelado sin QR válido.
- Revisión manual de accesibilidad (axe) en `/mi-entrada`.
- `ak:code-review` sobre el diff completo de la fase 4 del PRD antes de
  cerrarla; `ak:review-pr` obligatorio antes de cualquier merge, según norma
  del usuario.

## Risk & Rollback

- Riesgo: si finalmente se opta por una tarea de email nueva en vez de
  extender la existente, revisar que no se dupliquen las tres llamadas ya
  centralizadas en `_enviar_email_por_estado` (fase 3) — un solo punto de
  envío, no una llamada adicional dispersa por cada camino a `confirmed`.
- Rollback: la plantilla de email y la página pública son aditivas; si el QR
  incrustado da problemas de entrega (tamaño del correo, proveedores que
  bloquean adjuntos), se puede degradar a un enlace a `/mi-entrada` sin tocar
  la máquina de estados de entradas, que ya queda cerrada en la fase 1-3.
