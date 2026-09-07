---
phase: 3
title: "Fase 3: Aprobación, lista de espera automática y panel de organizador"
status: pending
priority: P1
effort: "3-3.5d"
dependencies: [2]
---

# Fase 3: Aprobación, lista de espera automática y panel de organizador

## Overview

El organizador necesita ver quién se ha inscrito, aprobar o rechazar cuando
el evento lo requiere, y que la lista de espera se mueva sola cuando se libera
una plaza. Esta fase entrega el panel (listado, detalle, acciones) y la
mecánica de lista de espera con promoción automática por cron, además de las
estadísticas y la gestión de preguntas personalizadas.

## Requirements

- Functional:
  - `GET /api/v1/organizations/{org}/events/{event}/registrations`: listado
    paginado con filtro por `status`, requiere `registrations:read`.
  - `GET /api/v1/organizations/{org}/events/{event}/registrations/{id}`:
    detalle con respuestas y consentimientos, requiere `registrations:read`.
  - `POST .../registrations/{id}/approve` y `.../reject`: solo válido desde
    `pending_approval`; `approve` revalúa aforo en ese momento (bloqueo de
    fila igual que la Fase 2) y decide entre `confirmed` y `waitlisted`;
    `reject` termina en `rejected` y, si liberaba una plaza que ya estaba
    `confirmed`, dispara la promoción de lista de espera. Requiere
    `registrations:write`.
  - `POST .../registrations/{id}/cancel` (panel del organizador): termina en
    `cancelled`; si la inscripción cancelada estaba `confirmed`, dispara la
    promoción de lista de espera. Requiere `registrations:write`.
  - Promoción de lista de espera: al liberar una plaza (cancelación o
    rechazo de una `confirmed`), se toma la inscripción `waitlisted` más
    antigua (`waitlist_position` o `created_at`), se marca
    `waitlist_promoted_at = now()` y
    `waitlist_promotion_expires_at = now() + intervalo configurable` (config
    de aplicación, no por evento, para el MVP). El enlace de confirmación
    lleva un token opaco de propósito `waitlist_promotion_confirm` en Redis
    (mismo mecanismo que `email_verify_registration`/`registration_cancel`),
    payload `registration_id`, TTL igual a la ventana de promoción — no una
    columna de tabla. Se envía el email de promoción (fase 4) con ese
    enlace.
  - `POST /api/v1/public/registrations/confirm-waitlist-promotion`: resuelve
    el token con `GETDEL` contra Redis, marca la inscripción `confirmed` si
    `waitlist_promotion_expires_at` no ha pasado; si el token ya caducó o no
    existe, responde que caducó (sin filtrar más detalle) y deja que el cron
    la reasigne.
  - Tarea cron nueva en `app/core/tasks.py`
    (`expire_waitlist_promotions_task`, `schedule=[{"cron": "*/15 * * *
    *"}]` o similar): busca inscripciones con `waitlist_promoted_at`
    establecido y `waitlist_promotion_expires_at` vencido sin confirmar,
    las devuelve a `waitlisted` (al final de la cola) y promueve a la
    siguiente — mismo patrón que `sweep_unverified_accounts_task`.
  - `GET .../registrations/stats`: iniciados, verificados, pendientes de
    aprobación, confirmados, rechazados, cancelados, en lista de espera,
    conversión verificados/iniciados y confirmados/verificados. Requiere
    `registrations:read`. **Fuera de alcance explícito de esta fase:**
    "emails enviados/entregados/abiertos" (PRD §4.3) — exige webhooks del
    proveedor de email, infraestructura que no existe todavía en
    `app/core/email.py`; se deja como decisión de alcance documentada, no
    como omisión.
  - Gestión de preguntas (`POST`/`PATCH`/`DELETE` sobre
    `event_registration_questions`): añadir siempre permitido; `PATCH` de
    tipo o `DELETE` de una pregunta con `event_registration_answers`
    asociadas responde `409` (decisión de la Fase 1 del plan). Editar
    `label`/`order`/`required` de una pregunta existente sí se permite
    siempre (no cambia la forma de la respuesta ya guardada).
  - Páginas del panel (Angular): listado de inscripciones con filtro,
    detalle con acciones, editor de preguntas del evento, tarjetas de
    estadísticas — dentro del área de administración de eventos ya existente
    de la fase 2 del PRD.
- Non-functional:
  - Todo endpoint de escritura sobre inscripciones exige
    `registrations:write`; lectura exige `registrations:read` — mismo
    patrón de dependencias de FastAPI que `events:*`.
  - La revaluación de aforo en `approve` y la promoción de lista de espera
    comparten la misma sección crítica (bloqueo de fila del evento) que la
    Fase 2, para no confirmar por encima de `capacity` desde dos caminos
    distintos (verificación automática vs aprobación manual).
  - Accesibilidad WCAG 2.1 AA en el panel (tablas, filtros, formularios de
    pregunta).

## Validation

- Test: rechazar una inscripción `confirmed` promueve a la primera persona en
  `waitlisted` y le pone `waitlist_promotion_expires_at`.
- Test: la tarea de expiración devuelve a `waitlisted` una promoción vencida
  sin confirmar y promueve a la siguiente persona.
- Test: `PATCH` de tipo o `DELETE` de una pregunta con respuestas asociadas
  responde `409`; sobre una pregunta sin respuestas, funciona.
- Test: estadísticas cuadran con un escenario sembrado (fixtures) con
  inscripciones en cada estado.
- Prueba manual del panel: aprobar/rechazar, ver lista de espera moverse tras
  cancelar una confirmada.

## Risk & Rollback

- Riesgo: la ventana de confirmación fija a nivel de aplicación (no por
  evento) puede no ajustarse a todos los organizadores; aceptable para el
  MVP de IAWIC según el alcance de esta fase — configurable por evento queda
  fuera si no se pide explícitamente.
- Riesgo: dos rutas a `confirmed` (verificación automática y aprobación
  manual) duplicando la lógica de aforo — mitigar extrayendo una única
  función de dominio `evaluar_estado_al_confirmar(evento, cupo_actual)`
  reutilizada por ambas, no dos implementaciones paralelas.
- Rollback: la tarea cron se puede desactivar sin migración (quitar el
  `schedule` o parar el worker de scheduler) dejando la promoción solo
  manual como red de seguridad.
