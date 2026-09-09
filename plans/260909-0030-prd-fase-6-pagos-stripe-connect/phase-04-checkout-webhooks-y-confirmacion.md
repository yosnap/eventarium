---
phase: 4
title: "Fase 4: Compra pública — guarda de pago, Checkout, webhooks y confirmación"
status: pending
priority: P1
effort: "4-4.5d"
dependencies: [3]
---

# Fase 4: Compra pública — guarda de pago, Checkout, webhooks y confirmación

## Overview

La fase con más superficie de riesgo del plan, y la que el red-team obligó a
rediseñar por completo.

**La premisa anterior era falsa.** El plan asumía que bastaba con sustituir el
bloqueo de `registration_mode == "paid"` en
`apps/api/app/modules/registrations/service.py:294-297` para que ninguna
entrada de un evento de pago se emitiera sin cobrar. Verificado contra el
código, hay **cuatro** caminos que dejan una inscripción en `confirmed` y
llaman a `_enviar_email_por_estado`, que es quien emite la entrada
(`service.py:199-203`):

| # | Camino | Dónde decide el estado | Dónde emite |
|---|--------|------------------------|-------------|
| 1 | `submit_registration` (alta directa) | `_evaluar_estado_por_aforo`, línea 337 | línea 384 |
| 2 | `verify_registration` (tras verificar email) | `_evaluar_estado_por_aforo`, línea 409 | línea 413 |
| 3 | `approve_registration` (aprobación manual) | `_evaluar_estado_por_capacidad`, línea 444 | línea 447 |
| 4 | `confirm_waitlist_promotion` (promoción de lista de espera) | **ninguno: asigna `"confirmed"` directamente**, línea 556 | línea 558 |

El camino 3 **no** pasa por `_evaluar_estado_por_aforo` (llama directamente a
`_evaluar_estado_por_capacidad`, con el comentario de que ya sabe que sale de
`pending_approval`), y el camino 4 no pasa por ninguno de los dos. Una guarda
puesta solo en `submit_registration` —o solo en `_evaluar_estado_por_aforo`—
deja tres agujeros por los que un evento de pago regala entradas.

Nota sobre el camino 3: `registration_mode` es un valor único
(`Literal["free", "approval", "paid"]`, `apps/api/app/modules/events/
schemas.py:17`), así que un evento no es «de aprobación **y** de pago» a la
vez. Pero `update_event` permite cambiar `registration_mode`
(`events/service.py:75-76`, `setattr` sobre cualquier campo recibido): un
evento que pasa de `approval` a `paid` conserva sus filas en
`pending_approval`, y aprobarlas después las llevaría a `confirmed` sin pago.
El camino 3 es real, no teórico.

## Diseño de la guarda (hallazgo #1)

Dos capas, ninguna de ellas opcional:

1. **Guarda de estado, en el punto donde el estado se decide.** Función nueva
   en `registrations/service.py`:

   `_estado_confirmable(session, evento, registration_id) -> str` — devuelve
   `"confirmed"` salvo que `evento.registration_mode == "paid"` y no exista un
   `event_payments` en `paid` para esa inscripción, en cuyo caso devuelve
   `"pending_payment"`. En el alta, `registration_id` es `None` (la fila aún no
   existe) y el resultado es siempre `pending_payment`, que es lo correcto:
   nadie ha pagado antes de inscribirse.

   Se invoca desde los **dos** puntos que hoy producen un `"confirmed"`
   evaluado y desde el que lo asigna a pelo:
   - `_evaluar_estado_por_capacidad` (líneas 138-155): sus dos `return
     "confirmed"` (línea 151, sin aforo; línea 155, con hueco) pasan por
     `_estado_confirmable`. Esto cubre los caminos 1, 2 y 3 de una vez, porque
     los tres desembocan ahí.
   - `confirm_waitlist_promotion` (línea 556): sustituye
     `inscripcion.status = "confirmed"` por el resultado de
     `_estado_confirmable`. La promoción de lista de espera de un evento de
     pago reserva la plaza y pide el pago; no confirma.
   - `confirmed_at` solo se fija cuando el estado resultante es realmente
     `confirmed` (los cuatro caminos ya lo condicionan así, líneas 346,
     411-412, 445-446 y 557; el cuarto pasa a condicionarlo).

2. **Cinturón de seguridad, en el punto único de emisión.**
   `_enviar_email_por_estado` (líneas 184-207), antes de llamar a
   `emitir_entrada`: si la inscripción está `confirmed`, el evento es `paid` y
   **no** hay un `event_payments` en `paid`, no emite y lanza un error de
   dominio (que aborta la transacción del llamador). No es redundancia
   decorativa: la capa 1 protege los caminos conocidos hoy; esta protege el
   quinto camino que alguien escriba dentro de seis meses, en el único sitio
   por el que necesariamente tiene que pasar.

   La consulta la resuelve `payments/repository.py::tiene_pago_confirmado`.
   `registrations/service.py` importa `payments.repository` (que solo importa
   sus propios modelos), no al revés: no hay ciclo de importación.

3. **`pending_payment` no envía su enlace de pago desde
   `_enviar_email_por_estado`.** Ese punto se ejecuta dentro de la transacción
   de la petición y con filas bloqueadas; crear allí una Checkout Session sería
   una llamada de red bajo bloqueo (hallazgo #12). El enlace lo despacha una
   tarea programada (ver más abajo), que es también la que lo reintenta.

## Flujo completo de los cuatro caminos, en un evento `paid`

- **1. Alta directa** (`submit_registration`): si el evento exige verificación
  de email → `pending_verification` (sin cambios). Si no → aforo bajo bloqueo
  del evento → `pending_payment` (o `waitlisted` si no cabe). El endpoint
  público de compra (abajo) continúa creando la Checkout Session y devuelve la
  URL en la misma respuesta.
- **2. Verificación de email** (`verify_registration`): al consumir el token,
  `_evaluar_estado_por_aforo` → `_evaluar_estado_por_capacidad` →
  `pending_payment`. La plaza queda reservada y el enlace de pago llega por
  correo.
- **3. Aprobación manual** (`approve_registration`): igual, vía
  `_evaluar_estado_por_capacidad` → `pending_payment`.
- **4. Promoción de lista de espera** (`confirm_waitlist_promotion`): al
  confirmar la promoción, `pending_payment` en vez de `confirmed`; enlace de
  pago por correo. La plaza sigue reservada porque `pending_payment` cuenta.
- **Cierre común:** solo el webhook `checkout.session.completed`, con
  `payment_status == "paid"`, mueve la inscripción de `pending_payment` a
  `confirmed`, y lo hace llamando a `_enviar_email_por_estado` —el mismo punto
  único de emisión— nunca a `emitir_entrada`.

**Ficheros creados en esta fase:**
`apps/api/app/modules/payments/checkout_service.py`,
`apps/api/app/modules/payments/webhooks.py` (router **y** handlers en un solo
fichero, ~350 líneas: dos ficheros para esto era parte del troceo que el
hallazgo #20 rechaza),
`apps/web/src/app/features/public/events/payment-return.ts` (+ spec).

**Ficheros existentes que amplía:** `payments/repository.py`,
`payments/schemas.py`, `payments/public_router.py`,
`registrations/service.py`, `registrations/repository.py`,
`apps/api/app/core/tasks.py`, `apps/api/app/main.py`,
`apps/web/src/app/features/public/events/event-registration-form.ts`,
`apps/web/src/app/app.routes.ts`.

## Requirements

- Functional:
  - **Desbloqueo de `paid`:** retirar el `ValidationDomainError` de
    `registrations/service.py:294-297`. El resto de `submit_registration` no
    cambia, incluida la rama que nunca revela si el email ya estaba inscrito
    (líneas 307-326). `submit_registration` pasa a **devolver** la inscripción
    (`EventRegistration | None`; `None` en la rama de «ya existía» y en la
    carrera de `IntegrityError`, línea 356), para que el endpoint de compra
    sepa si tiene que crear una sesión de pago sin volver a consultar.
  - **Reintento tras caducar (hallazgo #7).** `event_registrations` tiene
    `UNIQUE(event_id, email)` (`registrations/models.py:113`), así que una
    compra abandonada que acabe en `cancelled` bloquearía a esa persona para
    siempre en ese evento. La rama de «ya existe» de `submit_registration`
    gana una regla: si el evento es `paid`, la fila está `cancelled` y su
    `event_payments` está en `pending`/`expired` (**nunca llegó a moverse
    dinero**), la inscripción se reactiva — se revalúa el aforo y vuelve a
    `pending_payment` (o `waitlisted`), reutilizando la **misma** fila de
    `event_payments` (`UNIQUE(registration_id)`), con `checkout_attempts + 1`.
    Si el pago está en `paid`/`refunded`/`partially_refunded`, **no** se
    reactiva: una segunda compra exigiría una segunda fila de pago, que el
    `UNIQUE(registration_id)` no admite. Queda documentado como límite
    explícito de esta fase (ver Preguntas sin resolver del plan) y la respuesta
    pública sigue siendo la genérica de siempre.
  - **`pending_payment` cuenta como plaza reservada.**
    `count_reserved_registrations`
    (`registrations/repository.py:88-112`) añade una tercera rama al `or_`:
    `status == "pending_payment" AND payment_expires_at >= now()`, con la
    misma forma que la rama de promoción vigente que ya tiene (líneas
    104-108). El docstring de `_evaluar_estado_por_capacidad`
    (`service.py:138-149`), que hoy solo menciona la lista de espera, se
    actualiza.
  - **Liberación de plaza al cancelar (hallazgo #5).** `liberaba_una_plaza` en
    `_cancelar_inscripcion` (`registrations/service.py:264-266`) hoy solo
    contempla `confirmed` y `waitlisted` promovida. Pasa a incluir
    `pending_payment` dentro de su ventana, con la misma condición exacta que
    usa `count_reserved_registrations` — si una cuenta la plaza y la otra no la
    libera, el aforo se pierde silenciosamente. Test de regresión explícito.
  - `POST /public/events/{slug}/checkout` — Turnstile + `limit_per_ip`
    (`INSCRIPCION_POR_IP`, es el mismo acto). **Dos transacciones, no una:**
    - **T1 (con bloqueos, sin red).** En el orden de adquisición fijado en la
      fase 3 (`event_registrations` → `events` → `event_ticket_types` →
      `event_discount_codes`): crea o reactiva la inscripción vía
      `submit_registration`, valida vigencia y cupo del tipo y del código con
      los `COUNT` derivados **bajo `FOR UPDATE`**, fija `payment_expires_at =
      now + evento.payment_checkout_window_minutes` (columna del evento
      añadida en la fase 1, 30 minutos por defecto y editable por el
      organizador; **no** hay ajuste de instalación que leer — el evento ya
      está bloqueado en este punto por el orden de adquisición, así que el
      valor se lee de esa misma fila)
      <!-- Updated: Validation Session 1 - la ventana de pago se lee del evento, no de `get_settings()` -->
      , crea o reutiliza la fila de
      `event_payments` en `pending` con el importe calculado, el
      `stripe_account_id` de la cuenta activa y `checkout_attempts + 1`.
      **Commit.** A partir de aquí la plaza, el cupo y el uso del código están
      reservados por filas persistidas, no por bloqueos.
    - **T2 (con red, sin bloqueos).** Crea la Checkout Session con
      `idempotency_key = f"checkout_{payment.id}_{payment.checkout_attempts}"`
      y actualiza la fila con `stripe_checkout_session_id`, `checkout_url`,
      `expires_at` y `checkout_link_delivered_at`; propaga el `expires_at`
      **devuelto por Stripe** a `event_registrations.payment_expires_at`
      (hallazgo #16: el mínimo de 30 minutos de Stripe se mide desde la
      creación de la sesión, así que la ventana de la plataforma se alinea con
      la respuesta, nunca al revés). Devuelve la URL.
    - Si Stripe falla en T2: la fila queda en `pending` sin sesión, el barrido
      la expira por su ventana y libera todo; el endpoint devuelve un error
      accionable y un reintento reutiliza la fila con un `idempotency_key`
      distinto. **Nunca queda dinero cobrado sin fila**, porque el cobro no ha
      empezado.
    - Respuesta siempre con la misma forma —`{"message": <genérico>,
      "checkout_url": <url|null>}`— para no revelar si el email ya estaba
      inscrito: cuando la inscripción existente no es pagable, `checkout_url`
      es `null` y el detalle va por correo, como en el resto del flujo público.
    - 409 si no hay cuenta activa o `charges_enabled = false`; 503 si
      `payments_enabled` es `False`.
  - **Checkout Session:** `stripe_account=<acct_id de la fila del pago>`
    (direct charge), `mode="payment"`, **`payment_method_types=["card"]`**
    (hallazgo #3), `expires_at` calculado en el instante de la llamada como
    `now + evento.payment_checkout_window_minutes + 60 s` de margen técnico
    <!-- Updated: Validation Session 1 - la ventana sale del evento; el margen sustituye al mínimo de configuración -->
    (hallazgo #16: Stripe rechaza un `expires_at` a menos de 30 minutos vista y
    la ventana mínima por evento es justo 30, así que el tiempo entre calcular
    y enviar bastaría para cruzar el límite. El margen se aplica siempre, sin
    ramas; como la ventana efectiva de la plataforma se toma **de la respuesta
    de Stripe**, nunca resulta más corta que la configurada por el organizador),
    `success_url`/`cancel_url` en el dominio propio de la organización,
    `client_reference_id` y `metadata` informativos, **sin**
    `application_fee_amount`, y `price_data` ad-hoc con el importe ya
    descontado.
  - **Enlace de pago para los caminos 2, 3 y 4:** tarea programada
    `dispatch_pending_payment_links_task` (cron `* * * * *`) en
    `app/core/tasks.py`. Busca inscripciones en `pending_payment` cuyo pago no
    tenga `checkout_link_delivered_at`, ejecuta la misma función T2 de
    `checkout_service` y encola el correo con la URL. Se hace así, y no dentro
    de la petición, por el hallazgo #12 (llamada de red bajo bloqueos) y para
    que un fallo de Stripe se reintente solo, sin perder la verificación o la
    aprobación que ya ocurrió. Correo nuevo
    `send_registration_payment_link_email` (`to_email`, `organization_id`,
    `checkout_url`, `cancel_token`, `expira_el`), en la línea de las plantillas
    existentes (`tasks.py:196-310`).
  - `POST /api/v1/webhooks/stripe` — endpoint público sin `OrganizationDep`.
    La ruta real lleva el prefijo `API_PREFIX` como todas las demás: el router
    se incluye en el mismo `APIRouter(prefix=API_PREFIX)` de
    `apps/api/app/main.py:84-103`. **No existe ninguna ruta fuera de
    `/api/v1`.**
    - Lee el **raw body** (`await request.body()`), verifica la firma con
      `construct_event` antes de cualquier parseo: sin modelo Pydantic en la
      firma del handler, sin `await request.json()`. El único middleware
      registrado es CORS y solo en desarrollo (`main.py:72-81`), así que nada
      lee el cuerpo antes.
    - **Un solo endpoint y un solo secreto, registrado en Stripe como endpoint
      de cuentas conectadas** (`connect: true`), decisión del hallazgo #10.
      La documentación de Connect es explícita: el ámbito **Connected
      accounts** cubre «Direct charges for customers of your connected
      accounts» y «v1 `account.updated` events […] of your connected
      accounts», y `account.application.deauthorized` figura en su tabla de
      eventos de cuentas conectadas; además «Each event for a connected
      account contains a top-level `account` property that identifies the
      connected account»
      (<https://docs.stripe.com/connect/webhooks>). Los cuatro eventos que
      esta fase consume llegan por ese único canal, así que dos secretos serían
      un segundo camino sin ningún evento que lo recorra. Consecuencias
      explícitas: un evento **sin** `account` de nivel superior se marca
      `ignored` (es de ámbito plataforma, al que no estamos suscritos), y en
      local se usa `stripe listen --forward-connect-to
      localhost:8000/api/v1/webhooks/stripe`, no `--forward-to`.
    - **Idempotencia medida sobre el proceso, no sobre la recepción**
      (hallazgo #9): verifica firma → `INSERT stripe_webhook_events(id, status
      = 'received')` vía `maintenance_session`. Si choca con la PK, lee la fila
      existente: `processed`/`ignored` → 200 sin hacer nada; `received`/
      `failed` → **reencola la tarea** y responde 200 (Stripe está
      reintentando justamente porque no llegamos a terminar). Si no choca,
      encola y responde 200. El handler HTTP no procesa nada.
    - Un `event.account` que no resuelve a ninguna organización → `ignored` y
      200 (un 4xx/5xx haría a Stripe reintentar indefinidamente un evento que
      nunca podrá procesarse).
  - Tarea `process_stripe_webhook_task(event_id: str)` con
    **`retry_on_error=True, max_retries=5`** (hallazgo #9; es además el patrón
    de todas las tareas del proyecto, `tasks.py:44,50,73,...`). Relee el
    payload de la base de datos por su `event_id`, nunca del argumento. Marca
    `status = 'processed'` **en la misma transacción que aplica el efecto de
    dominio**: «procesado» solo es cierto si los efectos se confirmaron.
    Incrementa `attempts` y `last_attempt_at` en cada intento; agotados los
    reintentos, `failed` con el error.
  - Tarea `sweep_stuck_webhook_events_task` (cron `*/10 * * * *`): reencola las
    filas en `received` con más de 10 minutos y las `failed` con `attempts <
    5`; las que superan ese umbral se registran en el log a nivel `ERROR` con
    su `event_id`. Sin esto, un evento perdido entre la cola y el worker deja
    dinero cobrado sin inscripción confirmada, para siempre.
  - Tarea `purge_stripe_webhook_events_task` (cron diario): borra filas con
    más de `stripe_webhook_retention_days` (hallazgo #15).
  - **Handlers**, en `payments/webhooks.py`:
    - `checkout.session.completed`:
      1. **Localiza el pago exclusivamente por `stripe_checkout_session_id`**
         (`UNIQUE`), nunca por `metadata` ni `client_reference_id` — con
         Connect Standard el organizador controla su propio Dashboard y puede
         fabricar objetos con la `metadata` que quiera (hallazgo #2).
      2. **Verifica que `payment.organization_id` coincide con la organización
         resuelta desde `event.account`.** Si no coincide → `failed`, sin
         mutar nada, y log de seguridad. Si no existe pago con esa sesión →
         `ignored`.
      3. **Exige `payment_status == "paid"`** (hallazgo #3). Con
         `payment_method_types=["card"]` no debería llegar otra cosa, pero el
         organizador puede habilitar métodos diferidos en su propio Dashboard;
         un `unpaid`/`no_payment_required` se marca `ignored` y **no**
         confirma nada. `checkout.session.async_payment_succeeded/failed`
         quedan **fuera del alcance de esta fase, documentado**, no ignorado en
         silencio: aparecen en `docs/arquitectura.md` como el trabajo que hace
         falta antes de habilitar SEPA u otros métodos diferidos.
      4. Marca el pago `paid` con su `payment_intent_id` y `paid_at`
         (no-op si ya estaba `paid`: el handler es idempotente por sí mismo,
         además de por la tabla de eventos).
      5. Pone la inscripción en `confirmed` y llama a
         `_enviar_email_por_estado`. **El módulo de pagos no llama nunca a
         `emitir_entrada`** (Decisión #6 del plan).
    - `account.updated`: refresca las tres banderas de la fila **activa** de
      esa cuenta.
    - `account.application.deauthorized`: marca `deauthorized_at` y
      `charges_enabled = false`. La venta queda bloqueada al instante y la
      reconexión de la fase 2 sigue siendo posible.
    - `charge.refunded`: lo implementa la fase 5. Aquí se registra como
      `ignored` con su tipo, nunca como `failed`.
    - Tipo no reconocido → `ignored`.
  - **Barrido de `pending_payment` caducados:** `expire_pending_payments_task`
    (cron `*/5 * * * *`), hermana de `expire_waitlist_promotions_task`
    (`tasks.py:151-163`, con el mismo import diferido para evitar la
    importación circular que su docstring explica).
    - **Antes de expirar nada, consulta el estado real de la sesión en
      Stripe** para los pagos que tengan `stripe_checkout_session_id`: si
      Stripe la reporta pagada, se aplica la confirmación en vez de la
      expiración (es el caso de un webhook perdido). Es la única llamada
      síncrona a Stripe fuera del camino de la petición, y va en la tarea de
      fondo.
    - Si no: marca el pago `expired` (con lo que deja de contar para el cupo
      del tipo y para los usos del código, sin decrementar ningún contador —
      hallazgo #19) y cancela la inscripción **a través de
      `_cancelar_inscripcion`**, que ya revoca entrada si la hubiera y promueve
      la lista de espera, ahora también para `pending_payment` (hallazgo #5).
  - Frontend: paso de selección de tipo y código en el formulario público con
    el desglose del presupuesto de la fase 3; redirección a la URL de Stripe
    en el navegador (nunca en SSR); pantalla de retorno que consulta el estado
    real y **no** da el pago por bueno por el mero retorno de Stripe.
- Non-functional:
  - **Ninguna llamada de red a Stripe con bloqueos de fila abiertos**
    (hallazgo #12), en ninguno de los tres caminos (compra, tarea de enlaces,
    barrido). Se verifica leyendo el código y con un test que comprueba que
    T1 ha hecho commit antes de que el cliente simulado reciba la primera
    llamada.
  - **El `acct_id` nunca procede del cliente ni del contexto ambiental**
    (hallazgo #8): en la compra sale de la cuenta activa resuelta por el
    `organization_id` del evento público; en el webhook y en las tareas de
    fondo (`maintenance_session`, con `BYPASSRLS`) sale del
    `stripe_account_id` **persistido en la fila del pago**. El wrapper no
    acepta un `acct_id` de tipo `str` desde una petición.
  - **Toda llamada mutante lleva `idempotency_key` derivada de una PK
    persistida** (hallazgo #11).
  - `openapi.json` + cliente TypeScript regenerados; el endpoint de webhooks se
    documenta sin esquema de cuerpo, para que el cliente generado no invente
    un modelo tipado que invite a parsearlo.
  - WCAG 2.1 AA en el paso de compra y en la pantalla de retorno: el estado
    «confirmando tu pago» se anuncia en `aria-live` y la espera tiene salida
    clara, no un spinner indefinido.
  - Tamaños estimados: `checkout_service.py` ~320, `webhooks.py` ~350,
    `tasks.py` pasa de 310 a ~430 líneas. Ninguno cerca de 1000.

## Implementation Steps

1. `registrations/service.py`: `_estado_confirmable`, su uso en
   `_evaluar_estado_por_capacidad` y en `confirm_waitlist_promotion`, el
   cinturón de seguridad en `_enviar_email_por_estado`, la retirada del
   bloqueo de `paid`, el valor de retorno de `submit_registration` y la regla
   de reactivación. Docstrings actualizados (los tres afectados mienten hoy si
   no se tocan).
2. `registrations/repository.py`: `count_reserved_registrations` con la rama de
   `pending_payment` vigente; consulta de `pending_payment` caducados.
3. `registrations/service.py`: `liberaba_una_plaza` incluye `pending_payment`
   vigente.
4. `payments/repository.py`: `tiene_pago_confirmado`, búsqueda por
   `stripe_checkout_session_id`, alta/reutilización de la fila de pago,
   consultas de las tres tareas de fondo.
5. `payments/checkout_service.py`: T1 y T2 como funciones separadas y
   reutilizables (la compra usa las dos; la tarea de enlaces solo T2).
6. `payments/public_router.py`: endpoint de compra y endpoint de consulta de
   estado del pago para la pantalla de retorno.
7. `payments/webhooks.py`: router + handlers; registro en `main.py` dentro del
   mismo `APIRouter(prefix=API_PREFIX)`.
8. `core/tasks.py`: `process_stripe_webhook_task`,
   `sweep_stuck_webhook_events_task`, `purge_stripe_webhook_events_task`,
   `expire_pending_payments_task`, `dispatch_pending_payment_links_task` y el
   correo del enlace de pago.
9. Frontend: paso de compra y pantalla de retorno.
10. `openapi.json` + cliente TypeScript regenerados.

## Success Criteria

- [ ] **Los cuatro caminos de confirmación quedan cerrados en un evento
      `paid`**, cada uno con su test: alta directa, verificación de email,
      aprobación manual y promoción de lista de espera terminan en
      `pending_payment`, **no** en `confirmed`, y **ninguno** emite entrada
      (`event_tickets` vacía tras los cuatro)
- [ ] Un evento que pasa de `approval` a `paid` con inscripciones en
      `pending_approval`: aprobarlas las deja en `pending_payment`, no en
      `confirmed` — test del camino 3 sobre el caso real que lo hace posible
- [ ] Forzar `status = "confirmed"` en una inscripción de un evento `paid` sin
      pago y llamar a `_enviar_email_por_estado` **no emite entrada y falla
      con error de dominio** — test del cinturón de seguridad, independiente
      de la guarda de estado
- [ ] Compra completa de extremo a extremo en modo test: formulario →
      `pending_payment` → Checkout hosted → tarjeta de prueba →
      `checkout.session.completed` → `confirmed` → entrada emitida y correo con
      QR → QR escaneado como `valid` en el control de acceso de la fase 4 del
      PRD
- [ ] `grep -rn "emitir_entrada" app/modules/payments/` no devuelve nada
- [ ] Un `checkout.session.completed` con `payment_status != "paid"` **no
      confirma ni emite entrada**: se marca `ignored` — test explícito
      (hallazgo #3)
- [ ] Un `checkout.session.completed` firmado correctamente pero cuyo
      `event.account` pertenece a otra organización que la del pago localizado
      **no muta nada** y se marca `failed` — test explícito (hallazgo #2)
- [ ] Un evento cuya sesión no existe en `event_payments` se marca `ignored`;
      la búsqueda **no** usa `metadata` ni `client_reference_id` — verificado
      por `grep` sobre el handler
- [ ] Entregar el mismo `evt_...` de `checkout.session.completed` dos veces
      produce una sola entrada, un solo pago `paid` y un solo correo
- [ ] Una fila `received` cuya tarea nunca se ejecutó **se recupera**: el
      barrido la reencola y la compra acaba confirmada — test que simula la
      pérdida entre la cola y el worker (hallazgo #9)
- [ ] Una entrega repetida por Stripe de un evento en `received` reencola la
      tarea y responde 200, en vez de darlo por procesado
- [ ] Webhook sin cabecera `Stripe-Signature`, con firma inválida y con
      timestamp fuera de tolerancia: 400 en los tres casos, cero filas
      escritas en cualquier tabla; un cuerpo que no es JSON válido con firma
      incorrecta devuelve **400, no 422** (prueba de que no se parsea antes de
      verificar)
- [ ] Un evento **sin** `account` de nivel superior se marca `ignored`
      (hallazgo #10)
- [ ] `docs/desarrollo.md` documenta `stripe listen --forward-connect-to
      localhost:8000/api/v1/webhooks/stripe`; la ruta real de la API incluye
      el prefijo `/api/v1` — verificado contra `main.py:84-103`
- [ ] 3 compras concurrentes sobre un tipo con `max_quantity = 2`: solo 2
      prosperan y la tercera no crea Checkout Session
- [ ] 4 usos concurrentes de un código con `max_uses = 3`: exactamente 3
      prosperan; el `used_count` derivado queda en 3
- [ ] Con `capacity = 1` y una compra en curso, una segunda persona entra en
      lista de espera, no en `pending_payment`
- [ ] Una inscripción `pending_payment` caducada libera la plaza **y promueve
      a la siguiente de la lista de espera** — test de regresión del hallazgo
      #5, con `liberaba_una_plaza` verificado sobre `pending_payment`
- [ ] Un pago caducado deja de consumir cupo y uso de código sin que nadie
      decremente ningún contador; dos ejecuciones solapadas del barrido dejan
      el mismo resultado que una (hallazgo #19)
- [ ] El barrido **no** expira un pago cuya sesión Stripe reporta como pagada:
      lo confirma — test con el cliente simulado devolviendo `paid`
- [ ] Una compra abandonada que caduca **no bloquea a esa persona**: volver a
      inscribirse en el mismo evento con el mismo email reactiva la fila y
      devuelve una URL de pago nueva, reutilizando la misma fila de
      `event_payments` con `checkout_attempts = 2` (hallazgo #7)
- [ ] Ninguna llamada a Stripe ocurre con una transacción abierta que
      mantenga bloqueos de fila: T1 ha hecho commit antes de la primera
      llamada al cliente simulado (hallazgo #12)
- [ ] Dos creaciones de sesión para el mismo pago usan `idempotency_key`
      distintas (`checkout_attempts` distinto); un reintento del mismo intento
      usa la misma clave — test explícito (hallazgo #11)
<!-- Updated: Validation Session 1 - la ventana es del evento, no una variable de entorno -->
- [ ] `expires_at` de la Checkout Session se calcula en el instante de la
      llamada y `payment_expires_at` se fija **desde la respuesta de Stripe**;
      en un evento con la ventana en su mínimo (30 minutos) la **primera**
      compra funciona, sin que Stripe rechace la sesión (hallazgo #16)
- [ ] Dos eventos con ventanas distintas (30 y 120 minutos) producen
      `payment_expires_at` distintos para compras hechas en el mismo instante —
      test explícito de que el valor sale del evento
- [ ] `grep -rn "payment_checkout_window_minutes" apps/api/app/` solo aparece
      en el modelo/schema del evento y en el servicio de checkout; nunca vía
      `get_settings()`
- [ ] Comprar en un evento cuya organización tiene `charges_enabled = false`
      devuelve 409 antes de crear nada
- [ ] Manipular el cuerpo de la petición de compra no cambia la cuenta de
      destino ni el importe
- [ ] `account.updated` y `account.application.deauthorized` actualizan el
      estado; tras el segundo, una compra nueva devuelve 409
- [ ] Los caminos 2, 3 y 4 reciben su enlace de pago por correo vía
      `dispatch_pending_payment_links_task`, y la tarea es idempotente: dos
      ejecuciones no generan dos sesiones ni dos correos
      (`checkout_link_delivered_at`)
- [ ] La suite completa de inscripciones de la fase 3 del PRD sigue en verde
      **sin modificar ningún test previo**: si alguno hay que cambiarlo, el
      flujo gratuito se ha alterado
- [ ] La pantalla de retorno no da el pago por confirmado por el mero retorno
      de Stripe; cero violaciones de axe en el paso de compra y en el retorno
- [ ] `openapi.json` y el cliente TypeScript generado al día; el endpoint de
      webhooks no genera ningún modelo tipado de cuerpo

## Risk & Rollback

- Riesgo (**el más alto de la fase**): la ventana entre crear la Checkout
  Session y recibir el webhook es una ventana con dinero comprometido y
  ninguna entrada emitida. Mitigaciones acumuladas, todas verificables: el
  barrido consulta el estado real antes de expirar; el barrido de eventos
  atascados reencola lo perdido entre la cola y el worker; la tarea de proceso
  reintenta; y la fila del pago existe desde antes de la primera llamada a
  Stripe.
- Riesgo: `_evaluar_estado_por_capacidad` y `_enviar_email_por_estado` los usan
  **todos** los eventos, también los gratuitos. Las dos guardas nuevas son
  condiciones sobre `registration_mode == "paid"`, que hoy no existe en
  ninguna fila; aun así, el criterio de éxito exige que la suite previa siga
  en verde sin tocar ningún test.
- Riesgo: `count_reserved_registrations` la consumen dos caminos existentes
  (`_evaluar_estado_por_capacidad` y la promoción). Ampliarla afecta al aforo
  de todos los eventos, aunque para los gratuitos la condición nueva nunca se
  cumple. Test de regresión sobre un evento gratuito con lista de espera.
- Riesgo: la reactivación tras caducidad depende de distinguir «cancelada por
  no pagar» de «cancelada por la persona». Se distingue por el estado del pago
  (`pending`/`expired` = nunca se movió dinero), no por una columna nueva. Una
  inscripción cancelada tras haber pagado y sido reembolsada **no** se puede
  reactivar; es un límite conocido y anotado, no un olvido.
- Riesgo: un evento de pago con `email_verification_required` suma dos pasos
  antes de pagar (verificar y luego pagar). Es el comportamiento correcto pero
  alarga el embudo; se documenta para que el organizador lo decida a
  sabiendas.
- Riesgo: la ventana de pago de los caminos 2, 3 y 4 empieza a contar en el
  momento de la verificación/aprobación/promoción, no en el momento en que la
  persona abre el correo. Si caduca, la plaza se libera y la persona puede
  reintentar por el camino de reactivación. Es una decisión de producto
  anotada en las preguntas abiertas del plan (ventana de caducidad).
- Rollback: restaurar el bloqueo de `paid` (dos líneas) y desregistrar el
  router de webhooks. Antes de revertir hay que **desactivar el endpoint en el
  Dashboard de Stripe**, o Stripe seguirá reintentando contra una URL que ya
  no existe. Las entradas ya emitidas viven en `event_tickets`, independientes
  del módulo de pagos, y no se pierden.
