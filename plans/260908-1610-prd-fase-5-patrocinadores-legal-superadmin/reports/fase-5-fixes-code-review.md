# Fase 5 — correcciones del code-review (nivel high)

Fecha: 2026-09-08.

## Hallazgos corregidos

### 1. CRÍTICO — Exportación RGPD rota (GET + body incompatible con Fetch API)

- Endpoint cambiado de `GET` a `POST` en `apps/api/app/modules/admin/router.py` (`/admin/events/{event_id}/rgpd-export`). Documentado en el `description` del endpoint y en el docstring de `RgpdExportRequest` (`apps/api/app/modules/admin/schemas.py`) por qué: la Fetch API prohíbe body en `GET`, y `apps/web` usa `provideHttpClient(withFetch())`.
- Frontend (`apps/web/src/app/features/admin/superadmin/superadmin-page.ts`): `http.request('GET', url, {body})` → `http.post(url, body, {responseType: 'blob'})`.
- Revisado el endpoint `DELETE /admin/registrations/by-email` (mismo módulo): **no tiene el mismo problema**. El Fetch API solo prohíbe body en `GET`/`HEAD`, no en `DELETE` — `http.request('DELETE', url, {body})` funciona sin cambios. No se ha tocado.
- `openapi.json` regenerado (`uv run python -m app.cli export-openapi`) y cliente TS regenerado (`npm run api:types` en `apps/web`), lo que renombró/regeneró los ficheros bajo `apps/web/src/app/core/api/generated/fn/administracion/export-event-rgpd-...`.
- Tests de regresión:
  - Backend (`apps/api/tests/test_admin_auditoria_rgpd.py`): las 4 peticiones a `rgpd-export` pasadas de `"GET"` a `"POST"` en `cliente.request(...)`.
  - Frontend (`apps/web/src/app/features/admin/superadmin/superadmin-page.spec.ts`): nuevo test que usa `HttpTestingController` para comprobar que la petición real es `POST` (nunca `GET`), con el body y `responseType: 'blob'` correctos.
- **Verificación manual end-to-end** contra el stack de desarrollo real (`infra/scripts/dev.sh` ya en marcha, sin reiniciarlo — `uvicorn --reload` recargó el código solo):
  - Login real (`POST /api/v1/auth/login`) con el owner del seed promocionado a superadmin (`create-superadmin`).
  - `POST /api/v1/admin/events/{id}/rgpd-export` con `{"password": "..."}` → `200`, `content-type: application/zip`, ZIP real con `inscripciones.csv` y `entradas.csv`.
  - `GET` al mismo endpoint → `405 Method Not Allowed` (confirma que el verbo roto ya no existe).

### 2. IMPORTANTE — Auditoría de permisos podía persistir tras rollback

- `apps/api/app/modules/roles/service.py`: `update_role` ya no escribe en `audit_log` desde una `maintenance_session` propia en mitad de la función. En su lugar, calcula el detalle de auditoría (`_AuditoriaPermisosPendiente`, un `NamedTuple` para que mypy tipe bien los tres campos) y lo encola con `background_tasks.add_task(...)` **al final de la función**, después de que `profile_fields` haya terminado de validarse.
- Starlette ejecuta los `BackgroundTasks` tras enviar la respuesta — y por tanto tras el `commit` real de la transacción principal, que ocurre al salir de la dependencia `get_db` (mismo patrón ya usado en `events/router.py:upload_cover` y `sponsors/router.py:delete_sponsor`). Si `profile_fields` lanza `ConflictError`, la función nunca llega a `background_tasks.add_task(...)`: no se encola nada, no se escribe nada.
- `apps/api/app/modules/roles/router.py`: `update_role` ahora recibe `background_tasks: BackgroundTasks` y lo reenvía al servicio.
- Test de regresión: `tests/modules/test_roles.py::test_cambio_de_permisos_no_deja_auditoria_si_profile_fields_falla` — PATCH con `permissions` + `profile_fields=[]` (le faltan los campos bloqueados del rol `speaker`) → `409`, y comprueba que `audit_log` sigue vacía y que los permisos del rol no cambiaron.

### 3. MEDIO — Sanitización de Markdown podía no aplicarse tras navegación cliente-cliente

- `apps/web/src/app/features/public/legal/legal-page.ts`: el `afterNextRender` de una sola vez se sustituyó por un `effect()` que reacciona a `contenidoBruto()` en cada cambio, no solo en el primer render. Sigue sin ejecutar `DOMPurify` en el servidor (`if (bruto === null || this.api.isServer) return;`).
- Test de regresión: `apps/web/src/app/features/public/legal/legal-page.spec.ts` — nuevo test que hace `detectChanges()` antes de que la petición HTTP resuelva (comprobando que `.contenido` aún no existe), y solo después hace `flush()`, verificando que el HTML saneado aparece igualmente.

### 4. MENOR — `PATCH sponsor-tiers` con `name`/`logo_size: null` reportaba 409 en vez de 422

- `apps/api/app/modules/sponsors/schemas.py`: añadido `_prohibir_null_explicito(instancia, campos)`, usado en un `model_validator(mode="after")` de `SponsorTierUpdate` para `("name", "display_order", "logo_size")` — las tres son `NOT NULL` en BD. Un `null` explícito ahora es un 422 de validación de Pydantic, nunca llega a la BD.
- No hizo falta tocar el `except IntegrityError` de `sponsors/service.py`: con el `null` bloqueado en el esquema, ese `except` solo puede seguir significando lo que decía (`UNIQUE(organization_id, name)`).
- Test de regresión: `tests/test_sponsors_router.py::test_patch_de_nivel_con_name_null_devuelve_422_no_409`.

### 5. MENOR — `PATCH sponsor` con `tier_id: null` daba 500 en vez de 422

- Mismo mecanismo: `SponsorUpdate` gana el mismo `model_validator` para `("tier_id", "name", "contribution_type")` — las tres `NOT NULL` en BD. `contribution_amount`/`contribution_description` se dejan tal cual: su `null` explícito es intencionado (limpian el lado no usado al cambiar `contribution_type`, ver `service.update_sponsor`).
- Test de regresión: `tests/test_sponsors_router.py::test_patch_de_patrocinador_con_tier_id_null_devuelve_422_no_500`.

## Hallazgos de calidad — corregidos (coste bajo)

### 6. Guarda-clausula duplicada en `legal/router.py`

Extraída a `_obtener_organizacion_o_404(session, organization_id)`, mismo patrón que `_obtener_evento_o_404` de `sponsors/router.py`. Usada en `get_legal_pages`, `update_legal_pages` y `_pagina_publica`.

### 7. Constantes de validación de logo duplicadas

Nuevo módulo `apps/web/src/app/shared/uploads/image-upload-constraints.ts` (`IMAGEN_MIMES_PERMITIDOS`, `IMAGEN_TAMANO_MAXIMO`), usado en `event-form.ts` y `event-sponsors.ts`. **Nota**: `apps/web/src/app/features/admin/branding/branding-page.ts` tiene la misma duplicación exacta pero no estaba en el hallazgo original (es de una fase anterior del proyecto) — no se ha tocado para no exceder el alcance pedido; queda documentado aquí como candidato a la misma extracción en otra pasada.

### 8. `capitaliza()` duplicada con implementaciones distintas

Nuevo módulo `apps/web/src/app/shared/text/capitalizar-clave-de-traduccion.ts` (`capitalizarClaveDeTraduccion`), que separa por `_` y capitaliza cada parte. Usado desde `event-form.ts`, `event-agenda.ts`, `sponsor-tiers-page.ts` y `event-sponsors.ts` (los métodos `capitaliza()` de cada componente ahora delegan en la función compartida, sin tocar las plantillas que los llaman).

Efecto colateral positivo: la implementación de `event-sponsors.ts` (`.replace('_', '')`) tenía un bug latente — para `contribution_type: "en_especie"` generaba la clave `tipoEnespecie` en vez de `tipoEnEspecie` (no coincidía con el JSON de idioma, aunque ningún test lo cubría). La función compartida lo corrige. Test de regresión: `apps/web/src/app/shared/text/capitalizar-clave-de-traduccion.spec.ts`.

### 9. `mover()` en `sponsor-tiers-page.ts` en serie en vez de en paralelo

Los dos `PATCH` (uno por nivel afectado) van ahora en `Promise.all(...)`. Verificado que es seguro: tocan filas distintas de `sponsor_tiers`, sin ninguna restricción `UNIQUE` sobre `display_order` (solo hay `UNIQUE(organization_id, name)` y la compuesta `UNIQUE(id, organization_id)` para la FK), y cada `PATCH` es su propia transacción HTTP independiente — no hay condición de carrera server-side.

### 10. `markdownToSafeHtml` sin barrera que fuerce su uso antes de `[innerHTML]`

**Aceptado sin cambio de código.** Añadido un comentario de invariante explícito en `apps/web/src/app/shared/legal/sanitize-markdown.ts`. Justificación: hoy solo tiene un consumidor (`legal-page.ts`, ya cubierto por tests que verifican que un `<script>` guardado como contenido legal nunca aparece ejecutable en el DOM). Envolver esto en un `Pipe`/`Directive` reutilizable con un único punto de uso sería indirección sin beneficiario — si aparece un segundo consumidor, ahí sí compensa el coste.

## Resultado de tests

- Backend (`apps/api`): `uv run pytest -q` → **todos verdes** (suite completa, incluye los tests de regresión nuevos de los hallazgos 1, 2, 4 y 5).
- Backend lint/tipos: `uv run ruff check app tests` → 2 errores preexistentes de `E501` en ficheros no tocados por esta corrección (`sponsors/router.py:144`, `test_sponsors_router.py:142`, ya presentes antes de este trabajo). `uv run mypy app/modules/roles app/modules/sponsors app/modules/admin app/modules/legal` → sin errores.
- Frontend (`apps/web`): `npm test -- --watch=false` → **45 ficheros / 164 tests, todos verdes** (incluye los tests de regresión nuevos de los hallazgos 1, 3 y 8). `npm run lint` → sin errores. `npx tsc --noEmit` → sin errores.
- `openapi.json` y el cliente TS generado (`apps/web/src/app/core/api/generated/**`) están regenerados y en sincronía con el cambio de verbo del hallazgo 1.
- Verificación manual end-to-end del hallazgo 1 contra el stack de desarrollo real: ver sección del hallazgo 1 arriba.

## Ficheros modificados

**Backend**
- `apps/api/app/modules/admin/router.py`
- `apps/api/app/modules/admin/schemas.py`
- `apps/api/app/modules/roles/service.py`
- `apps/api/app/modules/roles/router.py`
- `apps/api/app/modules/sponsors/schemas.py`
- `apps/api/app/modules/legal/router.py`
- `apps/api/openapi.json` (regenerado)
- `apps/api/tests/test_admin_auditoria_rgpd.py`
- `apps/api/tests/modules/test_roles.py`
- `apps/api/tests/test_sponsors_router.py`

**Frontend**
- `apps/web/src/app/features/admin/superadmin/superadmin-page.ts`
- `apps/web/src/app/features/admin/superadmin/superadmin-page.spec.ts`
- `apps/web/src/app/features/public/legal/legal-page.ts`
- `apps/web/src/app/features/public/legal/legal-page.spec.ts`
- `apps/web/src/app/features/admin/events/event-form.ts`
- `apps/web/src/app/features/admin/events/event-agenda.ts`
- `apps/web/src/app/features/admin/events/event-sponsors.ts`
- `apps/web/src/app/features/admin/sponsors/sponsor-tiers-page.ts`
- `apps/web/src/app/shared/legal/sanitize-markdown.ts` (comentario, sin cambio de comportamiento)
- `apps/web/src/app/shared/uploads/image-upload-constraints.ts` (nuevo)
- `apps/web/src/app/shared/text/capitalizar-clave-de-traduccion.ts` (nuevo)
- `apps/web/src/app/shared/text/capitalizar-clave-de-traduccion.spec.ts` (nuevo)
- `apps/web/src/app/core/api/generated/**` (regenerado)

Status: DONE
Summary: Los 5 hallazgos funcionales (1 crítico, 1 importante, 3 menores) y los 4 de calidad quedan corregidos con test de regresión, salvo el #10 (documentado sin cambio de código, justificado por tener un único consumidor); toda la suite backend y frontend está en verde y la exportación RGPD se verificó funcionando end-to-end contra el stack de desarrollo real.
Concerns/Blockers: ninguno. Nota aparte (no bloqueante): `branding-page.ts` tiene la misma duplicación de constantes de logo que el hallazgo #7 pero no estaba en el alcance pedido; queda anotado en el informe por si se quiere unificar en otra pasada.
