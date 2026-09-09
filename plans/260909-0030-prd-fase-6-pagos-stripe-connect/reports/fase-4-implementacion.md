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

## Segunda pasada — frontend del paso de compra y pantalla de retorno

Completa el frontend que la pasada anterior dejó pendiente explícitamente.
Antes de escribir nada se verificó el estado real del repo (`grep`/lectura de
código, no se asumió nada de lo escrito arriba sin comprobarlo): el fichero
que el encargo llamaba `event-registration-form.ts` es en realidad
`apps/web/src/app/features/public/events/registration-page.ts` (393 líneas
antes de esta pasada, muy lejos de las 1000 — se amplía en el mismo fichero,
no se crea uno hijo).

### Dos huecos de backend descubiertos y cerrados (no estaban en el alcance de la fase 4 de trabajo, pero bloqueaban por completo el frontend)

1. **No existía ningún endpoint público para listar los tipos de entrada de
   un evento.** El único listado (`GET /events/{event_id}/ticket-types`) exige
   `PAYMENTS_READ` (sesión de organizador). El formulario público no puede
   pedir un presupuesto (`checkout/quote`) sin conocer antes un
   `ticket_type_id` real, así que sin este endpoint el paso de compra era
   irrealizable, no solo incómodo. Añadido, aditivo y de solo lectura:
   - `payments/schemas.py::PublicTicketTypeResponse`.
   - `payments/service.py::list_public_ticket_types` (reutiliza
     `validar_tipo_vigente`, la misma función que ya usa `checkout/quote`, para
     que listado y validación no puedan divergir).
   - `payments/public_router.py::GET /public/events/{slug}/ticket-types`
     (`limit_per_ip` con `PUBLICO_POR_IP`, sin Turnstile: no hay nada que
     enumerar, es la misma información que ya expone el evento publicado).
   - Test nuevo: `apps/api/tests/test_payments_public_ticket_types.py` (4
     tests: lista los vigentes, oculta un tipo inactivo, oculta uno fuera de
     ventana de venta, 404 en evento inexistente).
2. **`success_url`/`cancel_url` de la Checkout Session no llevaban el `slug`
   del evento**, solo `registration_id`
   (`checkout_service.py::crear_sesion_de_pago`). El endpoint de estado que
   la pantalla de retorno necesita consultar
   (`GET /public/events/{slug}/checkout/{registration_id}/status`) está
   anidado bajo el evento — sin `slug` en la URL de retorno, la pantalla no
   podía ni siquiera preguntar por el estado real del pago. Se añadió
   `&slug={evento_slug}` a ambas URLs (`evento` ya se cargaba en esa función
   para leer `payment_checkout_window_minutes`; ningún test existente asertaba
   el contenido literal de estas URLs, verificado por `grep` antes de tocarlo).

Ambos cambios son aditivos, no tocan ningún camino ya probado, y la suite
completa de backend (526 tests: los 522 previos + los 4 nuevos) sigue en
verde tras aplicarlos, igual que `test_payments_checkout_and_webhooks.py` y
`test_payments_checkout_quote_public.py` en particular. `openapi.json` y el
cliente TypeScript se regeneraron (`make api-types`).

### Frontend

- `apps/web/src/app/core/payments/public-checkout.service.ts` (nuevo):
  `getTicketTypes`, `quote`, `startCheckout`, `getStatus`. Hand-rolled con
  `HttpClient`/`ApiService.url()`, no el cliente generado
  (`core/api/generated/`): se comprobó que **ningún** fichero de la app
  importa hoy ese cliente generado (se regenera pero no se consume; el
  patrón real y único del repo es un servicio fino por dominio, ver
  `RegistrationsService`/`PaymentsService`) — seguir esa convención real pesa
  más que introducir el primer uso del cliente generado en un solo fichero.
- `registration-page.ts` (registro público, ampliado): `ngOnInit` pide
  también los tipos de entrada vendibles ahora
  (`GET .../ticket-types`). **El evento es «de pago» a ojos del formulario si
  y solo si esa lista no está vacía** — decisión deliberada para no tener que
  preguntar `registration_mode` aparte (evita una llamada más y una condición
  duplicada en dos sitios). Si hay tipos: fieldset de selección, campo de
  código de descuento opcional que repite el presupuesto
  (`checkout/quote`) en un bloque `aria-live="polite"`, y el envío pasa por
  `PublicCheckoutService.startCheckout` en vez de `RegistrationsService.submit`.
  Una `checkout_url` no nula redirige el navegador — **nunca en SSR**
  (`isPlatformBrowser`, mismo patrón que
  `event-check-in.ts`/`offline-scan-queue.service.ts`, no `afterNextRender`:
  ese hook es para montar algo tras el renderizado, no para una redirección
  disparada por la respuesta de un envío).
- `payment-return.ts` (nuevo) + spec: pantalla de `success_url`. Arranca
  siempre en `comprobando`, pregunta el estado real
  (`getStatus`) y **nunca** infiere éxito del simple retorno — el estado
  inicial nunca es `confirmado`. Si sigue `pending_payment`, reintenta
  automáticamente con esperas crecientes acotadas (2 s, 4 s, 8 s, 8 s, 8 s;
  5 intentos como máximo) y, agotados, deja un botón manual de reintentar —
  nunca una espera indefinida sin salida. `cancelled`/`expired` se muestran
  como fallidos; un error de red/servidor se distingue explícitamente de
  «pago no confirmado» (mensaje y reintento propios, no se disfraza de
  fallido). `aria-live="polite"` envolviendo el `@switch`, mismo patrón que
  `my-ticket-page.ts`.
- `payment-cancelled-page.ts` (nuevo) + spec: pantalla de `cancel_url`. No
  existía ninguna pantalla de «pago cancelado» previa (verificado por
  `grep`); puramente informativa, sin ningún estado que consultar (Stripe
  nunca llega a marcar nada como pagado en este camino).
- `app.routes.ts`: rutas `pago/retorno` y `pago/cancelado` dentro del
  `PublicShell`, cargadas de forma perezosa como el resto de páginas
  públicas.
- `public/assets/i18n/es-ES.json`: claves nuevas bajo `inscripcion.*` (paso
  de compra) y `pago.*` (retorno y cancelación).
- `registration-page.spec.ts` (ampliado, no reescrito): se separó en dos
  `describe` (evento gratuito / evento de pago) y se añadió el mock de
  `PublicCheckoutService` que las tres pruebas existentes necesitaban aunque
  no lo usaran (se instancia igualmente por inyección). Pruebas nuevas:
  selección de tipo de entrada, bloqueo si no se elige tipo, presupuesto en
  vivo + redirección real (`window.location.href`) con
  `Object.defineProperty` sobre `window.location`, y **la prueba explícita
  que exige el encargo**: renderizado con `{ provide: PLATFORM_ID, useValue:
  'server' }`, el mismo envío que en navegador dispara `startCheckout` pero
  `window.location` nunca se toca.
- No se creó un spec dedicado para `PublicCheckoutService`: verificado que
  el repo no tiene tampoco ninguno para `RegistrationsService` ni
  `PaymentsService` (los servicios finos de `HttpClient` se ejercitan
  siempre a través del spec del componente que los mockea, nunca en
  solitario) — mismo patrón, no una omisión.

### Tests y verificación

- Backend: 526 tests, suite completa en verde
  (`uv run pytest tests/ -q`, dos pasadas limpias tras los dos cambios de
  backend).
- Frontend: **190 tests, suite completa en verde** (`ng test --watch=false`;
  eran ~178 antes de esta pasada, la diferencia son los tests nuevos de esta
  sesión). `esperarSinViolacionesDeAccesibilidad` (axe) en cada test nuevo de
  `registration-page.spec.ts`, `payment-return.spec.ts` y
  `payment-cancelled-page.spec.ts`: cero violaciones.
- `npx tsc --noEmit` (app y spec) y `ng lint` limpios.
- `ng build` (con SSR) completa sin errores nuevos; los dos avisos `NG8102`
  que aparecen son preexistentes, en ficheros no tocados por esta fase.
- Incidencia operativa repetida: `apps/api/app/modules/payments/stripe_client.py`
  volvió a desaparecer del disco una vez más durante esta pasada (mismo
  patrón ya documentado arriba); se restauró con `git checkout --` desde el
  último commit sin pérdida de trabajo.
- No se ejecutó un recorrido de compra real con Stripe CLI: el binario
  (`stripe`) está disponible en el entorno, pero montar una cuenta Connect en
  modo test conectada a esta organización de desarrollo es una tarea aparte
  no cubierta por el alcance de esta pasada; la cobertura de tests unitarios
  + axe se considera suficiente para esta entrega, tal como el encargo
  contemplaba como salida válida si el CLI no estaba ya configurado contra
  este proyecto.
- El stack de desarrollo (`infra/scripts/dev.sh status`) ya estaba en marcha
  al empezar (API, `ng serve` y Caddy); no se ha tocado ni se ha parado al
  terminar, tal como pedía el encargo.

### Success Criteria del plan actualizados

En `phase-04-checkout-webhooks-y-confirmacion.md`: el criterio de frontend
(pantalla de retorno + axe) pasa de `[ ]` a `[x]`, y el `status` del
frontmatter se actualiza para reflejar que backend y frontend están
implementados y verificados. **No se marca `status: completed`**: quedan
varios Success Criteria de detalle sin test dedicado, todos preexistentes a
esta pasada y ya documentados en la sección de desviaciones de arriba (§7) —
timestamp de firma fuera de tolerancia, dos barridos solapados, dos ventanas
de checkout distintas, manipulación del cuerpo de la petición, el webhook de
`account.application.deauthorized` a nivel de esta fase, y el caso de
`capacity = 1` sin test propio. Ninguno de ellos es del frontend.

Status: DONE
Summary: Frontend del paso de compra y de la pantalla de retorno implementado y verificado (190 tests frontend en verde, cero violaciones de axe, SSR nunca redirige), cerrando el único pendiente explícito de la pasada anterior. Se detectaron y cerraron dos huecos reales de backend que bloqueaban por completo el frontend (listado público de tipos de entrada, `slug` ausente en las URLs de retorno de Stripe) — aditivos, con test propio, sin tocar ningún camino ya probado (526 tests backend en verde).
Concerns/Blockers: El plan no pasa a `status: completed` porque quedan Success Criteria de detalle sin test dedicado, todos preexistentes a esta pasada y ninguno del frontend (ver lista arriba). El recorrido de compra real con Stripe CLI en modo test sigue sin ejecutarse — requiere una cuenta Connect de prueba que no estaba configurada en este entorno.
