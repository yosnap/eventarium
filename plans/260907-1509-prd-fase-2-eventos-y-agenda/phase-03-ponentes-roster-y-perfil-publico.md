---
phase: 3
title: "Fase 3: Ponentes — roster, asignación y perfil público"
status: pending
priority: P1
effort: "2-2.5d"
dependencies: [2]
---

# Fase 3: Ponentes — roster, asignación y perfil público

## Overview

Añadir personas de la organización a un evento (`event_members`), asignarlas a
sesiones concretas con uno o varios roles libres (`event_session_participants`), y
dejar que **ellas mismas** activen su perfil público con un slug propio. El perfil
en sí (bio, currículum, web, contacto, redes) ya existe desde las fases 4 y 5 —
aquí solo se expone, con una lista blanca fija de campos, y se enlaza con el
historial de sesiones.

**Cambios de esta fase tras el red-team del plan** (ver `plan.md` → `## Red Team
Review`): la activación del perfil público es **autoservicio** (la propia persona,
sin `MEMBERS_WRITE`), no algo que un administrador hace por otra persona; el
historial y la ubicación del perfil se resuelven por `speaker_public_profiles`
(fase 1), no por columnas en `organization_members`; el historial filtra
`visibility='public'` además de `status='published'`; la respuesta pública solo
sirve una lista blanca fija de campos; el `PUT` de participantes lleva control de
concurrencia; los parámetros de ruta anidados usan nombres distintos por nivel.

## Requirements

- Functional:
  - `GET/POST /events/{event_id}/members`,
    `DELETE /events/{event_id}/members/{event_member_id}`: añadir o quitar a un
    miembro de la organización del roster del evento. Se elige entre los miembros
    ya existentes de la organización (cualquier rol, no solo `speaker`) — el modo
    de administrar quién pertenece a la organización sigue siendo `admin/members`,
    no se duplica aquí. Quitar a alguien con participaciones activas en sesiones
    de ese evento da 409 (mensaje explícito: cuántas sesiones), no 500 — la base
    de datos ya lo respalda con `RESTRICT` (fase 1), esto es la traducción a un
    error legible antes de que llegue el `IntegrityError`.
  - `PUT /events/{event_id}/sessions/{session_id}/participants`: reemplaza la
    lista completa de participantes de una sesión (cada uno con su `role_key`) en
    una sola petición — más simple para el editor de agenda que altas/bajas
    individuales. Lleva control de concurrencia optimista: la petición incluye
    `expected_updated_at` (el `updated_at` de la sesión que el cliente tenía
    cargado); si no coincide con el actual, 409 ("la agenda cambió, recarga antes
    de guardar") en vez de sobrescribir en silencio el trabajo de otra persona.
  - `PATCH /users/me/public-profile` (**autoservicio**, sin permiso especial más
    allá de estar autenticado): `public_slug` +
    `source_organization_member_id` (de qué membresía propia tomar la
    biografía). Enviar `public_slug: null` desactiva el perfil (borra la fila de
    `speaker_public_profiles`). 409 si el slug ya está en uso en la organización;
    422 si `source_organization_member_id` no pertenece a la propia persona o su
    rol no declara ningún campo de la lista blanca publicable.
  - `GET /users/me/public-profile/check-slug?slug=...`: ayuda de UX en vivo,
    mismo espíritu que `check-slug` de organizaciones pero **sin** `SECURITY
    DEFINER`: quien pregunta ya tiene contexto de organización (autenticado), así
    que una consulta normal bajo RLS basta.
  - Panel: en el editor de agenda de cada sesión, selector múltiple de
    participantes del roster del evento con su `role_key` (campo de texto libre
    con sugerencias: ponente, moderador, presentador). En `admin/account`
    (fase 5, cuenta propia): sección nueva para activar el perfil público + slug,
    visible solo si la persona tiene al menos una membresía con campos de perfil
    publicables.
- Non-functional: `EVENTS_WRITE` para roster y asignación a sesiones. El perfil
  público no exige ningún permiso de rol — es autoservicio sobre la propia
  identidad, igual que `PATCH /users/me` (fase 5) tampoco exige `MEMBERS_WRITE`.

## Lista blanca del perfil público

Nunca se sirve `profile_data` completo. La respuesta pública solo incluye, si
están presentes en `profile_data` de la membresía de origen: `bio`, `titular`,
`empresa`, `curriculum`, `web`, `contacto`. Cualquier otra clave (un campo a
medida que una organización haya añadido a ese rol — teléfono, DNI,
disponibilidad, talla de camiseta…) se descarta explícitamente, aunque exista en
`profile_data`. `PATCH /users/me/public-profile` valida en el momento de activar
que la membresía elegida declara al menos uno de esos campos en su rol
(`role_profile_fields`); si no, 422 — activar un perfil público vacío no tiene
sentido y sería una forma silenciosa de descubrir el mismo problema más tarde en
la página pública.

## Architecture

- `apps/api/app/modules/events/schemas.py` (**modificar**): `EventMemberCreate/
  Response`, `SessionParticipantsUpdate` (`expected_updated_at` + lista de
  `{event_member_id, role_key}`).
- `apps/api/app/modules/events/router.py` (**modificar**): endpoints de roster y
  de participantes de sesión, con nombres de parámetro `event_id`,
  `event_member_id`, `session_id` — nunca dos parámetros `{id}` en la misma ruta.
  El `PUT` de participantes captura `IntegrityError` (colisión de
  `UNIQUE(session_id, event_member_id, role_key)` entre dos peticiones
  concurrentes que pasaron la comprobación de `expected_updated_at` por una
  carrera estrecha) y la traduce a 409, nunca deja que llegue como 500.
- `apps/api/app/modules/users/schemas.py` (**modificar**, fase 5):
  `PublicProfileUpdate` (`public_slug: str | None`, `source_organization_member_id:
  str | None`).
- `apps/api/app/modules/users/router.py` (**modificar**, fase 5): los dos
  endpoints de perfil público, bajo `/me/public-profile` — mismo prefijo que ya
  usan los endpoints de cuenta propia de la fase 5 (`PATCH /users/me`,
  `/users/me/social-links`).
- `apps/api/app/modules/events/speakers_repository.py` (**crear**): la consulta
  del historial de un ponente (todas las `event_session_participants` de
  cualquier `organization_member_id` de ese `user_id` en la organización, unidas
  a `event_sessions` y `events`, filtradas a `events.status = 'published' AND
  events.visibility = 'public'`) — la usan tanto el endpoint de administración
  (previsualización) como el público (fase 4), de ahí que viva separada del
  router y reciba el filtro de visibilidad como parámetro explícito, no como
  valor por defecto que un llamador pudiera olvidar pasar.
- Frontend: `apps/web/src/app/features/admin/events/event-agenda.ts`
  (**modificar**): selector de participantes por sesión, envía
  `expected_updated_at` con cada guardado y muestra un aviso claro si el backend
  responde 409 por conflicto de concurrencia (recargar, no reintentar a ciegas).
  `apps/web/src/app/features/admin/account/account-page.ts` (**modificar**, fase
  5): sección de perfil público.

## Related Code Files

- Modify: `apps/api/app/modules/events/schemas.py`, `router.py`
- Create: `apps/api/app/modules/events/speakers_repository.py`
- Modify: `apps/api/app/modules/users/schemas.py`, `router.py`
- Create: `apps/api/tests/modules/test_event_speakers.py`
- Create: `apps/api/tests/modules/test_speaker_public_profile.py`
- Modify: `apps/web/src/app/features/admin/events/event-agenda.ts`
- Modify: `apps/web/src/app/features/admin/account/account-page.ts`
- Modify: `apps/web/public/assets/i18n/es-ES.json`

## Implementation Steps

1. Endpoints de roster (`event_members`): añadir, listar, quitar con la
   comprobación de participaciones activas → 409.
2. Endpoint de participantes de sesión: reemplazo completo de la lista con
   validación de pertenencia al roster (un `event_member_id` de otro evento da
   422), control de concurrencia optimista (`expected_updated_at` → 409) y
   captura de `IntegrityError` → 409.
3. Endpoints de perfil público en `users/router.py`: `PATCH .../public-profile`
   (autoservicio, valida que la membresía elegida es propia y que su rol declara
   al menos un campo publicable) y `GET .../check-slug`.
4. `speakers_repository.py`: consulta del historial por `user_id` a través de
   todas las membresías de esa persona en la organización, con el filtro
   `published AND public` como parámetro explícito de la función, reutilizable en
   la fase 4.
5. Serializador de la respuesta pública del perfil: aplica la lista blanca fija,
   nunca vuelca `profile_data` entero.
6. Frontend: selector de participantes en el editor de agenda (multi-select con
   campo de rol libre por cada selección, valor por defecto sugerido pero
   editable) y manejo del 409 de concurrencia.
7. Frontend: sección de perfil público en `account-page.ts`, con comprobación de
   slug en vivo.
8. Tests: roster, asignación válida e inválida (miembro de otro evento), varios
   roles para la misma persona en la misma sesión, quitar del roster con
   participaciones activas (409), conflicto de concurrencia en el `PUT` de
   participantes (409), colisión de `UNIQUE` bajo carrera concurrente traducida a
   409 (no 500), perfil público con slug duplicado (409), activar sobre una
   membresía ajena (422), activar sobre una membresía cuyo rol no declara ningún
   campo publicable (422), un campo a medida sensible del rol **no** aparece en
   la respuesta pública, historial que excluye un evento `published+private` o
   `published+hidden`, slug liberado al desactivar (comportamiento esperado, no
   fallo).
9. Tests de accesibilidad en las pantallas modificadas.
10. Regenerar `apps/api/openapi.json` + cliente TypeScript.

## Success Criteria

- [ ] Un `owner`/`organizer` añade a alguien de la organización al roster de un
      evento y lo asigna a una sesión con un rol libre
- [ ] La misma persona puede aparecer en la misma sesión con dos roles distintos
      (dos filas en `event_session_participants`)
- [ ] Asignar a una sesión a alguien que no está en el roster de ese evento falla
      con 422
- [ ] Quitar del roster a alguien con participaciones activas da 409, no 500
- [ ] Dos guardados concurrentes de la lista de participantes de la misma sesión:
      el segundo da 409 por `expected_updated_at` desactualizado, nunca
      sobrescribe en silencio el primero
- [ ] Una persona activa **su propio** perfil público (autoservicio, sin
      `MEMBERS_WRITE`); el slug se comprueba en vivo y es único por organización
- [ ] Activar el perfil sobre una membresía ajena, o sobre una cuyo rol no
      declara ningún campo publicable, falla con 422
- [ ] La respuesta pública del perfil solo incluye la lista blanca fija; un campo
      a medida sensible del rol (p. ej. teléfono) nunca aparece, con test
      explícito
- [ ] El historial de un ponente (`speakers_repository`) incluye sesiones de
      **todas** las membresías de esa persona y de **todas** las ediciones
      `published` + `public`, excluyendo explícitamente `hidden`/`private`
      aunque estén publicadas
- [ ] Cero violaciones de axe en las pantallas modificadas

## Risk Assessment

- Reemplazar la lista completa de participantes de una sesión en una sola
  petición (`PUT`) en vez de altas/bajas individuales simplifica el frontend pero
  exige que el backend valide **todo** el lote antes de aplicar nada (si un
  `event_member_id` no pertenece al evento, la petición entera falla, no se
  aplica parcialmente) → cubierto por el paso 2 y su test.
- Sin control de concurrencia, dos personas editando la misma agenda a la vez
  pierden ediciones sin ningún aviso → `expected_updated_at` + captura de
  `IntegrityError`, cubierto por un test que simula la carrera.
- Dejar que un administrador active el perfil público de otra persona
  convertiría un dato de consentimiento en una decisión ajena, y el propio rol
  `speaker` no tiene permiso para desactivarlo si algo sale mal → autoservicio
  puro sobre la identidad propia, sin vía administrativa de activación en esta
  fase.
- Señal de que el `role_key` libre se está quedando corto: si en producción
  aparecen decenas de valores casi iguales por error tipográfico ("Moderador" vs
  "moderador" vs "Moderadora"), valorar normalizar a minúsculas en el backend o
  pasar a una lista cerrada por organización — no aplicar ese cambio ahora sin
  evidencia real de que hace falta.
