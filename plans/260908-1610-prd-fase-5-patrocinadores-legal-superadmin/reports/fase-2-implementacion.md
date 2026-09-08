# Fase 2 — CRUD de patrocinadores y página pública: informe de implementación

Fecha: 2026-09-08

## Qué se creó

### Backend (`apps/api/app/modules/sponsors/`)

- `schemas.py` (nuevo): `SponsorTierCreate/Update/Response`,
  `SponsorCreate/Update/Response`, `PublicSponsor`/`PublicSponsorTier`, y
  `validate_contribution()` — valida que `monetaria`/`en_especie` sean
  mutuamente excluyentes con `contribution_amount`/`contribution_description`.
- `repository.py` (ampliado desde la fase 1): añadidas `sponsor_tiers_query`,
  `sponsors_query` (join con `SponsorTier` para ordenar por
  `display_order`), `get_sponsor`, `public_sponsors_query`.
- `service.py` (ampliado): `update_tier`, `create_sponsor`, `update_sponsor`
  (revalida la exclusividad de la aportación contra el estado ya guardado en
  un `PATCH` parcial), `delete_sponsor` (devuelve la clave del logo para que
  el router la borre en `BackgroundTask` tras el commit).
- `router.py` (nuevo): dos routers —
  `GET/POST/PATCH/DELETE /organizations/me/sponsor-tiers` y
  `GET/POST/PATCH/DELETE /events/{event_id}/sponsors` +
  `PUT /events/{event_id}/sponsors/{sponsor_id}/logo`. Permisos
  `SPONSORS_READ`/`SPONSORS_WRITE` según verbo. La subida de logo reutiliza
  `validate_upload`/`build_object_key`/`put_object` de `core/storage.py`
  (mismo patrón por contenido, no MIME declarado) y el borrado diferido a
  `BackgroundTask` post-commit de `events/router.py:upload_cover`.
- `app/modules/events/schemas.py`: `PublicEventDetail` ganó
  `sponsor_tiers: list[PublicSponsorTier]`.
- `app/modules/events/public_router.py`: `get_public_event` ahora incluye
  el bloque de patrocinadores agrupado por nivel y ordenado por
  `display_order`, con solo `name`/`logo_url`/`website` por patrocinador
  (nunca la aportación). Al vivir dentro del mismo endpoint que ya exige
  `published`+`public`, un evento en borrador/oculto nunca expone el
  bloque (mismo 404 uniforme).
- `app/main.py`: registrados los dos routers nuevos.

### Backend — tests (`apps/api/tests/test_sponsors_router.py`, nuevo)

7 tests HTTP end-to-end: crear/reordenar/listar niveles, 409 al borrar un
nivel con patrocinadores, 422 al asignar un `tier_id` de otra organización,
422 por aportación inconsistente (sin importe / con los dos campos), 403 sin
permiso, bloque público agrupado con logo real subido y aportación oculta,
evento en borrador sin bloque público.

### Frontend admin (`apps/web/src/app/features/admin/`)

- `sponsors/sponsor-tiers-page.ts` (nuevo) + `.spec.ts`: CRUD de niveles de
  la organización, reordenar con botones «↑»/«↓» (nunca arrastrar y soltar,
  WCAG 2.5.7) intercambiando `display_order` entre el nivel movido y su
  vecino con dos `PATCH`.
- `events/event-sponsors.ts` (nuevo) + `.spec.ts`: patrocinadores de un
  evento — alta/edición/baja, selector de nivel, tipo de aportación con
  campo condicional (importe si `monetaria`, descripción si `en_especie`,
  limpiando el otro campo al cambiar de tipo), subida de logo con
  validación de tipo/tamaño en cliente antes de subir.
- `events/event-form.ts`: embebido `<app-event-sponsors>` junto a
  `EventAgenda`/`EventRegistrations`.
- `app.routes.ts` + `layouts/admin/admin-shell.ts`: ruta y entrada de
  navegación `/admin/sponsor-tiers`.
- `public/assets/i18n/es-ES.json`: claves nuevas bajo `admin.sponsorTiers`,
  `admin.events.sponsors`, `publico.eventos.patrocinadores`.

### Frontend público

- `features/public/events/event-page.ts`: bloque «Patrocinadores» agrupado
  por nivel, con tamaño de logo por nivel (`tamano-large/medium/small`),
  cada patrocinador enlazado a su web si la tiene. Cubierto también con un
  test nuevo (agrupación + axe) en `event-page.spec.ts`.

### Cliente generado

- `make api-types` regenerado limpio: `openapi.json` y
  `apps/web/src/app/core/api/generated/**` reflejan los 9 endpoints nuevos
  (carpeta `fn/patrocinio/`), sin diff pendiente tras la regeneración.

## Decisiones tomadas (desviaciones justificadas del texto literal del plan)

1. **Ruta de niveles**: el plan escribe
   `/organizations/{id}/sponsor-tiers`, pero **ningún** endpoint existente
   de la API usa `{id}` en la ruta para "la organización actual" — el
   patrón establecido (`organizations/router.py`: `/organizations/me/...`
   para branding, miembros, datos generales) resuelve la organización del
   usuario autenticado, nunca de un parámetro de ruta. Usar `/me` es
   consistente con ese patrón y evita introducir una segunda forma de
   identificar "mi organización" en la misma API. Los patrocinadores del
   evento sí siguen el plan al pie de la letra
   (`/events/{event_id}/sponsors`, igual que `/events/{event_id}/sessions`).
2. **Bloque público como parte de `GET /public/events/{slug}`**, no un
   endpoint aparte. El plan lo dejaba abierto ("recibiéndolos ya resueltos
   desde el componente padre... si no [necesita datos propios]"): al vivir
   dentro del mismo endpoint que ya aplica el filtro `published`+`public`,
   el aislamiento de eventos en borrador/oculto es automático y gratuito
   (mismo 404 uniforme), sin duplicar esa comprobación en un segundo sitio.
3. **Aportación nunca pública, ni siquiera el importe**: el plan solo decía
   explícitamente que la *descripción* de "en especie" no es pública; se
   extendió el mismo criterio al importe monetario (tampoco se muestra) —
   ambos son la misma clase de dato ("valoración económica de un
   patrocinio") y el PRD no pide hacer pública ninguna de las dos formas.
4. **Reordenar con botones, no arrastrar y soltar**: el plan solo pedía
   "reordenables (`display_order`)" sin especificar mecanismo de UI. Se
   eligió el patrón más simple que cumple WCAG 2.1 AA sin esfuerzo
   adicional (nada que arrastrar, cada movimiento es un botón discreto con
   `aria-label`).

## Resultado de tests

- **Backend**: suite completa de `apps/api` en verde tras los cambios
  (comprobado dos veces, incluida tras añadir el test de subida real de
  logo). 7 tests nuevos en `test_sponsors_router.py`, todos los tests
  preexistentes de la fase 1 (`test_sponsors_service.py`,
  `test_sponsors_permisos.py`, `test_sponsors_rls_isolation.py`,
  `test_sponsors_legal_auditoria_migracion.py`) siguen en verde sin
  modificarlos.
- **Frontend**: suite completa de `apps/web` en verde — 139 tests (37 → 39
  ficheros de test), incluidos 2 ficheros nuevos
  (`sponsor-tiers-page.spec.ts`, `event-sponsors.spec.ts`) y ampliaciones a
  `event-page.spec.ts` (bloque público) y `event-form.spec.ts` (nuevas
  peticiones de `EventSponsors` embebido). `tsc --noEmit` limpio en
  `tsconfig.app.json` y `tsconfig.spec.json`.
- **Axe**: cero violaciones en las tres pantallas nuevas
  (`sponsor-tiers-page`, `event-sponsors` con datos poblados, bloque público
  de `event-page` con niveles/patrocinadores), verificado con
  `esperarSinViolacionesDeAccesibilidad` en cada spec.
- **openapi/cliente TS**: regenerados con `make api-types`; `git status`
  confirma que solo cambiaron los ficheros esperados (los 9 endpoints
  nuevos + los modelos que los referencian), sin ficheros huérfanos.

## Verificación manual en navegador real

No se realizó — el entorno de este agente no tiene acceso a un navegador
interactivo ni a levantar `docker compose`/Postgres/SeaweedFS para una
sesión E2E manual. La cobertura sustitutoria es la suite automatizada
(backend HTTP end-to-end contra Postgres real + subida real de logo contra
el almacén de objetos S3-compatible que ya usan los tests de `events`;
frontend con `HttpTestingController` + axe-core sobre el DOM real
renderizado por Angular en jsdom). Recomendado como siguiente paso antes de
cerrar la fase 5 completa: una pasada manual E2E (como la que sí se hizo en
la fase 4 del PRD, documentada en `docs/accesibilidad.md`).

## Ficheros modificados/creados

Backend:
- `apps/api/app/modules/sponsors/schemas.py` (nuevo)
- `apps/api/app/modules/sponsors/router.py` (nuevo)
- `apps/api/app/modules/sponsors/repository.py`
- `apps/api/app/modules/sponsors/service.py`
- `apps/api/app/modules/events/schemas.py`
- `apps/api/app/modules/events/public_router.py`
- `apps/api/app/main.py`
- `apps/api/tests/test_sponsors_router.py` (nuevo)
- `apps/api/openapi.json` (regenerado)

Frontend:
- `apps/web/src/app/features/admin/sponsors/sponsor-tiers-page.ts` (nuevo)
- `apps/web/src/app/features/admin/sponsors/sponsor-tiers-page.spec.ts` (nuevo)
- `apps/web/src/app/features/admin/events/event-sponsors.ts` (nuevo)
- `apps/web/src/app/features/admin/events/event-sponsors.spec.ts` (nuevo)
- `apps/web/src/app/features/admin/events/event-form.ts`
- `apps/web/src/app/features/admin/events/event-form.spec.ts`
- `apps/web/src/app/features/public/events/event-page.ts`
- `apps/web/src/app/features/public/events/event-page.spec.ts`
- `apps/web/src/app/app.routes.ts`
- `apps/web/src/app/layouts/admin/admin-shell.ts`
- `apps/web/public/assets/i18n/es-ES.json`
- `apps/web/src/app/core/api/generated/**` (regenerado)

Docs:
- `docs/modelo-de-datos.md` (sección "Patrocinadores")
- `docs/accesibilidad.md` (checklist manual de las tres pantallas nuevas)

Plan:
- `plans/260908-1610-prd-fase-5-patrocinadores-legal-superadmin/phase-02-crud-de-patrocinadores-y-pagina-publica.md`
  (status → completed, Success Criteria marcados con evidencia)

Status: DONE_WITH_CONCERNS
Summary: CRUD completo de niveles/patrocinadores y bloque público agrupado implementado y probado (backend HTTP + frontend con axe), openapi/cliente regenerados sin diff pendiente; toda la verificación es automatizada, sin pasada manual en navegador real por falta de entorno interactivo.
Concerns/Blockers: recomendable una verificación manual E2E en un navegador real antes de cerrar la fase 5 completa del PRD, igual que se hizo en la fase 4.
