---
phase: 1
title: "Fase 1: Modelo de datos, permisos y niveles de patrocinio"
status: completed
priority: P1
effort: "2-2.5d"
dependencies: []
---

# Fase 1: Modelo de datos, permisos y niveles de patrocinio

## Overview

Base de datos y permisos para las tres piezas de esta fase: patrocinadores,
legal/cookies y auditoría. Sin esto, ninguna fase de trabajo posterior tiene
dónde escribir.

## Requirements

- Functional:
  - `sponsor_tiers` (organización): `id`, `organization_id`, `name`,
    `display_order`, `logo_size` (enum: `large`/`medium`/`small`),
    `benefits` (texto libre), `UNIQUE(organization_id, name)`, **y
    `UNIQUE(id, organization_id)`** — sin esta segunda constraint, la FK
    compuesta de `sponsors` de abajo no puede crearse (PostgreSQL exige un
    índice único exacto sobre las columnas referenciadas; ningún otro
    `UNIQUE` de esta tabla las cubre).
  - `sponsors` (evento + nivel): `id`, `event_id`, `tier_id`,
    `organization_id` (denormalizado), `name`, `logo_object_key`, `website`,
    `contribution_type` (enum: `monetaria`/`en_especie`),
    `contribution_amount` (numeric, nullable — solo si `monetaria`),
    `contribution_description` (texto, nullable — solo si `en_especie`).
    FK compuesta `(event_id, organization_id)` → `events (id,
    organization_id)`, FK compuesta `(tier_id, organization_id)` →
    `sponsor_tiers (id, organization_id)`. `ondelete="CASCADE"` desde
    `events` (borrar un evento borra sus patrocinios), `ondelete="RESTRICT"`
    desde `sponsor_tiers` (no se puede borrar un nivel con patrocinadores
    activos — el organizador debe reasignarlos primero).
  - `audit_log`: `id`, `actor_user_id` (nullable, `ondelete="SET NULL"` —
    conserva la fila de auditoría aunque el usuario actor se borre después,
    p. ej. por el barrido de cuentas no verificadas; nunca `CASCADE`, que
    borraría la prueba de la propia auditoría), `organization_id`
    (nullable, sin FK con cascada por el mismo motivo), `action` (string
    corto, ej. `role.permissions_changed`, `organization.created`,
    `organization_domain.created`, `registration.rgpd_export`,
    `registration.rgpd_delete`), `entity_type`, `entity_id`, `detail`
    (jsonb), `created_at`. Tabla de instalación: **sin política RLS, pero
    con `REVOKE ALL ON audit_log FROM app_user`** explícito en la
    migración — ver Non-functional abajo, es la corrección de red-team más
    importante de esta fase.
  - `cookie_consents`: `id`, `organization_id`, `categories_accepted`
    (jsonb, lista de categorías), `created_at`. **Sin `user_id`, sin
    email, sin IP ni hash de IP en ninguna forma** — ver Decisión #3 del
    plan (un hash de IP sin sal es reversible por fuerza bruta y no
    aporta nada que `(organization_id, categorías, timestamp)` no dé ya
    para probar que se pidió consentimiento). `REVOKE ALL ... FROM
    app_user` salvo `GRANT INSERT` puntual, ya que el endpoint público de
    la fase 3 de trabajo sí escribe en esta tabla desde una sesión de
    `app_user` sin autenticar.
  - Campos nuevos en `Organization`: `legal_address` (texto, nullable),
    `tax_id` (string corto, nullable — NIF/CIF), y cuatro campos de texto
    largo nullable para el contenido editado de cada página legal
    (`legal_notice_content`, `privacy_policy_content`,
    `cookies_policy_content`, `registration_terms_content`) — `NULL`
    significa "usar la plantilla por defecto", coherente con la Decisión
    #2 del plan (texto plano/Markdown restringido, nunca HTML crudo).
  - Permiso nuevo: `SPONSORS_READ`, `SPONSORS_WRITE` (prefijo `sponsors:*`
    ya reservado en `core/permissions.py`). **`AUDIT_READ` NO se añade al
    enum `Permission`** — corrección de red-team: `OWNER` en
    `system_roles.py` se define como `permissions=tuple(Permission)`, así
    que cualquier permiso nuevo del enum se concede automáticamente a
    todo `owner` futuro sin pasar por ningún backfill. Un permiso pensado
    para ser "exclusivo de superadmin" no puede vivir en un enum que
    `OWNER` hereda entero. El endpoint de auditoría (fase 4 de trabajo)
    comprueba la dependencia `Superadmin` directamente
    (`app/core/deps.py`), que no depende de ningún `Permission` de rol.
  - `SPONSORS_READ`/`WRITE` llegan a las organizaciones por **dos vías, no
    una** (corrección de red-team, repite el bug ya corregido en la fase
    4 para `REGISTRATIONS_*`): (a) backfill a filas de `role_permissions`
    ya existentes con `organizations:write`, con `WHERE NOT EXISTS`
    (cubre organizaciones creadas antes de esta migración); (b) actualizar
    la plantilla `ORGANIZER` en `apps/api/app/modules/roles/
    system_roles.py` añadiendo `SPONSORS_READ`/`SPONSORS_WRITE` a su
    tupla de permisos en código (cubre organizaciones creadas después —
    `OWNER` ya los recibe automáticamente vía `tuple(Permission)`, no
    necesita backfill ni cambio de plantilla).
- Non-functional:
  - RLS en `sponsor_tiers`/`sponsors` igual que toda tabla de dominio
    (`organization_id = app_current_organization()`); test de aislamiento
    explícito entre dos organizaciones para ambas tablas, incluida la
    escritura cruzada (mismo patrón que fase 2, hallazgo #7 de su
    red-team).
  - **`audit_log`/`cookie_consents` sin RLS no equivale a "sin acceso".**
    Corrección de red-team (3 revisores independientes, misma cita):
    `infra/postgres/sql/roles.sql:45,50-51` concede
    `SELECT, INSERT, UPDATE, DELETE` a `app_user` sobre **toda** tabla
    nueva por `ALTER DEFAULT PRIVILEGES`, sin que haga falta ningún GRANT
    manual. Sin un `REVOKE` explícito, cualquier sesión de organización
    (`app_user`, usada por todo el panel y todos los endpoints públicos)
    puede leer y **borrar** el registro de auditoría completo de la
    instalación con solo un `JOIN` mal filtrado o un endpoint futuro que
    lea la tabla "porque está ahí" — cruzando la frontera multi-tenant que
    el resto del esquema protege en todas las demás tablas, y volviendo
    borrable desde el propio código de aplicación un log que se supone
    "de solo inserción". La migración debe incluir `REVOKE ALL ON
    audit_log FROM app_user` y `REVOKE ALL ON cookie_consents FROM
    app_user` seguido de `GRANT INSERT ON cookie_consents TO app_user`
    (necesario para el endpoint público de consentimiento de la fase 3).
  - `audit_log`/`cookie_consents` y `sponsor_tiers`/`sponsors` se añaden a
    la lista `TABLAS` de `apps/api/tests/conftest.py` (aislamiento entre
    tests por `TRUNCATE`) — corrección de red-team: sin esto, filas de
    `audit_log` escritas por un test persisten al siguiente dentro de la
    misma suite (no tienen FK con `CASCADE` hacia ninguna tabla de la
    lista actual, así que el `TRUNCATE ... CASCADE` existente no las
    alcanza), produciendo asserts de recuento intermitentes según el
    orden de ejecución.

## Implementation Steps

1. Migración Alembic: las cuatro tablas nuevas (con `UNIQUE(id,
   organization_id)` en `sponsor_tiers`) + columnas nuevas en
   `organizations`, con `downgrade()` simétrico.
2. En la misma migración: `REVOKE ALL ON audit_log, cookie_consents FROM
   app_user` + `GRANT INSERT ON cookie_consents TO app_user`.
3. Políticas RLS para `sponsor_tiers`/`sponsors` (`tenant_isolation`, mismo
   nombre de política que las tablas de dominio existentes).
4. Backfill de `SPONSORS_READ`/`WRITE` a roles existentes con
   `organizations:write` (`WHERE NOT EXISTS`, idempotente) **+**
   actualización de `ORGANIZER.permissions` en `system_roles.py` con
   `SPONSORS_READ`/`SPONSORS_WRITE`.
5. Modelos SQLAlchemy + comprobación de privilegios de `app_user` sobre las
   cuatro tablas nuevas: positiva para `sponsor_tiers`/`sponsors` (mismo
   patrón que `0002_esquema_base`), **negativa** para
   `audit_log`/`cookie_consents` (`has_table_privilege('app_user',
   'audit_log', 'SELECT')` debe dar `false`).
6. Añadir las cuatro tablas nuevas a `TABLAS` en `tests/conftest.py`.
7. Tests de aislamiento RLS (lectura y escritura cruzada) para
   `sponsor_tiers`/`sponsors`.

## Success Criteria

- [x] Migración aplica y revierte limpio: `alembic upgrade head` →
      `downgrade -1` → `upgrade head`, sin duplicar ni perder filas
      (verificado también con `downgrade base` → `upgrade head` desde
      cero, y con `tests/test_sponsors_legal_auditoria_migracion.py`)
- [x] Una organización de una fase anterior (sin recrear) tiene
      `SPONSORS_READ`/`WRITE` en su rol `owner` tras la migración, sin
      intervención manual (`tests/test_sponsors_permisos.py`, incluida una
      prueba adicional que inserta un rol a mano con `organizations:write`
      sin `sponsors:*` y comprueba que las sentencias de backfill de la
      migración se lo dan)
- [x] Una organización **creada después** de aplicar la migración (no una
      preexistente) tiene `sponsors:read`/`sponsors:write` en su rol
      `organizer` clonado — test explícito que crea la organización tras
      la migración, no antes
- [x] `AUDIT_READ` no existe como valor del enum `Permission` en ningún
      punto del código — no hay nada que backfillear ni que pueda colarse
      en `OWNER`
- [x] Dos organizaciones no pueden leer ni escribir (fila hija apuntando al
      padre de otra organización) los `sponsor_tiers`/`sponsors` de la otra
      — test explícito para ambos casos
- [x] Borrar un nivel de patrocinio con patrocinadores activos da 409, no
      un 500 de `IntegrityError` sin capturar
- [x] `has_table_privilege('app_user', 'audit_log', 'SELECT')` y
      `has_table_privilege('app_user', 'audit_log', 'DELETE')` son
      `false`; `has_table_privilege('app_user', 'cookie_consents',
      'SELECT')` es `false` y `'INSERT'` es `true` — test explícito, no
      solo revisión de la migración
- [x] Comprobación de privilegios de `app_user` sobre las cuatro tablas
      nuevas, mismo patrón que `0002_esquema_base`
- [x] Un test que escribe en `audit_log` y otro que asume la tabla vacía,
      ejecutados en el mismo run de la suite completa, no se contaminan
      entre sí

## Risk & Rollback

- Riesgo: `cookie_consents` sin `user_id` ni IP puede parecer "dato
  incompleto" a quien revise el modelo más adelante — documentado
  explícitamente en el propio comentario del modelo (Decisión #3 del
  plan), no solo aquí, para que no se "corrija" a futuro añadiendo un
  campo que reintroduce el problema de reversibilidad que se evita a
  propósito.
- Riesgo: el ciclo `downgrade` → `upgrade` del backfill de permisos, igual
  que en las fases 2-4, borra y reinserta todas las filas del permiso
  para los roles con `organizations:write` — si una organización había
  revocado `sponsors:write` manualmente de un rol a medida, una reversión
  y reaplicación accidental de la migración se lo devuelve en silencio.
  Es el mismo patrón ya aceptado en las fases 2-4 (no es nuevo de esta
  fase); se documenta aquí como limitación conocida, no se rediseña el
  patrón de backfill del proyecto en esta fase.
- Rollback: las cuatro tablas son aditivas y no tienen todavía ningún
  consumidor (fases de trabajo 2-4 aún no escritas); revertir la migración
  no afecta a ninguna tabla ni dato de las fases 1-4 ya cerradas.
