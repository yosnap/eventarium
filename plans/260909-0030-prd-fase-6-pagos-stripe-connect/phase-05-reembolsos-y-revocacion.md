---
phase: 5
title: "Fase 5: Reembolsos con outbox, política de plazo y revocación de entradas"
status: pending
priority: P1
effort: "2.5-3d"
dependencies: [4]
---

# Fase 5: Reembolsos con outbox, política de plazo y revocación de entradas

## Overview

Reembolso automático al cancelar una inscripción de pago y reembolso manual
total o parcial desde el panel. La revocación de la entrada **no se
construye**: existe desde la fase 4 del PRD y se reutiliza tal cual (Decisión
#1 del plan).

Tres cambios sustanciales respecto a la versión anterior de esta fase, los
tres de dinero real sin compensación:

- **El reembolso no se emite dentro de `_cancelar_inscripcion`** (hallazgos
  #11 y #12). La mitigación anterior («emitir el reembolso antes de tomar el
  bloqueo de aforo») no evitaba nada: los dos llamadores reales ya tienen la
  fila de la inscripción bloqueada **antes** de entrar
  (`registrations/service.py:492` con `get_registration_for_update`, y
  `service.py:522` con `session.get(..., with_for_update=True)`), así que
  cualquier llamada de red dentro de esa función ocurre con locks abiertos. Se
  sustituye por un **outbox**: `_cancelar_inscripcion` persiste una intención
  de reembolso y hace commit; una tarea la ejecuta contra Stripe con
  `idempotency_key` determinística.
- **La autocancelación pública deja de reembolsar incondicionalmente**
  (hallazgo #13): el token dura 90 días
  (`registration_cancel_token_ttl_days = 90`,
  `apps/api/app/core/config.py:106`), no está autenticado y hoy no comprueba
  ni si el evento ya ocurrió ni si la entrada ya se usó.
- **`refunded_cents` se consolida desde `charge.refunded` comparando el
  acumulado que reporta Stripe**, nunca sumando el delta.

**Ficheros creados en esta fase:**
`apps/api/app/modules/payments/refunds_service.py`,
`apps/web/src/app/features/admin/events/event-payments.ts` (+ spec).

**Ficheros existentes que amplía:** `payments/repository.py`,
`payments/schemas.py`, `payments/router.py`, `payments/webhooks.py` (handler de
`charge.refunded`), `registrations/service.py` (`_cancelar_inscripcion`),
`apps/api/app/core/tasks.py`, `apps/web/src/app/app.routes.ts`.

## Requirements

- Functional:
  - **Outbox de reembolso.** `_cancelar_inscripcion`
    (`registrations/service.py:237-274`) gana un paso **antes** del cambio de
    estado: si la inscripción tiene un `event_payments` en `paid`/
    `partially_refunded` **y** se cumple la política de reembolso, inserta una
    fila en `event_payment_refunds` (`reason = 'cancellation'`, `status =
    'pending'`, `revoke_ticket = true`, importe = pendiente íntegro). No llama
    a Stripe. Sigue revocando la entrada y promoviendo la lista de espera como
    hoy (líneas 258 y 271-273). Los tres caminos que cancelan (panel, enlace
    público y el barrido de la fase 4) heredan el comportamiento sin tocarlos
    (Decisión #14 del plan).
  - **Política de reembolso automático** (hallazgo #13). Se emite
    automáticamente solo si se cumplen las cuatro condiciones:
    1. el pago está en `paid`/`partially_refunded` con importe pendiente > 0;
    2. el evento **no ha empezado** (`now < event.starts_at`);
    3. la entrada **no se ha usado** (`event_tickets.used_at IS NULL`,
       `apps/api/app/modules/tickets/models.py:66`);
    4. faltan al menos `payment_refund_cutoff_hours` (config de la fase 1,
       por defecto 24) para `starts_at`.
    Fuera de esas condiciones la cancelación **se aplica igual** pero sin
    reembolso automático, con el motivo registrado en la fila del pago y
    visible en el panel; el organizador puede reembolsar a mano desde el
    listado de pagos. El correo de cancelación indica cuál de los dos casos
    ha ocurrido.
  - **Tarea `process_refunds_task`** (cron `*/2 * * * *` y encolada también
    al vuelo tras la cancelación): toma las filas `pending` de
    `event_payment_refunds`, las marca `submitted` con `attempts + 1` y
    `submitted_at`, y llama a `Refund.create_async` con
    `stripe_account = <stripe_account_id de la fila del pago>` (nunca la
    cuenta «actual» de la organización — un pago cobrado en una cuenta luego
    desconectada solo se reembolsa contra esa cuenta, hallazgo #17) y
    **`idempotency_key = f"refund_{refund.id}"`**, derivada de la PK
    persistida, así que un reintento nunca duplica el reembolso (hallazgo
    #11). Guarda `stripe_refund_id` y pasa la fila a `succeeded`; ante error,
    a `failed` con el mensaje, para reintento acotado y visible en el panel.
    Las filas `failed` con `attempts >= 5` se registran en el log a nivel
    `ERROR`: son dinero que el asistente espera y que no ha salido.
  - `GET /events/{event_id}/payments` (`PAYMENTS_READ`) — listado de pagos con
    estado, importe, descuento, importe reembolsado, motivo de «sin reembolso
    automático» si lo hubo, estado de los reembolsos en curso, y enlace a la
    inscripción.
  - `POST /events/{event_id}/payments/{payment_id}/refund`
    (`PAYMENTS_WRITE`) — reembolso manual. Cuerpo: `amount_cents` opcional
    (ausente = total pendiente) y `revoke_ticket`. Reglas:
    - Total → siempre revoca la entrada, ignorando `revoke_ticket`.
    - Parcial → **no** revoca salvo `revoke_ticket = true` (Decisión #15 del
      plan; pendiente de la pregunta abierta #1).
    - `amount_cents` mayor que `amount_cents - refunded_cents` → 409 **antes**
      de llamar a Stripe.
    - Pago que no esté en `paid`/`partially_refunded` → 409.
    - El endpoint **también escribe en el outbox** y devuelve 202 con el estado
      «reembolso en curso»: un solo camino de ejecución para el automático y
      el manual, igual que exige el no-funcional de abajo.
  - **Handler de `charge.refunded`** (registrado como `ignored` en la fase 4):
    es la fuente de verdad del importe reembolsado, **incluidos los reembolsos
    hechos por el organizador desde su propio Dashboard de Stripe**, que con
    Connect Standard puede hacer y la plataforma no controla. Localiza el pago
    por `stripe_payment_intent_id` (`UNIQUE`), verifica que
    `payment.organization_id` coincide con la organización de `event.account`
    (misma comprobación cruzada que el hallazgo #2 impone en la fase 4),
    **fija** `refunded_cents` al acumulado que reporta Stripe (`amount_refunded`
    del cargo), nunca suma el delta, actualiza `status`
    (`partially_refunded`/`refunded`) y, si es total, revoca la entrada.
  - **La revocación es la existente.** `revocar_entrada`
    (`apps/api/app/modules/tickets/service.py:82-93`) fija `revoked_at`; el
    control de acceso ya la rechaza antes de comprobar duplicado
    (`tickets/scanning.py:83-84`); `/mi-entrada` ya oculta el QR
    (`tickets/service.py:155-164`); el frontend ya pinta el resultado
    (`apps/web/src/app/features/admin/events/event-check-in.ts:64,122`). **No
    se añade ninguna columna, ningún estado nuevo ni ninguna comprobación en
    el escáner.**
  - **La fila de la entrada nunca se borra**: se conserva con su `revoked_at` y
    con sus `event_ticket_scans`.
  - Panel: pantalla de pagos del evento con acción de reembolso, diálogo de
    confirmación que muestra importe total, ya reembolsado y pendiente, y la
    casilla «revocar también la entrada» solo visible en reembolso parcial.
- Non-functional:
  - **Una sola implementación del reembolso.** El automático y el manual
    escriben la misma fila de outbox y los ejecuta la misma tarea. Dos
    implementaciones serían dos formas distintas de decidir si se revoca la
    entrada.
  - **Ninguna llamada de red a Stripe dentro de una transacción con bloqueos
    de fila abiertos** (hallazgo #12). Orden de adquisición documentado y
    único, el mismo de la fase 3: `event_registrations` → `events` →
    `event_ticket_types` → `event_discount_codes`. La tarea de reembolsos no
    toma ningún bloqueo de esa cadena mientras llama a Stripe: bloquea la fila
    de `event_payment_refunds`, hace commit del `submitted`, llama, y vuelve a
    abrir transacción para el resultado.
  - **El importe final lo escribe el webhook, no la respuesta de la llamada.**
    `Refund.create_async` devolviendo `succeeded` no se toma como verdad
    final: la tarea marca `succeeded` la **intención**, y `charge.refunded`
    consolida `refunded_cents`. Así el reembolso hecho desde el Dashboard de
    Stripe y el hecho desde el panel convergen en el mismo camino, sin dos
    escritores del mismo campo con reglas distintas.
  - **Un fallo de Stripe no puede dejar una cancelación sin rastro.** Con el
    outbox, la cancelación se confirma siempre y el reembolso queda `pending`
    o `failed` y **visible**; lo que se elimina es el caso opuesto y peor:
    dinero devuelto en Stripe sin ninguna fila que lo registre. Un reembolso
    `failed` aparece destacado en el panel del evento, no solo en el log.
  - `openapi.json` + cliente TypeScript regenerados.
  - WCAG 2.1 AA en la pantalla de pagos: cabeceras de tabla asociadas, diálogo
    con gestión de foco y cierre con `Escape`, resultado anunciado en
    `aria-live`.
  - Tamaños estimados: `refunds_service.py` ~280; `payments/webhooks.py` pasa
    de ~350 a ~430; `payments/router.py` a ~400.

## Implementation Steps

1. `payments/repository.py`: alta y consultas de `event_payment_refunds`,
   localización de pago por `payment_intent_id`.
2. `payments/refunds_service.py`: función única que valida importes y política
   y escribe la intención; función que la ejecuta contra Stripe.
3. `registrations/service.py`: paso de outbox en `_cancelar_inscripcion`, con
   la política de plazo y el docstring actualizado (hoy describe solo cancelar
   + revocar + promover).
4. `core/tasks.py`: `process_refunds_task` (cron + encolado al vuelo).
5. `payments/webhooks.py`: handler de `charge.refunded`.
6. `payments/router.py`: listado de pagos y endpoint de reembolso manual.
7. Frontend: pantalla de pagos con el diálogo de reembolso.
8. `openapi.json` + cliente TypeScript regenerados.

## Success Criteria

- [ ] Cancelar desde el panel una inscripción de pago `confirmed` dentro de
      plazo crea la intención de reembolso, revoca la entrada y promueve la
      lista de espera; la tarea emite el reembolso y `charge.refunded` deja el
      pago en `refunded`
- [ ] Cancelar desde el **enlace público de autocancelación** hace lo mismo,
      sin ningún código añadido en ese camino (hereda `_cancelar_inscripcion`)
      — test de los dos caminos
- [ ] `grep` no encuentra ninguna segunda implementación de la transición a
      `cancelled` fuera de `_cancelar_inscripcion`, ni ninguna llamada a
      `Refund` fuera de `payments/stripe_client.py`
- [ ] **Ninguna llamada a Stripe ocurre dentro de `_cancelar_inscripcion`** —
      verificado contando llamadas al cliente simulado durante una cancelación
      (hallazgo #12)
- [ ] Autocancelar con el evento ya empezado, con la entrada ya usada, o
      dentro de las `payment_refund_cutoff_hours` previas: la inscripción se
      cancela **sin** reembolso automático, con el motivo registrado y visible
      en el panel — tres tests, uno por condición (hallazgo #13)
- [ ] Un reembolso cuya llamada a Stripe tiene éxito y cuya escritura posterior
      falla **deja rastro**: la fila de `event_payment_refunds` existe desde
      antes de la llamada y el reintento usa la **misma** `idempotency_key`,
      sin duplicar el reembolso — test que simula el fallo tras la llamada
      (hallazgo #11)
- [ ] Dos ejecuciones concurrentes de `process_refunds_task` sobre la misma
      fila producen **un solo** reembolso en Stripe
- [ ] Reembolsar más del importe pendiente devuelve 409 **antes** de llamar a
      Stripe — verificado contando llamadas
- [ ] Dos reembolsos parciales sucesivos que suman el total dejan el pago en
      `refunded` y revocan la entrada al completarse el segundo
- [ ] Un `charge.refunded` originado en el Dashboard de Stripe (con `stripe
      trigger --stripe-account`) actualiza `refunded_cents` y revoca la
      entrada si es total, sin que nadie haya tocado el panel
- [ ] Entregar el mismo `evt_...` de `charge.refunded` dos veces deja
      `refunded_cents` en el mismo valor: se **fija** al acumulado de Stripe,
      no se suma
- [ ] Un `charge.refunded` cuyo `event.account` no coincide con la
      organización del pago no muta nada y se marca `failed`
- [ ] Tras un reembolso total, el QR se rechaza en el check-in con resultado
      `revoked` y la fila de `event_tickets` **sigue existiendo** con sus
      `event_ticket_scans` intactos
- [ ] Un reembolso parcial no revoca la entrada (el QR sigue `valid`); con la
      casilla marcada, sí la revoca
- [ ] No se ha añadido ninguna columna ni estado nuevo a `event_tickets` —
      verificado con el diff de `apps/api/app/modules/tickets/`
- [ ] Un organizador de la organización A no puede reembolsar un pago de B, ni
      manipulando el `payment_id` ni el cuerpo; el `acct_id` del reembolso sale
      del `stripe_account_id` **de la fila del pago**, no de la cuenta actual
      de la organización — test con una cuenta desconectada y otra nueva
      (hallazgo #17)
- [ ] Un reembolso `failed` tras agotar reintentos aparece destacado en el
      panel del evento, no solo en el log
- [ ] Cero violaciones de axe en la pantalla de pagos y su diálogo (foco y
      `Escape` incluidos)
- [ ] `openapi.json` y el cliente TypeScript generado al día

## Risk & Rollback

- Riesgo: con Connect Standard el organizador puede reembolsar desde su propio
  Dashboard sin pasar por la plataforma. Si el estado del pago solo se
  escribiera desde el endpoint del panel, la base de datos divergiría de
  Stripe en silencio y una entrada reembolsada seguiría escaneando como
  válida. Por eso `charge.refunded` es la fuente de verdad del importe.
- Riesgo: el outbox introduce una latencia entre cancelar y ver el dinero
  devuelto (hasta el siguiente ciclo de la tarea, más el encolado al vuelo).
  Es el precio de no llamar a Stripe bajo bloqueos y de no perder reembolsos
  ante un fallo de la base de datos. La UI lo refleja como «reembolso en
  curso», no como «reembolsado».
- Riesgo: la `idempotency_key` de Stripe caduca a las 24 horas. Los reintentos
  de la tarea ocurren en minutos, así que la garantía se sostiene; un
  reintento manual días después sí podría duplicar. Se documenta y por eso las
  filas `failed` se escalan a log `ERROR` en vez de reintentarse
  indefinidamente.
- Riesgo: reembolsar es irreversible. El diálogo debe mostrar los tres
  importes y exigir confirmación explícita; no basta un botón en la fila.
- Riesgo: la Decisión #15 (parcial no revoca) contradice una lectura literal
  del enunciado de la fase. Está anotada como pregunta abierta #1 del plan y
  debe resolverse **antes** de implementar esta fase.
- Riesgo: el borrado RGPD (`admin/service.py:206-253`) cancela la inscripción
  antes de borrarla, así que ahora también dispara la política de reembolso.
  Es coherente (borrar a un asistente que había pagado es cancelar su
  inscripción) y la fila del pago sobrevive con `registration_id NULL`; queda
  anotado como pregunta abierta del plan por si el criterio de producto es
  otro.
- Rollback: retirar los endpoints de reembolso es un commit. El paso de outbox
  en `_cancelar_inscripcion` es una condición sobre pagos que solo existen en
  eventos de pago. Lo que **no** se puede revertir son los reembolsos ya
  emitidos: si esta fase se revierte con ventas en curso, el handler de
  `charge.refunded` debe mantenerse activo para que la base de datos no
  diverja de Stripe.
