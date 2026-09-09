---
title: "PRD Fase 6 — Pagos con Stripe Connect, tipos de entrada, descuentos y reembolsos"
description: "Eventos de pago end-to-end: cuenta Stripe Connect Standard por organización con onboarding hosted, tipos de entrada y códigos de descuento por evento, Checkout hosted con direct charges sin comisión, webhooks firmados e idempotentes, y reembolsos automáticos/manuales que revocan la entrada reutilizando el flujo de cancelación de la fase 3."
status: pending
priority: P1
effort: "14.5-17.5d"
branch: develop
tags: [pagos, stripe, stripe-connect, entradas, descuentos, reembolsos, webhooks]
created: 2026-09-09
prd_phase: 6
blockedBy: [5]
blocks: [7]
---

# PRD Fase 6 — Pagos con Stripe Connect, tipos de entrada, descuentos y reembolsos

## Overview

Con las fases 1-5 cerradas, `registration_mode = "paid"` sigue siendo el único
valor del enum que el producto no soporta: hoy está bloqueado explícitamente
con un `ValidationDomainError` en
`apps/api/app/modules/registrations/service.py:294-297`. Esta fase lo
desbloquea de extremo a extremo.

Alcance según `docs/prd.md` §4.5 (bloque **S**), completo:

- **Stripe Connect**: cada organización conecta su propia cuenta y cobra
  directamente; la plataforma no custodia dinero ni cobra comisión.
- **Tipos de entrada por evento**: nombre, precio, cantidad máxima, ventana
  de venta.
- **Códigos de descuento** gestionados en la base de datos propia.
- **Stripe Checkout hosted**, webhooks con firma verificada, reembolsos desde
  el panel.
- **Facturación delegada**: Stripe emite los recibos; la plataforma no genera
  ninguna factura.

## Non-goals

Volcado de ingresos a contabilidad (§4.5 último punto → §4.8, fase 7 del PRD,
**S**): esta fase deja los pagos en una tabla propia consultable, pero no
construye ningún libro contable ni asiento. Generación de facturas (§4.5
explícitamente delegado a Stripe — no se construye ningún generador de PDF ni
numeración fiscal). Comisión de plataforma (`application_fee_amount`): el
proyecto es gratuito por decisión ya tomada, se implementan **direct charges**
sin comisión (ver Decisión #3). Payment Element embebido / Stripe.js en el
frontend: se usa Checkout hosted, la página de pago la aloja Stripe. Accounts
v2 de Stripe (sigue en preview, ver Decisión #2). Suscripciones, abonos de
varios eventos, pagos recurrentes, wallet (fase 9, **P**). Patrocinios de pago
por Stripe (§4.6 quedó cerrado en la fase 5 sin pasarela). Payouts y
conciliación bancaria (los gestiona el organizador en su propio Dashboard de
Stripe, que es justo lo que aporta Connect Standard).

## Decisiones de diseño (ingeniería, no interview de producto)

1. **La revocación de entradas YA EXISTE — no se crea nada nuevo, se
   reutiliza.** La premisa de partida de esta fase decía que la fase 4 «no
   dejó preparado» el concepto de revocación y que `EventTicket` solo tiene
   `issued_at`/`used_at`/`used_by_event_member_id`. **Es falso, verificado
   en código:**
   - `apps/api/app/modules/tickets/models.py:70` — `revoked_at:
     Mapped[datetime | None]` ya existe en la tabla.
   - `apps/api/app/modules/tickets/service.py:82-93` — `revocar_entrada()`
     ya está implementada e es idempotente/no-op si no hay entrada.
   - `apps/api/app/modules/tickets/scanning.py:83-84` — el control de acceso
     **ya rechaza** una entrada revocada (`if ticket.revoked_at is not None:
     return "revoked"`), antes de comprobar duplicado.
   - `apps/api/app/modules/tickets/models.py:126` y
     `apps/api/app/modules/tickets/schemas.py:12` — `revoked` ya es un valor
     válido de `EventTicketScan.result`, y el frontend ya lo pinta
     (`apps/web/src/app/features/admin/events/event-check-in.ts:64,122,229`).
   - `apps/api/app/modules/tickets/repository.py:91` y
     `apps/api/app/modules/tickets/service.py:163` — `/mi-entrada` ya oculta
     el QR de una entrada revocada.

   Consecuencia para el plan: **no se añade ningún estado `revoked` nuevo, ni
   columna, ni comprobación en el check-in.** El servicio de reembolsos de la
   fase 5 de trabajo llama a la `revocar_entrada` existente. Un plan que
   hubiera añadido un `status` paralelo en `event_tickets` habría creado una
   segunda fuente de verdad sobre la validez de una entrada, con dos caminos
   de código que el escáner tendría que consultar por separado — exactamente
   el fallo que el proyecto evita en el resto del esquema.

2. **Stripe Connect Standard v1 con Account Links, no OAuth ni Accounts
   v2.** Standard + direct charges es la única combinación que cumple
   literalmente el requisito del PRD «la plataforma no custodia dinero»: el
   cargo ocurre en la cuenta del organizador, que asume fraude y disputas y
   tiene su propio Dashboard. OAuth está desaconsejado por la propia
   documentación de Stripe para plataformas nuevas. Accounts v2 exige
   `Stripe-Version: 2026-08-26.preview` — un proyecto open source sin equipo
   dedicado a seguir APIs en preview no debe atarse a ella para mover dinero
   real (ver `plans/reports/researcher-260909-0019-stripe-connect-fase6-pagos.md`
   §1-§2).

3. **Direct charges sin `application_fee_amount`, con el hueco preparado
   pero no construido.** El 100% del importe va a la organización. El
   parámetro `stripe_account=<acct_id>` viaja en **un único punto del
   código** (`stripe_client.py`, ver Decisión #7), así que migrar a
   destination charges el día que exista comisión es cambiar ese wrapper, no
   los llamadores. No se añade hoy ningún campo `application_fee` a ninguna
   tabla ni ningún parámetro opcional muerto: sería configuración sin caso de
   uso, y el enunciado dice explícitamente que no habrá comisión.

4. **`organization_stripe_accounts` es una tabla separada, con una cuenta
   *activa* por organización, no columnas en `organizations`.** Tres motivos
   concretos, no estéticos: (a) `organizations` es la tabla raíz del tenant y
   la leen decenas de caminos (resolución por host, branding, páginas
   legales, panel) — el estado de la pasarela no debe viajar en cada uno de
   ellos; (b) el ciclo de vida es distinto: una organización que desconecta
   su cuenta (`account.application.deauthorized`) borra/marca una fila, no
   nulifica cinco columnas de la tabla raíz; (c) el rollback de la fase es un
   `DROP TABLE` limpio en vez de un `ALTER TABLE` sobre la tabla más usada
   del esquema. Lleva RLS igual que toda tabla de dominio
   (`organization_id = app_current_organization()`) **más**
   `UNIQUE(id, organization_id)`, para poder ser destino de una FK compuesta
   si una fase futura la necesita — mismo patrón que `sponsor_tiers` en la
   fase 5 (hallazgo #4 de su red-team: sin esa constraint la FK compuesta
   simplemente no se puede crear y `alembic upgrade` aborta).

   **Corrección tras el red-team (hallazgo #17):** la unicidad **no** es
   `UNIQUE(organization_id)` sino un índice único **parcial** sobre
   `(organization_id) WHERE deauthorized_at IS NULL`. Con la constraint
   simple, una organización que desconecta su cuenta no puede volver a
   conectarse jamás sin tocar la base de datos a mano, y sobrescribir la fila
   perdería el `acct_id` con el que se cobraron los pagos anteriores — que es
   la única cuenta contra la que esos pagos se pueden reembolsar. Por eso
   `event_payments` guarda además su propio `stripe_account_id`: el reembolso
   se resuelve por la cuenta **del pago**, no por la cuenta actual de la
   organización.

5. **`pending_payment` es un estado nuevo de `EventRegistration`, y **cuenta
   como plaza reservada** con ventana de caducidad.** El flujo es: formulario
   público → inscripción en `pending_payment` → Checkout Session → webhook
   `checkout.session.completed` → `confirmed`. Si `pending_payment` no
   contara para el aforo, N personas podrían abrir Checkout a la vez sobre la
   última plaza y todas pagar: se cobra a gente que no cabe, en cuentas de
   Stripe que la plataforma no controla, y el reembolso es manual. Por tanto:
   - `count_reserved_registrations`
     (`apps/api/app/modules/registrations/repository.py:88-112`) incluye
     `pending_payment` cuya ventana no haya expirado — exactamente el mismo
     patrón que ya usa para una promoción de lista de espera dentro de su
     ventana (`waitlist_promotion_expires_at`, líneas 104-108).
   - **Y `liberaba_una_plaza` en `_cancelar_inscripcion`
     (`registrations/service.py:264-266`) incluye la misma condición**
     (hallazgo #5): hoy solo contempla `confirmed` y `waitlisted` promovida.
     Si una función cuenta la plaza y la otra no la libera, el aforo se pierde
     en silencio en cuanto caduca la primera compra.
   - Tarea programada de barrido, hermana de
     `expire_waitlist_promotions_task` (`apps/api/app/core/tasks.py:151-163`,
     cron `*/15 * * * *`), que libera las inscripciones `pending_payment`
     caducadas y promueve lista de espera si procede — **consultando antes a
     Stripe** el estado real de la sesión, para no cancelar una compra que sí
     se pagó y cuyo webhook se perdió.
   - **El orden es: sesión primero, ventana después** (hallazgo #16). Stripe
     exige que `expires_at` esté al menos 30 minutos por delante **del
     instante en que se crea la sesión**; calcular `payment_expires_at` antes
     y pasar esa misma cifra garantiza que la primera compra falle. Por tanto:
     `expires_at` se calcula en el momento de la llamada, y
     `payment_expires_at` de la inscripción se **fija desde la respuesta de
     Stripe**. Nunca se deja el default de 24 h de Stripe, que bloquearía una
     plaza un día entero.
   <!-- Updated: Validation Session 1 - la ventana de pago pasa de `core/config.py` a `events.payment_checkout_window_minutes` -->
   - **La duración de la ventana es un campo del evento, no un ajuste de
     instalación** (validación, sesión 1): columna
     `events.payment_checkout_window_minutes` (`NOT NULL DEFAULT 30`, `CHECK
     BETWEEN 30 AND 1439`), precargada a 30 minutos en el formulario del
     organizador y editable ahí. Vive en `events` y no en
     `event_ticket_types` porque la ventana protege una **plaza**, y la plaza
     es del evento: el aforo (`events.capacity`) y la fila que la retiene
     (`event_registrations.payment_expires_at`, una por `(event_id, email)`)
     son ambos de nivel evento. Para respetar el mínimo de Stripe con una
     ventana de 30, la Checkout Session se crea con `expires_at = now +
     ventana + 60 s` de margen técnico, siempre y sin ramas.

6. **La guarda de pago vive donde se decide el estado, no en
   `submit_registration`; y el punto único de emisión actúa además como
   cinturón de seguridad.** (Reescrita entera tras el hallazgo #1, el más
   grave del red-team y confirmado por dos revisores independientes.)

   La versión anterior de esta decisión asumía que interceptar
   `submit_registration` bastaba. **Es falso.** Hay **cuatro** caminos que
   dejan una inscripción en `confirmed` y llaman a `_enviar_email_por_estado`,
   que es quien emite la entrada (`registrations/service.py:199-203`):
   `submit_registration` (estado en la línea 337, emisión en la 384),
   `verify_registration` (409 / 413), `approve_registration` (444 / 447) y
   `confirm_waitlist_promotion` (**556, que asigna `"confirmed"`
   directamente**, / 558). Además, `approve_registration` no pasa por
   `_evaluar_estado_por_aforo` sino por `_evaluar_estado_por_capacidad`, y
   `confirm_waitlist_promotion` no pasa por ninguna de las dos. Una guarda
   puesta en un solo camino deja tres vías por las que un evento de pago
   regala entradas: verificación de email, aprobación manual y lista de
   espera.

   Diseño resultante, en dos capas:
   - **Capa 1, guarda de estado:** función `_estado_confirmable`, invocada
     desde los dos `return "confirmed"` de `_evaluar_estado_por_capacidad`
     (líneas 151 y 155) —lo que cubre los caminos 1, 2 y 3, que desembocan
     todos ahí— y desde `confirm_waitlist_promotion` (línea 556). En un evento
     `registration_mode == "paid"` sin `event_payments` en `paid`, el estado
     resultante es `pending_payment`, nunca `confirmed`.
   - **Capa 2, cinturón de seguridad:** `_enviar_email_por_estado` se niega a
     emitir un `confirmed` de evento de pago sin pago verificado. Protege al
     quinto camino que alguien escriba más adelante, en el único sitio por el
     que necesariamente tiene que pasar.

   Se mantiene lo que sí era cierto de la decisión original: **la entrada se
   emite en un único punto**. El webhook de pago no llama nunca a
   `emitir_entrada`; pone la inscripción en `confirmed` y llama a
   `_enviar_email_por_estado`, igual que los cuatro caminos existentes.

7. **Todas las llamadas a Stripe pasan por un único wrapper
   `payments/stripe_client.py` que exige el `acct_id`.** El riesgo #1 de la
   investigación (`researcher-260909-0019` §8.1) es la confusión de
   `account_id`: crear una Checkout Session o un Refund contra la cuenta de
   plataforma, o contra la organización equivocada, en un sistema
   multi-tenant. Mitigación estructural, no por disciplina: ninguna función
   de servicio importa `stripe` directamente; el wrapper recibe siempre un
   `OrganizationStripeAccount` **ya resuelto** (tipo propio, nunca un
   `acct_id` de tipo `str` que venga del body/query), y `ruff` bloquea
   `import stripe` fuera de ese fichero. Todas las llamadas usan las
   variantes `*_async` del SDK (`stripe[async]`): una llamada síncrona dentro
   de un `async def` de FastAPI bloquea el event loop del proceso entero.

   **Dos correcciones tras el red-team:**
   - «Siempre desde el contexto RLS de la petición» no cubría los dos caminos
     **sin petición HTTP** —el webhook y las tareas de fondo, ambos sobre
     `maintenance_session`, que corre con `BYPASSRLS`
     (`apps/api/app/core/database.py:114-123`)— donde no hay contexto RLS que
     actúe de barrera (hallazgo #8). Regla real, válida en los tres caminos:
     el `acct_id` sale siempre de la fila del pago (`event_payments.
     stripe_account_id`) o de la cuenta activa resuelta por `organization_id`,
     y la resolución la hace una única función del repositorio.
   - Toda llamada **mutante** (crear sesión, crear reembolso) lleva
     `idempotency_key` derivada de una PK ya persistida (hallazgo #11), no
     generada al vuelo: un reintento con clave distinta es un cobro o un
     reembolso duplicado.
   - La excepción a capturar es `stripe.StripeError`, del módulo raíz:
     `stripe.error` **no existe desde la v13** («Removed deprecated module
     shims […] `stripe.error`», changelog del SDK). Versión fijada:
     `stripe[async]>=15.6,<16.0` (última estable, 15.6.1).

8. **Códigos de descuento en base de datos propia, no Stripe Promotion
   Codes.** Con direct charges los coupons vivirían en la cuenta *conectada*,
   fuera del alcance del panel multi-tenant; Checkout admite un solo código
   por sesión; y el precio final hay que calcularlo antes de redirigir de
   todos modos (para comprobar cupo del tipo de entrada y ventana de venta).
   Mantener el precio en dos fuentes de verdad (BD y Stripe) es la vía
   directa a cobrar un importe distinto del anunciado. El importe ya
   descontado se pasa a Stripe como `price_data` ad-hoc.
   **Límite de usos total configurable por código, sin límite por persona:**
   las inscripciones no requieren cuenta de usuario
   (`EventRegistration.user_id` es nullable,
   `apps/api/app/modules/registrations/models.py:130-132`), así que «una vez
   por persona» sería un límite por email autodeclarado — una falsa garantía
   que invita a apoyarse en ella.

   **Sin contador `used_count`** (hallazgo #19): el consumo de un código —y el
   cupo de un tipo de entrada— se **derivan** de `event_payments` con un
   `COUNT` sobre los estados consumibles, ejecutado con la fila del código y
   la del tipo bloqueadas (`FOR UPDATE`). Un contador que la compra
   incrementa y el barrido de caducados decrementa se desajusta en cuanto dos
   ejecuciones del cron se solapan, y ninguna constraint lo detecta; el
   derivado no puede desajustarse porque sale de la misma tabla que decide si
   se cobró. El coste es un `COUNT` sobre índice dentro de una sección crítica
   que ya existe.

9. **El endpoint de webhooks es la única ruta de la API sin tenant por
   `Host`.** Todos los endpoints públicos actuales resuelven la organización
   por el `Host` de la petición (`OrganizationDep`,
   `apps/api/app/modules/registrations/public_router.py:1-8`). Stripe llama a
   una URL fija, sin ese `Host`. Por tanto el webhook: (a) verifica la firma
   sobre el **raw body** antes de cualquier parseo — nunca un modelo Pydantic
   en la firma del handler, nunca `await request.json()` antes de
   `construct_event`, porque cualquier manipulación del cuerpo invalida el
   HMAC; (b) resuelve la organización a partir del `event.account`
   (`acct_...`) contra `organization_stripe_accounts`, usando
   `maintenance_session` (`apps/api/app/core/database.py:114-123`), que es el
   mecanismo ya establecido para operaciones sin tenant en contexto; (c) si
   el `acct_id` no resuelve a ninguna organización, responde 200 y no hace
   nada (Stripe reintentaría indefinidamente un 4xx/5xx por un evento que
   nunca podrá procesarse). La ruta real es `/api/v1/webhooks/stripe`: **no
   hay ninguna ruta fuera del prefijo**, todos los routers se montan en el
   mismo `APIRouter(prefix=API_PREFIX)` (`apps/api/app/main.py:36,84-103`).

   **Resolver el tenant no es autorizar la mutación** (hallazgo #2). Con
   Connect Standard el organizador tiene Dashboard y API propios: puede
   firmar eventos legítimos desde **su** cuenta con la `metadata` o el
   `client_reference_id` que quiera. Por tanto el handler (a) localiza el pago
   **exclusivamente** por el identificador que emitió la plataforma
   (`stripe_checkout_session_id`, o `stripe_payment_intent_id` en el
   reembolso, ambos `UNIQUE`), nunca por `metadata` ni `client_reference_id`;
   y (b) exige que `payment.organization_id` coincida con la organización
   resuelta desde `event.account` antes de mutar nada. Si no coincide, el
   evento se marca `failed` con log de seguridad y no toca ninguna fila.

10. **Idempotencia por `event.id` medida sobre el *proceso*, no sobre la
    recepción.** Stripe reenvía el mismo evento ante timeout o 5xx. El
    endpoint: verifica firma → inserta `stripe_webhook_events(id = event.id,
    status = 'received')` → si el `INSERT` choca con la PK, mira el estado de
    la fila existente: `processed`/`ignored` → 200 sin hacer nada;
    `received`/`failed` → **reencola la tarea** y 200. Si no choca, encola y
    200.

    La versión anterior daba por procesado todo lo meramente recibido
    (hallazgo #9, confirmado por dos revisores): un evento perdido entre la
    cola y el worker dejaba dinero cobrado sin inscripción confirmada, para
    siempre, porque el reintento de Stripe chocaba con la PK y se descartaba.
    Correcciones: `status = 'processed'` se escribe **en la misma transacción
    que aplica el efecto de dominio**; la tarea lleva `retry_on_error=True,
    max_retries=5` (que es además el patrón de todas las tareas del proyecto,
    `apps/api/app/core/tasks.py:44,50,73`); y una tarea de barrido reencola
    las filas `received` antiguas y las `failed` con reintentos disponibles,
    escalando a log `ERROR` las que los agoten.

    El procesamiento en segundo plano **relee el payload de la base de
    datos**, nunca del argumento serializado en Redis: el argumento sería una
    segunda copia del evento que podría divergir y que además metería el
    payload de Stripe en la cola. Sin esta tabla, un reenvío duplicado de
    `checkout.session.completed` puede confirmar dos veces (el
    `UNIQUE(registration_id)` de `event_tickets` lo salva por casualidad,
    `apps/api/app/modules/tickets/models.py:55`) y un reenvío de
    `charge.refunded` sumaría dos veces el importe reembolsado — por eso ese
    handler **fija** `refunded_cents` al acumulado que reporta Stripe en vez
    de sumar el delta.

    **Un solo endpoint y un solo secreto, de ámbito «cuentas conectadas»**
    (hallazgo #10). Un webhook de Stripe tiene ámbito: *Your account*
    (`connect: false`) o *Connected accounts* (`connect: true`), y **cada
    endpoint tiene su propio secreto de firma**. Con direct charges, los
    cuatro eventos que consume esta fase llegan por el segundo ámbito: la
    documentación lo dice literalmente —«Direct charges for customers of your
    connected accounts» y «v1 `account.updated` events […] of your connected
    accounts» en el ámbito *Connected accounts*, con
    `account.application.deauthorized` en su tabla de eventos de cuentas
    conectadas— y añade que «Each event for a connected account contains a
    top-level `account` property that identifies the connected account»
    (<https://docs.stripe.com/connect/webhooks>). Por tanto **un** endpoint
    registrado con `connect: true` y **un** `stripe_webhook_secret`: un
    segundo secreto sería un canal sin ningún evento que lo recorra. Dos
    consecuencias obligatorias: un evento **sin** `account` de nivel superior
    se marca `ignored` (sería de ámbito plataforma, al que no estamos
    suscritos), y en local se usa `stripe listen --forward-connect-to`, no
    `--forward-to`.

11. **`stripe_webhook_events` es tabla de instalación, con `REVOKE ALL ...
    FROM app_user`.** Mismo razonamiento y misma corrección que la fase 5
    aplicó a `audit_log`/`cookie_consents` (su hallazgo #1 de red-team):
    `infra/postgres/sql/roles.sql:45,50-51` concede `SELECT, INSERT, UPDATE,
    DELETE` a `app_user` sobre **toda** tabla nueva vía `ALTER DEFAULT
    PRIVILEGES`, así que «sin RLS» no significa «sin acceso» sino «legible y
    borrable por cualquier sesión de organización». El registro de eventos
    procesados es el mecanismo antirreplay: si `app_user` puede borrarlo,
    puede reabrir la ventana de reprocesar un evento ya aplicado. Solo lo
    escribe/lee `app_maintainer` (el endpoint de webhooks y la tarea de
    fondo, ambos con `maintenance_session`), así que el `REVOKE` no rompe
    ningún camino. Precedente exacto en
    `apps/api/alembic/versions/0012_patrocinio_legal_auditoria.py:278-291`.

    **Y su `payload` no es el evento crudo** (hallazgo #15): un
    `checkout.session.completed` incluye `customer_details.email` y
    `customer_details.address`, así que guardar el evento entero convertiría
    esta tabla en un almacén de datos personales sin retención, invisible para
    el borrado RGPD de la fase 5 del PRD. Se persiste una proyección con lista
    blanca de los campos que el handler procesa, y una tarea diaria purga las
    filas con más de `stripe_webhook_retention_days` (90 por defecto). Lo que
    no se procesa, no se guarda.

12. **Dinero en enteros de unidad mínima (céntimos), nunca en float ni
    `Numeric` con decimales libres.** Es lo que espera la API de Stripe
    (`unit_amount`, `amount`) y elimina de raíz cualquier desajuste de
    redondeo entre lo que la plataforma calcula (precio − descuento) y lo que
    Stripe cobra. `currency` se guarda como `char(3)` en minúsculas (formato
    de Stripe), fija por evento, para que un tipo de entrada en euros y otro
    en dólares no puedan compartir una misma Checkout Session — Stripe
    rechazaría la sesión y el error llegaría al asistente, no al organizador.

13. **Bloqueo de venta, no bloqueo de configuración — desde el alta y desde
    la edición.** Se puede crear y editar un evento `paid` y sus tipos de
    entrada sin Stripe conectado (el organizador prepara el evento mientras
    completa el KYC, que en Stripe puede tardar días). Lo que se bloquea es:
    (a) publicar el evento (`status` → `published` con `registration_mode =
    "paid"`) y (b) crear una Checkout Session.

    **La guarda va en una función compartida invocada por `create_event`
    *y* por `update_event`** (hallazgo #4). `create_event`
    (`apps/api/app/modules/events/service.py:33-47`) no valida absolutamente
    nada de estado: hace `Event(organization_id=..., **datos)`, así que un
    evento se puede dar de alta ya `published` y `paid`. Poner la guarda solo
    en `update_event` —que es lo que decía la versión anterior de este plan—
    la dejaba abierta de par en par por el camino más directo. Ambas
    comprueban `charges_enabled = true` en
    `organization_stripe_accounts`, **leído de la base de datos y refrescado
    por `account.updated`**, no consultando a Stripe en cada petición: una
    llamada de red en el camino de publicar o de comprar convierte una caída
    de la API de Stripe en una caída de la página pública del evento.

14. **El reembolso automático extiende `_cancelar_inscripcion`, no lo
    duplica.** `apps/api/app/modules/registrations/service.py:237-274` ya es
    el núcleo compartido de la cancelación por el organizador y de la
    autocancelación pública, y ya llama a `revocar_entrada` (línea 258) y
    promueve la lista de espera. La fase 5 del PRD reutilizó ese mismo
    servicio para el borrado RGPD en vez de hacer un `DELETE` directo (su
    hallazgo #7 de red-team, un `Critical`). Esta fase hace lo mismo:
    `_cancelar_inscripcion` gana un paso **antes** de cambiar el estado. Un
    servicio de reembolso paralelo que también cancelara sería la tercera
    implementación de la misma transición, y la primera que se olvidaría de
    promover la lista de espera.

    **Pero ese paso no llama a Stripe: escribe en un outbox** (hallazgos #11 y
    #12). La mitigación anterior —«emitir el reembolso antes de tomar el
    bloqueo de aforo»— no evitaba nada: los dos llamadores reales ya entran
    con la fila de la inscripción bloqueada (`registrations/service.py:492`,
    `get_registration_for_update`; y `service.py:522`, `session.get(...,
    with_for_update=True)`), así que cualquier llamada de red dentro de
    `_cancelar_inscripcion` ocurre con locks abiertos. Diseño real: la
    cancelación persiste una fila de intención en `event_payment_refunds` y
    hace commit; una tarea la ejecuta contra Stripe con
    `idempotency_key = refund_{id}` derivada de esa PK. Así (a) ninguna
    llamada de red sostiene un bloqueo de fila y (b) es imposible que Stripe
    devuelva dinero sin que exista una fila que lo registre, porque la fila
    precede a la llamada.

    **Y el reembolso automático tiene política, no es incondicional**
    (hallazgo #13): la autocancelación pública usa un token de 90 días
    (`registration_cancel_token_ttl_days = 90`,
    `apps/api/app/core/config.py:106`), sin autenticar, y hoy no comprueba ni
    si el evento ya ocurrió ni si la entrada ya se usó. Reembolsar
    automáticamente exige que el evento no haya empezado, que la entrada no se
    haya usado (`event_tickets.used_at`,
    `apps/api/app/modules/tickets/models.py:66`) y que falten al menos
    `payment_refund_cutoff_hours` para `starts_at`. Fuera de esas condiciones
    la cancelación se aplica igual, sin reembolso automático y con el motivo
    visible en el panel, donde el organizador puede reembolsar a mano.

15. **Reembolso total revoca la entrada; reembolso parcial no.** Un
    reembolso parcial manual es un ajuste de precio (descuento a posteriori,
    corrección de un cobro de más), no una anulación: revocar la entrada
    dejaría a alguien que ha pagado la mayor parte del importe sin poder
    entrar. El panel ofrece una casilla explícita «revocar también la
    entrada» para el caso parcial, desmarcada por defecto. El reembolso
    automático por cancelación es siempre total y siempre revoca. Ver
    Preguntas sin resolver #1: es la única decisión de esta fase que puede
    ser de producto y no de ingeniería.

16. **`PAYMENTS_READ`/`PAYMENTS_WRITE` llegan por las DOS vías, no una.**
    Obligación citada aquí explícitamente porque es un bug ya corregido dos
    veces en el proyecto (`REGISTRATIONS_*` en la fase 4, `SPONSORS_*` en la
    fase 5): el backfill de una migración solo alcanza a las filas de
    `role_permissions` que existían al aplicarla. `OWNER` recibe cualquier
    permiso nuevo automáticamente porque se define como
    `permissions=tuple(Permission)`
    (`apps/api/app/modules/roles/system_roles.py:41`), pero `ORGANIZER`
    enumera los suyos uno a uno (líneas 51-79) — sin tocar esa tupla en
    código, toda organización creada **después** de la migración clona un
    organizador sin permisos de pagos. El prefijo `payments:*` ya está
    reservado en `apps/api/app/core/permissions.py:7`.

## Requirements

- Functional:
  - **Conexión Stripe (organización):** `organization_stripe_accounts` con
    `stripe_account_id` (`acct_...`, único en la instalación),
    `charges_enabled`, `payouts_enabled`, `details_submitted`,
    `connected_at`, `deauthorized_at`, y **una sola cuenta activa por
    organización** (índice único parcial `WHERE deauthorized_at IS NULL`).
    Endpoints de panel: iniciar onboarding (crea `Account` Standard +
    `AccountLink` de tipo `account_onboarding`, devuelve la URL de un solo
    uso), consultar estado, y regenerar el enlace cuando caduca
    (`refresh_url`). Al volver del `return_url` **se consulta el `Account`
    real**, nunca se asume éxito por el mero retorno.
    **Reconexión sin intervención manual:** una organización cuya única fila
    está `deauthorized_at` se trata como «sin cuenta» y puede volver a
    conectar, conservando la fila antigua para poder reembolsar sus pagos.
  - **Tipos de entrada (evento):** `event_ticket_types` con `name`,
    `description`, `price_cents` (entero ≥ 0), `currency`, `max_quantity`
    (nullable = sin límite), `sales_start_at`, `sales_end_at` (ambos
    nullable), `sort_order`, `is_active`. CRUD desde el panel del evento. No
    son reutilizables entre eventos por decisión del enunciado.
  - **Códigos de descuento (evento):** `event_discount_codes` con `code`
    (único por evento, comparado en mayúsculas), `discount_type`
    (`percentage`/`fixed_amount`), `discount_value`, `max_uses` (nullable =
    ilimitado), `valid_from`, `valid_until`, `ticket_type_id` (nullable =
    aplica a todos los tipos del evento). **Sin `used_count`**: el consumo se
    deriva de `event_payments` (Decisión #8). CRUD desde el panel. Endpoint
    público de validación que devuelve el precio final antes de redirigir a
    Stripe.
  - **Compra pública:** en un evento `paid`, el formulario de inscripción
    pide además tipo de entrada y código opcional; crea la inscripción en
    `pending_payment` y devuelve la URL de la Checkout Session hosted. Se
    desbloquea `registration_mode == "paid"` en
    `apps/api/app/modules/registrations/service.py:294-297`. **Los otros tres
    caminos que confirman una inscripción** (verificación de email, aprobación
    manual y promoción de lista de espera) también terminan en
    `pending_payment` en un evento de pago, y reciben su enlace de checkout
    por correo (Decisión #6).
  - **Reintento tras caducar:** una compra abandonada no puede dejar a esa
    persona bloqueada para siempre en el evento por el `UNIQUE(event_id,
    email)` de `event_registrations` (`registrations/models.py:113`). Si el
    pago nunca pasó de `pending`/`expired`, volver a inscribirse reactiva la
    fila y reutiliza la misma fila de pago.
  - **Registro de pagos:** `event_payments` con `registration_id` (nullable,
    `ondelete SET NULL` para que el borrado RGPD no falle), `stripe_account_id`
    (la cuenta donde se cobró), `ticket_type_id`, `discount_code_id`
    (nullable), `stripe_checkout_session_id`, `checkout_url`,
    `checkout_attempts`, `checkout_link_delivered_at`,
    `stripe_payment_intent_id` (nullable hasta que el pago completa),
    `amount_cents`, `discount_cents`, `currency`, `status`
    (`pending`/`paid`/`refunded`/`partially_refunded`/`expired`),
    `refunded_cents`, `paid_at`, `refunded_at`, `expires_at`. Consultable
    desde el panel; **sin ninguna integración contable** (fase 7).
  - **Outbox de reembolsos:** `event_payment_refunds` con `payment_id`,
    `amount_cents`, `reason`, `revoke_ticket`, `status`, `stripe_refund_id`,
    `attempts` y `error`. Es la intención persistida **antes** de llamar a
    Stripe (Decisión #14) y el histórico de reembolsos del panel.
  - **Webhooks:** endpoint público único en `/api/v1/webhooks/stripe`,
    registrado en Stripe **con ámbito de cuentas conectadas**
    (`connect: true`), que verifica la firma con
    `stripe.Webhook.construct_event` sobre el raw body y atiende
    `checkout.session.completed` (solo con `payment_status == "paid"`),
    `charge.refunded`, `account.updated` y
    `account.application.deauthorized`. Idempotencia por `event.id` **medida
    sobre el proceso** en `stripe_webhook_events`, con reencolado de lo
    recibido y no procesado; procesamiento en segundo plano vía taskiq.
  - **Reembolsos:** automático al cancelar una inscripción de pago
    (extendiendo `_cancelar_inscripcion`, no duplicándolo, y **sujeto a la
    política de plazo y uso de la Decisión #14**); manual total o parcial
    desde el panel del organizador. Ambos escriben la misma intención en el
    outbox y los ejecuta la misma tarea, con `Refund.create_async`,
    `idempotency_key` derivada de la PK y el `stripe_account` **de la fila del
    pago**. Reembolso total → `revocar_entrada` (la ya existente, ver Decisión
    #1).
  - **Permisos:** `PAYMENTS_READ`/`PAYMENTS_WRITE`, por backfill a roles
    existentes **y** actualizando la plantilla `ORGANIZER` en
    `system_roles.py` (Decisión #16).
  - **Barrido de `pending_payment` caducados:** tarea programada que libera
    plazas y promueve lista de espera, hermana de
    `expire_waitlist_promotions_task`.
- Non-functional (los cinco primeros salen de
  `plans/reports/researcher-260909-0019-stripe-connect-fase6-pagos.md` §8):
  - **Confusión de `account_id` imposible por construcción:** ninguna
    llamada a Stripe fuera de `payments/stripe_client.py`; el `acct_id`
    procede del `stripe_account_id` de la fila del pago o de la cuenta activa
    resuelta por `organization_id`, **también en el webhook y en las tareas de
    fondo**, que corren sobre `maintenance_session` con `BYPASSRLS` y donde no
    hay contexto RLS que sirva de barrera. Nunca de un parámetro del cliente.
    Test explícito de que un organizador de A no puede disparar un cobro ni un
    reembolso contra la cuenta de B.
  - **Autorización, no solo resolución, en los handlers de webhook:** el pago
    se localiza por el identificador emitido por la plataforma
    (`stripe_checkout_session_id`/`stripe_payment_intent_id`), nunca por
    `metadata`, y se verifica que su `organization_id` coincide con el de
    `event.account` antes de mutar nada.
  - **Idempotencia de eventos duplicados y recuperación de los perdidos:**
    reenviar el mismo `event.id` no produce ningún efecto adicional (ni
    segunda entrada, ni segundo importe reembolsado); y un evento recibido que
    nunca llegó a procesarse **se reencola**, no se descarta. Tests explícitos
    de ambos.
  - **Ninguna llamada de red a Stripe con bloqueos de fila abiertos**, en los
    cuatro caminos (compra, enlaces de pago, barrido de caducados,
    reembolsos), con orden de adquisición de bloqueos único y documentado.
  - **Toda llamada mutante con `idempotency_key` derivada de una PK
    persistida**, y la intención persistida antes de la llamada.
  - **Replay sin firma imposible:** una petición al webhook con firma
    ausente, inválida o con timestamp fuera de la tolerancia recibe 400 y no
    escribe nada; el body nunca se parsea antes de verificar. Test explícito
    para los tres casos.
  - **Mezcla de claves test/live:** validación al arrancar
    (`_validar_produccion` en `apps/api/app/core/config.py:128-135`) — en
    `production`, una `stripe_secret_key` que empiece por `sk_test_` aborta
    el arranque; un error de modo devuelto por Stripe se traduce a un mensaje
    claro para el organizador, no a un 500 genérico.
  - **`client_secret` expuesto: no aplica y queda documentado.** Con
    Checkout hosted la página de pago la aloja Stripe y el frontend solo
    recibe una URL de redirección; no hay `client_secret` de `PaymentIntent`
    en ningún punto del código ni del cliente TypeScript generado. Se
    verifica con un `grep` explícito como criterio de éxito, para que el día
    que alguien migre a Payment Element el hueco sea visible.
  - **RLS multi-tenant** en las **cinco** tablas de dominio
    (`organization_stripe_accounts`, `event_ticket_types`,
    `event_discount_codes`, `event_payments`, `event_payment_refunds`), todas
    con `UNIQUE(id, organization_id)` y FK compuestas contra `(id,
    organization_id)` del padre; test de aislamiento explícito de **lectura y
    escritura cruzada** entre dos organizaciones para cada una.
    `stripe_webhook_events` es de instalación, sin RLS pero con `REVOKE ALL
    ... FROM app_user` y con payload recortado y purga programada (Decisión
    #11).
  - **Secretos opcionales, validados si se informan:** `stripe_secret_key` y
    `stripe_webhook_secret` en `core/config.py` **con valor por defecto
    vacío** — una instalación que no vende nada, y el CI, no deben dejar de
    arrancar por una pasarela que no usan. Si están informados se les aplica la
    validación de longitud mínima, mismo patrón que
    `jwt_secret`/`ticket_qr_secret` (`apps/api/app/core/config.py:116-121`).
    Nunca en base de datos, nunca en logs, nunca en un mensaje de error
    devuelto al cliente.
  - **Sin llamadas síncronas a Stripe** en código async: solo variantes
    `*_async` del SDK (`stripe[async]>=15.6,<16.0`), con timeout explícito.
  - **WCAG 2.1 AA** con cero violaciones de axe en las cuatro pantallas
    nuevas: conexión de Stripe, tipos de entrada, códigos de descuento, y
    pagos/reembolsos; más el paso de compra del formulario público y la
    pantalla de retorno de pago.
  - **Ningún fichero supera las 1000 líneas** — el módulo `payments` sigue la
    convención real del repositorio (un `service.py` por módulo; el mayor del
    proyecto tiene 723 líneas) y se parte solo cuando una fase nueva añade una
    responsabilidad con su propio ciclo de vida: `models.py`, `schemas.py`,
    `repository.py`, `stripe_client.py`, `service.py`, `checkout_service.py`,
    `refunds_service.py`, `webhooks.py`, `router.py`, `public_router.py`. Diez
    ficheros, cada uno creado por **una sola** fase (hallazgo #20; la versión
    anterior preveía catorce con propiedad disputada entre tres fases).
  - `openapi.json` + cliente TypeScript regenerados en cada fase de trabajo
    que toca el backend.

## Success Criteria

- [ ] Una organización conecta su cuenta Stripe desde el panel: se crea un
      `Account` Standard, se redirige al onboarding hosted, y al volver el
      estado real (`charges_enabled`/`payouts_enabled`/`details_submitted`)
      se lee del `Account` consultado, no del mero retorno a `return_url`
- [ ] Un evento `paid` con tipos de entrada se puede crear y editar sin
      Stripe conectado, pero **no** se puede publicar ni generar una Checkout
      Session hasta `charges_enabled = true` — test explícito de cuatro casos
      (crear en borrador: 200; **crear ya publicado: 409**; publicar
      editando: 409; checkout: 409)
- [ ] **Ninguno de los cuatro caminos que confirman una inscripción emite
      entrada sin cobro** en un evento `paid`: alta directa, verificación de
      email, aprobación manual y promoción de lista de espera terminan en
      `pending_payment` — un test por camino, más un test del cinturón de
      seguridad de `_enviar_email_por_estado`
- [ ] Un asistente compra una entrada de pago de extremo a extremo con
      Stripe CLI (`stripe listen --forward-connect-to
      localhost:8000/api/v1/webhooks/stripe` + `stripe trigger
      --stripe-account`): inscripción en `pending_payment` → Checkout →
      `checkout.session.completed` con `payment_status = "paid"` →
      `confirmed` → entrada emitida y correo con QR enviado, con el QR
      escaneando como `valid` en el control de acceso de la fase 4
- [ ] Un `checkout.session.completed` con `payment_status != "paid"`, o cuyo
      `event.account` no corresponde a la organización del pago, **no confirma
      ni emite entrada**
- [ ] Un evento de webhook recibido cuya tarea se perdió se recupera solo: el
      barrido lo reencola y la compra acaba confirmada
- [ ] Una compra abandonada que caduca no bloquea a esa persona: puede volver
      a inscribirse y pagar en el mismo evento
- [ ] Una organización que desconecta su cuenta de Stripe puede reconectarla
      desde el panel, sin tocar la base de datos, y sigue pudiendo reembolsar
      los pagos cobrados con la cuenta anterior
- [ ] La entrada del flujo de pago se emite pasando por
      `_enviar_email_por_estado`
      (`apps/api/app/modules/registrations/service.py:184-207`), no por una
      llamada propia a `emitir_entrada` desde el módulo de pagos — verificado
      por `grep`: `emitir_entrada` no aparece en `app/modules/payments/`
- [ ] Reenviar el mismo `event.id` de `checkout.session.completed` dos veces
      no crea una segunda entrada ni un segundo pago; reenviar el mismo
      `charge.refunded` dos veces no suma dos veces `refunded_cents` — test
      explícito para ambos
- [ ] Una petición al webhook sin cabecera `Stripe-Signature`, con firma
      inválida, y con un timestamp fuera de tolerancia devuelve 400 en los
      tres casos y no escribe ninguna fila en `stripe_webhook_events` ni en
      ninguna otra tabla
- [ ] Un código de descuento con `max_uses = 3` se agota exactamente a los
      3 usos, incluidos 3 intentos concurrentes sobre el mismo código — test
      de concurrencia real, no secuencial
- [ ] Un tipo de entrada con `max_quantity = 2` no vende una tercera entrada
      aunque tres compras se inicien a la vez; el aforo del evento cuenta las
      inscripciones `pending_payment` dentro de su ventana igual que cuenta
      las promociones de lista de espera vigentes
- [ ] Una inscripción `pending_payment` cuya ventana caduca sin pago libera
      su plaza y promueve a la siguiente persona de la lista de espera, vía
      la tarea programada de barrido
<!-- Updated: Validation Session 1 - criterio de la ventana de pago por evento -->
- [ ] La ventana de pago se configura **por evento** en el formulario del
      organizador (precargada a 30 minutos, rango 30-1439) y dos eventos con
      ventanas distintas producen caducidades distintas; no existe ninguna
      variable de entorno que la fije
- [ ] Cancelar una inscripción de pago `confirmed` **dentro de la política de
      reembolso** (desde el panel **y** desde el enlace público de
      autocancelación) deja el reembolso íntegro en curso, revoca la entrada
      con la `revocar_entrada` existente y promueve la lista de espera — sin
      ninguna lógica de cancelación duplicada fuera de `_cancelar_inscripcion`
      y **sin ninguna llamada a Stripe dentro de esa función**
- [ ] Cancelar con el evento ya empezado, con la entrada ya usada o dentro de
      las `payment_refund_cutoff_hours` previas: se cancela **sin** reembolso
      automático, con el motivo visible en el panel
- [ ] Un reembolso cuya escritura posterior falla no duplica el dinero al
      reintentarse: la intención existe antes de la llamada y la
      `idempotency_key` es la misma
- [ ] Un reembolso manual total desde el panel revoca la entrada y el QR
      pasa a rechazarse en el check-in con resultado `revoked`; un reembolso
      parcial **no** la revoca salvo que el organizador marque la casilla
      explícita
- [ ] La entrada revocada por reembolso deja de aceptarse en el control de
      acceso pero **su fila sigue existiendo** en `event_tickets` (no se
      borra), y sus `event_ticket_scans` se conservan
- [ ] Dos organizaciones no ven ni pueden escribir los tipos de entrada,
      códigos de descuento, pagos, reembolsos ni la cuenta Stripe de la otra —
      test de aislamiento de lectura y de escritura cruzada para las cinco
      tablas
- [ ] Un organizador de la organización A no puede disparar un cobro ni un
      reembolso contra el `acct_id` de la organización B, aunque manipule el
      cuerpo de la petición — test explícito
- [ ] `import stripe` no aparece en ningún fichero de `app/` fuera de
      `app/modules/payments/stripe_client.py`; ninguna llamada síncrona del
      SDK (sin sufijo `_async`) dentro de un `async def` — verificado con
      regla de lint, no solo por revisión
- [ ] No existe ningún `client_secret` de Stripe en el backend, en el
      frontend ni en el cliente TypeScript generado (`grep` explícito) — se
      usa Checkout hosted, la página de pago la aloja Stripe
- [ ] Una organización **creada después** de aplicar la migración de esta
      fase tiene `payments:read`/`payments:write` en su rol `organizer`
      clonado, sin intervención manual — no solo una organización de una fase
      anterior (Decisión #16)
- [ ] `has_table_privilege('app_user', 'stripe_webhook_events', 'SELECT')` y
      `'DELETE'` son `false` tras la migración — comprobación negativa
      explícita
- [ ] En `app_env = production`, arrancar con una `stripe_secret_key` que
      empiece por `sk_test_` aborta el arranque con un mensaje explícito;
      arrancar **sin ninguna variable de Stripe** funciona y deja la
      instalación operativa para todo lo que no sea vender
- [ ] Una inscripción en `pending_payment` no rompe con 500 el listado ni las
      estadísticas de inscripciones — el `Literal` de estados y los contadores
      incluyen el estado nuevo
- [ ] `alembic upgrade head` → `downgrade` → `upgrade head` limpio para las
      **seis** tablas nuevas y el backfill de permisos, sin duplicar ni perder
      filas
- [ ] Cero violaciones de axe en las pantallas nuevas (conexión Stripe, tipos
      de entrada, códigos de descuento, pagos y reembolsos, paso de compra del
      formulario público y pantalla de retorno de pago); checklist WCAG
      completado en `docs/accesibilidad.md`
- [ ] `openapi.json` y el cliente TypeScript generado están al día (CI falla
      si no); ningún fichero del repo supera las 1000 líneas
- [ ] `docs/` actualizado: `arquitectura.md` (los cuatro caminos de
      confirmación y dónde vive la guarda de pago, flujo de pago, webhooks de
      ámbito Connect, outbox de reembolsos y métodos de pago diferidos como
      trabajo pendiente), `modelo-de-datos.md` (seis tablas nuevas +
      `pending_payment` + consumo derivado), `accesibilidad.md`, y
      `desarrollo.md` (Stripe CLI en local con `--forward-connect-to`)
- [ ] `ak:code-review` (high) sobre el diff completo de la fase 6 antes de
      cerrarla; `ak:review-pr` antes de cualquier merge

## Fases de trabajo

Las seis son **estrictamente secuenciales** (1 → 2 → 3 → 4 → 5 → 6): la
versión anterior presentaba la 3 como paralelizable con la 2 pese a compartir
cuatro ficheros con ella (hallazgo #20). Cada fichero nuevo lo crea una sola
fase; las posteriores lo amplían con secciones propias.

1. **Modelo de datos, superficie del estado nuevo, permisos y configuración**
   — las seis tablas nuevas (cinco de dominio con RLS y
   `UNIQUE(id, organization_id)`, más `stripe_webhook_events` con `REVOKE ALL
   FROM app_user` y payload recortado), el estado `pending_payment` **junto con
   el `Literal`, las estadísticas, los mensajes públicos y el frontend que lo
   enumeran**, permisos `PAYMENTS_*` por las dos vías, configuración de Stripe
   opcional y validada, dependencia `stripe[async]` y la regla de lint que
   confina `import stripe`.
2. **Conexión Stripe Connect (onboarding, reconexión y bloqueo de venta)** —
   `stripe_client.py` completo, servicio y endpoints de onboarding con Account
   Links, reconexión tras desautorización, pantalla de panel, y la guarda de
   `charges_enabled` compartida por el alta **y** la edición de eventos.
3. **Tipos de entrada, códigos de descuento y cálculo de precio** — CRUD de
   ambos catálogos, validación pública con precio final, consumo derivado de
   cupos y usos, y el contrato de bloqueo y su orden de adquisición.
4. **Compra pública: guarda de pago, Checkout, webhooks y confirmación** —
   desbloqueo de `registration_mode = "paid"`, **guarda de pago en los cuatro
   caminos de confirmación**, `pending_payment` con reserva de plaza, reintento
   tras caducar, Checkout en dos transacciones, endpoint de webhooks firmado
   con idempotencia sobre el proceso, y barridos de caducados y de eventos
   atascados.
5. **Reembolsos con outbox, política de plazo y revocación** — intención
   persistida antes de llamar a Stripe, tarea con `idempotency_key`
   determinística, reembolso manual total/parcial, `charge.refunded` como
   fuente de verdad del importe, y revocación mediante la `revocar_entrada` ya
   existente.
6. **Verificación de extremo a extremo y cierre de fase** — recorrido completo
   con Stripe CLI en modo test, revisión de las diez superficies de riesgo,
   accesibilidad, `docs/`, y `ak:code-review` (high) sobre el diff completo.

## Red Team Review

### Sesión — 2026-09-09
**Revisores:** 4 (Security Adversary, Failure Mode Analyst, Assumption
Destroyer, Scope & Complexity Critic), sobre `plan.md` y las 6 fases de
trabajo. Los 4 verificaron cada afirmación contra el código real (grep/glob),
no contra la lectura del plan.
**Hallazgos:** 38 brutos → 20 tras deduplicar (misma raíz señalada por 2-3
revisores independientes cuenta como una sola). Todos con evidencia
`file:line`, ninguno rechazado por falta de evidencia.
**Severidad:** 9 Critical, 9 High, 2 Medium.
**Confirmado por ≥2 revisores independientes (señal más fuerte de fallo
real, no ruido):** #1 (caminos de confirmación sin pago), #3 (checkout sin
verificar `payment_status`), #7 (reintento bloquea al comprador), #9
(idempotencia por recepción, no por proceso), #10 (secreto único de
webhook), #11 (reembolso sin compensación), #15 (RGPD vs `event_payments`).

| # | Hallazgo | Severidad | Aplicado a |
|---|---|---|---|
| 1 | Solo `submit_registration` se bloquea para eventos de pago; `verify_registration`, `approve_registration` y `confirm_waitlist_promotion` (fase 3-4, ya existentes) también ponen `status="confirmed"` y emiten entrada sin pasar por pago — un evento de pago con verificación de email, aprobación manual, o lista de espera regala entradas | Critical | Fase 4 rediseñada: guarda movida a `_evaluar_estado_por_aforo`/`_enviar_email_por_estado`, no a `submit_registration` |
| 2 | El webhook resuelve la organización por `event.account` pero no verifica que el pago localizado por `metadata`/`client_reference_id` pertenezca a esa misma organización — un organizador (con Dashboard propio en Standard) puede firmar un evento válido contra la cuenta de otra organización | Critical | Fase 4: búsqueda exclusiva por `stripe_checkout_session_id` (`UNIQUE`) + verificación cruzada `organization_id` antes de mutar nada |
| 3 | `checkout.session.completed` se trata como prueba de cobro sin comprobar `payment_status`; métodos de pago diferidos (SEPA, etc., habilitables por el organizador en su propio Dashboard Standard) confirman y emiten entrada sin haber cobrado nunca | Critical | Fase 4: exige `payment_status == "paid"`; documenta restricción a `payment_method_types=["card"]` como límite explícito de esta fase, con `async_payment_succeeded/failed` fuera de alcance documentado, no ignorado en silencio |
| 4 | `create_event` no lleva la guarda de `charges_enabled` (solo `update_event`) — un evento de pago se puede publicar de alta directamente | Critical | Fase 2: guarda extraída a función compartida, invocada por alta y edición |
| 5 | El barrido de `pending_payment` caducados no promueve lista de espera: `liberaba_una_plaza` en `_cancelar_inscripcion` no incluye `pending_payment` en su condición | Critical | Fase 1/4: `liberaba_una_plaza` amplía su condición; test de regresión explícito |
| 6 | `RegistrationStatus` es un `Literal` cerrado en el schema de la API — añadir `pending_payment` a la BD sin tocar el schema/mensajes/stats rompe con 500 el listado de inscripciones en cuanto exista una compra en curso | Critical | Fase 1: actualizar `RegistrationStatus`, `_MENSAJES_POR_ESTADO`, `RegistrationStatsResponse` y el frontend en el mismo cambio que añade el estado a la BD |
| 7 | Una compra `pending_payment`/`cancelled` por caducidad deja al comprador bloqueado para siempre en ese evento (`UNIQUE(event_id, email)`, sin camino de reactivación) | Critical | Fase 4: transición explícita de reintento sobre una fila `cancelled` por caducidad de un evento `paid`, reutilizando la fila de `event_payments` |
| 8 | La mitigación de confusión de `account_id` ("siempre desde el contexto RLS de la petición") no cubre los dos caminos sin petición HTTP (barrido, webhook), ambos sobre `maintenance_session` con `BYPASSRLS` | Critical | Fase 4/5: el `acct_id` se resuelve siempre desde `organization_id` de la fila del pago, verificado contra `organization_stripe_accounts` en el propio wrapper, en los tres caminos |
| 9 | La idempotencia del webhook marca "recibido" (INSERT) no "procesado"; sin `retry_on_error` en la tarea taskiq ni barrido de filas `received`/`failed`, un evento perdido entre la cola y el proceso no se recupera nunca — dinero cobrado sin inscripción confirmada | Critical | Fase 4: idempotencia mide estado procesado, `retry_on_error=True` en la tarea, tarea de barrido de `received`/`failed` antiguos |
| 10 | Un único `stripe_webhook_secret`/endpoint para eventos que con direct charges llegan por **dos canales distintos** (Connect vs plataforma), cada uno con secreto propio — la propia fase 6 lo reconoce con `--forward-connect-to` y las fases 1/4 lo contradicen | High | Fase 1/4: dos secretos o endpoint único marcado explícitamente como de cuentas conectadas, decidido y documentado con cita a la doc de Stripe |
| 11 | Reembolso con éxito en Stripe + fallo de la transacción de BD después = dinero devuelto sin ninguna fila que lo registre; sin `idempotency_key` en las llamadas mutantes, un reintento duplica el reembolso | High | Fase 5: patrón outbox (persistir intención + commit antes de llamar a Stripe) + `idempotency_key` determinística en toda llamada mutante |
| 12 | La mitigación de "reembolso antes del lock de aforo" no evita nada: los dos llamadores reales ya toman `FOR UPDATE` sobre la fila de inscripción *antes* de entrar en `_cancelar_inscripcion` — la llamada de red a Stripe ocurre con locks de fila tomados | High | Fase 5: ninguna llamada de red a Stripe dentro de una transacción con locks de fila abiertos; orden de adquisición único documentado |
| 13 | La autocancelación pública (token de 90 días, sin autenticar) dispara reembolso automático íntegro sin política de plazo, sin comprobar si el evento ya ocurrió ni si la entrada ya se usó | High | Fase 5: política explícita de reembolso (plazo, evento no comenzado, entrada no usada); fuera de esas condiciones, cancela sin reembolso automático |
| 14 | `stripe_secret_key`/`stripe_webhook_secret` obligatorios sin valor por defecto rompen el arranque de instalaciones que no venden nada (y CI, que escribe el `.env` con los secretos actuales) | High | Fase 1: campos con default vacío, validación de longitud solo si están informados |
| 15 | El borrado RGPD (fase 5 del PRD, ya en producción) colisiona con `event_payments` (sin `ondelete` declarado en la FK a `event_registrations`) y `stripe_webhook_events.payload` retiene PII (email, dirección) sin ninguna retención ni relación con el borrado | High | Fase 1: `ondelete="SET NULL"` + anonimización explícita del pago en el borrado RGPD; purga programada o payload recortado en `stripe_webhook_events` |
| 16 | `payment_checkout_window_minutes = 30` por defecto garantiza que la primera Checkout Session falle: Stripe exige `expires_at` ≥ 30 min **desde la creación de la sesión**, y el plan calcula `payment_expires_at` antes, con la misma cifra exacta | High | Fase 4: `expires_at` de Stripe se calcula en el instante de crear la sesión; `payment_expires_at` de la inscripción se fija desde la respuesta de Stripe, no al revés; margen técnico de `+ 60 s` sobre la ventana del evento, cuyo rango válido es 30-1439 minutos (<!-- Updated: Validation Session 1 - antes «mínimo de configuración > 30», ahora rango de la columna `events.payment_checkout_window_minutes` -->) |
| 17 | Desconectar la cuenta de Stripe (`account.application.deauthorized`) es irreversible desde la plataforma: ninguna fase describe la reconexión, y el `UNIQUE(organization_id)` más la rama "si ya hay fila, no crea cuenta" bloquean cualquier intento posterior | High | Fase 2: onboarding trata una fila con `deauthorized_at` como "sin cuenta"; criterio de éxito explícito de reconexión sin intervención manual en BD |
| 18 | `stripe.error.StripeError` no existe en el SDK a partir de la v13 (shims de módulo eliminados); el plan fija "mínimo v13" y pide capturar esa excepción — el primer error de Stripe sería un 500 opaco, justo lo que el plan quiere evitar | Medium | Fase 2: `stripe.StripeError` del módulo raíz; pin de versión corregido a la última estable con `[async]` |
| 19 | `used_count` de un código de descuento es incrementable **y decrementable** por el barrido de caducados sin guarda de idempotencia (a diferencia del incremento, que sí usa `FOR UPDATE`); dos ejecuciones solapadas del cron lo desajustan | Medium | Fase 3/4: decremento condicionado al estado del pago en la misma sentencia que marca `expired`, o derivar el consumo de `event_payments` en vez de mantener un contador mutable en dos direcciones |
| 20 | El módulo `payments` se parte en ~14 ficheros contra la convención del repo (ningún módulo existente lo hace; el mayor `service.py` del proyecto tiene 723 líneas en un único fichero), y tres fases (2, 3, 5) se disputan la propiedad de los mismos ficheros (`repository.py`, `schemas.py`, `router.py`) pese a presentarse como paralelizables | Medium | Fases 2/3/5 reescritas con propiedad de fichero exclusiva por fase; desglose ajustado a la convención real del repo |

**Hallazgos de calidad/alcance no aplicados por ser alcance ya confirmado por
el usuario** (Scope Critic, correctamente marcados como preguntas, no como
recorte): reembolso parcial revocando o no la entrada, visibilidad de
`payouts_enabled`/`details_submitted` en el panel, devolución de uso de
código de descuento al reembolsar — quedan en "Preguntas sin resolver"
abajo, no se tocan sin respuesta del usuario.

**Correcciones factuales menores aplicadas sin ser hallazgos de diseño:**
`_evaluar_estado_por_aforo` es el nombre real de la función (el plan mezclaba
ese nombre con `_evaluar_estado_por_capacidad`, que es una función interna
distinta); no existe ningún prefijo `/api/v1` "fuera" del webhook — todos los
routers, incluido el de webhooks, se montan bajo el mismo `API_PREFIX`, así
que la URL real de Stripe CLI es `/api/v1/webhooks/stripe`, no
`/webhooks/stripe`.

### Whole-Plan Consistency Sweep
- Ficheros releídos: `plan.md`, las 6 `phase-0N-*.md` (pendiente tras la
  reescritura de las fases 1, 2, 3, 4 y 5 — ver nota abajo).
- Deltas de decisión: 20 (lista de arriba).
- **Reescritura completada** (ver la entrada de abajo): las fases 1-5 se
  reescribieron enteras y la 6 se ajustó. Las Decisiones #4, #5, #6, #7, #8,
  #9, #10, #11, #13 y #14, los Requirements, los Success Criteria y el
  desglose de fases de `plan.md` quedan alineados con esa reescritura.
- Contradicciones sin resolver: 0.

### Reescritura tras red-team — 2026-09-09

Reescritas por completo las fases de trabajo 1-5 (no parches) y ajustada la
fase 6. **Los 20 hallazgos quedan aplicados**, con estas dos precisiones
explícitas:

| # | Dónde queda aplicado |
|---|----------------------|
| 1 | Fase 4, secciones «Diseño de la guarda» y «Flujo completo de los cuatro caminos»; Decisión #6 reescrita. Guarda en `_evaluar_estado_por_capacidad` (cubre alta, verificación y aprobación) **y** en `confirm_waitlist_promotion`, más cinturón de seguridad en `_enviar_email_por_estado` |
| 2 | Fase 4 (handler de `checkout.session.completed`) y fase 5 (`charge.refunded`): búsqueda solo por identificador emitido por la plataforma + verificación cruzada de `organization_id`; Decisión #9 ampliada |
| 3 | Fase 4: `payment_status == "paid"` obligatorio, `payment_method_types=["card"]`, y `async_payment_*` documentado como fuera de alcance en `docs/arquitectura.md` (fase 6) |
| 4 | Fase 2: `_asegurar_venta_posible` invocada desde `create_event` **y** `update_event`; Decisión #13 reescrita |
| 5 | Fase 4: `liberaba_una_plaza` incluye `pending_payment` vigente, con la misma condición que `count_reserved_registrations`; Decisión #5 ampliada |
| 6 | Fase 1: `RegistrationStatus`, `RegistrationStats`, `get_registration_stats`, `_MENSAJES_POR_ESTADO`, `registration-types.ts` y cliente generado, en el mismo cambio que el estado |
| 7 | Fase 4: reactivación de una fila `cancelled` cuyo pago nunca pasó de `pending`/`expired`, reutilizando la fila de `event_payments` |
| 8 | Fases 2, 4 y 5: el `acct_id` sale de `event_payments.stripe_account_id` o de la cuenta activa resuelta por `organization_id`, con tipo propio en el wrapper; Decisión #7 ampliada |
| 9 | Fase 4: idempotencia por estado procesado, escritura de `processed` en la misma transacción del efecto, `retry_on_error=True`, barrido de `received`/`failed`; Decisión #10 reescrita |
| 10 | Fase 4 y Decisión #10: **un** endpoint de ámbito «cuentas conectadas» con **un** secreto, con cita a <https://docs.stripe.com/connect/webhooks>; eventos sin `account` → `ignored`; `--forward-connect-to` en local |
| 11 | Fase 5: outbox `event_payment_refunds` + `idempotency_key` derivada de la PK; fase 4: `idempotency_key` de la sesión derivada de `event_payments.id` + `checkout_attempts` |
| 12 | Fases 3, 4 y 5: orden de adquisición único y documentado, checkout en dos transacciones, reembolso fuera de `_cancelar_inscripcion` |
| 13 | Fase 5 y Decisión #14: política de reembolso automático (evento no empezado, entrada no usada, `payment_refund_cutoff_hours`) |
| 14 | Fase 1: secretos con default vacío, validación de longitud solo si están informados, `payments_enabled` |
| 15 | Fase 1: FK `SET NULL (registration_id)`, payload recortado con lista blanca y purga programada; Decisión #11 ampliada |
| 16 | Fase 4: `expires_at` calculado en el instante de la llamada, con `+ 60 s` de margen técnico, y `payment_expires_at` fijado desde la respuesta de Stripe; fase 1: rango validado 30-1439 en la columna del evento (<!-- Updated: Validation Session 1 - la mitigación pasa de mínimo de configuración global a rango de la columna del evento + margen -->) |
| 17 | Fases 1 y 2: índice único parcial de cuenta activa, reconexión tratando `deauthorized_at` como «sin cuenta», y `stripe_account_id` en la fila del pago; Decisión #4 ampliada |
| 18 | Fases 1 y 2: `stripe.StripeError` del módulo raíz y `stripe[async]>=15.6,<16.0` (verificado contra el changelog del SDK y contra PyPI: 15.6.1) |
| 19 | Fases 1 y 3: eliminada la columna `used_count`; consumo de códigos y cupos derivado de `event_payments`; Decisión #8 ampliada |
| 20 | Fases 2-5: diez ficheros en `payments/`, cada uno creado por una sola fase, con la fase 3 declarada dependiente de la 2 (fin de la propiedad disputada) |

**Precisiones, no excepciones:**

1. El hallazgo #1 se resuelve en `_evaluar_estado_por_capacidad`, **no** en
   `_evaluar_estado_por_aforo` como sugería la columna «Aplicado a» de la
   tabla. Verificado en código: `approve_registration`
   (`registrations/service.py:444`) llama directamente a
   `_evaluar_estado_por_capacidad`, saltándose `_evaluar_estado_por_aforo`; y
   `confirm_waitlist_promotion` (línea 556) no llama a ninguna de las dos.
   Poner la guarda en `_evaluar_estado_por_aforo` habría dejado abiertos los
   caminos 3 y 4 — exactamente el fallo que el hallazgo denuncia.
2. El hallazgo #10 se cierra con **un solo secreto**, no con dos, tras
   verificar la documentación de Stripe: los cuatro eventos que consume esta
   fase (`checkout.session.completed` y `charge.refunded` de direct charges,
   `account.updated` y `account.application.deauthorized` de cuentas
   conectadas) llegan **todos** por el ámbito *Connected accounts*. Dos
   secretos habrían creado un segundo canal sin ningún evento que lo
   recorriera. Lo que sí se corrige es la contradicción que el hallazgo
   señalaba: el endpoint queda declarado explícitamente como de cuentas
   conectadas y en local se usa `--forward-connect-to`, no `--forward-to`.

Los tres puntos que el Scope Critic marcó como «preguntas, no recortes»
(reembolso parcial y su efecto sobre la entrada, visibilidad de
`payouts_enabled`/`details_submitted`, devolución de uso de código al
reembolsar) **no se han decidido** aquí; siguen abajo como preguntas abiertas.
La reescritura ha añadido dos preguntas nuevas (#4 y #5), que tampoco se
deciden sin el usuario.

## Validation Log

### Session 1 — 2026-09-09
**Trigger:** `/ak:plan validate` tras el red-team y la reescritura de fases.
**Questions asked:** 6 (5 preguntas del plan + 1 aclaración sobre alcance de
la ventana de pago, surgida de la respuesta del usuario a la pregunta 2).

#### Questions & Answers

1. **[Producto]** Reembolso parcial, ¿revoca la entrada o no?
   - Options: Parcial no revoca salvo casilla (Recomendado) | Todo reembolso
     revoca siempre
   - **Answer:** Parcial no revoca salvo casilla
   - **Rationale:** confirma la Decisión #15 tal como estaba escrita — un
     reembolso parcial es un ajuste de precio, no una anulación.
2. **[Producto]** Ventana de `pending_payment`, ¿qué duración?
   - Options: 30 min (Recomendado) | 60 min | 15 min
   - **Answer (aclaración del usuario):** «¿Se puede configurar en el
     evento?» — pregunta de alcance, no de valor. Se relanzó como pregunta
     de alcance (ver #2b).
2b. **[Arquitectura]** ¿La ventana de pago es global de instalación o
    configurable por evento?
    - Options: Global, 30 min por defecto (Recomendado) | Por evento,
      configurable al crearlo
    - **Answer:** Por evento, configurable al crearlo
    - **Rationale:** eventos distintos (muy demandados vs. con margen)
      pueden necesitar políticas distintas; el usuario lo prefiere explícito
      en el formulario de evento en vez de un único valor de instalación.
    - **Valor por defecto:** 30 minutos, precargado en el formulario y
      editable por el organizador al crear/editar el evento de pago.
3. **[Alcance]** ¿Multi-divisa necesaria ahora?
   - Options: No, solo euros (Recomendado) | Sí, multi-divisa ahora
   - **Answer:** No, solo euros
   - **Rationale:** confirma la Decisión #12 sin cambios — ningún evento
     previsto necesita otra divisa.
4. **[Producto]** Borrado RGPD de quien pagó, ¿reembolsa automáticamente?
   - Options: Sí, reembolsar automáticamente (Recomendado) | No, borrar sin
     reembolsar
   - **Answer:** Sí, reembolsar automáticamente
   - **Rationale:** confirma que el borrado RGPD es una cancelación como
     cualquier otra a efectos de reembolso; la fila de pago sobrevive con
     `registration_id NULL` para el registro económico.
5. **[Alcance]** ¿Se permite recomprar tras un reembolso, en esta fase?
   - Options: No permitir en esta fase (Recomendado) | Permitir recompra
     ahora
   - **Answer:** No permitir en esta fase
   - **Rationale:** límite conocido y acotado; evita la complejidad de
     soportar varias filas de pago por inscripción. Documentado como
     limitación conocida, no como olvido.

#### Confirmed Decisions
- Reembolso parcial nunca revoca automáticamente (casilla explícita para
  hacerlo manualmente) — Decisión #15 sin cambios.
- **Ventana de `pending_payment` pasa de configuración global a campo por
  evento**: columna `events.payment_checkout_window_minutes` (`NOT NULL
  DEFAULT 30`, `CHECK BETWEEN 30 AND 1439`), con 30 minutos precargados y
  editables en el formulario del evento. **Esto es un cambio respecto a la
  Decisión #5 original**, que la asumía como ajuste de configuración de
  instalación.
  <!-- Updated: Validation Session 1 - granularidad resuelta: `events`, no `event_ticket_types` -->
  **Granularidad resuelta en la propagación:** vive en `events` y no en
  `event_ticket_types`. Un pago es de **un solo** tipo de entrada
  (`event_payments.ticket_type_id` es una columna simple, fase 1), pero lo
  que la ventana protege es la **plaza**, y la plaza es del evento: el aforo
  (`events.capacity`) y la fila que la retiene
  (`event_registrations.payment_expires_at`, una por `(event_id, email)`)
  son de nivel evento. Con la ventana por tipo de entrada, una misma fila de
  inscripción podría quedar sujeta a dos caducidades distintas sin ninguna
  regla que dijera cuál gana.
- Divisa única por evento, `eur` por defecto — sin cambios.
- Borrado RGPD reembolsa automáticamente — confirma el diseño ya escrito en
  la fase 5 reescrita, sin cambios de código necesarios.
- Recompra tras reembolso: fuera de alcance de esta fase, documentado como
  limitación conocida.

#### Action Items
- [x] Fase 1: `payment_checkout_window_minutes` sale de `core/config.py` y
      pasa a ser la columna `events.payment_checkout_window_minutes`
      (`NOT NULL DEFAULT 30`, `CHECK BETWEEN 30 AND 1439`), con su migración,
      su modelo, sus schemas y sus criterios de éxito. No queda ningún ajuste
      de instalación equivalente.
- [x] Fase 2: el formulario de evento (`event-form.ts`) expone el campo de
      ventana de pago, precargado a 30 minutos, editable, con validación de
      rango espejo en el cliente.
- [x] Fase 4: el cálculo de `expires_at`/`payment_expires_at` lee
      `evento.payment_checkout_window_minutes` (con `+ 60 s` de margen
      técnico al llamar a Stripe), no `get_settings()`.

#### Impact on Phases
- Fase 1 (Modelo de datos): columna nueva de ventana de pago por evento en
  vez de config global; Success Criteria actualizados.
- Fase 2 (Conexión Stripe / formulario de evento): campo nuevo en el
  formulario correspondiente.
- Fase 4 (Checkout y confirmación): lee la ventana del evento, no de
  `get_settings()`.

### Whole-Plan Consistency Sweep (Validation Session 1)
- Ficheros releídos: `plan.md` (el cambio de la pregunta 2b se delegó al
  planificador en una pasada posterior, no inline, para mantener la
  reescritura completa en un solo lugar — **ya propagado**, ver la pasada
  post-propagación).
- Deltas de decisión comprobados: 5 (reembolso parcial confirmado sin
  cambio; ventana de pago cambia de global a por-evento; divisa confirmada
  sin cambio; RGPD+reembolso confirmado sin cambio; recompra tras reembolso
  confirmada fuera de alcance).
- Referencias obsoletas a reconciliar en la próxima pasada: toda mención de
  `payment_checkout_window_minutes` como ajuste de `core/config.py` en las
  fases 1, 2 y 4 pasa a ser un campo del evento — **reconciliadas** en la
  pasada post-propagación (también en la fase 6, que la listaba como variable
  de entorno).
- Contradicciones sin resolver: **0** — resueltas en la pasada de
  propagación descrita justo debajo.

### Whole-Plan Consistency Sweep (post-propagación)
Pasada acotada al único cambio de decisión de la pregunta 2b. No se reabrió
ningún otro hallazgo del red-team.

- Ficheros releídos y editados: `phase-01-*.md`, `phase-02-*.md`,
  `phase-04-*.md`, `plan.md`. Releídos sin cambios de fondo: `phase-03-*.md`
  (para verificar la relación compra↔tipos de entrada antes de decidir dónde
  vive la columna) y `phase-05-*.md`. `phase-06-*.md` editado solo para
  retirar `PAYMENT_CHECKOUT_WINDOW_MINUTES` de la lista de variables de
  entorno documentadas.
- Elección de tabla: **`events.payment_checkout_window_minutes`**, no
  `event_ticket_types`. Justificación en Confirmed Decisions.
- Rango: `CHECK BETWEEN 30 AND 1439` y `Field(ge=30, le=1439)`. El hallazgo
  #16 sigue mitigado, pero por otra vía: en vez de un mínimo de 31 en la
  configuración, la Checkout Session se crea con `+ 60 s` de margen técnico
  sobre la ventana del evento (fase 4), lo que permite honrar el «30 minutos
  por defecto» que pidió el usuario sin que Stripe rechace la primera sesión.
  El máximo 1439 sale del límite de 24 h de Stripe menos ese margen.
- Verificación por `grep` sobre el directorio del plan: no queda ninguna
  mención de `payment_checkout_window_minutes` como ajuste de
  `core/config.py` ni de `PAYMENT_CHECKOUT_WINDOW_MINUTES` como variable de
  entorno en ninguna de las seis fases ni en `plan.md`. Las únicas menciones
  restantes son la columna del evento, sus validaciones, su lectura en la
  fase 4 y el registro histórico del red-team (fila 16), anotado con el
  cambio de mitigación.
- Propiedad de ficheros: la columna y sus schemas (`events/models.py`,
  `events/schemas.py`) son de la fase 1; el campo del formulario
  (`event-form.ts`) es de la fase 2; `events/service.py` sigue siendo de la
  fase 2. Ninguna otra fase toca esos ficheros, así que el cambio no crea
  propiedad disputada.
- Contradicciones sin resolver: 0.
