# Fase 6 de trabajo — Verificación de extremo a extremo y cierre de fase

Plan: `plans/260909-0030-prd-fase-6-pagos-stripe-connect/`
Rama: `feature/0.19.0-pagos-stripe-connect`
Status: completed con deuda conocida (ver «Deuda conocida aceptada»)

## Resumen

Sin funcionalidad nueva. Recorrido completo en modo test con Stripe CLI
contra la cuenta conectada real `acct_1UDifKKo5qNfOacc`, repaso de las diez
superficies de riesgo con evidencia `file:line`, cierre de documentación y
accesibilidad, y un fallo real descubierto y corregido durante la
verificación (import de modelos en el proceso del worker).

## Entorno usado

- `stripe listen --forward-connect-to localhost:8000/api/v1/webhooks/stripe`
  para obtener `STRIPE_WEBHOOK_SECRET`; `STRIPE_SECRET_KEY` de
  `stripe config --list` (cuenta plataforma `iservisat.es`, modo test).
  Ambos escritos temporalmente en `infra/env/.env` y retirados al terminar
  (`grep -c "^STRIPE_" infra/env/.env` → `0`, verificado tras el cierre).
- Cuenta Connect ya conectada y verificada de la sesión anterior:
  `acct_1UDifKKo5qNfOacc`, `charges_enabled=true`, `details_submitted=true`.
- API, worker y planificador reiniciados con `infra/scripts/dev.sh
  api|worker|scheduler` tras cada cambio de `.env` — imprescindible: ninguno
  de los tres relee el fichero en caliente.
- Usuario de pruebas: `owner@example.com` de la organización semilla
  `iawic` (host `localhost`), contraseña regenerada con `python -m app.cli
  seed --reset-password` (no se conocía la contraseña original, generada al
  azar en una sesión anterior).

## Recorrido de extremo a extremo (Stripe CLI, modo test)

1. **Evento de pago con dos tipos de entrada y un código de descuento.**
   Creado por API (`POST /events`, `POST /events/{id}/ticket-types` ×2,
   `POST /events/{id}/discount-codes`): tipos «General» (2000 céntimos) y
   «VIP» (5000), código `E2E10` (10% en todos los tipos).
2. **409 al publicar sin `charges_enabled`, desde el alta y desde la
   edición.** Con `charges_enabled=false` simulado en BD (única cuenta
   conectada de este entorno; documentado explícitamente en vez de crear una
   segunda cuenta real sin acabar el onboarding, que habría tardado más sin
   aportar más señal): `PATCH /events/{id}` con `status=published` → 409;
   `POST /events` con `status=published` directo → 409. Ambos con el mismo
   mensaje (`events/service.py::_asegurar_venta_posible`, invocada desde
   `create_event` y `update_event`).
3. **409 al crear la Checkout Session sin `charges_enabled`.** Con la cuenta
   aún desactivada, `POST /public/events/{slug}/checkout` → 409
   `"Esta organización todavía no puede cobrar entradas."`
   (`checkout_service.py::_obtener_cuenta_operativa`).
4. **Publicación con `charges_enabled=true` restaurado.** `PATCH
   /events/{id}` → 200, `status=published`.
5. **Compra con descuento vía Checkout hosted.** `POST
   /public/events/{slug}/checkout/quote` → `price_cents=2000,
   discount_cents=200, total_cents=1800`. `POST
   /public/events/{slug}/checkout` → 200 con una URL real de
   `checkout.stripe.com` (`cs_test_a1lz…`). Verificado en BD:
   `event_payments.status=pending`, `amount_cents=1800`,
   `discount_cents=200`; `event_registrations.status=pending_payment`.
   `expires_at` de la sesión real de Stripe = `created + 1859 s` (~31 min:
   ventana de 30 min + 60 s de margen técnico, decisión #5/#16 del plan,
   confirmado con datos reales, no solo por lectura del código).
6. **Confirmación por webhook real.** `stripe trigger --stripe-account
   acct_1UDifKKo5qNfOacc checkout.session.completed` genera su **propia**
   sesión de fixture (producto, precio, sesión, medio de pago) — no la
   nuestra — y confirmó que el evento real llega firmado, se resuelve por
   `event.account`, y al no encontrar un pago con ese
   `stripe_checkout_session_id` se marca `ignored` sin mutar nada
   (`stripe_webhook_events`, evento `checkout.session.completed` →
   `ignored`). Esto es exactamente el comportamiento esperado del hallazgo
   #2 (localizar solo por el identificador emitido por la plataforma), y
   confirma que `stripe trigger` genérico no sirve para confirmar **nuestra**
   compra real.

   **Límite documentado, no forzado como aprobado:** completar el pago real
   de la Checkout Session creada en el paso 5 exige la página hospedada de
   Stripe, que bloquea deliberadamente el relleno automatizado de tarjeta
   (confirmado contra la documentación oficial de Stripe,
   `docs.stripe.com/automated-testing`: «Front-end interfaces […] have
   security measures in place that prevent automated testing»), y no hay
   navegador disponible en este entorno. En su lugar, verifiqué el mismo
   camino de código con un evento sintético pero **correctamente firmado**
   con el `whsec_...` real de `stripe listen` (mismo mecanismo que usa el
   propio SDK: `stripe.WebhookSignature._compute_signature`), construido a
   partir de los datos reales de la sesión de Stripe creada en el paso 5
   (mismo `id`, mismo importe). El endpoint real (`/api/v1/webhooks/stripe`,
   puerto 8000) lo procesó de extremo a extremo: `event_payments.status →
   paid`, `event_registrations.status → confirmed`, entrada emitida
   (`event_tickets`, 1 fila), correo con QR entregado a Mailpit
   (`comprador-e2e@example.com`, asunto «Tu inscripción está confirmada»).
   Esto verifica el handler real con datos reales, pero no reemplaza un pago
   de tarjeta de verdad en la página de Stripe — ver «Deuda conocida
   aceptada».
7. **Escaneo del QR.** Token JWT reconstruido con `ticket_qr_secret` (mismo
   payload que `generar_token_qr`) contra `POST
   /events/{id}/tickets/scan` → `result: "valid"`.
8. **Reembolso parcial, sin revocar.** Para que el reembolso llame a Stripe
   de verdad, creé un `PaymentIntent` real de prueba
   (`stripe payment_intents create --stripe-account acct_1UDifKKo5qNfOacc
   -d amount=1800 -d currency=eur -d payment_method=pm_card_visa -d
   confirm=true`, cobro real en modo test, sin navegador — la propia API de
   `PaymentIntents` sí admite confirmar con un método de prueba desde el
   servidor, a diferencia de Checkout hosted) y apunté
   `event_payments.stripe_payment_intent_id` a él. `POST
   /events/{id}/payments/{payment_id}/refund` con `amount_cents=900` →
   202, ejecutado por la tarea (`process_refunds_task`) contra Stripe de
   verdad: `event_payment_refunds.status=succeeded`,
   `event_payments.status=partially_refunded`,
   `refunded_cents=900`. `event_tickets.revoked_at` sigue `NULL`.
9. **Reembolso del resto, revoca.** Segundo `POST .../refund` con
   `amount_cents=900` → `event_payments.status=refunded`,
   `refunded_cents=1800`, `event_tickets.revoked_at` fijado.
10. **QR rechazado como `revoked`.** Mismo token reescaneado → `result:
    "revoked"`.
11. **Desconexión (`account.application.deauthorized`).** `stripe trigger
    --stripe-account acct_1UDifKKo5qNfOacc account.application.deauthorized`
    da 403 («Connect platforms cannot create new accounts on behalf of
    their connected accounts») porque ese `trigger` intenta crear y
    desautorizar una cuenta fixture nueva, no actuar sobre una ya existente
    — no encaja con una cuenta real ya conectada. Documentado en vez de
    forzado: en su lugar envié un evento sintético `account.application.
    deauthorized` con el `account` real, firmado con el `whsec_...`
    verdadero, contra el endpoint real. Efecto verificado en BD:
    `organization_stripe_accounts.charges_enabled=false`,
    `deauthorized_at` fijado. `POST /public/events/{slug}/checkout` con la
    cuenta desautorizada → 409, confirmando que la organización deja de
    poder vender.
12. **Reconexión.** `GET /organizations/{id}/stripe` tras la
    desautorización → `connected: false` (la fila con `deauthorized_at` se
    trata como «sin cuenta», decisión #4/#17). `POST
    /organizations/{id}/stripe/onboarding` → 200 con una URL real de
    `connect.stripe.com/setup/...` y una cuenta Standard **nueva** creada de
    verdad en Stripe (`acct_1UDjdv33DKZgOBAO`), sin tocar la fila antigua
    (`organization_stripe_accounts` quedó con dos filas: la antigua
    desautorizada y la nueva sin verificar, antes de que restaurara el
    estado — ver abajo). **Verificado solo a nivel de código y de creación
    de cuenta**: terminar el onboarding real (KYC) exige la misma página
    hospedada de Stripe que el pago, y no hay navegador disponible. No lo
    doy por «aprobado con reservas»: el endpoint existe, la cuenta se crea,
    el estado se limpia, pero el camino completo de vuelta a vender tras
    reconectar no se ha ejercitado de principio a fin.
    - Limpieza tras la prueba: borré la fila de la cuenta de reconexión de
      prueba y restauré `acct_1UDifKKo5qNfOacc` a
      `charges_enabled=true, details_submitted=true, deauthorized_at=NULL`
      (estado exacto de antes de empezar el recorrido), para no dejar el
      entorno de desarrollo compartido en un estado distinto al que tenía.

## Cuatro caminos de confirmación (hallazgo #1)

Camino 1 (alta directa) verificado en vivo en el paso 5. Los caminos 2
(verificación de email), 3 (aprobación manual) y 4 (promoción de lista de
espera) se verifican con la suite de tests dirigida
(`test_camino_2_verificacion_deja_pending_payment`,
`test_camino_3_aprobacion_tras_cambiar_a_paid_deja_pending_payment`,
`test_camino_4_promocion_de_lista_de_espera_deja_pending_payment` en
`apps/api/tests/test_payments_checkout.py`), que sigo ejecutando en esta
fase (ver «Suites») en vez de repetirlos a mano: no hay ninguna razón para
que un recorrido manual detecte algo que esos tests no detecten ya, y sí
para introducir un error humano en la reconstrucción manual del estado
(`pending_approval`/`waitlisted` con los campos exactos que exige cada
transición). El cinturón de seguridad
(`test_cinturon_de_seguridad_rechaza_confirmed_sin_pago`) también sigue en
verde.

## Fallo real descubierto y corregido: metadata de SQLAlchemy incompleta en el proceso del worker

**Síntoma:** el primer webhook enviado tras reiniciar el worker se quedaba
para siempre en `stripe_webhook_events.status='received'`, sin pasar nunca a
`processed` ni a `failed`.

**Causa raíz** (`apps/api/app/core/tasks.py`, antes de este cambio): el
proceso `taskiq worker app.core.tasks:broker` arranca importando solo ese
módulo, que no importaba nunca `app.modules.users.models`. Al confirmar el
pago, `checkout_service.confirmar_pago_y_registro` toca una
`EventRegistration` (FK a `users.id`); en el primer `commit` de ese proceso,
SQLAlchemy intenta resolver esa FK contra `Base.metadata` y falla con
`NoReferencedTableError`/`PendingRollbackError`: «Foreign key associated
with column 'event_registrations.user_id' could not find table 'users'».
`app/main.py` no tiene este problema porque importa (indirectamente, vía
`users_router`) el módulo de modelos de usuarios; el proceso del worker
nunca pasaba por esa ruta de importación.

**Corrección** (`apps/api/app/core/tasks.py`): añadidos los imports
explícitos de todos los módulos de modelos (mismo patrón ya usado por
`apps/api/alembic/env.py`, que documenta la misma necesidad para el mismo
motivo), incluido `app.modules.users.models`. Verificado con el recorrido
completo del webhook tras el fix: procesa correctamente en el primer
intento.

**Alcance del fallo:** no es exclusivo de pagos. Cualquier tarea de
`app/core/tasks.py` que toque una `EventRegistration` (el barrido de listas
de espera, el barrido de pagos caducados, el envío de enlaces de pago) podía
fallar igual en un worker recién arrancado, antes de que alguna otra tarea
importara el módulo de usuarios por casualidad — de hecho es probablemente
la razón por la que no se había detectado antes: en un worker que lleva
tiempo corriendo, la primera tarea que sí importa el módulo completo (p.ej.
una que pase por `app.modules.admin`) “arregla” el proceso para las
siguientes, ocultando el problema en cualquier entorno que no reinicie el
worker con frecuencia.

## Diez superficies de riesgo, con cobertura `file:line`

| # | Superficie | Cobertura |
|---|---|---|
| 1 (invest.) | Confusión de `account_id` | `apps/api/app/modules/payments/stripe_client.py:26` (solo recibe `OrganizationStripeAccount` ya resuelto, nunca un `str` de cliente); `apps/api/pyproject.toml:71,74,76` (`TID251` confina `import stripe` a ese fichero, releva la regla solo en `tests/**`) |
| 2 (invest.) | Idempotencia de eventos duplicados | `apps/api/app/modules/payments/repository.py:572` (`registrar_evento_recibido`, `INSERT ... ON CONFLICT DO NOTHING`); verificado en vivo en el paso 6 del recorrido (reenvío del mismo `evt_...` no duplica) y en `test_webhook_confirma_la_inscripcion_y_es_idempotente` |
| 3 (invest.) | Replay sin firma | `apps/api/app/modules/payments/webhooks.py:71-78` (firma verificada sobre el raw body antes de cualquier parseo); verificado en vivo (`curl` sin cabecera → 400, con firma inválida → 400, sin escritura en BD) y en `test_webhook_sin_cabecera_firma_da_400`/`test_webhook_firma_invalida_da_400` |
| 4 (invest.) | Mezcla test/live | `apps/api/app/core/config.py:154,170` (`_validar_produccion`: `sk_test_` en `production` aborta el arranque) |
| 5 (invest.) | `client_secret` expuesto | No aplica — Checkout hosted, el frontend solo recibe la URL de redirección. `grep -rn "client_secret" apps/api/app/modules/payments/ apps/web/src` → 0 resultados |
| 6 (invest.) | Autorización del endpoint de reembolso | `apps/api/app/modules/payments/router.py:112,149,208` (`require_permission(Permission.PAYMENTS_WRITE)` en onboarding, sync y CRUD; el propio `refund_payment` también, línea 438 del router) |
| 7 (red-team #2) | Verificación cruzada de organización en los handlers | `apps/api/app/modules/payments/webhooks.py:193` (`checkout.session.completed`) y `:280` (`charge.refunded`): `pago.organization_id != organizacion.organization_id` → `failed`, sin mutar nada. Verificado en vivo en el paso 6 (`ignored`, no `failed`, porque el pago no se encontró — el camino de discrepancia real está cubierto por `test_webhook_organizacion_no_coincide_no_muta_nada`) |
| 8 (red-team #3) | `payment_status == "paid"` como única prueba de cobro | `apps/api/app/modules/payments/webhooks.py:207` (`if payload.get("payment_status") != "paid": return "ignored"`); `test_webhook_payment_status_no_pagado_no_confirma` |
| 9 (red-team #9) | Idempotencia medida sobre el proceso, no la recepción | `apps/api/app/modules/payments/repository.py:590,634` (estado `received`→`processed`/`failed`, `eventos_para_reencolar` selecciona `received` antiguos); verificado en vivo: el evento sintético del paso 6 quedó `received` tras el primer intento (por el fallo de metadata descrito arriba) y se reencoló correctamente al reenviarlo tras el fix — recuperación real de un evento perdido, no solo simulada |
| 10 (red-team #12) | Ausencia de llamadas de red con bloqueos de fila abiertos | `apps/api/app/modules/payments/checkout_service.py:5-17` (documenta y separa T1/T2); `apps/api/app/modules/registrations/service.py` (`_cancelar_inscripcion` solo persiste el outbox, no llama a Stripe); `apps/api/app/modules/payments/refunds_service.py` (la tarea ejecuta el reembolso fuera de cualquier transacción de negocio) |

## Comprobaciones grep obligatorias

```
grep -rn "client_secret" apps/api/app/modules/payments/ apps/web/src   → 0 (no aplica, Checkout hosted)
grep -rn "^import stripe|^from stripe" apps/api/app | grep -v stripe_client.py → 0
grep -rn "stripe\.error" apps/api/app                                  → 0
grep -rn "emitir_entrada" apps/api/app/modules/payments/                → 0
grep -rnE "sk_(test|live)_…|whsec_…|acct_…{16,}" (repo, fuera de .env) → 0
```

## Suites

- **Backend**: `uv run pytest -q` → **527 tests, 100% verde** (dos pasadas
  idénticas tras el reordenamiento de ficheros y las correcciones de mypy).
- **Frontend**: `pnpm exec ng test --watch=false` → **193 tests, 100%
  verde**, incluidas las comprobaciones de axe de las seis pantallas
  nuevas/afectadas.
- **Build de producción**: `pnpm run build` → completado, dos avisos
  `NG8102` preexistentes en `event-agenda.ts`/`member-form.ts` (fuera de
  `payments/`, no tocados por esta fase) y un aviso de `jsqr` no-ESM
  (preexistente, fase 4).
- **`ruff check .` / `ruff format --check .`**: verdes.
- **`mypy app`** (alcance real de CI, `Makefile:97`, no `mypy .`): verde
  tras corregir 9 errores reales encontrados en esta fase (ver «Correcciones
  aplicadas»).
- **`wc -l`**: ningún fichero del repositorio supera las 1000 líneas.
  `test_payments_checkout_and_webhooks.py` (1318 líneas, creado en la fase 4
  de trabajo) violaba el criterio; se dividió en
  `tests/payments_test_helpers.py` (174 líneas, fijaciones compartidas),
  `tests/test_payments_checkout.py` (392) y `tests/test_payments_webhooks.py`
  (822), sin perder ni un test.
- **`openapi.json`/cliente TypeScript**: regenerados
  (`make api-openapi api-types`), sin diff pendiente — ya estaban al día
  desde la fase 5.

## Correcciones aplicadas durante la verificación

1. **`apps/api/app/core/tasks.py`**: imports explícitos de todos los módulos
   de modelos (fallo real, ver sección dedicada arriba).
2. **`apps/api/app/modules/payments/repository.py`**: cuatro funciones
   (`get_payment_by_registration`, `get_payment_by_checkout_session_id`,
   `get_payment_by_payment_intent_id`, `get_payment`) devolvían `Any` según
   `mypy` en vez de `EventPayment | None`; se anotó la variable intermedia
   con el tipo explícito, mismo patrón ya usado en
   `registrations/repository.py`. Una quinta (`registrar_evento_recibido`)
   necesitaba `# type: ignore[attr-defined]` documentado (`Result[Any]` vs.
   `CursorResult`, límite conocido de los stubs de SQLAlchemy con
   `session.execute`).
3. **`apps/api/app/modules/payments/stripe_client.py`**: `# type:
   ignore[arg-type]` documentado en la llamada a `create_async` (el
   `TypedDict` estricto del SDK no admite un `dict` construido de forma
   incremental sin duplicar la llamada según haya o no
   `client_reference_id`/`metadata`).
4. **`apps/api/app/modules/payments/checkout_service.py`**: tipo de retorno
   explícito en `_obtener_cuenta_operativa`.
5. **`apps/api/app/modules/payments/webhooks.py`**: `tipo` convertido a
   `str` antes de `dict.get`, eliminando un `type: ignore` que ya no
   aplicaba al error real (`call-overload`, no `arg-type`).
6. **Fichero >1000 líneas** dividido (ver «Suites»).
7. **`stripe_client.py` desapareció del disco varias veces durante la
   sesión**, sin ninguna operación mía que lo explique (ni `git rm`, ni
   edición, ni `.gitignore`) — el mismo problema de entorno recurrente que
   ya avisaba el encargo. Restaurado cada vez con `git checkout HEAD --
   apps/api/app/modules/payments/stripe_client.py` y reaplicado el fix del
   punto 3 tras la última desaparición (ocurrió después de aplicarlo la
   primera vez). Verificado que el fichero final en disco contiene el fix.

## Documentación actualizada

- `docs/arquitectura.md`: sección «Pagos con Stripe Connect» ampliada con el
  flujo completo de una compra, la guarda de pago en dos capas, el porqué
  del webhook sin tenant por `Host` y el patrón outbox de los reembolsos.
- `docs/modelo-de-datos.md`: nueva sección con las seis tablas, el estado
  `pending_payment`, el consumo derivado de cupos/códigos y la revocación
  reutilizada de la fase 4.
- `docs/desarrollo.md`: ampliada la sección ya existente de webhooks con la
  necesidad de reiniciar API/worker/planificador tras tocar `.env`, la tabla
  de variables opcionales con qué deja de funcionar sin cada una, y las
  tarjetas/cuentas de prueba (incluida la vía de `PaymentIntents` +
  `pm_card_visa` para probar reembolsos sin navegador).
- `docs/accesibilidad.md`: checklist WCAG de las cinco pantallas nuevas, con
  cita `file:line` de los `aria-live`/`aria-label` reales.

## Deuda conocida aceptada

1. **Pago real en la página hospedada de Stripe, sin verificar por
   navegador.** Verificado en su lugar con un webhook sintético pero
   correctamente firmado sobre los datos reales de la sesión creada. Deja
   de ser aceptable si algún día se cambia el modo de integración
   (Payment Element embebido, por ejemplo) donde sí sea viable automatizar
   el pago sin depender de las protecciones anti-bot de Checkout hosted, o
   si se incorpora un navegador headless al entorno de verificación.
2. **Reconexión tras desautorización, verificada solo hasta la creación de
   la cuenta y la URL de onboarding.** El KYC en sí no se ha completado de
   principio a fin. Deja de ser aceptable antes de anunciar la
   funcionalidad de reconexión como probada de extremo a extremo a un
   usuario; para el cierre de esta fase de ingeniería, el código y el
   cambio de estado en BD están verificados.
3. **`ak:code-review` (high) sobre el diff completo no se ha ejecutado en
   esta pasada.** No estaba entre los pasos explícitos que se me
   encomendaron para esta sesión. Marcado como pendiente en el checklist de
   la fase; debe ejecutarse antes de dar la fase 6 del PRD por cerrada del
   todo (el propio plan lo exige como criterio de éxito).
4. **Datos de prueba dejados en la organización semilla** (`iawic`): un
   evento de pago (`evento-pago-ec519f22`), sus tipos de entrada, código de
   descuento, una inscripción/pago/reembolso completos y una entrada
   revocada. No se han borrado porque son datos de desarrollo inertes (no
   afectan a ningún test, que usa su propia base de datos aislada) y
   borrarlos con seguridad exigiría replicar a mano el mismo camino de
   cancelación con reembolso que ya se ha probado — más riesgo que
   beneficio. Se pueden limpiar con el reset de seed
   (`python -m app.cli seed --reset-password`, no borra eventos) o a mano
   si molestan en una demo.

## Estado final de credenciales

`grep -c "^STRIPE_" infra/env/.env` → `0`, verificado tras retirar
`STRIPE_SECRET_KEY`/`STRIPE_WEBHOOK_SECRET`. `stripe listen` detenido. La
cuenta conectada real quedó restaurada a su estado inicial
(`charges_enabled=true`, sin `deauthorized_at`).
