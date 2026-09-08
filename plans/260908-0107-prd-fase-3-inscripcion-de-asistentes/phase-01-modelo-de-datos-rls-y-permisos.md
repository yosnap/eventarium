---
phase: 1
title: "Fase 1: Modelo de datos, RLS y permisos"
status: done
priority: P1
effort: "2-2.5d"
dependencies: []
---

## Estado — implementado 2026-09-08

Rama `feat/0.13.0-modelo-de-inscripciones-rls-y-permisos` (desde `develop`, sin
mergear todavía).

**Archivos:**
- `apps/api/app/modules/registrations/models.py` (nuevo) — los 4 modelos SQLAlchemy
- `apps/api/alembic/versions/0010_inscripcion_de_asistentes.py` (nuevo) — migración
- `apps/api/app/core/permissions.py` — añade `REGISTRATIONS_READ`/`REGISTRATIONS_WRITE`
- `apps/api/tests/test_registrations_rls_isolation.py` (nuevo, 8 tests)
- `apps/api/tests/modules/test_registrations_constraints.py` (nuevo, 9 tests)
- `apps/api/tests/modules/test_registrations_permissions_backfill.py` (nuevo, 4 tests)

**Verificado (comandos ejecutados en esta sesión, no solo escritos):**
- `alembic upgrade head` aplica `0010` sin error sobre `ia_week_test`; `alembic history` encadena `0009 → 0010` sin huecos.
- `pytest -q` (suite completa del API): **196 passed**, 0 failed.
- `ruff check app tests`: sin hallazgos. `ruff format --check`: sin diffs.
- `mypy app/modules/registrations`: sin errores.
- Dos bugs reales encontrados y corregidos durante la propia verificación (no
  hipotéticos): (1) `options=None` explícito se codificaba como JSON `null`
  en vez de SQL `NULL` — corregido con `JSONB(none_as_null=True)`; (2) el
  `CHECK` con `jsonb_typeof(options)='array'` se evaluaba a `NULL`
  (desconocido → constraint satisfecho) cuando `options` era `NULL` de
  verdad — corregido añadiendo `options IS NOT NULL` explícito. Sin este
  segundo fix, una pregunta `single_choice` sin opciones se habría podido
  crear igualmente.

**Pendiente antes de mergear a develop:** commit, PR, `ak:review-pr`, merge,
y solo entonces el bump de versión + release (norma del usuario: nunca saltar
la revisión de PR).

### Checklist de criterios de aceptación (Requirements/Validation de esta fase)

Functional:
- [x] `event_registration_questions` con `type`/`label`/`required`/`sort_order`/`options` — `models.py:40-94`
- [x] `event_registrations` con email/nombre/`user_id`/estado/lista de espera/timestamps, **sin** columnas de token — `models.py:97-160`
- [x] `event_registration_answers` con `value` jsonb — `models.py:163-205`
- [x] `event_registration_consents` con los 3 consentimientos independientes — `models.py:208-235`
- [x] Permisos `REGISTRATIONS_READ`/`REGISTRATIONS_WRITE` en `permissions.py` — verificado por `test_registrations_permissions_backfill.py` (4/4 passed)
- [x] Backfill anclado a `organizations:write`, no al nombre del rol — mismos 4 tests, incluye caso "rol a medida sin ese permiso no recibe nada" y "ejecutar dos veces no duplica"
- [x] Tokens en Redis, no columnas (hallazgo del red-team) — confirmado leyendo `models.py`: no existe ninguna columna `*_token_hash`
- [x] Resolución de `user_id` vía `app_find_user_by_email` — documentado en el comentario de `models.py:126-129` (la implementación real del endpoint público es fase 2, aquí solo el modelo lo deja preparado)

Non-functional:
- [x] RLS `ENABLE`+`FORCE`+policy `tenant_*` en las 4 tablas — migración `0010`, `_activar_rls()`; verificado por `test_registrations_rls_isolation.py::test_una_sesion_solo_ve_las_filas_de_su_organizacion` parametrizado en las 4 tablas (4/4 passed)
- [x] FK compuestas `(id, organization_id)` — verificado por los 4 tests `test_no_se_puede_*_ajen*` de `test_registrations_rls_isolation.py` (4/4 passed, cada uno espera `DBAPIError`)
- [x] `UNIQUE(event_id, email)` — verificado por `test_no_se_puede_inscribir_dos_veces_el_mismo_email_al_mismo_evento` (passed) y `test_el_mismo_email_puede_inscribirse_a_eventos_distintos` (passed, confirma que NO es una unicidad global)
- [x] `UNIQUE(registration_id, question_id)` en answers — `test_no_se_puede_responder_dos_veces_a_la_misma_pregunta` (passed), añadido tras detectar el hueco
- [x] `CHECK` de `options` por tipo — 7 tests parametrizados (`test_options_invalido_para_el_tipo_falla` x4, `test_options_valido_para_el_tipo_funciona` x3), todos passed; incluye el caso NULL-vs-JSON-null que falló en la primera pasada y quedó corregido
- [x] Índice `(event_id, status)` — creado en migración (`ix_event_registrations_event_id_status`); no hay test dedicado (no es lo habitual testear la existencia de un índice, es aceptable)
- [x] Migración `0010` encadenada tras `0009`, `downgrade()` explícito — **ciclo `downgrade -1` → verificado con `psql \dt` que las 4 tablas desaparecen → `upgrade head` → verificado que las 4 tablas vuelven → `pytest -q` completo: 197 passed** (196 + el test nuevo de la UNIQUE)

Sin huecos pendientes en esta fase de trabajo.

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
