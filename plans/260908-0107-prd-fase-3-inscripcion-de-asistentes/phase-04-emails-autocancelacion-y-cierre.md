---
phase: 4
title: "Fase 4: Emails transaccionales, autocancelación y cierre de fase"
status: pending
priority: P1
effort: "1.5-2d"
dependencies: [3]
---

# Fase 4: Emails transaccionales, autocancelación y cierre de fase

## Overview

Cierra el embudo con las plantillas de email que faltan (confirmación,
aprobación, rechazo, entrada en lista de espera, promoción, cancelación), el
enlace de autocancelación con token firmado, y una pasada end-to-end del
embudo completo antes de marcar la fase 3 del PRD como cerrada.

## Requirements

- Functional:
  - Nuevas tareas en `app/core/tasks.py`, mismo patrón que
    `send_verification_email`/`send_password_reset_email`:
    `send_registration_confirmed_email`, `send_registration_approved_email`
    (si aplica, puede fusionarse con confirmación), `send_registration_rejected_email`,
    `send_registration_waitlisted_email`,
    `send_waitlist_promotion_email` (incluye el enlace de confirmación de la
    promoción y su caducidad), `send_registration_cancelled_email`.
  - Enlace de autocancelación (`/cancelar-inscripcion?token=...`) en todo
    email que lo ofrezca según la Decisión #5 (`waitlisted`, `confirmed`,
    `promoted`): el token se genera **en el momento de encolar cada email**,
    no una sola vez al confirmar, con propósito `registration_cancel` en
    Redis (mismo mecanismo que `email_verify_registration` de la Fase 2) —
    así una persona en `waitlisted` también puede cancelar, no solo una
    `confirmed`.
  - `POST /api/v1/public/registrations/cancel`: recibe el token, lo resuelve
    con `GETDEL` contra Redis (un solo uso; reutilizarlo falla sin detalle),
    marca `cancelled_at` y `status = cancelled`, y dispara la promoción de
    lista de espera si liberaba una plaza `confirmed` (misma función de
    dominio de la Fase 3).
  - Página pública de resultado (`/cancelar-inscripcion`), mismo patrón que
    `/verificar-correo` y `/verificar-inscripcion`.
  - Actualizar `docs/prd.md` si el alcance real implementado difiere del
    redactado (por ejemplo, si la ventana de confirmación de lista de espera
    se documenta con su valor concreto).
- Non-functional:
  - Todos los enlaces de email usan `settings.web_base_url`, igual que las
    tareas ya existentes.
  - Ningún email revela si un email tiene o no cuenta asociada, ni detalles
    de otras inscripciones.

## Validation

- Test end-to-end del embudo `free` sin aprobación: alta → verificación →
  confirmación (email con enlace de cancelación) → cancelación → promoción de
  lista de espera si había alguien esperando.
- Test end-to-end del embudo `approval` con aforo agotado: alta →
  verificación → `pending_approval` → `approve` → `waitlisted` (aforo
  agotado) → cancelación de una `confirmed` → promoción automática →
  confirmación del promovido dentro de plazo.
- Test: token de cancelación de un solo uso — reutilizarlo tras cancelar
  falla explícitamente, sin filtrar el motivo exacto.
- Revisión manual de accesibilidad (axe) en las páginas públicas nuevas de
  esta fase, siguiendo el estándar WCAG 2.1 AA del PRD.
- `ak:code-review` sobre el diff completo de la fase 3 del PRD antes de
  cerrarla; `ak:review-pr` obligatorio antes de cualquier merge, según norma
  del usuario.

## Risk & Rollback

- Riesgo: acumular seis plantillas de texto plano sin sistema de plantillas
  reutilizable puede duplicar código entre tareas; extraer un helper común
  de cuerpo de email (asunto + cuerpo + pie legal) si al escribir la tercera
  plantilla ya hay tres copias casi idénticas — no adelantar la abstracción
  antes de verla repetida.
- Rollback: cada tarea de email es independiente; una plantilla con un bug
  se puede desactivar (dejar de encolarla) sin afectar a la máquina de
  estados, que ya quedó cerrada en la fase 3.
