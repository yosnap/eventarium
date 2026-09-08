# Fase 1 — Modelo de datos, permisos y niveles de patrocinio

Implementación completa. Migración aplicada y probada en la base de datos de
tests (`ia_week_test`); suite completa de `apps/api` en verde (353 tests).

## Qué se creó

- **Migración** `apps/api/alembic/versions/0012_patrocinio_legal_auditoria.py`
  (revision id acortado por límite de `alembic_version.version_num`
  `varchar(32)`, ver Desviaciones):
  - `sponsor_tiers` (organización) con `UNIQUE(organization_id, name)` y
    `UNIQUE(id, organization_id)`.
  - `sponsors` (evento + nivel), FK compuesta `CASCADE` a `events`, FK
    compuesta `RESTRICT` a `sponsor_tiers`.
  - `audit_log`: sin RLS, `REVOKE ALL ... FROM app_user` explícito.
  - `cookie_consents`: sin RLS, `REVOKE ALL` + `GRANT INSERT` a `app_user`.
  - Columnas legales nuevas en `organizations` (`legal_address`, `tax_id`,
    `legal_notice_content`, `privacy_policy_content`,
    `cookies_policy_content`, `registration_terms_content`).
  - Backfill `sponsors:read`/`sponsors:write` con `WHERE NOT EXISTS`.
  - `downgrade()` simétrico completo.
- **Permisos**: `SPONSORS_READ`/`SPONSORS_WRITE` en
  `apps/api/app/core/permissions.py`; `AUDIT_READ` explícitamente no añadido
  (documentado en el docstring del módulo).
- **Plantilla de rol**: `ORGANIZER` en
  `apps/api/app/modules/roles/system_roles.py` actualizada con
  `SPONSORS_READ`/`SPONSORS_WRITE` en código (no solo backfill).
- **Modelos**:
  - `apps/api/app/modules/sponsors/models.py` — `SponsorTier`, `Sponsor`.
  - `apps/api/app/core/audit.py` — `AuditLog`.
  - `apps/api/app/modules/legal/models.py` — `CookieConsent`.
  - `apps/api/app/modules/organizations/models.py` — columnas legales
    añadidas al modelo `Organization`.
- **Repository/service mínimos** (`apps/api/app/modules/sponsors/
  repository.py`, `service.py`): `create_tier`/`delete_tier` con captura de
  `IntegrityError` → `ConflictError` (409). Es el mínimo necesario para
  probar el hallazgo de 409 vs 500; el CRUD completo queda para la fase 2.
- **`alembic/env.py`**: registrados los tres módulos de modelos nuevos
  (`sponsors`, `legal`, `audit`) para que `Base.metadata` los conozca
  (autogenerate/compare_type futuros).
- **`apps/api/tests/conftest.py`**: `sponsor_tiers`, `sponsors`, `audit_log`,
  `cookie_consents` añadidas a `TABLAS`.
- **Tests nuevos**:
  - `test_sponsors_legal_auditoria_migracion.py`: privilegios positivos/
    negativos de `app_user`, ciclo `downgrade -1` → `upgrade head`.
  - `test_sponsors_rls_isolation.py`: aislamiento de lectura y escritura
    cruzada para `sponsor_tiers`/`sponsors`, más el 409/`IntegrityError` de
    la FK `RESTRICT` a nivel de base de datos.
  - `test_sponsors_service.py`: 409 real vía el servicio (no solo la BD),
    404 sobre nivel inexistente, borrado exitoso sin patrocinadores.
  - `test_sponsors_permisos.py`: `AUDIT_READ` fuera del enum, plantilla
    `ORGANIZER` con `sponsors:*` en código, backfill real sobre un rol
    insertado a mano simulando el estado anterior a esta migración, y una
    organización creada en el propio test tras la migración con
    `sponsors:*` en su `organizer`.
  - `test_audit_log_y_cookie_consents.py`: aislamiento entre tests (la
    adición a `TABLAS` evita contaminación) y ausencia de campos de IP/
    email/`user_id` en `CookieConsent`.

## Decisiones tomadas (margen que dejaba el plan)

- **Ubicación de modelos**: `AuditLog` en `app/core/audit.py` (tal como
  sugería la tarea, no un módulo de dominio — no pertenece a ningún
  tenant); `CookieConsent` en `app/modules/legal/models.py` (módulo nuevo,
  reservado para el resto de piezas legales de la fase 3); `SponsorTier`/
  `Sponsor` en `app/modules/sponsors/models.py`.
- **`logo_size`/`contribution_type` como `String` con comentario de valores
  válidos**, no un `ENUM` nativo de PostgreSQL — mismo patrón que
  `Event.status`/`Event.visibility`/`Event.location_mode` en el esquema
  existente; el proyecto no usa tipos enum nativos en ningún sitio.
- **Revision id acortado**: `0012_patrocinadores_legal_y_auditoria` (37
  caracteres) supera el límite de `alembic_version.version_num
  varchar(32)` y el `UPDATE` final de cada `upgrade` falla con
  `StringDataRightTruncationError`. Renombrado a
  `0012_patrocinio_legal_auditoria` (31 caracteres). Descubierto
  ejecutando la migración de verdad, no en revisión estática — confirma
  por qué el plan pide ejecutar el ciclo real, no solo leerlo.
- **Repository/service mínimo de `sponsor_tiers`**: solo `get_tier`,
  `create_tier`, `delete_tier` — justo lo necesario para el test del 409,
  sin adelantar el CRUD completo (patrocinadores, reordenar niveles, subir
  logo) que corresponde a la fase 2.

## Resultado de tests

- Suite completa `apps/api/tests/`: **353 passed**, 0 fallos.
- `ruff check .` (todo `apps/api`): sin errores.
- `mypy app` (modo `strict`): sin errores.
- Ciclo de migración verificado dos veces: `upgrade head` → `downgrade -1`
  → `upgrade head` (test automatizado) y `downgrade base` → `upgrade head`
  desde una base vacía (manual, para confirmar que toda la cadena de
  migraciones sigue siendo consistente).
- Privilegios de `app_user` comprobados por SQL directo y por test:
  `sponsor_tiers`/`sponsors` con `SELECT`; `audit_log` sin `SELECT` ni
  `DELETE`; `cookie_consents` sin `SELECT`, con `INSERT`.

## Desviaciones del plan (con justificación)

1. **Revision id más corto que el propuesto en los ejemplos del plan**
   (`0012_patrocinio_legal_auditoria` en vez de un nombre más descriptivo
   tipo `0012_patrocinadores_legal_y_auditoria`) — límite duro de
   `varchar(32)` en `alembic_version`, no una preferencia de estilo.
2. **No se tocó `docs/`** (arquitectura, modelo de datos, despliegue):
   fuera del alcance explícito de esta fase de trabajo según las
   instrucciones recibidas («no implementes... nada de fases 2-5»); el
   Success Criterion de nivel de plan sobre `docs/` corresponde a la fase 5
   de trabajo (cierre), no a esta.
3. **No se tocaron `organizations/schemas.py` ni `router.py`** para
   exponer los campos legales nuevos: son columnas de modelo puras para
   que la fase 3 las use; añadir los campos a los esquemas Pydantic sin
   validación/edición real habría sido trabajo de esa fase, no de esta.

## Preguntas sin resolver

Ninguna. El diseño de la fase estaba completamente especificado por el plan
y su red-team; no hubo ninguna decisión de arquitectura pendiente de
resolver durante la implementación.
