---
phase: 2
title: "Fase 2: Escaneo y check-in (API)"
status: pending
priority: P1
effort: "1.5-2d"
dependencies: [1]
---

# Fase 2: Escaneo y check-in (API)

## Overview

Los endpoints que la app de escaneo (fase 3) va a consumir: escanear un QR
(individual y en lote, para la sincronización offline), buscar manualmente, y
ver el detalle de una entrada.

## Requirements

- Functional:
  - `POST /api/v1/events/{event_id}/tickets/scan`: body `{token, client_scan_id,
    client_scanned_at, device_label?}`. Decodifica el JWT con
    `ticket_qr_secret`; si la firma o el `exp` fallan → `result=invalid_signature`
    o `expired` sin más detalle (mismo principio de no filtrar información
    que el resto de tokens del proyecto). Si decodifica, resuelve la entrada
    por `tid`; si no existe → `not_found`. Si `revoked_at` no es nulo →
    `revoked`. Si `used_at` ya está puesto → `duplicate` (con los datos de
    quién y cuándo la usó por primera vez, para que el staff decida en el
    momento). Si nada de lo anterior, `SELECT ... FOR UPDATE` sobre la fila
    de la entrada (dos escaneos casi simultáneos del mismo QR en dos
    dispositivos son el caso real que hay que serializar) y marca
    `used_at`/`used_by_event_member_id` → `valid`. Registra siempre una fila
    en `event_ticket_scans` con el resultado, `client_scan_id` incluido —
    si `client_scan_id` ya existe (reintento de red), devuelve el resultado
    ya guardado sin volver a evaluar nada (idempotencia real, no solo un
    "no falles dos veces").
  - `POST /api/v1/events/{event_id}/tickets/scan/batch`: body `{scans: [...]}`
    (misma forma que el individual, repetida), procesados en el orden de
    `client_scanned_at` dentro de la petición; devuelve un array con el
    resultado de cada `client_scan_id` en el mismo orden.
  - `GET /api/v1/events/{event_id}/tickets/search?q=`: busca por nombre o
    email (`ILIKE`) entre inscripciones `confirmed` con entrada emitida y no
    revocada del evento; devuelve id de la entrada, nombre, email completo (el
    staff necesita confirmar la identidad de la persona igual que en un
    control de acceso físico, sin enmascarar) y si ya tiene `used_at`.
  - `POST /api/v1/events/{event_id}/tickets/{ticket_id}/check-in-manual`:
    mismo efecto que un escaneo válido pero originado desde la búsqueda
    manual (mismas reglas de duplicado/revocado, mismo registro en
    `event_ticket_scans` con un `result` adicional `manual` en vez de
    `valid` — para poder diferenciar en la auditoría cuántos check-ins
    fueron por cámara y cuántos manuales).
  - `GET /api/v1/events/{event_id}/tickets/{registration_id}`: detalle de la
    entrada de una inscripción concreta (para el panel de organizador:
    reenviar el email, ver su estado). Requiere `tickets:read`.
- Non-functional:
  - `scan`/`scan/batch`/`check-in-manual` requieren `tickets:write`;
    `search`/el detalle requieren `tickets:write` y `tickets:read`
    respectivamente, según la decisión #7 del plan (permiso de organización,
    sin acotar al roster del evento).
  - Sin rate limiting específico: a diferencia de los endpoints públicos de
    la fase 3, estos exigen sesión autenticada con permiso — el mismo
    patrón que el resto del panel de organizador, no el de formularios
    públicos.

## Validation

- Test: escanear un QR válido de una entrada sin usar → `valid`, `used_at`
  queda fijado, el email/nombre devueltos coinciden con la inscripción.
- Test: escanear el mismo QR una segunda vez → `duplicate`, sin sobrescribir
  `used_at` ni `used_by_event_member_id` originales.
- Test: escanear un QR de una entrada revocada (inscripción cancelada
  después de emitida) → `revoked`.
- Test: escanear un JWT con firma inválida (`ticket_qr_secret` distinto) o
  caducado → `invalid_signature`/`expired`, sin filtrar cuál de los dos es
  exactamente si eso simplifica el mensaje (a decidir al implementar, según
  lo que ya haga `consume_token` como referencia).
- Test de concurrencia: dos escaneos simultáneos (`asyncio.gather`) del mismo
  QR válido → exactamente uno `valid`, el otro `duplicate` — mismo patrón que
  los tests de concurrencia de aforo de las fases 2/3.
- Test: reenviar la misma petición de escaneo con idéntico `client_scan_id`
  no cambia el resultado ya registrado ni cuenta como un segundo intento en
  `event_ticket_scans`.
- Test: `scan/batch` con varios escaneos, alguno duplicado entre sí dentro
  del mismo lote, devuelve el resultado correcto para cada uno respetando el
  orden de `client_scanned_at`.
- Test: `search` no devuelve inscripciones `waitlisted`/`pending_approval`/
  `rejected`/`cancelled` (solo `confirmed` con entrada vigente).

## Risk & Rollback

- Riesgo: `scan/batch` con un lote grande (cola offline de toda una jornada
  sincronizando de golpe) podría tardar si cada escaneo abre su propia
  sección crítica secuencialmente — aceptable para el volumen esperado
  (cientos, no miles, por dispositivo); si se vuelve un problema real,
  agrupar por lotes más pequeños desde el cliente antes de optimizar el
  servidor.
- Rollback: los endpoints son aditivos; desactivarlos (quitar el router del
  montaje) no afecta a la fase 3 ya cerrada.
