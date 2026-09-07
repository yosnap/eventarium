---
phase: 1
title: "Fase 1: Modelo de datos, RLS y permisos"
status: pending
priority: P1
effort: "2-2.5d"
dependencies: []
---

# Fase 1: Modelo de datos, RLS y permisos

## Overview

Las cuatro tablas nuevas (`event_registration_questions`,
`event_registrations`, `event_registration_answers`,
`event_registration_consents`), sus políticas RLS con FK compuestas por
organización, los permisos `registrations:read` / `registrations:write`, y las
constraints de base de datos que fijan la máquina de estados de una
inscripción. Sin esta fase no hay dónde guardar nada de las fases siguientes.

## Requirements

- Functional:
  - `event_registration_questions`: `event_id`, `organization_id`,
    `type` (`short_text`/`single_choice`/`multiple_choice`), `label`,
    `required` (bool), `order`, `options` (`jsonb`, lista de cadenas, solo
    para `single_choice`/`multiple_choice` — `NULL`/vacío en `short_text`).
  - `event_registrations`: `event_id`, `organization_id`, `email`
    (normalizado a minúsculas, como ya hace `users`), `full_name`, `user_id`
    nullable (enlace si el email coincide con una cuenta existente, resuelto
    con `app_find_user_by_email` — ver Non-functional),
    `status` (`pending_verification` / `pending_approval` / `confirmed` /
    `rejected` / `cancelled` / `waitlisted`), `waitlist_position` nullable,
    `waitlist_promoted_at` nullable, `waitlist_promotion_expires_at`
    nullable, timestamps de cada transición relevante
    (`verified_at`, `approved_at`, `rejected_at`, `cancelled_at`,
    `confirmed_at`).
    **Sin columnas de token**: la verificación de email y la cancelación no
    guardan hash ni caducidad en la tabla — ver Non-functional, "tokens en
    Redis".
  - `event_registration_answers`: `registration_id`, `question_id`,
    `organization_id`, `value` (`jsonb`: cadena para `short_text`/
    `single_choice`, lista de cadenas para `multiple_choice`).
  - `event_registration_consents`: `registration_id`, `organization_id`,
    `data_processing_accepted_at` (obligatorio, no nullable),
    `marketing_accepted_at` (nullable), `recording_accepted_at` (nullable).
  - Permisos nuevos en `app/core/permissions.py`:
    `REGISTRATIONS_READ = "registrations:read"`,
    `REGISTRATIONS_WRITE = "registrations:write"` (el prefijo ya está
    reservado en el docstring del módulo).
  - Migración de backfill: todo rol con la capacidad `organizations:write`
    recibe también `registrations:read`/`registrations:write` — mismo
    criterio que usó `0009` para `events:*` (nunca por nombre de rol).
- Non-functional:
  - **Tokens en Redis, no en columnas de tabla:** todo token opaco de un solo
    uso en este proyecto vive en Redis con TTL, nunca como columna Postgres
    (verificación de correo, cambio de correo, recuperación de contraseña,
    refresh tokens — `apps/api/app/modules/auth/verification.py`,
    `apps/api/app/modules/auth/service.py`). La verificación de email y la
    cancelación de una inscripción siguen el mismo patrón: dos propósitos
    nuevos en `verification.py` (p. ej. `email_verify_registration`,
    `registration_cancel`) cuyo payload es el `registration_id`, con
    `GETDEL` atómico para garantizar un solo uso. Esto es distinto de
    `waitlist_promoted_at`/`waitlist_promotion_expires_at`, que sí son
    estado de dominio persistente (no secretos de un solo uso) y sí van en
    la tabla.
  - **Resolución de `user_id` por email:** el endpoint público no tiene
    organización en contexto y `users` está bajo RLS ("solo el propio
    usuario o quien comparta organización con él"), así que una consulta
    directa a `users` desde ahí fallaría. Se reutiliza la función
    `SECURITY DEFINER` ya existente `app_find_user_by_email(p_email)`
    (`apps/api/alembic/versions/0004_correo_y_verificacion.py`), ya
    `GRANT`eada a `app_user` — no se crea una función nueva.
  - Mismo patrón de RLS que `events`/`event_sessions`:
    `organization_id = app_current_organization()`, `ENABLE` + `FORCE ROW
    LEVEL SECURITY`, `organization_id` denormalizado en las cuatro tablas.
  - FK compuestas `(id, organization_id)` de `event_registrations` hacia
    `events`, y de `event_registration_answers`/`event_registration_consents`
    hacia `event_registrations`, igual que el resto del dominio de eventos.
  - `UNIQUE (event_id, email)` en `event_registrations`: es la garantía a
    nivel de base de datos de la decisión "una inscripción por email y
    evento" — el alta debe hacer `INSERT ... ON CONFLICT DO NOTHING` seguido
    de una lectura, nunca confiar solo en una comprobación previa (evita la
    condición de carrera de dos envíos simultáneos con el mismo email).
  - `UNIQUE (registration_id, question_id)` en `event_registration_answers`.
  - Constraint `CHECK` en `event_registration_questions.options`: no vacío ni
    nulo cuando `type IN ('single_choice', 'multiple_choice')`; debe ser
    `NULL` cuando `type = 'short_text'`.
  - Índice sobre `(event_id, status)` en `event_registrations` para el
    recuento de aforo y las estadísticas (consultas frecuentes de la fase 3).
  - Migración `0010`, encadenada tras `0009_eventos_agenda_y_ponentes`, con
    `downgrade()` explícito y la comprobación de privilegios de `app_user`.
  - Modelos SQLAlchemy en `apps/api/app/modules/registrations/models.py`
    (módulo nuevo, no dentro de `events`), siguiendo el mismo
    `TimestampMixin` y `new_uuid7()` que el resto del dominio.

## Validation

- `alembic upgrade head` y `alembic downgrade -1` limpios sobre una base de
  datos con la fase 2 ya aplicada.
- Test de RLS: una sesión con `app_current_organization()` de la organización
  B no puede leer ni escribir inscripciones de la organización A (mismo
  patrón de test que ya existe para `events`).
- Test de constraint: insertar dos inscripciones con el mismo `(event_id,
  email)` falla con violación de `UNIQUE`; insertar una pregunta
  `single_choice` sin `options` falla con violación de `CHECK`.

## Risk & Rollback

- Riesgo: olvidar la FK compuesta y dejar una FK simple permitiría, bajo
  RLS, colgar una respuesta de una organización de una pregunta de otra.
  Mitigación: revisar contra el mismo checklist que usó la fase 2
  (`plan.md` de `260907-1509-prd-fase-2-eventos-y-agenda`).
- Rollback: `alembic downgrade -1` antes de mergear; sin datos de producción
  que migrar todavía (fase nueva).
