---
phase: 2
title: "Fase 2: CRUD de eventos y agenda en el panel"
status: done
priority: P1
effort: "2-2.5d"
dependencies: [1]
---

# Fase 2: CRUD de eventos y agenda en el panel

## Overview

Backend y frontend para que un `owner`/`organizer` cree, edite y publique eventos, y
les construya la agenda de sesiones. Sin ponentes todavía (fase 3): una sesión se
crea, se tipa y se ordena, pero su lista de participantes llega en la fase
siguiente.

**Corregido en red-team del plan:** las rutas anidadas usan un nombre de
parámetro distinto en cada nivel (`{event_id}`, `{session_id}`) — dos parámetros
con el mismo nombre en la misma ruta (`/events/{id}/sessions/{id}`) no es una
ruta válida en Starlette (colisión de grupo con nombre repetido, la aplicación no
arranca). También se añade la regeneración del cliente TypeScript, ya exigida por
CI para cualquier cambio de API.

## Requirements

- Functional:
  - `GET/POST /events`, `GET/PATCH /events/{event_id}` (organización actual, vía
    `usuario.organization_id`, igual que `organizations/router.py`).
  - `PUT /events/{event_id}/cover`: sube la portada (mismo patrón que
    `PUT /organizations/me/branding/logo`, con la corrección de la fase 2: el
    objeto anterior se borra **después** del commit, no tras el `flush()`).
  - `GET/POST /events/{event_id}/sessions`,
    `PATCH/DELETE /events/{event_id}/sessions/{session_id}`.
  - Sin `DELETE /events/{event_id}`: un evento se archiva (`status = archived`),
    no se borra — evita perder el histórico de sesiones/ponentes que otras fases
    referencian.
  - Panel: listado de eventos (con filtro por estado), formulario de evento,
    editor de agenda agrupado por día con alta/edición/eliminación de sesiones y
    reordenación dentro del día.
- Non-functional: `EVENTS_READ` para listar/ver, `EVENTS_WRITE` para
  crear/editar/publicar/agenda, igual que el resto del panel usa
  `require_permission`.

## Architecture

- `apps/api/app/modules/events/schemas.py` (**crear**): `EventCreate`,
  `EventUpdate`, `EventResponse`, `EventSessionCreate/Update/Response`. `slug` con
  el mismo `SLUG_PATTERN` que organizaciones (importado de
  `organizations/schemas.py`, no duplicado).
- `apps/api/app/modules/events/repository.py` (**crear**): consultas de lectura
  reutilizadas por el router de administración y, en la fase 4, por el router
  público — comparten la misma forma de construir la respuesta, solo cambia el
  filtro de estado/visibilidad.
- `apps/api/app/modules/events/service.py` (**crear**): validación de fechas
  (`ends_at > starts_at` para evento y para cada sesión; una sesión debe caer
  dentro del rango del evento), unicidad de slug por organización (`ConflictError`
  409, comprobado en BD, no solo en el esquema).
- `apps/api/app/modules/events/router.py` (**crear**): monta en `/events`, sigue
  el patrón de `organizations/router.py` (`CurrentUserDep`, `DbDep`,
  `require_permission(Permission.EVENTS_READ/WRITE)`). Subida de portada: igual
  que `upload_logo` en `organizations/router.py`, pero el objeto anterior
  (`almacen.delete_object(anterior)`) se borra **después** de que la transacción
  haga `commit`, no tras `session.flush()` — un rollback posterior al `flush()`
  (deadlock, timeout, fallo de otra validación) dejaría la fila apuntando a un
  objeto ya borrado, y esta portada es más visible que el logotipo: alimenta
  `og:image` en una página pública indexada por redes sociales.
- Frontend: `apps/web/src/app/features/admin/events/` — `events-page.ts` (listado),
  `event-form.ts` (crear/editar campos del evento + portada), `event-agenda.ts`
  (sesiones agrupadas por día). Reutiliza `app-input`, `app-card`,
  `app-error-summary` y el patrón de subida de imagen ya usado en
  `branding-page.ts` para la portada.
- Ruta nueva en `admin-shell.ts`: enlace "Eventos" en la navegación lateral, entre
  "Miembros" y "Mi cuenta".

## Related Code Files

- Create: `apps/api/app/modules/events/schemas.py`, `repository.py`, `service.py`,
  `router.py`
- Modify: `apps/api/app/main.py` (registra el router nuevo, mismo patrón que los
  demás módulos)
- Create: `apps/api/tests/modules/test_events.py`
- Create: `apps/web/src/app/features/admin/events/events-page.ts`,
  `event-form.ts`, `event-agenda.ts` (+ sus `.spec.ts`)
- Modify: `apps/web/src/app/app.routes.ts`, `apps/web/src/app/layouts/admin/admin-shell.ts`
- Modify: `apps/web/public/assets/i18n/es-ES.json`

## Implementation Steps

1. Esquemas Pydantic con la validación de fechas y patrón de slug.
2. `service.py`: creación/edición con comprobación de slug único (`ConflictError`
   409) y validación de fechas; publicar (`status → published`) exige al menos los
   campos obligatorios ya rellenos (no exige tener sesiones: un evento puede
   publicarse antes de cerrar la agenda).
3. Router de administración: CRUD de evento + subida de portada + CRUD de
   sesiones.
4. Registrar el router en `main.py`.
5. Frontend: listado, formulario de evento, editor de agenda (agrupar sesiones por
   fecha calculada a partir de `starts_at`, no un campo `day` aparte — evita
   desincronización entre el día declarado y el horario real).
6. Enlace de navegación y rutas.
7. Tests: creación, edición, slug duplicado (409), fechas de sesión fuera del
   rango del evento (422), publicar sin agenda (permitido), archivar (no
   `DELETE`), permisos (`EVENTS_READ`/`WRITE` exigidos, un rol sin ellos recibe
   403), subida de portada seguida de un fallo posterior al `flush()` no deja el
   objeto anterior borrado con la fila sin actualizar (verificar el orden
   borrado-tras-commit, no solo el resultado feliz).
8. Tests de accesibilidad (axe) en las tres pantallas nuevas.
9. `uv run python -m app.cli export-openapi` + `pnpm api:types` (o el comando
   equivalente que ya use el proyecto para regenerar el cliente TypeScript) y
   comprobar que ambos quedan committeados — CI falla si no coinciden con el
   código.

## Success Criteria

- [x] Un evento se crea, se edita y se publica desde el panel
- [x] El slug es único por organización; repetirlo da 409, no un error genérico
- [x] Una sesión fuera del rango de fechas del evento se rechaza con 422
- [x] La agenda agrupa las sesiones por día automáticamente a partir de su horario
- [x] Sin `EVENTS_WRITE` no se puede crear ni editar (403); sin `EVENTS_READ` no se
      puede ni listar
- [x] El objeto de la portada anterior se borra solo tras confirmar la
      transacción; un fallo posterior al `flush()` deja la fila apuntando al
      objeto todavía existente, nunca a uno ya borrado
- [x] `apps/api/openapi.json` y el cliente TypeScript generado están al día con
      los endpoints nuevos
- [x] Cero violaciones de axe en listado, formulario y editor de agenda

## Risk Assessment

- Añadir un campo `day` independiente del horario invitaría a que ambos se
  desincronizasen (una sesión movida de horario sin actualizar su `day`) → la
  agenda se agrupa siempre por la fecha de `starts_at`, sin campo redundante.
- Permitir `DELETE` de un evento con sesiones y (en fases futuras) inscripciones
  reales sería destructivo sin aviso → esta fase no expone `DELETE`, solo
  archivar; si una fase posterior necesita borrado real, que sea una decisión
  explícita con sus propias salvaguardas, no un efecto colateral de esta fase.
- Copiar el orden borrado-tras-`flush()` del logotipo de branding sin corregirlo
  dejaría la portada pública (más expuesta que el logotipo: alimenta `og:image`
  en una página indexada) rota ante cualquier fallo posterior en la misma
  transacción → orden invertido, cubierto por un test que fuerza un fallo tras el
  `flush()`.
- Verificación manual en navegador (2026-09-07): se detectó que `slice(0, 16)`
  sobre el ISO en UTC que devuelve la API, usado directamente como valor de un
  `<input type="datetime-local">`, deja el campo en UTC en vez de en la hora
  local del navegador — desincronizado del valor que sí se convierte de local a
  UTC al guardar. Corregido con un helper `isoAValorLocal()` (y el agrupado por
  día de la agenda, que tenía el mismo problema) en
  `apps/web/src/app/features/admin/events/datetime-local.ts`.
