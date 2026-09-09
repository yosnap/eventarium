# Fase 5 de trabajo — Reembolsos con outbox, política de plazo y revocación de entradas

Plan: `plans/260909-0030-prd-fase-6-pagos-stripe-connect/`
Rama: `feature/0.19.0-pagos-stripe-connect`
Status: completed

## Resumen

Reembolso automático al cancelar una inscripción de pago (panel, enlace
público de autocancelación y RGPD, los tres vía `_cancelar_inscripcion`) y
reembolso manual total/parcial desde el panel, ambos escribiendo la misma
fila de outbox (`event_payment_refunds`) y ejecutados por la misma tarea.
`charge.refunded` es la fuente de verdad de `refunded_cents` (se fija al
acumulado de Stripe, nunca se suma) y decide la revocación de la entrada
reutilizando `revocar_entrada` (fase 4, sin cambios).

## Ficheros

Creados:
- `apps/api/app/modules/payments/refunds_service.py` — política de
  reembolso automático, outbox (automático + manual), ejecución contra
  Stripe (`process_refunds_task`/`sweep_stuck_refunds_task`), listado de
  pagos del panel con motivo derivado de «sin reembolso automático».
- `apps/api/tests/test_payments_refunds.py` — 22 tests.
- `apps/web/src/app/features/admin/events/event-payments.ts` (+ `.spec.ts`)
  — pantalla `/admin/events/:eventId/payments`.

Ampliados:
- `apps/api/app/modules/payments/repository.py` — CRUD del outbox, búsqueda
  de pago por `payment_intent_id`, listado de pagos/reembolsos.
- `apps/api/app/modules/payments/schemas.py` — `PaymentListItem`,
  `PaymentRefundOut`, `RefundRequest`, `RefundAcceptedResponse`.
- `apps/api/app/modules/payments/router.py` — `GET
  /events/{event_id}/payments`, `POST
  /events/{event_id}/payments/{payment_id}/refund`.
- `apps/api/app/modules/payments/webhooks.py` — handler real de
  `charge.refunded` (antes `ignored`).
- `apps/api/app/modules/registrations/service.py` — paso de outbox en
  `_cancelar_inscripcion`, antes del cambio de estado.
- `apps/api/app/core/tasks.py` — `process_refunds_task` (cron `*/2 * * * *`)
  y `sweep_stuck_refunds_task` (cron `*/10 * * * *`); `send_registration_
  cancelled_email` gana el parámetro `reembolso`.
- `apps/api/app/main.py` — registro del router de pagos (necesario, no
  listado explícitamente en la fase pero imprescindible para exponer los
  endpoints).
- `apps/web/src/app/app.routes.ts`, `event-form.ts` (enlace a la pantalla),
  `public/assets/i18n/es-ES.json` (cadenas del panel).
- `apps/api/openapi.json` y `apps/web/src/app/core/api/generated/**`
  regenerados.

## Diseño aplicado (verificado contra el código real, no supuesto)

- **Outbox, nunca Stripe dentro de `_cancelar_inscripcion`.** Verificado que
  los dos llamadores reales (`cancel_registration` vía
  `get_registration_for_update`, `cancel_registration_by_token` vía
  `session.get(..., with_for_update=True)`) ya bloquean la fila antes de
  entrar. `preparar_reembolso_por_cancelacion` solo persiste una intención;
  `_ejecutar_reembolso` bloquea la fila del reembolso, marca `submitted` y
  hace commit (fin del `async with`) **antes** de llamar a Stripe.
- **Una sola implementación.** El automático y el manual llaman a
  `repository.crear_intencion_reembolso`; ambos los ejecuta
  `refunds_service._ejecutar_reembolso`, invocada por
  `process_refunds_task`/`sweep_stuck_refunds_task`. `grep` confirma una
  sola asignación `inscripcion.status = "cancelled"` y una sola llamada
  `refunds.create_async` en todo el módulo de pagos.
- **`idempotency_key = f"refund_{refund.id}"`**, derivada de la PK
  persistida antes de la llamada.
- **`acct_id` de la fila del pago**, nunca de la cuenta activa de la
  organización — probado con una cuenta desconectada y otra nueva
  conectada después.
- **Política de plazo** (evento no empezado, entrada no usada,
  `payment_refund_cutoff_hours`) como función pura
  (`evaluar_politica_reembolso_automatico`), reutilizada para decidir el
  outbox y para derivar el motivo mostrado en el panel — nunca una columna
  guardada (mismo criterio que `used_count`, hallazgo #19 de una fase
  anterior).
- **`refunded_cents` fijado, no sumado**, con verificación cruzada
  `organization_id` antes de mutar (mismo patrón que
  `checkout.session.completed`).
- **Revocación por total vs. casilla parcial**: `_handle_charge_refunded`
  revoca siempre que el acumulado alcance el total, o si algún reembolso
  `succeeded` de ese pago tiene `revoke_ticket = true` aunque el pago siga
  `partially_refunded` — así dos parciales sucesivos que suman el total
  revocan al completarse el segundo, y una casilla marcada revoca aunque el
  pago no llegue al 100%.

## Incidencias operativas

`apps/api/app/modules/payments/stripe_client.py` desapareció del disco al
menos 6 veces durante la sesión (inestabilidad de E/S del volumen externo,
avisada de antemano). Cada vez se restauró con `git checkout --
stripe_client.py` y se verificó `import app.main` antes de continuar. No
afectó al resultado final: el fichero nunca se editó en esta fase y su
contenido en el commit final es idéntico al de la fase 2.

## Tests

- Backend: `apps/api/tests/test_payments_refunds.py`, 22 tests, cubren
  outbox de cancelación (panel y enlace público), ausencia de llamadas a
  Stripe dentro de `_cancelar_inscripcion`, las tres condiciones de la
  política de plazo, fallo de escritura tras éxito en Stripe con reintento
  de la misma clave, concurrencia (dos ejecuciones simultáneas → un solo
  reembolso), 409 antes de llamar a Stripe, reembolso total revoca
  ignorando la casilla, parcial no revoca salvo casilla, aislamiento
  cross-tenant, `acct_id` de la fila del pago, y seis tests del webhook
  `charge.refunded` (total, reenvío sin duplicar, organización cruzada,
  dos parciales sucesivos, revocación por casilla en parcial).
  Suite completa de `apps/api`: **526 passed, 0 failed** (ejecución
  limpia, aislada, sin colisión con otro proceso de tests).
- Frontend: `event-payments.spec.ts`, 3 tests (listado sin violaciones de
  axe, apertura del diálogo con el importe pendiente preseleccionado,
  reembolso total revoca ignorando la casilla). Suite completa de
  `apps/web`: **193 passed, 0 failed** (190 previos + 3 nuevos).
- `ruff check`, `ng lint`: sin hallazgos en los ficheros de esta fase.
- `mypy`: sin regresiones (los 2 `no-any-return` nuevos en `repository.py`
  siguen el mismo patrón preexistente que ya tenían
  `get_payment_by_registration`/`get_payment_by_checkout_session_id`, no
  bloqueante en este proyecto).

## Success Criteria

Los 18 criterios del `.md` de la fase están marcados `[x]`, cada uno con el
test o la verificación por `grep`/código que lo respalda — ver el fichero
`phase-05-reembolsos-y-revocacion.md` actualizado.

## Desviaciones respecto al `.md` de la fase

- `main.py` se editó (no listado en «Ficheros existentes que amplía») para
  registrar el nuevo router de pagos — imprescindible para exponer los
  endpoints; ningún otro fichero fuera de la lista se tocó salvo
  integraciones de la misma naturaleza (`event-form.ts` para el enlace a
  la pantalla, `es-ES.json` para las cadenas).
- El «motivo de sin reembolso automático» no se persiste en ninguna
  columna nueva de `event_payments` (no había ninguna en el modelo de esta
  fase y añadirla exigía tocar `models.py`/una migración, fuera de la
  propiedad de fichero de esta fase): se deriva en cada lectura del panel
  con la misma función pura que decide el outbox, evitando un valor
  obsoleto si el organizador reembolsa a mano más tarde.
- «Encolado al vuelo» del reembolso automático se implementó dentro de
  `_cancelar_inscripcion` (llamando a `process_refunds_task.kiq()`), no en
  los routers de `registrations` (no están en la propiedad de fichero de
  esta fase) — mismo patrón que ya usa la función para los correos.

## Preguntas sin resolver

Ninguna nueva. Las preguntas abiertas del `plan.md` (recompra tras
reembolso, visibilidad de `payouts_enabled`/`details_submitted`) siguen sin
tocarse, fuera del alcance de esta fase.

Status: DONE
Summary: Outbox de reembolsos + política de plazo + webhook `charge.refunded` implementados y verificados; 526 tests backend y 193 frontend en verde; `openapi.json`/cliente TS al día; fase marcada `completed`.
