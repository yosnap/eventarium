# Fase 4 — Superadmin: auditoría y RGPD — Informe de implementación

Status: DONE

## Decisión de sesión de escritura de `audit_log` (paso 1 requerido)

Dos opciones estaban sobre la mesa: `GRANT INSERT ON audit_log TO app_user`
en una migración nueva, o que `roles.service.update_role` (que corre bajo
`app_user`, `get_db`) abra su propia `maintenance_session()` solo para el
insert de auditoría.

**Elegida: `maintenance_session()` propia, sin tocar privilegios.** Motivos:

- No amplía los privilegios de `app_user` sobre una tabla que la fase 1 de
  trabajo dejó deliberadamente con `REVOKE ALL` (hallazgo #1 del red-team del
  plan) — cualquier `GRANT` puntual reabre parcialmente esa superficie.
- El patrón ya existe en el propio proyecto: `registrations/service.
  expire_waitlist_promotions` (tarea cron) ya usa `maintenance_session()`
  fuera de `app/modules/admin`, así que no es un patrón nuevo ni rompe el
  test estático `test_solo_el_modulo_admin_usa_el_motor_de_mantenimiento`
  (que solo vigila `get_maintenance_db`, no `maintenance_session`).
- Las otras dos acciones instrumentadas (alta de organización, alta de
  dominio) ya corren bajo `get_maintenance_db` en `admin/router.py`, así que
  ahí el registro de auditoría usa la misma sesión de la petición sin abrir
  ninguna nueva.

Un solo helper de escritura (`app.core.audit.registrar_auditoria`) se usa en
los tres puntos de instrumentación (rol, organización, dominio) y en los tres
endpoints nuevos.

## Qué se creó/modificó

**Backend**
- `app/core/audit.py`: `registrar_auditoria()` — único punto de inserción en
  `audit_log`.
- `app/core/security.py`: `hash_email_with_salt()` — HMAC-SHA256 con
  `jwt_secret` como clave, usado por el borrado RGPD (decisión #6 del plan:
  nunca el email en claro en `audit_log.detail`).
- `app/core/ratelimit.py`: `AUDIT_LOG_POR_IP`, `RGPD_EXPORT_POR_IP`,
  `RGPD_DELETE_POR_IP`.
- `app/modules/roles/service.py` + `router.py`: `update_role` audita
  `role.permissions_changed` (permisos antes/después) vía
  `maintenance_session()` propia cuando el payload trae `permissions`.
- `app/modules/admin/schemas.py` (nuevo): `AuditLogEntry`,
  `Reauthentication` (mixin de contraseña en el body), `RgpdExportRequest`,
  `DeleteRegistrationRequest`.
- `app/modules/admin/service.py` (nuevo): `verificar_password_de_superadmin`,
  `list_audit_log`, `exportar_rgpd_evento` (ZIP en memoria, CSV con prefijado
  anti-fórmulas `_celda_segura`, sin JWT del QR), `borrar_inscrito_por_email`
  (reutiliza `registrations.service.cancel_registration`, anonimiza
  `event_ticket_scans.ticket_id`, borrado real de la fila),
  `audit_detail_borrado`.
- `app/modules/admin/router.py`: instrumenta alta de organización/dominio;
  añade `GET /admin/audit-log`, `GET /admin/events/{id}/rgpd-export`,
  `DELETE /admin/registrations/by-email`, los tres con `Superadmin` +
  `limit_per_ip` + (los dos últimos) reautenticación por contraseña.
- `apps/api/openapi.json`: regenerado.

**Frontend**
- `apps/web/src/app/features/admin/superadmin/superadmin-page.ts` (+ spec):
  pantalla nueva — tabla de auditoría filtrable (organización, acción, rango
  de fechas) + formulario de exportación RGPD (descarga el ZIP) + formulario
  de borrado por email (con `confirm()` nativo antes de enviar).
- `apps/web/src/app/app.routes.ts`: ruta `admin/superadmin`.
- `apps/web/src/app/layouts/admin/admin-shell.ts`: enlace de navegación
  visible solo si `auth.currentUser()?.is_superadmin`.
- `apps/web/public/assets/i18n/es-ES.json`: claves `admin.superadminNav` y
  `admin.superadmin.*`.
- Cliente TS regenerado (`ng-openapi-gen`): nuevos modelos/fn de
  `administracion` (`AuditLogEntry`, `DeleteRegistrationRequest`,
  `RgpdExportRequest`, `PageAuditLogEntry`).

**Tests**
- `apps/api/tests/test_admin_auditoria_rgpd.py` (nuevo, 10 tests): 403 para
  organizador en los tres endpoints; auditoría de alta de organización/
  dominio/cambio de rol; filtro por rango de fechas; exportación RGPD con
  celda `=cmd|...` neutralizada y comparada campo a campo contra la BD (email,
  nombre, estado, respuesta); CSV de entradas sin JWT (columnas exactas
  verificadas); reautenticación incorrecta → 401 en export y en borrado;
  borrado de `confirmed` con lista de espera → email de promoción encolado,
  fila borrada, escaneo anonimizado (no borrado) y auditoría con hash (nunca
  el email en el `detail`); 404 al borrar una inscripción inexistente;
  rate-limit del export tras 11 peticiones → 429.
- `apps/web/.../superadmin-page.spec.ts` (nuevo, 2 tests, con
  `esperarSinViolacionesDeAccesibilidad`): listado inicial sin violaciones de
  axe; borrado con reautenticación recarga la auditoría.

## Resultado de tests

- Backend completo (`uv run pytest`, apps/api): **364 tests, 0 fallos**
  (incluye los 10 nuevos de esta fase, más toda la suite previa de fases 1-3
  sin regresiones).
- `uv run mypy app/`: sin errores.
- `uv run ruff check app/`: sin errores nuevos (1 error preexistente en
  `sponsors/router.py`, ajeno a esta fase, no tocado).
- Frontend: `superadmin-page.spec.ts` (2/2) y `shells.spec.ts` (3/3, nav
  intacta) en verde; `pnpm lint` y `tsc --noEmit` sin errores.
- `make api-types`: `openapi.json` regenerado y cliente TS regenerado sin
  diferencias pendientes.

## Desviaciones del plan (con justificación)

- **`GET`/`DELETE` con cuerpo JSON**: el plan pide explícitamente
  `GET /admin/events/{id}/rgpd-export` y
  `DELETE /admin/registrations/by-email` llevando la contraseña de
  reautenticación en el body — no es RESTful en sentido estricto, pero
  FastAPI y `httpx`/Angular `HttpClient.request()` lo soportan sin problema;
  se implementó tal cual lo pide el plan en vez de forzarlo a POST, que
  habría contradicho el método declarado en Requirements/Implementation
  Steps.
- **`DeleteRegistrationRequest.event_id` como `str`** (no `UUID` de Pydantic):
  mismo patrón que `registrations/router.py` (`registration_id: str`), que
  convierte con `uuid.UUID(...)` en el propio handler — se mantuvo la
  convención existente del código en vez de introducir un tipo distinto solo
  aquí.
- **Panel de superadmin es una pantalla nueva**, no una ampliación de una
  vista de evento existente: no existía ninguna vista de evento accesible
  específicamente a superadmin en el panel (`apps/web/.../features/admin/`
  solo tiene el panel de organizador); construir una pantalla nueva bajo
  `/admin/superadmin`, visible solo si `is_superadmin`, era la opción que el
  propio `phase-04-*.md` dejaba abierta para este caso.

## Preguntas sin resolver

Ninguna.
