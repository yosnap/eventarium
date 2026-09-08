---
phase: 1
title: "Fase 1: Modelo de datos, permisos y emisión automática"
status: done
priority: P1
effort: "1.5-2d"
dependencies: []
---

# Fase 1: Modelo de datos, permisos y emisión automática

## Overview

Tablas `event_tickets` y `event_ticket_scans`, permisos `tickets:*` y su
backfill, generación del JWT de la entrada, y emisión/revocación automática
enganchada a las transiciones de `event_registrations` ya existentes desde la
fase 3.

## Requirements

- Functional:
  - `event_tickets`: `id`, `event_id`+`organization_id` (FK compuesta a
    `events`), `registration_id`+`organization_id` (FK compuesta a
    `event_registrations`, `UNIQUE` — una entrada por inscripción),
    `issued_at`, `used_at` (nullable), `used_by_event_member_id` (nullable,
    FK a `event_members`), `revoked_at` (nullable).
  - `event_ticket_scans`: `id`, `ticket_id`+`organization_id` (FK compuesta a
    `event_tickets`), `event_id` (denormalizado), `scanned_by_event_member_id`
    (FK a `event_members`, no nullable), `client_scan_id` (`UUID`, `UNIQUE`),
    `client_scanned_at`, `scanned_at` (`server_default=func.now()`), `result`
    (`valid`/`duplicate`/`expired`/`invalid_signature`/`revoked`/`not_found`),
    `device_label` (nullable).
  - `app/core/permissions.py`: `TICKETS_READ = "tickets:read"`,
    `TICKETS_WRITE = "tickets:write"` (el prefijo ya está reservado desde la
    fase 0, ver el docstring del módulo).
  - `app/modules/roles/system_roles.py`: añadir `TICKETS_WRITE` a
    `VOLUNTEER.permissions`; añadir `TICKETS_READ`+`TICKETS_WRITE` a
    `ORGANIZER.permissions` (`OWNER` ya tiene todos vía `tuple(Permission)`).
  - Migración con backfill (mismo patrón que `0009`/`0010`): `tickets:read`+
    `tickets:write` a cualquier rol con `organizations:write`; además
    `tickets:write` a los roles ya clonados de la plantilla `volunteer`
    (`roles.key = 'volunteer'`) en organizaciones existentes.
  - `app/core/config.py`: `ticket_qr_secret: str` (obligatorio, validado con
    el mismo mínimo de longitud que `jwt_secret` — `field_validator`
    reutilizable o duplicado si no conviene compartirlo), `ticket_qr_expiry_margin_hours: int = 48`.
  - `app/modules/tickets/` (módulo nuevo): `models.py` (los dos modelos),
    `repository.py`, `service.py` con:
    - `emitir_entrada(session, inscripcion) -> EventTicket`: crea la fila si
      no existe ya una para esa `registration_id` (idempotente — el reenvío
      del formulario con un email ya `confirmed`, fase 3, pasa por el mismo
      punto de enganche sin ser una confirmación nueva; que sea idempotente
      evita una entrada duplicada silenciosa). Carga el `Event` internamente
      (`session.get(Event, inscripcion.event_id)`) para `evento.ends_at` —
      `_enviar_email_por_estado` no tiene el evento cargado en todos sus
      llamadores (`confirm_waitlist_promotion` no lo necesita hoy), así que
      es más simple que `emitir_entrada` lo resuelva por su cuenta que
      cambiar la firma de sus cinco llamadores.
    - `revocar_entrada(session, registration_id) -> None`: marca
      `revoked_at` si existe una entrada para esa inscripción; no-op si no
      existe (una inscripción `waitlisted`/`pending_approval` cancelada
      nunca tuvo entrada).
    - `generar_token_qr(ticket) -> str`: JWT HS256 con `ticket_qr_secret`,
      payload `{"tid": str(ticket.id), "eid": str(ticket.event_id), "exp": ...}`
      con `exp` = `evento.ends_at` (en UTC) + `ticket_qr_expiry_margin_hours`,
      y `nonce` (un `secrets.token_urlsafe(8)` como claim `jti`, no como
      identificador de negocio — solo para que dos tokens de la misma
      entrada nunca sean el string idéntico, por higiene, aunque el propio
      JWT ya varía por `iat`).
  - Enganchar `emitir_entrada` dentro de `_enviar_email_por_estado`
    (`registrations/service.py`, fase 3) cuando `inscripcion.status ==
    "confirmed"`: es la única función por la que pasan los cinco puntos que
    pueden dejar una inscripción en `confirmed` (alta directa sin
    verificación, verificación, aprobación, promoción de lista de espera, y
    el reenvío al resubmitir el formulario con un email ya confirmado) —
    engancharlo ahí en vez de en cada llamador evita repetir la condición
    cinco veces. Como `emitir_entrada` es idempotente, el caso de reenvío
    (que no es una confirmación nueva) simplemente no crea una segunda
    entrada. Enganchar `revocar_entrada` al principio de
    `_cancelar_inscripcion` (antes de cambiar el estado): revocar si había
    entrada, no-op si no la había (una inscripción `waitlisted`/
    `pending_approval` cancelada nunca tuvo entrada).
- Non-functional:
  - RLS en las dos tablas nuevas, mismo patrón que `event_registrations`
    (política por `organization_id` vía `app.organization_id`).
  - El JWT nunca lleva nombre, email ni ninguna otra columna de
    `event_registrations` en su payload — solo `tid`/`eid`/`exp`/`jti`.

## Validation

- Test: confirmar una inscripción (los tres caminos: verificación directa,
  aprobación, promoción de lista de espera) emite exactamente una entrada;
  llamar a `emitir_entrada` dos veces para la misma inscripción no crea una
  segunda fila (constraint `UNIQUE(registration_id)` + manejo del
  `IntegrityError`, mismo patrón que `submit_registration`).
- Test: cancelar una inscripción `confirmed` con entrada revoca la entrada
  (`revoked_at` no nulo); cancelar una `waitlisted` sin entrada no falla
  (no-op).
- Test: `generar_token_qr` produce un JWT verificable con `PyJWT.decode` y el
  mismo `ticket_qr_secret`; decodificarlo con un secreto distinto falla.
- Test de permisos: un rol clonado de `volunteer` en una organización
  existente antes de esta migración tiene `tickets:write` tras aplicarla,
  pero no `tickets:read` (salvo que ya tuviera `organizations:write`).

## Risk & Rollback

- Riesgo: enganchar la emisión dentro de `_enviar_email_por_estado`
  (fase 3) acopla el módulo `registrations` al módulo `tickets` nuevo —
  aceptable porque la propia fase 3 ya documentó que "sin una inscripción
  `confirmed` no hay a qué emitir una entrada" como su razón de ser; es un
  acoplamiento de dominio esperado, no accidental.
- Rollback: revertir la migración elimina las tablas nuevas y las
  columnas/permisos añadidos; el enganche en `registrations/service.py`
  queda como código muerto si `tickets` no está instalado — mejor quitar
  también esa llamada en el mismo revert que dejarla fallando en producción.
