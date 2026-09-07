---
phase: 1
title: "Fase 1: Modelo de datos, RLS y permisos"
status: done
priority: P1
effort: "2-2.5d"
dependencies: []
---

# Fase 1: Modelo de datos, RLS y permisos

## Overview

Las cinco tablas nuevas (`events`, `event_sessions`, `event_members`,
`event_session_participants`, `speaker_public_profiles`), sus políticas RLS con
claves foráneas compuestas por organización, y los permisos `events:read` /
`events:write` con su backfill para organizaciones ya existentes. Sin esta fase no
hay nada que exponer por API ni por UI.

**Cambios de esta fase tras el red-team del plan** (ver `plan.md` → `## Red Team
Review`): el perfil público vive en `speaker_public_profiles` (tabla propia por
`(organization_id, user_id)`, no dos columnas en `organization_members`); las
tablas hijas usan FK **compuestas** contra `(id, organization_id)` del padre, no
FK simples; la migración se numera `0009` (encadenada tras `0008_cuenta_y_recuperacion`, la migración de cierre de la fase 1 del PRD — este plan asume esa fase ya mergeada);
incluye `downgrade()` explícito y la comprobación de privilegios de `app_user`
que ya exige `0002_esquema_base`; el backfill de permisos se ancla a la
**capacidad** (`organizations:write`), no al nombre del rol.

## Requirements

- Functional:
  - `events`: título, slug (único por organización), resumen, descripción, portada,
    estado (`draft`/`published`/`archived`), visibilidad (`public`/`hidden`/`private`),
    zona horaria, `starts_at`/`ends_at`, modo de lugar (`in_person`/`online`/`hybrid`)
    con nombre/dirección/URL online, aforo, modo de inscripción
    (`free`/`approval`/`paid`), `email_verification_required`.
  - `event_sessions`: tipo (`talk`/`break`/`service`/`other`), título, descripción,
    horario, sala, plataforma de vídeo (`youtube`/`vimeo`/`twitch`/`other`) + URL,
    materiales (`jsonb` de `{label, url}`), orden.
  - `event_members`: qué miembros de la organización participan en qué evento.
  - `event_session_participants`: qué `event_member` participa en qué sesión y con
    qué rol libre (`role_key`), permitiendo varias filas por persona+sesión con
    roles distintos.
  - `speaker_public_profiles`: una fila por `(organization_id, user_id)` — nunca
    por membresía — con `public_slug` (único por organización) y
    `source_organization_member_id` (de qué membresía se toma la biografía a
    publicar).
  - Backfill de `role_permissions`: `events:read`/`events:write` para todo rol
    existente que ya tenga `organizations:write` (no solo `owner`/`organizer` por
    nombre — un rol a medida con esa misma capacidad también lo necesita).
- Non-functional: mismo patrón de RLS que toda tabla de dominio
  (`organization_id = app_current_organization()`, `ENABLE` + `FORCE ROW LEVEL
  SECURITY`); `organization_id` denormalizado en las cuatro tablas hijas, igual que
  `role_permissions` lo lleva pese a tener `role_id`; toda FK de una tabla hija al
  recurso "padre" de otra tabla nueva es **compuesta** contra `(id,
  organization_id)`, para que la integridad referencial de PostgreSQL —que no pasa
  por RLS— no permita colgar una fila de un recurso de otra organización;
  `video_url` exige `https` y un dominio de la lista de la plataforma declarada
  (`youtube.com`/`youtu.be`, `vimeo.com`, `twitch.tv`; para `other` cualquier
  `https`), y cada entrada de `materials` exige `https`, para no servir un
  `iframe`/enlace controlado por terceros desde el propio dominio de la
  organización.

## Architecture

- `apps/api/app/modules/events/models.py` (**crear**): `Event`, `EventSession`,
  `EventMember`, `EventSessionParticipant`, `SpeakerPublicProfile`, siguiendo el
  mismo `Base` + `TimestampMixin` que `organizations/models.py`. `Event` declara
  `UniqueConstraint("id", "organization_id")` además de la PK simple, necesaria
  para que las FK compuestas de las tablas hijas puedan referenciarla (mismo
  requisito en `EventSession` y `EventMember`, que a su vez son padres de otra
  tabla).
- `apps/api/app/core/permissions.py` (**modificar**): añade `EVENTS_READ`,
  `EVENTS_WRITE` al enum; retira el prefijo `events:*` del comentario de prefijos
  reservados (ya no está reservado, está en uso).
- `apps/api/app/modules/roles/system_roles.py` (**modificar**): añade
  `Permission.EVENTS_READ`/`EVENTS_WRITE` a `ORGANIZER.permissions` (`OWNER` no
  necesita cambio: usa `tuple(Permission)`).
- Nueva migración `0009_eventos_agenda_y_ponentes.py` (`down_revision =
  "0008_cuenta_y_recuperacion"`, la migración de cierre de la fase 1 del PRD; el
  nombre completo del fichero cabe sin truncarse en el `varchar(32)` de
  `alembic_version.version_num` — comprobado: 30 caracteres):
  1. Crea las cinco tablas. `events`, `event_sessions` y `event_members` llevan
     `UNIQUE (id, organization_id)` además de su PK. Las tablas hijas declaran FK
     compuestas: `event_sessions (event_id, organization_id) REFERENCES events
     (id, organization_id)`; `event_members (event_id, organization_id)
     REFERENCES events (id, organization_id)`; `event_session_participants
     (session_id, organization_id) REFERENCES event_sessions (id,
     organization_id)` y `(event_member_id, organization_id) REFERENCES
     event_members (id, organization_id)`. `ondelete`: `CASCADE` desde
     `event_sessions`/`event_members` hacia `events` (un evento no se borra en
     esta fase, pero si algún día se hiciera, no debe dejar huérfanos) y desde
     `event_session_participants` hacia `event_sessions`; `RESTRICT` (la falta de
     `ondelete` explícito en PostgreSQL) desde `event_session_participants` hacia
     `event_members` — quitar a alguien del roster con participaciones activas se
     rechaza a nivel de base de datos como último cinturón de seguridad, aunque el
     servicio (fase 3) ya lo comprueba antes y devuelve 409 en vez de dejar que
     llegue el error de integridad.
     `UniqueConstraint`s: `events (organization_id, slug)`; `event_members
     (event_id, organization_member_id)`; `event_session_participants (session_id,
     event_member_id, role_key)`; `speaker_public_profiles (organization_id,
     user_id)` y `speaker_public_profiles (organization_id, public_slug)`.
  2. `ALTER TABLE ... ENABLE/FORCE ROW LEVEL SECURITY` + `CREATE POLICY tenant_X ON X
     USING (organization_id = app_current_organization()) WITH CHECK (...)` para las
     cinco tablas nuevas, mismo texto que ya generaba el bucle de `0003_politicas_rls`
     para las tablas de esa migración (aquí se escribe explícito porque ese bucle ya
     se ejecutó y no se puede reabrir).
  3. Comprobación de privilegios de `app_user` sobre las cinco tablas nuevas,
     mismo patrón que `_verificar_privilegios_de_app_user()` en
     `0002_esquema_base.py` — falla la migración con un mensaje explícito en vez
     de dejar que el primer `GET /events` en producción devuelva `permission
     denied for table events`.
  4. Backfill: `INSERT INTO role_permissions (role_id, permission,
     organization_id) SELECT r.id, 'events:read', r.organization_id FROM roles r
     WHERE EXISTS (SELECT 1 FROM role_permissions rp WHERE rp.role_id = r.id AND
     rp.permission = 'organizations:write') AND NOT EXISTS (SELECT 1 FROM
     role_permissions rp2 WHERE rp2.role_id = r.id AND rp2.permission =
     'events:read')` (y lo mismo para `events:write`) — ancla a la capacidad
     (`organizations:write`), no al nombre del rol; `NOT EXISTS` lo hace
     idempotente ante una segunda ejecución.
  5. `downgrade()`: revertir en orden inverso — `DELETE FROM role_permissions
     WHERE permission IN ('events:read', 'events:write') AND role_id IN (SELECT
     id FROM roles WHERE ...)` solo para las filas que el propio `upgrade`
     insertó (mismo criterio de capacidad, no un `DELETE` ciego que también se
     llevaría por delante un `events:write` que alguien hubiera concedido a mano
     a otro rol tras el `upgrade`); `DROP POLICY`/`NO FORCE ROW LEVEL SECURITY`;
     `DROP TABLE` de las cinco tablas en orden inverso de creación. Se documenta
     explícitamente en el propio fichero de migración que el `DROP TABLE` es
     **destructivo**: un `downgrade` después de que existan eventos reales borra
     esos eventos sin posibilidad de recuperación — válido para el ciclo de
     pruebas y para revertir un despliegue fallido *antes* de que haya datos
     reales, no como operación segura en producción con datos.

## Related Code Files

- Create: `apps/api/app/modules/events/__init__.py`, `models.py`
- Create: `apps/api/alembic/versions/0009_eventos_agenda_y_ponentes.py`
- Modify: `apps/api/app/core/permissions.py`
- Modify: `apps/api/app/modules/roles/system_roles.py`
- Create: `apps/api/tests/test_events_rls_isolation.py`
- Create: `apps/api/tests/modules/test_events_permissions_backfill.py`

## Implementation Steps

1. Modelos SQLAlchemy de las cinco tablas nuevas, con las relaciones mínimas que de
   verdad se usan (no relaciones especulativas): `Event.sessions`,
   `Event.members`, `EventSession.participants`.
2. Migración: tablas + `UNIQUE(id, organization_id)` + FK compuestas + `ondelete`,
   RLS, comprobación de privilegios, backfill, `downgrade()` — en ese orden, cada
   paso con su propio bloque `op.execute`/`op.create_table` para que un fallo a
   mitad de camino sea legible en el log de CI.
3. Actualizar `core/permissions.py` y `system_roles.py`.
4. Test de aislamiento **de lectura**: dos organizaciones, cada una con un evento,
   sesión, miembro de evento, participante de sesión y perfil público; verificar
   que ninguna consulta bajo el contexto RLS de una ve las filas de la otra, para
   las cinco tablas.
5. Test de aislamiento **de escritura**: bajo el contexto RLS de la organización A,
   intentar insertar una `event_session` con `organization_id = A` pero
   `event_id` de un evento de la organización B; debe fallar por violación de la
   FK compuesta, no insertarse silenciosamente. Repetir para `event_members` y
   `event_session_participants`.
6. Test del backfill: usando la sesión de mantenimiento, crear un rol con permiso
   `organizations:write` y **sin** `events:read`/`events:write` (simulando el
   estado anterior a esta migración), ejecutar directamente la sentencia SQL del
   backfill (no `alembic downgrade`, que no es un estado real intermedio
   alcanzable en la suite) y comprobar que el rol recibe ambos permisos; ejecutar
   la misma sentencia una segunda vez y comprobar que no duplica filas. Repetir
   con un rol que **no** tiene `organizations:write` (p. ej. `speaker`) y
   comprobar que no recibe `events:*`. Un tercer caso cubre el hallazgo del
   red-team: un rol a medida con `key` distinto de `owner`/`organizer` pero con
   `organizations:write` sí recibe el backfill.
7. Test de `ondelete`: quitar a alguien del roster de un evento (`event_members`)
   mientras tiene una fila en `event_session_participants` debe rechazarse (409
   desde el servicio de la fase 3; a nivel de base de datos, `IntegrityError` por
   `RESTRICT` si se intentara sin pasar por el servicio).
8. `uv run alembic upgrade head` → `downgrade 0008_cuenta_y_recuperacion` →
   `upgrade head` en local (test y dev), confirmando que no quedan tablas ni
   políticas residuales tras el `downgrade`.

## Success Criteria

- [x] Las cinco tablas existen con `UNIQUE(id, organization_id)` en los padres, FK
      compuestas en las hijas, y `organization_id` denormalizado donde corresponde
- [x] RLS activa (`FORCE`) en las cinco tablas, con política idéntica en forma a
      las ya existentes
- [x] `app_user` tiene privilegios verificados sobre las cinco tablas nuevas al
      final de la migración, con el mismo patrón que `0002_esquema_base`
- [x] Insertar una fila hija con `organization_id` propio pero apuntando al
      recurso padre de otra organización falla por la FK compuesta, con test
      explícito — no solo se comprueba que no se **lee**, se comprueba que no se
      puede **escribir**
- [x] Un rol con `organizations:write` (tenga o no `key IN ('owner',
      'organizer')`) recibe `events:read`/`events:write` tras el backfill; un rol
      sin esa capacidad no lo recibe
- [x] `uv run alembic upgrade head` → `downgrade 0008_cuenta_y_recuperacion` →
      `upgrade head` limpio, sin errores, sin tablas ni políticas residuales
- [x] Quitar a alguien del roster de un evento con participaciones activas en
      sesiones falla por integridad a nivel de base de datos (`RESTRICT`), con
      test explícito — la traducción a 409 en el servicio HTTP es alcance de la
      fase 3, que todavía no existe
- [x] `speaker_public_profiles` es única por `(organization_id, user_id)` y por
      `(organization_id, public_slug)`
- [x] Tests de aislamiento (lectura y escritura) en verde para las cinco tablas
      nuevas
- [x] `uv run ruff check` / `uv run mypy app` sin hallazgos

## Risk Assessment

- Olvidar el backfill dejaría a toda organización ya existente sin poder usar
  eventos hasta que alguien edite el rol a mano → cubierto explícitamente por el
  Success Criteria y un test dedicado, no solo por inspección.
- Una política RLS mal copiada (p. ej. sin `FORCE`) filtraría datos entre
  organizaciones sin que ningún test de la aplicación lo note hasta producción →
  test de aislamiento explícito por tabla, ejecutado en CI, no solo revisión manual.
- Una FK simple (no compuesta) permitiría a un bug de servicio, no solo a un
  atacante, colgar una fila del recurso de otra organización sin que RLS lo
  impida (la integridad referencial de PostgreSQL no pasa por RLS) → FK
  compuestas contra `(id, organization_id)` en toda tabla hija, verificado con un
  test de escritura, no solo de lectura.
- Ejecutar el `downgrade()` en un entorno con eventos reales borra esos eventos
  sin posibilidad de recuperación → documentado explícitamente en el propio
  fichero de migración; no se ofrece backup automático dentro de esta fase (ver
  la norma general del proyecto de hacer backup antes de cualquier cambio de
  esquema o dato).
- Señal de que este diseño se rompe: si una fase posterior necesita que
  `event_session_participants.role_key` tenga semántica especial más allá de una
  etiqueta libre (permisos distintos por rol de sesión, por ejemplo), habrá que
  reconsiderar si sigue siendo texto libre o pasa a referenciar un catálogo — no
  aplicar ese cambio de alcance sin volver a este plan.
