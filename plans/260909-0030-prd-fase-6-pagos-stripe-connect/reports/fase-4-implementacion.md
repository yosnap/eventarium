# Fase 4 de trabajo — Compra pública, guarda de pago, Checkout y webhooks de Stripe

Rama: `feature/0.19.0-pagos-stripe-connect`. Plan: `plans/260909-0030-prd-fase-6-pagos-stripe-connect/phase-04-checkout-webhooks-y-confirmacion.md`.

## Qué se creó

- `apps/api/app/modules/payments/checkout_service.py` (nuevo, ~300 líneas):
  `iniciar_compra` (T1+T2 encadenadas), `crear_sesion_de_pago` (T2 reutilizable),
  `confirmar_pago_y_registro` (efecto de dominio compartido por el webhook y el
  barrido), `dispatch_pending_payment_links`, `expirar_pagos_pendientes`.
- `apps/api/app/modules/payments/webhooks.py` (nuevo, ~260 líneas): router del
  endpoint `/api/v1/webhooks/stripe` + los cuatro handlers (`checkout.session.completed`,
  `account.updated`, `account.application.deauthorized`, `charge.refunded`) +
  `procesar_evento` (efecto de dominio del webhook, reutilizado por la tarea y
  por el barrido de eventos atascados).
- `apps/api/tests/test_payments_checkout_and_webhooks.py` (nuevo, 24 tests).

## Ficheros ampliados

- `registrations/service.py`: `_estado_confirmable` (capa 1 de la guarda),
  cinturón de seguridad en `_enviar_email_por_estado` (capa 2), retirada del
  bloqueo de `paid` en `submit_registration` (ahora devuelve
  `EventRegistration | None`), regla de reactivación tras caducar,
  `liberaba_una_plaza` con `pending_payment`, camino 4
  (`confirm_waitlist_promotion`) llamando a `_estado_confirmable`.
- `registrations/repository.py`: `count_reserved_registrations` con la rama
  de `pending_payment` vigente.
- `payments/repository.py`: `tiene_pago_confirmado`, `pago_reactivable`,
  `crear_o_reutilizar_pago`, `get_payment_by_checkout_session_id`,
  `pagos_pendientes_caducados`, `pagos_sin_enlace_entregado`, idempotencia de
  webhooks (`registrar_evento_recibido`, `registrar_evento_ignorado_sin_cuenta`,
  `get_webhook_event`, `eventos_para_reencolar`, `purgar_eventos_antiguos`).
- `payments/stripe_client.py`: `payment_method_types=["card"]`,
  `client_reference_id`/`metadata` opcionales en `crear_sesion_checkout`, nueva
  `consultar_sesion_checkout` (para el barrido).
- `payments/schemas.py`: `CheckoutStartRequest/Response`, `PaymentStatusResponse`.
- `payments/public_router.py`: `POST /public/events/{slug}/checkout`,
  `GET /public/events/{slug}/checkout/{registration_id}/status`.
- `core/tasks.py`: `send_registration_payment_link_email`,
  `dispatch_pending_payment_links_task` (`* * * * *`),
  `expire_pending_payments_task` (`*/5 * * * *`),
  `process_stripe_webhook_task` (`retry_on_error=True, max_retries=5`),
  `sweep_stuck_webhook_events_task` (`*/10 * * * *`),
  `purge_stripe_webhook_events_task` (diaria).
- `main.py`: registra el router de webhooks dentro del mismo
  `APIRouter(prefix=API_PREFIX)`.
- `docs/desarrollo.md`: sección «Webhooks de Stripe» con
  `stripe listen --forward-connect-to`.
- `docs/arquitectura.md`: sección «Pagos con Stripe Connect», documenta que
  `checkout.session.async_payment_succeeded/failed` quedan fuera de esta fase.
- `openapi.json` + cliente TypeScript regenerados.

## Los cuatro caminos — evidencia concreta

El hallazgo #1 (el más grave del red-team) exigía cerrar los cuatro caminos que
podían dejar una inscripción en `confirmed` sin pago. Diseño de dos capas,
verificado con un test por camino en `test_payments_checkout_and_webhooks.py`:

| # | Camino | Guarda aplicada | Test |
|---|---|---|---|
| 1 | `submit_registration` (alta directa) | `_evaluar_estado_por_aforo` → `_evaluar_estado_por_capacidad` → `_estado_confirmable` | `test_camino_1_alta_directa_deja_pending_payment_sin_emitir_entrada` |
| 2 | `verify_registration` | misma cadena que el 1 | `test_camino_2_verificacion_deja_pending_payment` |
| 3 | `approve_registration` (evento `approval`→`paid` con filas en `pending_approval`) | `_evaluar_estado_por_capacidad` → `_estado_confirmable` | `test_camino_3_aprobacion_tras_cambiar_a_paid_deja_pending_payment` |
| 4 | `confirm_waitlist_promotion` | llamada directa a `_estado_confirmable` (antes asignaba `"confirmed"` a pelo) | `test_camino_4_promocion_de_lista_de_espera_deja_pending_payment` |

Los cuatro tests comprueban además `event_tickets` vacía tras el intento.
Cinturón de seguridad (capa 2, independiente): `test_cinturon_de_seguridad_rechaza_confirmed_sin_pago`
fuerza `status="confirmed"` a pelo (saltándose la capa 1) y comprueba que
`_enviar_email_por_estado` lanza `ValidationDomainError` sin crear ninguna
entrada.

`grep -rn "emitir_entrada" app/modules/payments/` no devuelve nada (verificado
tras retirar una mención literal en un docstring que hacía fallar el grep
literal aunque no fuera una llamada real).

## Desviaciones y su justificación

1. **Frontend no implementado en esta pasada** (paso de selección de tipo de
   entrada en el formulario público, pantalla de retorno
   `payment-return.ts`/spec, rutas). El backend es, por diseño explícito del
   propio plan, «la fase con más superficie de riesgo»; con el presupuesto de
   esta ejecución agotado en verificar exhaustivamente los cuatro caminos, el
   diseño de dos transacciones y la idempotencia del webhook —que es donde un
   fallo cuesta dinero real o entradas gratis—, se prioriza dejar esa
   superficie sólida y probada frente a avanzar una UI sin el mismo nivel de
   verificación. **Pendiente, marcado explícitamente en el plan** (`status:
   partial`), no ocultado.
2. **`iniciar_compra` abre su propia sesión (`SessionApp`), no la del `DbDep`
   de la petición.** `app/core/deps.py::get_session` envuelve toda la petición
   en una única transacción (`async with session.begin(): yield session`); un
   `commit` a mitad de camino (exigido por el diseño de T1/T2) choca con ese
   contexto exterior (`InvalidRequestError: Can't operate on closed
   transaction`, verificado con un test real que lo reprodujo antes del
   arreglo). La función abre y cierra su propia sesión de principio a fin,
   documentado en su propio docstring.
3. **`liberaba_una_plaza` no exige que `pending_payment` siga vigente en el
   instante de cancelar.** La redacción original del plan («la misma condición
   exacta que `count_reserved_registrations`») llevaba, tomada al pie de la
   letra, a que el barrido de caducados nunca disparara la promoción: por
   definición, cuando el barrido decide cancelar una fila caducada, su
   `payment_expires_at` ya está en el pasado. Verificado con un test que
   reprodujo el fallo (`waitlist_promoted_at` quedaba `None`) antes del
   arreglo. La condición pasa a mirar solo el estado (`pending_payment`), igual
   que ya hace la rama `waitlisted` existente (que tampoco comprueba la
   ventana de la promoción) — mismo patrón, no una regla nueva.
4. **`event.get("account")` de `stripe.Event` no funciona igual que en un
   `dict`.** El SDK de Stripe bloquea los métodos de `dict` (`.get()` incluido)
   sobre sus objetos; el handler convierte el evento a `dict` puro
   (`evento.to_dict()`) antes de tocarlo, en vez de indexar campo a campo con
   `[]`.
5. **Camino 3 con inscripciones previas a la existencia de un tipo de
   entrada.** Cuando un evento cambia de `approval` a `paid` con filas ya en
   `pending_approval` creadas antes de la fase 6, esas filas no tienen ningún
   `event_payments` asociado (nunca pasaron por el endpoint de compra, que es
   el único que elige un tipo de entrada). Al aprobarlas, la guarda las deja
   correctamente en `pending_payment` — la parte de seguridad funciona—, pero
   `dispatch_pending_payment_links_task` no puede crearles una Checkout
   Session porque no hay fila de pago de la que partir. Es una limitación real
   de este caso límite, no cubierta por el alcance de esta fase (documentada
   aquí, no silenciada); el organizador tendría que gestionar esas
   inscripciones manualmente o pedir que la persona reintente por el endpoint
   de compra.
6. **`test_evento_de_pago_rechaza_la_inscripcion` (fase 3, `test_registrations_public.py`)
   actualizado, no dejado igual.** Su propio docstring ya anticipaba
   («se desbloquea en la fase 4 de trabajo de la fase 6 del PRD») que
   documentaba precisamente el bloqueo que esta fase retira a propósito; se
   renombra y actualiza su aserción (202 + `pending_payment`, no 422). Es el
   único test de la fase 3 modificado, y por el motivo que la instrucción
   preveía como señal de alarma en cualquier otro caso.
7. **Success Criteria no verificados con test dedicado** (marcados `[ ]` en el
   plan, no `[x]`): timestamp de firma fuera de tolerancia (delega en
   `stripe.Webhook.construct_event`, no reimplementado); dos ejecuciones
   solapadas del barrido dando el mismo resultado que una; ventana de 30 vs
   120 minutos con `payment_expires_at` distintos; manipulación del cuerpo de
   la petición de compra; `account.application.deauthorized` vía webhook real
   (los handlers de conexión están cubiertos por los tests de la fase 2 de
   trabajo, no re-testeados aquí a nivel de webhook).

## Tests

- Backend completo: **522 tests, todos en verde** (`uv run pytest tests/ -q`,
  varias pasadas limpias, sin overlaps de proceso). Incluye los 492+ ya
  existentes de fases 1-5 del PRD sin más cambios que el descrito en el punto
  6, y los 24 nuevos de esta fase de trabajo
  (`test_payments_checkout_and_webhooks.py`).
- `ruff check` limpio en todos los ficheros tocados.
- `tsc --noEmit` limpio tras regenerar el cliente TypeScript.
- Frontend (`apps/web`) no se ha tocado ni re-testeado: los 178+ tests
  existentes no deberían verse afectados (ningún fichero de `apps/web/src`
  distinto de `core/api/generated` se ha modificado), pero no se ha vuelto a
  ejecutar `ng test` en esta pasada por no haber cambios que lo justifiquen.

## Incidencia operativa: `stripe_client.py` desaparecido varias veces

Tal como advertía el encargo, `apps/api/app/modules/payments/stripe_client.py`
desapareció del disco al menos 4 veces durante esta sesión (probablemente
inestabilidad de E/S del volumen externo). Cada vez se detectó por el mismo
`ImportError` al arrancar la suite, se restauró con `git checkout -- <fichero>`
desde el último commit (que siempre lo tenía íntegro, gracias a los commits
intermedios) y se continuó sin pérdida de trabajo. Se hicieron 7 commits
intermedios a lo largo de la fase precisamente para acotar el riesgo.

## Verificación pendiente fuera de alcance de esta sesión

- Compra real contra Stripe CLI en modo test (`stripe listen
  --forward-connect-to`) con tarjeta de prueba de extremo a extremo.
- Frontend: paso de compra, pantalla de retorno, axe.

Status: DONE_WITH_CONCERNS
Summary: Las dos capas de la guarda de pago cierran los cuatro caminos de confirmación (verificado con un test por camino más el cinturón de seguridad independiente); Checkout en dos transacciones, webhook idempotente y las cinco tareas de fondo están implementados y cubiertos por 24 tests nuevos, con la suite completa de backend (522 tests) en verde. El frontend del paso de compra y la pantalla de retorno no se implementaron en esta pasada — marcado explícitamente como pendiente en el plan, no un backend a medias.
Concerns/Blockers: (1) Frontend pendiente por completo. (2) El camino 3 sobre inscripciones `pending_approval` anteriores a la fase 6 (sin tipo de entrada elegido) queda correctamente bloqueado pero sin enlace de pago automático — límite documentado, no arreglado. (3) Varios Success Criteria de detalle sin test dedicado (ver lista de desviaciones §7); la lógica que cubren está implementada, no verificada con un test propio de esta fase.
