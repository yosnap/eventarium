---
phase: 4
title: "Fase 4: Superadmin — auditoría y RGPD"
status: completed
priority: P1
effort: "2-2.5d"
dependencies: [1]
---

# Fase 4: Superadmin — auditoría y RGPD

## Overview

Amplía `apps/api/app/modules/admin/router.py` (ya existente desde fase 0/1,
hoy solo gestiona altas de organizaciones y de dominios) con auditoría,
exportación RGPD de un evento y borrado de un inscrito bajo solicitud.
Instrumenta `audit_log` en las acciones sensibles ya existentes, no solo en
las nuevas.

**Corrección de red-team sobre el alcance real de `admin/router.py`:**
`apps/api/app/modules/admin/router.py` (119 líneas) solo expone hoy
`GET/POST /organizations` y `GET/POST /organizations/{id}/domains`. **No
existe ningún endpoint de activación/desactivación de organización** —
`Organization.is_active` es una columna con efecto real en
`get_current_organization` (deniega el acceso si es `false`), pero ningún
router la modifica; solo se fija en el alta. Las acciones que sí existen y
sí se auditan en esta fase son: cambio de permisos de un rol, alta de
organización, alta de dominio.

## Requirements

- Functional:
  - `_registrar_auditoria(session, *, actor_user_id, organization_id,
    action, entity_type, entity_id, detail)` — helper único en
    `app/modules/admin/` (o `app/core/audit.py` si se ve reutilizable desde
    otros módulos ya en esta fase), usado por todos los puntos de
    instrumentación de abajo. Un solo helper evita implementaciones
    paralelas divergentes del mismo registro.
  - **Resolver primero desde qué sesión se escribe cada punto de
    instrumentación**, antes de escribir el helper — corrección de
    red-team: la instrumentación de "cambio de permisos de un rol" ocurre
    dentro del módulo `roles`, que corre bajo `app_user` (sesión de
    organización, `get_db`), mientras que las tres acciones nuevas de este
    módulo corren bajo `app_maintainer` (`get_maintenance_db`). Como
    `audit_log` ahora tiene `REVOKE ALL ... FROM app_user` (fase 1 de
    trabajo), el helper necesita `GRANT INSERT ON audit_log TO app_user`
    explícito en la migración de la fase 1 **o** el punto de
    instrumentación de `roles` debe escribir en `audit_log` a través de
    una llamada a `maintenance_session` propia para ese insert únicamente
    (sin usar `app_user` para leer/escribir nada más de la tabla). Decidir
    una de las dos y documentarla aquí antes de implementar; no dejarlo
    para que lo resuelva quien lo escriba sobre la marcha.
  - Instrumentar `audit_log` en: cambio de permisos de un rol (`roles`,
    fase 1), alta de organización y alta de dominio (`admin/router.py`,
    ya existentes), y las tres acciones nuevas de este módulo. **No** se
    instrumenta activación/desactivación de organización porque ese
    endpoint no existe (ver Overview) — no se inventa uno nuevo fuera de
    alcance solo para tener algo que auditar.
  - `GET /admin/audit-log`: filtros `organization_id`, `date_from`,
    `date_to`, `action`; paginado (mismo patrón `limit`/`cursor` o
    `page`/`page_size` que ya use el listado de inscripciones, fase 3).
    Protegido con `Superadmin`, con `limit_per_ip`.
  - `GET /admin/events/{event_id}/rgpd-export`: genera un ZIP en memoria
    (o fichero temporal, sin persistirlo — se descarga y se descarta) con
    un CSV de `event_registrations` (con sus `event_registration_answers`
    resueltas por texto de pregunta, no solo `question_id`) y un CSV de
    `event_tickets` de ese evento. Vía `maintenance_session` (bypassa RLS
    deliberadamente — operación de superadmin sobre cualquier
    organización). Registra la exportación en `audit_log`. **Protección
    contra inyección de fórmulas** (corrección de red-team: las respuestas
    del CSV las escribe cualquiera en el formulario público sin
    autenticar): toda celda cuyo primer carácter sea `=`, `+`, `-`, `@`,
    tab o retorno de carro se prefija con `'` antes de escribirse en el
    CSV. `limit_per_ip` estricto y **reautenticación por contraseña**
    (Validation Session 1: la petición lleva la contraseña actual del
    superadmin en el body — nuevo esquema Pydantic con ese campo,
    verificado con `verify_password`/`hash_password` del propio
    superadmin antes de generar nada — sin sesión de reautenticación
    aparte ni claim nuevo en el JWT) exigida antes de generar la
    exportación. <!-- Updated: Validation Session 1 - export sin JWT del QR -->
    El CSV de `event_tickets` incluye `emitida_en`, `usada_en`,
    `revocada_en` y el estado de la entrada — **nunca el JWT del QR**: es
    una credencial de acceso físico válida mientras el ticket no esté
    revocado, y exportarla en un CSV descargable expondría esa credencial,
    no solo un dato personal.
  - `DELETE /admin/registrations/by-email`: recibe `event_id` + `email`,
    localiza la inscripción y **reutiliza el servicio de cancelación
    (`registrations.service`), no un `DELETE` SQL directo desconectado de
    esa lógica** — corrección de red-team: borrar una inscripción
    `confirmed` sin pasar por `_cancelar_inscripcion`/
    `_promote_next_waitlisted` deja el aforo con un hueco que nunca se
    ofrece a la lista de espera. La llamada equivalente a cancelar debe
    ejecutarse antes o como parte de la operación de borrado, con la
    promoción disparándose igual que en una cancelación normal.
    Adicionalmente: antes de borrar la fila (o como parte de la misma
    transacción), los `event_ticket_scans` del ticket de esa inscripción
    se anonimizan poniendo `ticket_id = NULL` (la FK ya lo admite) en vez
    de perderse por la cascada — son evidencia de control de acceso físico
    al evento, no dato personal de la persona borrada. Registra el
    borrado en `audit_log` con un **hash con sal del email** (nunca el
    email en claro) más el `registration_id` ya borrado en el `detail` —
    corrección de red-team: guardar el email en claro trasladaría la PII
    de una tabla protegida a otra, contradiciendo el propio objetivo del
    borrado. `limit_per_ip` y reautenticación reciente, igual que la
    exportación.
  - Panel de superadmin: pantalla de auditoría (tabla filtrable) y acción
    de exportar/borrar desde la vista de evento existente (o una nueva
    pantalla de superadmin si no hay una vista de evento accesible a
    superadmin todavía — depende de lo que ya exista en el panel actual,
    verificar al implementar).
- Non-functional: ningún endpoint de esta fase acepta el permiso de rol de
  organización (`REGISTRATIONS_WRITE`, etc.) como alternativa a
  `Superadmin` — son operaciones que ni el propio organizador de los datos
  debe poder ejecutar sobre sí mismo sin pasar por soporte. Los tres
  endpoints nuevos llevan `limit_per_ip` — corrección de red-team:
  `admin/router.py` es hoy el único módulo de la API sin ningún límite de
  peticiones (`grep -rn "ratelimit" apps/api/app/modules/admin/` no
  encuentra nada), y un token de superadmin robado sin ese límite permite
  iterar la exportación RGPD sobre todos los eventos de todas las
  organizaciones sin fricción.

## Implementation Steps

1. Decidir y documentar la sesión de escritura de `audit_log` desde
   `roles` (ver Requirements) antes de escribir el helper.
2. Helper de auditoría + instrumentación en los puntos ya existentes
   (cambio de rol, alta de organización, alta de dominio) sin cambiar su
   comportamiento observable, solo añadir el registro.
3. `GET /admin/audit-log` con filtros, paginado y `limit_per_ip`.
4. Mecanismo de reautenticación reciente (verificación de contraseña) para
   los dos endpoints siguientes.
5. `GET /admin/events/{event_id}/rgpd-export` (generación de ZIP + CSV con
   prefijado anti-fórmulas, `limit_per_ip`, reautenticación).
6. `DELETE /admin/registrations/by-email` (reutilizando el servicio de
   cancelación, anonimizando `event_ticket_scans`, hash con sal del email
   en `audit_log`, `limit_per_ip`, reautenticación).
7. Panel de superadmin: pantalla de auditoría + acciones de exportar/borrar.
8. Tests: un organizador (no superadmin) recibe 403 en los tres endpoints
   nuevos; el registro de auditoría se crea correctamente para cada acción;
   borrar un `confirmed` con lista de espera no vacía promueve a la
   siguiente persona; una celda de respuesta que empieza por `=` sale
   prefijada en el CSV.

## Success Criteria

- [x] Un cambio de permisos de un rol, un alta de organización y un alta
      de dominio quedan en `audit_log` sin cambiar el comportamiento
      previo de esos endpoints
- [x] `GET /admin/audit-log` filtra correctamente por organización y rango
      de fechas, con test explícito de cada filtro
- [x] La exportación RGPD de un evento con datos reales produce un ZIP
      cuyo CSV de inscripciones coincide campo a campo con lo que hay en
      base de datos (test que compara el CSV generado contra las filas
      reales, no solo que el ZIP no esté vacío), con una respuesta que
      empieza por `=` (o `+`/`-`/`@`) neutralizada con prefijo `'` en la
      celda resultante
- [x] Borrar un inscrito `confirmed` por email en un evento con lista de
      espera no vacía: la fila de `event_registrations` y lo que cuelga de
      ella (respuestas, consentimientos, entrada) desaparece, sus
      `event_ticket_scans` quedan con `ticket_id = NULL` (no borrados), la
      siguiente persona en lista de espera recibe el email de promoción
      (mismo mecanismo que una cancelación normal), y `audit_log` guarda
      un hash del email, nunca en claro
- [x] Los tres endpoints nuevos exigen reautenticación reciente y tienen
      `limit_per_ip` — test explícito de que una petición sin reautenticar
      o por encima del límite se rechaza
- [x] Un organizador autenticado (sin `is_superadmin`) recibe 403 en los
      tres endpoints nuevos, con test explícito
- [x] Panel de superadmin muestra la auditoría filtrable y permite
      exportar/borrar desde la interfaz, no solo por API directa

## Risk & Rollback

- Riesgo: no existe hoy ningún endpoint de activación/desactivación de
  organización — se documenta como hueco real de `admin/router.py` (fuera
  del alcance M explícito de esta fase, que solo pide auditoría de lo que
  ya existe), sin inventar un endpoint nuevo solo para tener algo que
  auditar.
- Riesgo: la reautenticación reciente añade fricción a una operación de
  soporte que ya de por sí es poco frecuente — aceptado deliberadamente,
  es la mitigación mínima frente a un token de superadmin robado con
  capacidad de exfiltrar PII de toda la instalación.
- Rollback: los tres endpoints nuevos son aditivos sobre `admin/router.py`
  ya existente; deshabilitarlos (quitar la ruta) no afecta a ningún flujo
  de organizador ni de asistente.
