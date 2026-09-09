---
phase: 3
title: "Fase 3: Tipos de entrada, códigos de descuento y cálculo de precio"
status: pending
priority: P1
effort: "2-2.5d"
dependencies: [2]
---

# Fase 3: Tipos de entrada, códigos de descuento y cálculo de precio

## Overview

CRUD de los dos catálogos que definen qué se vende y a qué precio, más la
**única** implementación del cálculo de precio final. Todo vive en la base de
datos de la plataforma (Decisión #8 del plan): Stripe recibe un importe ya
calculado y nunca calcula descuentos.

Cambios respecto a la versión anterior de esta fase:

- **Ya no se declara paralelizable con la fase 2** (hallazgo #20). Dependía de
  ella de hecho: comparte `repository.py`, `schemas.py`, `service.py` y
  `router.py`, que la fase 2 crea. Se declara `dependencies: [2]` y se acabó la
  propiedad disputada.
- **No hay `pricing.py` aparte** (hallazgo #20): el cálculo son funciones
  puras y viven como funciones de módulo en `payments/service.py`, que es la
  convención real del repositorio (un `service.py` por módulo; el mayor del
  proyecto tiene 723 líneas, `apps/api/app/modules/registrations/service.py`).
- **No hay `used_count`** (hallazgo #19): el consumo de un código se deriva de
  `event_payments`.

**Ficheros creados en esta fase:**
`apps/api/app/modules/payments/public_router.py` (solo el presupuesto),
`apps/web/src/app/features/admin/events/event-ticket-types.ts`,
`event-discount-codes.ts` (+ specs).

**Ficheros de la fase 2 que amplía (secciones propias, sin solaparse):**
`payments/repository.py`, `payments/schemas.py`, `payments/service.py`,
`payments/router.py`; `apps/api/app/core/ratelimit.py`,
`apps/api/app/main.py`, `apps/web/src/app/app.routes.ts`.

## Requirements

- Functional:
  - `GET/POST/PATCH/DELETE /events/{event_id}/ticket-types`
    (`PAYMENTS_READ`/`PAYMENTS_WRITE`) — CRUD con `sort_order` reordenable.
    Borrar un tipo con códigos o pagos asociados → 409 comprobado en el
    servicio **y** garantizado por la FK sin `ondelete` de la fase 1; nunca un
    500 de `IntegrityError` sin capturar. Un tipo con pagos puede desactivarse
    (`is_active = false`) pero no borrarse.
  - `GET/POST/PATCH/DELETE /events/{event_id}/discount-codes` — CRUD.
    `code` se normaliza a mayúsculas al guardar y al comparar; el
    `UNIQUE(event_id, code)` de la fase 1 impide duplicados. La respuesta
    incluye `used_count` **derivado** (`COUNT` sobre `event_payments`), de solo
    lectura y sin columna que lo respalde.
  - `POST /public/events/{slug}/checkout/quote` — presupuesto público:
    recibe `ticket_type_id` y `code` opcional y devuelve `price_cents`,
    `discount_cents`, `total_cents`, `currency`, o el rechazo. Con
    `limit_per_ip` propio (`CHECKOUT_QUOTE_POR_IP` en
    `app/core/ratelimit.py`, que ya reúne los quince límites del proyecto,
    líneas 27-78) y Turnstile (`require_turnstile`, ya usado por el formulario
    público de inscripción, `apps/api/app/modules/registrations/
    public_router.py:25`): sin ambos, este endpoint es un oráculo para
    enumerar códigos por fuerza bruta.
  - **Cálculo de precio, en `payments/service.py`, funciones puras:**
    - `calcular_precio_final(price_cents, discount_type, discount_value)` —
      aplica el descuento, redondea a la baja al céntimo y **satura en 0**.
      La fase 4 la reutiliza tal cual para el importe que envía a Stripe: que
      el presupuesto y el cobro salgan de la misma función es lo único que
      garantiza que no se cobre un importe distinto del anunciado.
    - `validar_tipo_vigente(tipo, ahora)` — `is_active`, ventana
      `sales_start_at`/`sales_end_at`.
    - `validar_codigo_vigente(codigo, tipo, usos, ahora)` — ventana
      `valid_from`/`valid_until`, `max_uses` frente a los usos **derivados**, y
      `ticket_type_id` compatible.
    - Ninguna de las tres toca la base de datos: se testean sin fixtures.
  - **El cupo de un tipo de entrada también es derivado**, por el mismo
    criterio que el uso de los códigos: `COUNT(event_payments WHERE
    ticket_type_id = X AND status IN ('pending','paid','partially_refunded',
    'refunded'))` frente a `max_quantity`. No hay contador denormalizado en
    `event_ticket_types`.
  - Panel: pantalla de tipos de entrada y pantalla de códigos dentro del
    evento, visibles solo si `registration_mode === 'paid'`, con el aviso de
    que el evento no podrá publicarse hasta conectar Stripe (enlazando a la
    pantalla de la fase 2).
- Non-functional:
  - **Contrato de bloqueo, fijado aquí y consumido en la fase 4.** Toda
    comprobación de cupo o de usos que preceda a un cobro se hace con `SELECT
    ... FOR UPDATE` sobre la fila del tipo de entrada **y** sobre la del
    código, dentro de la misma transacción que crea el pago, y el `COUNT`
    derivado se ejecuta **con esas filas ya bloqueadas**. Sin ese bloqueo, N
    compras concurrentes leen el mismo total y todas pasan — y con el consumo
    derivado el riesgo es idéntico al que tenía el contador. El repositorio ya
    tiene el precedente: `lock_event_for_capacity`
    (`apps/api/app/modules/registrations/repository.py:51-64`).
  - **Orden de adquisición de bloqueos, único para todo el módulo** (hallazgo
    #12): `event_registrations` → `events` → `event_ticket_types` →
    `event_discount_codes`. Es el orden que ya usan los caminos existentes
    (`cancel_registration` bloquea la inscripción en
    `registrations/service.py:492` y después el evento en la línea 272 vía
    `_cancelar_inscripcion`); invertirlo en el camino de compra provocaría
    interbloqueos entre una compra y una cancelación concurrentes. Se
    documenta en el docstring del módulo y la fase 4 lo respeta.
  - **Un presupuesto nunca reserva nada**: es informativo, no consume cupo ni
    uso de código. Explícito en el docstring del endpoint.
  - RLS: test de que un código de descuento no puede apuntar a un
    `ticket_type_id` de otra organización (escritura cruzada).
  - `openapi.json` + cliente TypeScript regenerados.
  - WCAG 2.1 AA en ambas pantallas: campos de precio numéricos con
    `inputmode`, errores asociados al campo con `aria-describedby`, y el mismo
    patrón de fecha/hora accesible que ya emplea
    `apps/web/src/app/features/admin/events/event-form.ts`.
  - Tamaños tras esta fase: `payments/service.py` ~480, `repository.py` ~330,
    `router.py` ~300, `schemas.py` ~230, `public_router.py` ~120.

## Implementation Steps

1. `payments/service.py`: las tres funciones puras de precio y vigencia, con
   sus tests unitarios sin base de datos.
2. `payments/repository.py`: consultas de catálogos, las variantes con `FOR
   UPDATE`, y los dos `COUNT` derivados (usos de código, cupo de tipo).
3. `payments/service.py`: CRUD de tipos de entrada y de códigos.
4. `payments/router.py`: endpoints de panel de ambos catálogos.
5. `payments/public_router.py`: presupuesto, con `CHECKOUT_QUOTE_POR_IP` y
   Turnstile; registro del router en `app/main.py`.
6. Frontend: dos pantallas nuevas dentro del evento, condicionadas a
   `registration_mode === 'paid'`.
7. `openapi.json` + cliente TypeScript regenerados.

## Success Criteria

- [ ] Un organizador crea 3 tipos de entrada con precios, cupos y ventanas de
      venta distintas, los reordena, y el orden se refleja en el panel y en el
      formulario público
- [ ] Un tipo fuera de su ventana de venta no se ofrece en el formulario
      público y su presupuesto se rechaza
- [ ] El cálculo de precio tiene **una sola** implementación: `grep` no
      encuentra ninguna otra multiplicación por el porcentaje ni resta del
      importe fijo en `app/modules/payments/` ni en `app/modules/registrations/`
- [ ] Un descuento `fixed_amount` mayor que el precio produce total 0, nunca
      negativo; un `percentage` de 100 produce 0 — test unitario sobre las
      funciones puras
- [ ] Un código caducado, agotado, inexistente o asociado a otro tipo de
      entrada produce **un mensaje único de cara al público** («este código no
      es válido para esta entrada») con el motivo exacto solo en el log del
      servidor — cuatro casos, un solo mensaje visible
- [ ] El presupuesto tiene `limit_per_ip` y Turnstile; superar el límite
      devuelve 429 — test explícito
- [ ] Pedir 50 presupuestos sobre un código de 1 uso no consume ese uso: el
      `used_count` derivado sigue en 0 porque no se ha creado ningún
      `event_payments` — test explícito
- [ ] `used_count` de la respuesta del panel coincide siempre con el número de
      `event_payments` en estado consumible, incluso tras expirar un pago:
      un pago `expired` **deja de contar** sin que nadie decremente nada
      (hallazgo #19) — test con un pago llevado a `expired`
- [ ] Borrar un tipo de entrada con códigos o pagos asociados devuelve 409 con
      mensaje claro; desactivarlo (`is_active = false`) sí funciona
- [ ] Un código de descuento no puede apuntar a un `ticket_type_id` de otra
      organización — test de escritura cruzada
- [ ] Las pantallas de tipos y de códigos solo aparecen en un evento `paid`
- [ ] El orden de adquisición de bloqueos está documentado en el docstring del
      módulo de pagos y coincide con el que ya usan los caminos de
      cancelación existentes
- [ ] Cero violaciones de axe en ambas pantallas
- [ ] `openapi.json` y el cliente TypeScript generado al día

## Risk & Rollback

- Riesgo: dos formas de expresar un descuento comparten la columna
  `discount_value` como entero; un `50` significa 50 % o 0,50 € según
  `discount_type`. Mitigación: los `CHECK` condicionados de la fase 1 acotan
  cada rango, la UI muestra la unidad junto al campo, y el cálculo nunca lee
  `discount_value` sin mirar `discount_type` en la misma expresión. La
  alternativa (dos columnas nullable) exigiría un `CHECK` de exclusividad
  igual de frágil y dejaría una columna vacía en cada fila.
- Riesgo: pasar de contador a consumo derivado cambia el coste de la
  comprobación de un `SELECT` de una fila a un `COUNT` sobre índice, dentro de
  la sección crítica de la compra. A la escala del producto (cientos de pagos
  por evento) es despreciable; si algún día dejara de serlo, la solución es un
  índice parcial por estado, no reintroducir el contador de dos direcciones.
- Riesgo: el contrato de bloqueo se define aquí pero se consume en la fase 4.
  Si esa fase lo implementa con una comprobación optimista, solo el test de
  concurrencia lo detecta — de ahí que sea criterio de éxito allí y no una
  recomendación.
- Riesgo: el endpoint público de presupuesto revela si un código existe si se
  descuida el mensaje. Por eso el mensaje único es criterio de éxito y por eso
  lleva Turnstile además del `limit_per_ip`.
- Rollback: ambos catálogos son aditivos y solo visibles en eventos `paid`,
  que no se pueden vender todavía (fase 4). Retirar pantallas y endpoints no
  afecta a ningún evento existente.
