---
phase: 2
title: "Fase 2: Registro y alta de organización"
status: pending
priority: P1
effort: "3.5-4d"
dependencies: [1]
---

# Fase 2: Registro y alta de organización

## Overview

De una cuenta verificada a una organización operativa con su propio subdominio, sin que
un superadministrador intervenga. Es el cambio de mayor riesgo del plan: hoy
`create_organization` es una operación de mantenimiento invocada por el CLI o por
`modules/admin` con el rol `app_maintainer` (`BYPASSRLS`); aquí se expone a cualquier
usuario autenticado, con las salvaguardas que evitan que se convierta en una vía de
ocupación de subdominios o en un bypass de RLS.

Incluye la página web de creación de organización: sin ella el flujo de registro de la
fase 1 no llega a ningún sitio.

## Decisiones validadas — Sesión 2026-09-07

- El usuario **elige** su subdominio, con sugerencia automática a partir del nombre y
  comprobación de disponibilidad en vivo.
- Turnstile obligatorio en producción sobre este endpoint (formulario público),
  reutilizando `core/turnstile.py` de la fase 1.
- Correo verificado obligatorio antes de crear (403 si no) — ver fase 1: el estado «no
  verificado» se predica de la cuenta, no de la organización. El borrado por caducidad
  de este plan aplica a **cuentas de usuario** no verificadas (fase 1), no a
  organizaciones: una organización no puede existir sin que su creador ya haya
  verificado.
- **Decisión cerrada tras spike (2026-09-07)**: Taskiq 0.12.6 soporta *scheduling*
  nativo (`TaskiqScheduler` + `LabelScheduleSource`), pero `TaskiqScheduler` es una
  clase separada que corre en su propio proceso (`taskiq scheduler …`), distinto de
  `taskiq worker`. **Se añade un cuarto servicio `scheduler`** a
  `infra/docker-compose.yml`, `infra/docker-compose.prod.yml` y `docs/despliegue.md`
  como parte de esta fase — no queda como decisión aplazada a la implementación.

## Hallazgos aplicados en esta fase

Este es el fichero con más correcciones: la creación de organización por autoservicio
fue el hallazgo Critical del red-team.

### Red-team (seguridad y supuestos no verificados)

| # | Hallazgo | Corrección |
|---|---|---|
| Critical | El plan original decía «reutiliza `create_organization`» sin especificar el motor de conexión. Reutilizarlo tal cual desde un router público exigiría dar `engine_maintenance`/`BYPASSRLS` a ese router, rompiendo la invariante «solo `modules/admin` usa el motor de mantenimiento», probada con un test estático desde la fase 0 | Función `SECURITY DEFINER` de alcance mínimo (`app_bootstrap_organization`), invocada desde `engine_app` con el rol normal de la API — mismo patrón que `app_resolve_organization` de la fase 0. El router de autoservicio nunca importa `get_maintenance_db` |
| Critical | Contradicción: «correo verificado obligatorio para crear» vs «organización no verificada se borra a los 7 días» — ninguna organización llegaría a ese estado | Resuelto: el borrado por caducidad aplica a la **cuenta de usuario** (fase 1), no a la organización |
| High | El *scheduling* del aviso/borrado exige un proceso `taskiq scheduler`, que hoy no existe en ningún Compose ni en `docs/despliegue.md` | Confirmado por spike: servicio `scheduler` nuevo, añadido en esta fase |
| Medium | `check-slug` sin límite de peticiones propio | Límite por IP independiente del de creación |
| Medium | Condición de carrera entre `check-slug` y la creación real | La creación captura el conflicto `UNIQUE` de base de datos como única fuente de verdad; `check-slug` es solo ayuda de UX |
| Low | La lista de reservados solo se exigía en la creación | Se aplica también en `check-slug` |

### Predict/debate (5 personas, sobre el plan ya endurecido)

| # | Quién | Hallazgo | Corrección |
|---|---|---|---|
| Importante | Arquitectura | `app_bootstrap_organization` es multi-escritura dentro de `SECURITY DEFINER` (a diferencia de `app_resolve_organization`, que solo lee); si `p_owner_user_id` viniera de un valor de formulario, cualquiera podría crear una organización a nombre de otra persona | `p_owner_user_id` se pasa **siempre** desde el usuario del token autenticado, nunca de un campo del cuerpo de la petición; test explícito que intenta forzar un `p_owner_user_id` ajeno y espera fallo |
| Importante | Arquitectura | Dos caminos de creación de organización (`OrganizationService.create` para admin/CLI, `app_bootstrap_organization` para autoservicio) pueden divergir con el tiempo | Test de paridad: mismo `name`/`slug` por ambos caminos produce el mismo conjunto de roles clonados y el mismo branding por defecto |
| Importante | Rendimiento | Límites de peticiones sin cifra fija | Constantes explícitas en `core/ratelimit.py`, coherentes con las de la fase 1 |
| Opcional | Rendimiento | `check-slug` sin *debounce* agotaría el límite por IP con el uso normal | El campo de slug aplica *debounce* de 300-500 ms antes de llamar a `check-slug` |
| Bloqueante | UX | Ninguna fase incluía la página de creación de organización | Página añadida a esta fase |
| Opcional | UX | El panel recién creado queda vacío (sin eventos, fuera de alcance) | Mensaje explícito de «los eventos llegan en la próxima fase» en vez de pantalla en blanco (aplicado en fase 3, donde vive el dashboard) |

## Requirements

- Functional:
  - `GET /api/v1/organizations/check-slug?slug=…`: comprobación de disponibilidad
    (formato, reservados, unicidad), con su propio límite de peticiones por IP. Es
    ayuda de UX, no la validación de seguridad.
  - `POST /api/v1/organizations` (nuevo, distinto del endpoint de superadmin): nombre,
    slug deseado, token de Turnstile. Autenticado, exige `email_verified_at` no nulo
    (403 si no). Invoca `app_bootstrap_organization` con el `user_id` del token (nunca
    del cuerpo) — crea organización, clona roles del sistema, registra al creador como
    `owner`, añade el dominio `{slug}.{DOMINIO_BASE}` — en una sola transacción
    atómica. El conflicto de unicidad de slug/host a nivel de base de datos se traduce
    a 409.
  - Página web `create-organization-page.ts`: nombre, sugerencia de slug con
    comprobación en vivo (debounce 300-500 ms), Turnstile.
  - Servicio `scheduler` (proceso `taskiq scheduler app.core.tasks:scheduler`): ejecuta
    el barrido de cuentas no verificadas definido en esta fase — aviso por correo a los
    5 días, borrado a los 7, sobre cuentas con `email_verified_at=null` (fase 1).
- Non-functional: `DOMINIO_BASE` en configuración, validado en producción (no vacío,
  igual que ya se exige `DEFAULT_ORGANIZATION_SLUG` vacío); el slug se valida contra
  `^[a-z0-9]+(?:-[a-z0-9]+)*$` más la lista de reservados (`www`, `api`, `admin`,
  `mail`, `app`, `media`, y el propio dominio raíz), aplicada igual en `check-slug` y en
  la creación; límite de creación por IP y por usuario con cifra fija en
  `core/ratelimit.py`; Turnstile fail-closed en este endpoint, igual que en el
  registro.

## Architecture

- `app_bootstrap_organization(p_name, p_slug, p_owner_user_id, p_host) RETURNS uuid`:
  función `SECURITY DEFINER` de alcance mínimo, con `REVOKE ALL ... GRANT EXECUTE TO
  app_user`, siguiendo el patrón de `app_resolve_organization` (migración
  `0003_politicas_rls`) pero con escritura multi-tabla dentro del bypass — por eso
  `p_owner_user_id` nunca puede venir de un valor no verificado: el router lo obtiene
  del `CurrentUser` ya autenticado, igual que cualquier otro endpoint. Internamente
  aplica la misma lógica que `OrganizationService.create` y `add_domain` (clonación de
  roles, branding por defecto), pero expuesta de forma auditable y de alcance mínimo,
  en vez de delegar el bypass a todo un motor de conexión.
- `app_check_slug_available(p_slug) RETURNS boolean`: función `SECURITY DEFINER`
  equivalente para la comprobación en vivo, sin exponer más que un booleano.
- Nuevo router `modules/organizations/self_service.py` (o ampliar `router.py` si no
  crece más allá de 300 líneas), separado de `modules/admin` para que el test estático
  de la fase 0 (`get_maintenance_db` solo en `admin`) siga siendo la garantía real: este
  router **nunca** debe aparecer en esa lista.
- `apps/api/app/core/tasks.py` se amplía con una instancia `scheduler` (`TaskiqScheduler`
  + `LabelScheduleSource`) y una tarea con `schedule` fijo (p. ej. cada hora) que
  consulta `users` con `email_verified_at=null` (usando el índice parcial de la fase 1)
  y calcula antigüedad; envía el aviso a los que cumplen 5 días y no lo han recibido,
  borra los que cumplen 7. Verificar entre medias simplemente hace que el barrido deje
  de seleccionar esa cuenta, sin cancelación explícita.
- Compose de desarrollo y de producción: nuevo servicio `scheduler`, misma imagen que
  `worker`, comando `taskiq scheduler app.core.tasks:scheduler`.

## Related Code Files

- Create: `apps/api/alembic/versions/` (nueva migración: `app_bootstrap_organization`,
  `app_check_slug_available`, y sus `REVOKE`/`GRANT`)
- Create: `apps/api/app/modules/organizations/self_service.py`
- Modify: `apps/api/app/modules/organizations/router.py`, `schemas.py`
- Modify: `apps/api/app/core/config.py` (`DOMINIO_BASE`, lista de reservados)
- Modify: `apps/api/app/core/ratelimit.py` (constantes de creación y `check-slug`)
- Modify: `apps/api/app/core/tasks.py` (`scheduler`, tarea de barrido)
- Create: `apps/api/app/core/cleanup.py` (lógica del barrido, invocada por la tarea)
- Create: `apps/api/tests/modules/test_self_service_organizations.py`
- Create: `apps/api/tests/test_cleanup_unverified_accounts.py`
- Create: `apps/web/src/app/features/public/create-organization/create-organization-page.ts`
- Modify: `apps/web/src/app/app.routes.ts` (ruta `/crear-organizacion`)
- Modify: `infra/docker-compose.yml`, `infra/docker-compose.prod.yml`, `Makefile`
  (target para arrancar el scheduler en desarrollo), `docs/despliegue.md`

## Implementation Steps

1. Migración con `app_bootstrap_organization` y `app_check_slug_available`, siguiendo
   exactamente el patrón de `SECURITY DEFINER` + `REVOKE`/`GRANT` ya usado;
   `p_owner_user_id` documentado en el propio SQL como «debe venir del token, nunca de
   entrada de usuario».
2. `DOMINIO_BASE` en `Settings`, validado en producción; lista de reservados.
3. `check-slug`: valida formato, reservados, y llama a `app_check_slug_available`; con
   su propio límite de peticiones.
4. Endpoint de creación: exige correo verificado y Turnstile, invoca
   `app_bootstrap_organization` con el `user_id` del token, traduce el conflicto
   `UNIQUE` a 409.
5. `core/tasks.py`: instancia `scheduler`, tarea de barrido con `schedule` fijo.
   Servicio `scheduler` en ambos Compose y target de Makefile.
6. `create-organization-page.ts` con sugerencia de slug, *debounce*, Turnstile.
7. Tests: creación válida deja al creador como `owner`; slug repetido → 409; slug
   reservado → 422 (en creación y en `check-slug`); sin verificar el correo → 403;
   Turnstile inválido → 422, caído → 503; límite de peticiones en ambos endpoints;
   condición de carrera (dos creaciones concurrentes con el mismo slug: una gana, la
   otra recibe 409, no un error 500); intento de crear con un `p_owner_user_id` ajeno
   falla; test de paridad entre `OrganizationService.create` y
   `app_bootstrap_organization`; comprobación estática de que
   `self_service.py`/`router.py` no importan `get_maintenance_db`; el aviso se envía a
   los 5 días y no antes; la cuenta desaparece a los 7 días y no antes; verificar tras
   el aviso cancela el borrado; `EXPLAIN` de la consulta del barrido no muestra
   *sequential scan*.
8. Actualizar `docs/arquitectura.md` (las dos funciones `SECURITY DEFINER` nuevas y el
   servicio `scheduler`) y `docs/despliegue.md` (cuarto servicio en EasyPanel/Compose).

## Success Criteria

- [ ] Un usuario verificado crea su organización y aparece como `owner`
- [ ] El subdominio responde en `GET /api/v1/tenant/branding` inmediatamente después
- [ ] No se puede repetir un slug ni usar uno reservado, ni en la creación ni en
      `check-slug`
- [ ] Un usuario sin verificar no puede crear organización
- [ ] No se puede crear una organización a nombre de otro usuario
- [ ] `self_service.py` y `router.py` de organizaciones no usan `get_maintenance_db`
      (test estático)
- [ ] Dos creaciones concurrentes con el mismo slug: una tiene éxito, la otra recibe
      409 limpio
- [ ] `app_bootstrap_organization` y `OrganizationService.create` producen los mismos
      roles y el mismo branding por defecto (test de paridad)
- [ ] El servicio `scheduler` corre y ejecuta el barrido según su `schedule`
- [ ] Una cuenta sin verificar recibe el aviso a los 5 días y se borra a los 7
- [ ] Tests de aislamiento existentes siguen en verde

## Risk Assessment

- Exponer la creación de organización sin las validaciones de superadmin sigue siendo
  el punto de mayor riesgo del plan → mitigado con `SECURITY DEFINER` de alcance
  mínimo en vez de `engine_maintenance`, `p_owner_user_id` solo del token, y revisión de
  PR obligatoria centrada en la migración y en `self_service.py`.
- Colisión entre el router de autoservicio y el de `modules/admin` → mantenerlos en
  módulos separados; el test estático de la fase 0 se amplía explícitamente a este
  router nuevo.
- Ventana de squat de 7 días por intento, repetible → riesgo residual aceptado
  (documentado en `plan.md`), no se sobre-diseña de entrada.
- Servicio `scheduler` nuevo en producción sin experiencia previa de despliegue →
  probarlo primero en el Compose de desarrollo; documentar en `docs/despliegue.md` con
  el mismo nivel de detalle que `worker`.
