---
title: "PRD Fase 2 — Eventos, agenda y ponentes"
description: "Eventos con agenda multi-día, sesiones tipadas (charla, descanso, servicio, otro), ponentes con perfil público e historial entre ediciones, y página pública del evento con SSR y OG tags."
status: done
priority: P1
effort: "8-10.5d"
tags: [eventos, agenda, sesiones, ponentes, ssr]
created: 2026-09-07
prd_phase: 2
blockedBy: []
blocks: []
---

# PRD Fase 2 — Eventos, agenda y ponentes

## Overview

La fase 1 dejó organizaciones, branding, roles con campos de perfil y cuenta propia
completos. Esta fase añade el primer objeto de negocio real: el **evento**, con su
agenda de sesiones tipadas y sus ponentes, más la página pública que lo muestra al
mundo. Es la base sobre la que se apoyan la inscripción (fase 3) y las entradas (fase
4): sin evento y sin sesiones no hay a qué inscribirse ni a qué dar acceso.

Alcance según `docs/prd.md` §4.2 y §4.7, solo lo marcado **M** (MVP IAWIC Valencia):

- Evento: título, slug, resumen, descripción, portada, estado, visibilidad, zona
  horaria, fechas, lugar, aforo, modo de inscripción y verificación de email
  obligatoria — **como campos de configuración**; la lógica de inscripción en sí
  llega en la fase 3.
- Agenda multi-día con sesiones tipadas: charla, descanso, servicio, otro.
- Una sesión puede tener varios ponentes, y una misma persona puede tener varios
  roles en la misma sesión (p. ej. ponente **y** moderador a la vez).
- Perfil público de ponente (reutiliza los campos de perfil del rol `speaker` de la
  fase 4: bio, titular, empresa, currículum, web, contacto, más los enlaces sociales
  de la fase 5) con historial de sesiones entre ediciones.
- Página pública del evento con SSR y etiquetas OG para compartir.

## Non-goals

Inscripción tipo Luma, verificación de email de asistentes, aprobación, lista de
espera (fase 3). Entradas QR y check-in (fase 4). Patrocinadores (fase 5). Pagos y
tipos de entrada (fase 6). Contabilidad (fase 7). Reviews de ponencias, contadores de
visualización de vídeo, eventos recurrentes, lugares cercanos (todos **S** en el PRD).
CfP (**P**).

## Decisiones tomadas — Sesión de validación 2026-09-07

| # | Pregunta | Decisión |
|---|---|---|
| 1 | Roles de participación en una sesión (ponente, moderador…) | Concepto general: una sesión puede tener varias personas y **una misma persona puede tener varios roles a la vez en la misma sesión** (p. ej. ponente y moderador). El rol de participación en una sesión es una etiqueta libre por asignación (`role_key`), independiente del rol de la persona en la organización — así una organización puede llamarlo "moderador", "presentador" o lo que necesite, sin esperar a un catálogo cerrado |
| 2 | Vídeo embebido | Campo de plataforma explícito (`video_platform`: youtube/vimeo/twitch/other) + `video_url`, en vez de detección automática por patrón de URL |
| 3 | URL pública del ponente | Slug legible por persona (único por organización), con comprobación de disponibilidad en vivo como la del slug de organización (fase 2 del PRD, no fase 1). **Corregido en red-team:** el slug y el interruptor público no viven en `organization_members` (una fila por rol) sino en una tabla propia por `(organization_id, user_id)` — ver "Modelo de datos" |
| 4 | Materiales de sesión | Sí: lista simple `[{label, url}]` en la sesión, editable desde el panel |

## Requirements

- Functional:
  - CRUD de eventos (`events`) por organización: campos según PRD §4.2, con `slug`
    único por organización.
  - CRUD de sesiones (`event_sessions`) agrupadas por día dentro de un evento:
    charla, descanso, servicio, otro; horario, sala, vídeo (plataforma + URL),
    materiales, orden.
  - Roster de participantes del evento (`event_members`): personas de la
    organización (cualquier miembro, no solo con rol `speaker`) añadidas a un evento
    concreto.
  - Asignación de participantes a sesiones con un rol libre por asignación
    (`event_session_participants`): una persona puede aparecer en la misma sesión
    varias veces con roles distintos.
  - Perfil público de ponente: **solo** una lista blanca fija de campos
    (`bio`, `titular`, `empresa`, `curriculum`, `web`, `contacto` — nunca el
    `profile_data` completo, que puede llevar campos a medida no pensados para
    publicarse) tomados de una membresía de origen que la propia persona elige,
    más enlaces sociales (fase 5, `user_social_links`), historial de sesiones en
    las que ha participado en **cualquier evento `published` y `public`** de la
    organización (nunca `hidden`/`private`, aunque esté publicado). Visible solo
    si la propia persona activa su perfil público, en autoservicio — nunca un
    tercero en su nombre.
  - Subida de portada del evento: mismo patrón que el logotipo de branding (PNG,
    JPEG, WebP, comprobación por contenido).
  - Página pública del evento (SSR, OG tags) y del ponente (SSR).
  - Listado público de eventos publicados de la organización.
- Non-functional: aislamiento multi-tenant vía RLS igual que toda tabla de dominio
  existente (`organization_id = app_current_organization()`); WCAG 2.1 AA con cero
  violaciones de axe en las pantallas nuevas; ningún fichero supera las 1000 líneas.

## Decisión de arquitectura: sin funciones `SECURITY DEFINER` nuevas

A diferencia de la fase 1, esta fase **no tiene el problema del huevo y la gallina**:
las páginas públicas de evento y ponente se sirven bajo el subdominio de la propia
organización, así que el host ya resuelve el contexto RLS (`app_current_organization()`)
antes de leer nada. La única diferencia con una lectura autenticada es un filtro
adicional a nivel de aplicación (`status = 'published' AND visibility = 'public'`
para eventos y para el historial de un ponente; existencia de su fila en
`speaker_public_profiles` para el ponente), no un problema de RLS. No hace falta
ninguna función `SECURITY DEFINER` nueva en esta fase.

**Corregido en red-team:** esta sección citaba `home-page.ts` como precedente de
carga de datos en SSR — no lo es, ese componente solo espera un `import()`
dinámico de plantilla, sin ninguna petición HTTP. El precedente real de este
proyecto para pedir datos a la API durante el renderizado en servidor es
`ThemingService` (`apps/web/src/app/core/theming/theming.service.ts`), que reenvía
`X-Forwarded-Host` con `ApiService.serverForwardHeaders()` y guarda el resultado en
`TransferState` para no repetir la petición al hidratar en el cliente. Las cuatro
páginas públicas de esta fase (evento, sesión, ponente, listado) siguen ese patrón,
detallado en la fase 4 de trabajo — no el de `home-page.ts`.

## Modelo de datos (resumen; detalle completo en la fase 1 de trabajo)

```
events (organization_id, slug UNIQUE per org, title, status, visibility, ...)
  UNIQUE (id, organization_id)
  └─ event_sessions (event_id, organization_id, session_type, starts_at, ends_at, ...)
     FK (event_id, organization_id) → events (id, organization_id)
     UNIQUE (id, organization_id)
event_members (event_id, organization_id, organization_member_id)
  UNIQUE(event_id, organization_member_id); UNIQUE (id, organization_id)
  FK (event_id, organization_id) → events (id, organization_id)
  └─ event_session_participants (session_id, event_member_id, organization_id, role_key)
     UNIQUE(session_id, event_member_id, role_key)
     FK (session_id, organization_id) → event_sessions (id, organization_id)
     FK (event_member_id, organization_id) → event_members (id, organization_id)
speaker_public_profiles (organization_id, user_id, public_slug, source_organization_member_id)
  UNIQUE(organization_id, user_id); UNIQUE(organization_id, public_slug)
```

`event_sessions`, `event_members` y `event_session_participants` llevan
`organization_id` **denormalizado** (no solo derivable vía `event_id`/`session_id`),
igual que `role_permissions` lo lleva pese a tener `role_id`: es el patrón ya
establecido para que la política RLS filtre en la propia tabla, sin subconsultas.

**Corregido en red-team — claves foráneas compuestas:** una FK simple
(`event_id → events.id`) no está acotada por organización, y en PostgreSQL la
comprobación de integridad referencial **no pasa por RLS**: nada impedía, tal como
estaba el plan, que una fila hija con `organization_id` propio apuntara a un
`event_id` de otra organización. Cada tabla hija usa una FK **compuesta** contra
`(id, organization_id)` del padre, así que la propia base de datos garantiza que el
padre referenciado pertenece a la misma organización — no solo la disciplina del
servicio.

**Corregido en red-team — identidad del ponente:** `is_public`/`public_slug` no
viven en `organization_members` (una fila por *rol*: la misma persona puede tener
varias, y el slug quedaría fragmentado o duplicado entre ellas). Viven en
`speaker_public_profiles`, una tabla nueva con una fila por `(organization_id,
user_id)` — la persona, no la membresía — con `source_organization_member_id`
indicando de qué membresía en concreto se toma la biografía a publicar. El
historial de sesiones se resuelve por `user_id` a través de todas las membresías
de esa persona en la organización, no solo la que activó el perfil.

## Permisos nuevos

`EVENTS_READ`, `EVENTS_WRITE` (el prefijo `events:*` ya estaba reservado en
`core/permissions.py` desde la fase 0). Cubren eventos, sesiones, roster de
participantes y asignación a sesiones — son la misma superficie de edición, no hay
motivo para separarlos como sí se hizo con `branding:write`.

Se conceden a `owner` (automático: su plantilla usa `tuple(Permission)`) y a
`organizer`. **Las organizaciones ya creadas no se enteran de un permiso nuevo en la
plantilla** — sus filas de `role_permissions` son una copia tomada en el momento de
creación, no una referencia viva a la plantilla. La migración de esta fase hace un
backfill explícito, con `WHERE NOT EXISTS` para que aplicarlo dos veces no duplique
filas.

**Corregido en red-team:** el backfill **no** se ancla al nombre del rol
(`key IN ('owner', 'organizer')`) — una organización pudo haber creado un rol a
medida con otra clave y los mismos permisos de gestión, y ese rol se quedaría sin
`events:*` para siempre. Se ancla a la **capacidad**: todo rol que ya tenga
`organizations:write` recibe `events:read`/`events:write`, exista o no con ese
nombre exacto. Sigue sin cubrir un rol a medida que gestiona *solo* eventos sin
tener `organizations:write` — no existe tal rol hoy (fase 1 no lo permite crear),
así que no es un caso real todavía.

Ventana de despliegue: entre aplicar esta migración y desplegar el código nuevo,
una organización creada por autoservicio (`POST /organizations`, sin
autenticación) seguiría clonando plantillas del proceso viejo, sin `events:*`. Este
proyecto despliega migración y código en el mismo paso (`infra/scripts/dev.sh` /
`docker compose up` reconstruye y migra antes de servir), no en despliegue
progresivo (*rolling*) con instancias mixtas — se documenta como limitación
aceptada de la estrategia de despliegue actual, no como algo que esta fase deba
resolver con una tarea de reconciliación en el arranque.

## Success Criteria

- [x] Un `owner`/`organizer` crea un evento, le añade una agenda multi-día con
      sesiones de los cuatro tipos, y lo publica
- [x] Una organización de la fase 1 ya existente (sin recrear) tiene `EVENTS_WRITE`
      en su rol `owner` tras aplicar la migración de esta fase, sin intervención
      manual
- [x] Una sesión admite varios ponentes y una misma persona con varios roles a la
      vez en la misma sesión (p. ej. ponente y moderador)
- [x] El perfil de ponente solo publica la lista blanca fija de campos, nunca
      `profile_data` completo — un campo a medida sensible (p. ej. teléfono, DNI)
      añadido a un rol no aparece en la respuesta pública, con test explícito
- [x] Un ponente activa **su propio** perfil público en autoservicio, sin depender
      de que un tercero lo haga por él, con un slug propio comprobado por
      disponibilidad en vivo
- [x] El historial de un ponente muestra sus sesiones en **todas las membresías**
      de esa persona y en **todas** las ediciones `published` + `public` de la
      organización (nunca `hidden`/`private`, aunque estén publicadas)
- [x] Un evento en borrador o con visibilidad oculta/privada no aparece en el
      listado público ni resuelve su página de detalle ni la de ninguna de sus
      sesiones (404 uniforme)
- [x] Dos organizaciones no ven los eventos, sesiones ni ponentes de la otra: tests
      de aislamiento explícitos sobre las cinco tablas nuevas, incluida una prueba
      de que no se puede **escribir** una fila hija apuntando al recurso padre de
      otra organización (no solo que no se lea)
- [x] La página pública del evento lleva etiquetas OG correctas (título, descripción,
      imagen de portada) y responde con SSR, verificado con una petición con
      `X-Forwarded-Host` y sin ejecutar JavaScript en el cliente
- [x] `alembic upgrade head` → `downgrade` → `upgrade head` limpio, sin duplicar ni
      perder filas de permisos
- [x] Cero violaciones de axe en las pantallas nuevas; checklist WCAG completado
- [x] CI en verde; ningún fichero supera las 1000 líneas
- [x] `docs/` actualizado: arquitectura, modelo de datos y accesibilidad reflejan lo
      nuevo

## Red Team Review

### Sesión — 2026-09-07
**Revisores:** 3 (Security Adversary, Assumption Destroyer, Failure Mode Analyst), tier Standard (Fact Checker + Contract Verifier), sobre `plan.md` y las 4 fases.
**Hallazgos:** 24 brutos → 15 tras deduplicar y pasar el filtro de evidencia (todos con cita `file:line`), 0 rechazados.
**Severidad:** 5 Critical, 9 High, 1 Medium.

| # | Hallazgo | Severidad | Aplicado a |
|---|---|---|---|
| 1 | El perfil público se anclaba a `organization_members` (una fila por rol): se fragmenta si una persona tiene varias membresías, y el endpoint de activación exigía `MEMBERS_WRITE` — un permiso que el propio rol `speaker` no tiene, contradiciendo "lo activa esa persona"; ese endpoint de autoservicio no existía | Critical | plan.md (modelo de datos, criterios); Fase 1 (tabla `speaker_public_profiles`); Fase 3 (endpoints de autoservicio bajo `/users/me`) |
| 2 | `profile_data` se exponía sin lista blanca: cualquier campo de rol a medida (teléfono, DNI, disponibilidad…) saldría en la página pública | Critical | plan.md (Requirements, Success Criteria); Fase 3 (serialización con lista blanca fija); Fase 4 |
| 3 | El patrón de SSR citado (`home-page.ts`) no hace ninguna petición HTTP; faltaba `X-Forwarded-Host`/`TransferState` — las páginas públicas se servirían vacías o con datos de otra organización | Critical | plan.md (Decisión de arquitectura); Fase 4 (Architecture reescrita sobre `ThemingService`) |
| 4 | Migración numerada `0009` sobre una cabeza real `0007`; el paso de verificación del backfill citaba un test inexistente y sería vacuamente cierto tal como estaba descrito | Critical | Fase 1 (numeración `0008`, paso de verificación reescrito) |
| 5 | Sin `downgrade()` definido pese a que el propio criterio de éxito exige el ciclo `upgrade → downgrade → upgrade` | Critical | Fase 1 (downgrade explícito y simétrico) |
| 6 | Backfill anclado a `key IN ('owner','organizer')`: un rol a medida con los mismos permisos pero otra clave se queda sin `events:*` para siempre; además no cubre la ventana entre migrar y desplegar el código nuevo | High | plan.md (Permisos nuevos); Fase 1 (ancla por capacidad `organizations:write`) |
| 7 | Sin FK compuesta: la comprobación de integridad referencial no pasa por RLS, así que nada impedía escribir una fila hija con `organization_id` propio apuntando al recurso padre de otra organización | High | plan.md (Modelo de datos); Fase 1 (`UNIQUE(id, organization_id)` + FK compuestas) |
| 8 | El historial de ponente (`speakers_repository`) solo filtraba `status='published'`, más laxo que la regla pública `published AND public` — un evento `published+private` se filtraría por la puerta del perfil de ponente | High | Fase 3 (filtro de visibilidad parametrizado y exigido) |
| 9 | La página de detalle de sesión no tenía endpoint definido, sin filtro de publicación, con IDs UUIDv7 enumerables (ordenados temporalmente) | High | Fase 4 (endpoint anidado `GET /public/events/{slug}/sessions/{id}`, filtrado por el evento padre) |
| 10 | Rutas con el mismo nombre de parámetro repetido en la misma URL (`/events/{id}/sessions/{id}`): Starlette no arranca con nombres de grupo duplicados | High | Fase 2 y Fase 3 (parámetros `event_id`/`session_id`/`event_member_id` distintos) |
| 11 | Sin `ondelete` en ninguna FK nueva: quitar a alguien del roster de un evento publicado podía dar 500 (`IntegrityError` sin capturar) o borrar en cascada su agenda sin aviso | High | Fase 1 (`ondelete` explícito); Fase 3 (409 si tiene participaciones activas) |
| 12 | El `PUT` que reemplaza toda la lista de participantes de una sesión perdía ediciones concurrentes entre dos personas editando la misma agenda a la vez | High | Fase 3 (control de concurrencia optimista + `IntegrityError` → 409) |
| 13 | La subida de portada heredaba el patrón "borrar el objeto anterior tras `flush()`, no tras `commit`" del logotipo de branding: un rollback deja la imagen pública rota sin posibilidad de recuperarla | High | Fase 2 (borrado diferido a después del commit) |
| 14 | Sin la comprobación de privilegios de `app_user` sobre las tablas nuevas, patrón ya establecido en `0002_esquema_base` para detectar en la propia migración un entorno con los `GRANT` mal aplicados | High | Fase 1 (paso de verificación añadido) |
| 15 | `video_url`/`materials` sin validar esquema — un `video_url` o enlace de materiales controlado por terceros se serviría en un `iframe`/enlace desde el propio dominio de la organización | Medium | Fase 1 (validación de esquema `https` + dominio por plataforma) |

**Notas adicionales no elevadas a hallazgo formal** (por debajo del límite de 15, se resuelven igualmente al implementar): el prefijo público (`/public/...`) queda fijado tal cual en el plan en vez de dejarlo abierto a decidir en implementación; los endpoints públicos y `check-public-slug` llevan `limit_per_ip`, mismo patrón que el resto de endpoints públicos del proyecto; toda modificación de API en las fases 2-4 incluye regenerar `apps/api/openapi.json` y `pnpm api:types`, como ya exige el resto del proyecto.

### Whole-Plan Consistency Sweep
- Ficheros releídos: `plan.md`, `phase-01-modelo-de-datos-rls-y-permisos.md`, `phase-02-crud-de-eventos-y-agenda.md`, `phase-03-ponentes-roster-y-perfil-publico.md`, `phase-04-pagina-publica-ssr-y-cierre.md`.
- Deltas de decisión comprobados: 15 (lista de arriba).
- Referencias obsoletas reconciliadas: `organization_members.public_slug`/`is_public` → `speaker_public_profiles`; `MEMBERS_WRITE` en el endpoint de perfil público → autoservicio sin permiso especial; numeración de migración `0009` → `0008`; rutas con `{id}` repetido → `{event_id}`/`{session_id}`/`{event_member_id}`; cita de `home-page.ts` como precedente de SSR con datos → `ThemingService`.
- Contradicciones sin resolver: 0.

## Fases de trabajo

1. **Modelo de datos, RLS y permisos** — cinco tablas con FK compuestas, políticas,
   backfill de permisos anclado por capacidad.
2. **CRUD de eventos y agenda en el panel** — backend + frontend de administración.
3. **Ponentes: roster, asignación y perfil público** — `event_members`,
   `event_session_participants`, autoservicio de `speaker_public_profiles`,
   historial filtrado por visibilidad.
4. **Página pública del evento con SSR, cierre de fase** — listado y detalle
   públicos con SSR real (`serverForwardHeaders`/`TransferState`), OG tags,
   documentación, verificación de extremo a extremo.
