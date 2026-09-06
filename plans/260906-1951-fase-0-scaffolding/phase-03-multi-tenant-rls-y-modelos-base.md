---
phase: 3
title: "Fase 3: Multi-tenant con RLS y modelos base"
status: completed
priority: P1
effort: "2-3d"
dependencies: [2]
---

# Fase 3: Multi-tenant con RLS y modelos base

## Overview
Esquema mínimo para que el multi-tenant sea real y verificable: organizaciones con dominios y branding, usuarios, roles clonados desde plantillas del sistema con campos de perfil predefinidos, roles personalizados, permisos y membresías. Políticas RLS **fail-closed** en todas las tablas de dominio (incluida `users`), regla anti-escalada de privilegios, tests de aislamiento y seed idempotente ejecutado con el rol de mantenimiento. Los eventos e inscripciones se añaden en las fases 1-3 del PRD reutilizando estos cimientos.

## Requirements
- Functional: migración con las tablas del esquema; políticas RLS; endpoints `GET/PATCH /api/v1/organizations/me`, `GET/PUT /api/v1/organizations/me/branding` (subida de logo validada), `GET/POST/PATCH/DELETE /api/v1/roles`, `GET/POST /api/v1/organizations/me/members`, `GET /api/v1/users/me`; `GET /api/v1/tenant/branding` real; **módulo `admin` de superadmin** (validación #3 y #6): `POST/GET /api/v1/admin/organizations`, `POST /api/v1/admin/organizations/{id}/domains`, protegidos por `require_superadmin` (`users.is_superadmin`), sin UI; CLI equivalente `create-organization`, `add-domain`, `create-superadmin`; seed idempotente con organización "IAWIC", dominio `localhost`, branding demo, 5 roles clonados con sus campos, owner `owner@example.com` con **contraseña generada** (`secrets.token_urlsafe(12)`) o tomada de `SEED_OWNER_PASSWORD`, mostrada por consola y nunca fija en el código (validación #4). <!-- Updated: Validation Session 1 - admin + seed -->
- Non-functional: UUID v7; `created_at/updated_at`; constraints explícitas; RLS `ENABLE + FORCE` en todas las tablas de dominio; sin GUC de bypass; validación de `profile_data` contra `role_profile_fields`; un `models.py` por módulo ≤ 300 líneas.

## Architecture

### Esquema (decisión: clonación de roles — hallazgo #3)
```
organizations            id, slug*, name, legal_name, description, website, contact_email, is_active
organization_domains     id, organization_id, host*, is_primary
organization_branding    organization_id PK/FK, template_key, logo_object_key, favicon_object_key,
                         colors JSONB, fonts JSONB, social_links JSONB, organizer_blurb
users                    id, email*, password_hash NULL, full_name, avatar_object_key, locale, is_active, is_superadmin
user_social_links        id, user_id, kind, url
roles                    id, organization_id NOT NULL, key, name, description, is_system,
                         system_template_key NULL                  UNIQUE(organization_id, key)
role_permissions         role_id, permission                        PK compuesta
role_profile_fields      id, organization_id NOT NULL, role_id, key, label, field_type, options JSONB,
                         is_required, is_locked, sort_order         UNIQUE(role_id, key)
organization_members     id, organization_id, user_id, role_id, profile_data JSONB   UNIQUE(org, user, role)
```
- **Plantillas del sistema** viven en código (`modules/roles/system_roles.py`): `owner`, `organizer`, `speaker`, `volunteer`, `attendee`, cada una con permisos y campos predefinidos (PRD §3). Al crear una organización (`OrganizationService.create`, con `engine_maintenance`) se clonan como filas propias con `is_system=true`, `system_template_key` y campos `is_locked=true`. No existen filas sin `organization_id`; RLS es uniforme.
- Roles del sistema: no se pueden borrar ni perder campos bloqueados; sí se pueden añadir campos y permisos (dentro de la regla anti-escalada).
- **Regla anti-escalada (hallazgo #4)**: en `RoleService.create/update` y `MemberService.assign`, el conjunto de permisos concedido debe ser subconjunto de los permisos efectivos del actor; asignar o modificar `owner` requiere ser `owner`; un actor no puede modificar su propio rol para ganar permisos. Test por cada regla.
- **RLS fail-closed (hallazgos #1, #8, #10)**: función SQL `app_current_organization() RETURNS uuid` = `NULLIF(current_setting('app.organization_id', true), '')::uuid`. Para cada tabla con `organization_id`: `ENABLE` + `FORCE ROW LEVEL SECURITY`, política `USING (organization_id = app_current_organization())` y `WITH CHECK` igual. `organizations`: `USING (id = app_current_organization())`. **`users` y `user_social_links` también con RLS**: visible si `users.id = app_current_user()` (GUC `app.user_id` fijado junto con la organización) o si existe `organization_members` con `user_id = users.id AND organization_id = app_current_organization()`. Sin contexto → 0 filas, nunca error. Sin GUC de bypass: las operaciones transversales (alta de organización, seed, superadmin) usan el rol `app_maintainer` a través de `engine_maintenance` y de servicios explícitos, nunca desde `get_db`. En la API, **solo** `modules/admin` puede inyectar `get_maintenance_db`; `require_superadmin` valida el JWT sin exigir organización (los endpoints de admin son globales a la instalación) y comprueba `is_superadmin` en BD en cada petición.
- Historial de participación: se implementa cuando exista `event_members` (fase 2 del PRD); aquí solo se garantiza que `organization_members.profile_data` se reutiliza entre ediciones.

## Related Code Files
- Create: `apps/api/app/modules/{organizations,users,roles}/{models,schemas,repository,service,router}.py`
- Create: `apps/api/app/modules/roles/system_roles.py`, `apps/api/app/modules/roles/authorization.py` (regla anti-escalada)
- Create: `apps/api/app/modules/admin/{schemas,service,router}.py`, `apps/api/tests/modules/test_admin.py`
- Create: `apps/api/app/shared/dynamic_fields.py`
- Create: `apps/api/alembic/versions/0002_esquema_base.py`, `apps/api/alembic/versions/0003_politicas_rls.py`
- Create: `apps/api/app/seed/demo.py` (idempotente)
- Create: `apps/api/tests/modules/test_organizations.py`, `test_roles.py`, `test_members.py`, `test_branding.py`, `test_authorization.py`, `apps/api/tests/test_rls_isolation.py`, `apps/api/tests/test_seed_idempotente.py`
- Modify: `apps/api/app/core/permissions.py`, `apps/api/app/core/deps.py` (`require_permission` real; fija también `app.user_id`), `apps/api/app/modules/tenant/router.py`, `apps/api/app/main.py`, `apps/api/alembic/env.py`

## Implementation Steps
1. Modelos SQLAlchemy por módulo; `organization_id NOT NULL` en `roles` y `role_profile_fields`.
2. `alembic revision --autogenerate` → revisar índices/constraints → `0002_esquema_base` (ejecutada como `app_maintainer`; los privilegios para `app_user` los da `ALTER DEFAULT PRIVILEGES` de la fase 1; la migración verifica con `has_table_privilege('app_user', …)` y falla si no).
3. Migración manual `0003_politicas_rls`: funciones `app_current_organization()` y `app_current_user()`, políticas por tabla incluida `users`, `FORCE`; `downgrade` elimina políticas y funciones.
4. Catálogo de permisos: `organizations:read|write`, `branding:write`, `roles:read|write`, `members:read|write`, `users:read`; reservar prefijos para fases futuras.
5. `system_roles.py`: plantillas declarativas (key, permisos, campos con `is_locked`).
6. `OrganizationService.create` (engine de mantenimiento): crea organización, dominio principal, branding por defecto y clona plantillas.
7. Repositorios con filtro explícito por organización; un helper solo para tests (`unsafe_select_all`) que omite el filtro para demostrar que RLS protege.
8. `authorization.py`: `ensure_can_grant(actor_permissions, requested_permissions)`, `ensure_can_manage_role(actor, role)`; usado por servicios de roles y membresías.
9. Servicios: organización (datos, logo vía `StorageProvider` con validación), roles (crear desde plantilla o desde cero, editar campos no bloqueados, impedir borrar `is_system`), membresías (alta con validación de `profile_data` y anti-escalada), usuarios (`me`).
10. `require_permission` real: fija `app.user_id`, resuelve roles del usuario en la organización → permisos.
11. `tenant/branding` real (+ URL pública del logo vía `S3_PUBLIC_BASE_URL`).
12. Seed idempotente (`INSERT … ON CONFLICT` / búsqueda previa por `slug`/`email`/`host`) con `engine_maintenance`; ejecutable dos veces sin error; la contraseña del owner solo se genera/aplica en la primera creación (en ejecuciones posteriores no se sobrescribe salvo `--reset-password`).
12b. Módulo `admin`: `require_superadmin`, servicio que reutiliza `OrganizationService.create` y `add_domain`; CLI `create-superadmin`, `create-organization`, `add-domain`.
13. Tests (BD real, `TRUNCATE` entre tests): CRUD por módulo; campos dinámicos; anti-escalada (crear rol con permiso no poseído → 403; asignar `owner` sin ser `owner` → 403; auto-modificación de rol → 403); **aislamiento RLS**: dos organizaciones, sesión fijada en A, `unsafe_select_all` devuelve solo A en cada tabla incluida `users`; INSERT con `organization_id` de B falla; sin contexto → 0 filas; dos sesiones consecutivas del pool no heredan contexto; `pg_roles` confirma `app_user` sin `BYPASSRLS`.

## Success Criteria
- [x] `alembic upgrade head` crea esquema y políticas; `downgrade` limpio
- [x] `make db-seed` dos veces seguidas deja los mismos datos; login del owner OK
- [x] `test_rls_isolation.py` en verde en CI, incluida `users`
- [x] `test_authorization.py` en verde (3 reglas anti-escalada)
- [x] Crear rol "presentador" con campos propios y alta de miembro con `profile_data` válido; rechazar inválido
- [x] Borrar `speaker` → 409; añadir campo a `speaker` → OK; borrar campo bloqueado → 409
- [x] `GET /tenant/branding` con host `localhost` devuelve branding demo con URL de logo funcional; host desconocido → 404
- [x] `POST /api/v1/admin/organizations` con superadmin crea organización + dominio + roles clonados; con usuario normal → 403; sin token → 401

## Risk Assessment
- Política de `users` con subconsulta a `organization_members` (que también tiene RLS) → la subconsulta se evalúa bajo el mismo contexto, coherente; verificar rendimiento con índice `(organization_id, user_id)`; señal: `EXPLAIN` con seq scan; respuesta: índice.
- Servicios con `engine_maintenance` mal expuestos → solo `modules/admin` puede usar `get_maintenance_db`; test estático (grep en CI) que falla si aparece en cualquier otro `modules/*/router.py` o `service.py`.
- Sobrediseño del esquema → solo lo listado.
