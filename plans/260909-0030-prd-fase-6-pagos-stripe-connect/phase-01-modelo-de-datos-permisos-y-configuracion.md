---
phase: 1
title: "Fase 1: Modelo de datos, superficie de API del estado nuevo, permisos y configuración"
status: pending
priority: P1
effort: "2.5-3d"
dependencies: []
---

# Fase 1: Modelo de datos, superficie de API del estado nuevo, permisos y configuración

## Overview

Esquema, permisos y configuración sobre los que se apoyan las fases 2-5. Nada
de esta fase llama todavía a Stripe.

Cambio respecto a la versión anterior de esta fase (hallazgo #6 del red-team):
**añadir `pending_payment` a la base de datos sin actualizar en el mismo
cambio la superficie de API que enumera los estados rompe con 500 el listado
de inscripciones en cuanto exista una compra en curso.** `RegistrationStatus`
es un `Literal` cerrado en `apps/api/app/modules/registrations/schemas.py:10-17`
y `RegistrationStats` enumera un contador por estado
(`schemas.py:141-153`). Por tanto el estado nuevo y toda su superficie de
lectura entran juntos, en esta fase.

**Ficheros creados en esta fase:**
`apps/api/alembic/versions/0013_pagos_stripe_connect.py`,
`apps/api/app/modules/payments/__init__.py`,
`apps/api/app/modules/payments/models.py`.

**Ficheros existentes que amplía esta fase (ninguna otra fase los toca en el
mismo punto):** `apps/api/app/core/permissions.py`,
`apps/api/app/modules/roles/system_roles.py`, `apps/api/app/core/config.py`,
`apps/api/pyproject.toml`, `apps/api/tests/conftest.py`,
`apps/api/app/modules/events/models.py` y
`apps/api/app/modules/events/schemas.py` (solo la ventana de pago por evento;
la fase 2 toca `events/service.py`, que es otro fichero),
`apps/api/app/modules/registrations/schemas.py` (enum + stats),
`apps/api/app/modules/registrations/public_router.py` (solo
`_MENSAJES_POR_ESTADO`, líneas 44-48),
`apps/api/app/modules/registrations/service.py` (solo el `dict` de retorno de
`get_registration_stats`, líneas 618-628),
`apps/web/src/app/features/admin/events/registration-types.ts` y el cliente
TypeScript generado.

## Requirements

- Functional:
  - `organization_stripe_accounts` — `id`, `organization_id`,
    `stripe_account_id` (`String(255)`, `UNIQUE` en toda la instalación: es la
    clave por la que el webhook resuelve el tenant), `charges_enabled`,
    `payouts_enabled`, `details_submitted` (los tres `Boolean NOT NULL DEFAULT
    false`), `connected_at` (nullable), `deauthorized_at` (nullable),
    `last_synced_at` (nullable), más `TimestampMixin` como el resto del
    esquema (`apps/api/app/modules/tickets/models.py:78` lo usa en
    `EventTicketScan`).
    - **Índice único parcial `uq_organization_stripe_accounts_activa ON
      organization_stripe_accounts (organization_id) WHERE deauthorized_at IS
      NULL`, no `UNIQUE(organization_id)`** (hallazgo #17): una organización
      tiene **una cuenta activa**, pero conserva el histórico de las
      desconectadas. Con `UNIQUE(organization_id)` a secas, una organización
      que desconecta su cuenta no puede volver a conectarse nunca sin tocar la
      base de datos a mano, y además se perdería el `acct_id` con el que se
      cobraron los pagos antiguos (necesario para reembolsarlos).
    - `UNIQUE(id, organization_id)` para poder ser destino de una FK
      compuesta. FK simple `organization_id → organizations.id
      ondelete=CASCADE` (mismo patrón que `organization_branding`,
      `apps/api/app/modules/organizations/models.py:75-93`).
  - `event_ticket_types` — `id`, `event_id`, `organization_id`, `name`
    (`String(160)`), `description` (`Text`, nullable), `price_cents`
    (`Integer NOT NULL`, `CHECK >= 0`), `currency` (`String(3) NOT NULL
    DEFAULT 'eur'`, minúsculas), `max_quantity` (`Integer`, nullable = sin
    límite, `CHECK > 0`), `sales_start_at`, `sales_end_at` (nullable),
    `sort_order`, `is_active`. FK compuesta `(event_id, organization_id) →
    events (id, organization_id)` `ondelete=CASCADE`.
    `UNIQUE(id, organization_id)`, `UNIQUE(event_id, name)`.
    `CHECK (sales_end_at IS NULL OR sales_start_at IS NULL OR sales_end_at >
    sales_start_at)`.
  - `event_discount_codes` — `id`, `event_id`, `organization_id`, `code`
    (`String(60)`, guardado en mayúsculas), `discount_type` (`CHECK IN
    ('percentage','fixed_amount')`), `discount_value` (`Integer`, con dos
    `CHECK` condicionados por `discount_type`: 1..100 si `percentage`, `> 0`
    si `fixed_amount` — mismo patrón que el `CheckConstraint` por tipo de
    `event_registration_questions`, `apps/api/app/modules/registrations/
    models.py:61-67`), `max_uses` (`Integer`, nullable = ilimitado, `CHECK >
    0`), `valid_from`/`valid_until` (nullable), `ticket_type_id` (nullable =
    todos los tipos). FK compuesta al evento (`CASCADE`) y FK compuesta
    `(ticket_type_id, organization_id) → event_ticket_types (id,
    organization_id)` sin `ondelete` (RESTRICT). `UNIQUE(event_id, code)`,
    `UNIQUE(id, organization_id)`.
    - **Sin columna `used_count`** (hallazgo #19). El consumo de un código es
      **derivado**: `COUNT(event_payments WHERE discount_code_id = X AND
      status IN ('pending','paid','partially_refunded','refunded'))`. Un
      contador mutable en dos direcciones (lo incrementa la compra, lo
      decrementa el barrido de caducados) se desajusta en cuanto dos
      ejecuciones del cron se solapan, y no hay ninguna constraint que lo
      detecte. El derivado no puede desajustarse: es la misma tabla que decide
      si se cobró. El coste es un `COUNT` sobre índice dentro de la sección
      crítica de la compra, despreciable a la escala de este producto.
  - `event_payments` — `id`, `organization_id`, `event_id`, `registration_id`
    (**nullable**), `stripe_account_id` (`String(255) NOT NULL`),
    `ticket_type_id`, `discount_code_id` (nullable),
    `stripe_checkout_session_id` (`String(255)`, nullable hasta que se crea la
    sesión, `UNIQUE`), `checkout_url` (`Text`, nullable),
    `checkout_attempts` (`Integer NOT NULL DEFAULT 0`),
    `checkout_link_delivered_at` (nullable), `stripe_payment_intent_id`
    (`String(255)`, nullable, `UNIQUE`), `amount_cents`, `discount_cents`
    (`DEFAULT 0`), `currency`, `status` (`CHECK IN
    ('pending','paid','refunded','partially_refunded','expired')`),
    `refunded_cents` (`DEFAULT 0`), `paid_at`, `refunded_at`, `expires_at`.
    - `stripe_account_id` **se copia en la fila del pago**, no se consulta a
      la organización en el momento de reembolsar (hallazgos #8 y #17): un
      pago cobrado en una cuenta que después se desconectó solo se puede
      reembolsar contra **esa** cuenta.
    - `UNIQUE(registration_id)` — una inscripción, un pago. Un reintento tras
      caducar reutiliza la fila (hallazgo #7), no crea una segunda.
    - FK compuesta `(registration_id, organization_id) → event_registrations
      (id, organization_id)` con **`ondelete="SET NULL (registration_id)"`**
      (hallazgo #15): el borrado RGPD (`apps/api/app/modules/admin/
      service.py:206-253`) borra la fila de `event_registrations`; sin
      `ondelete` declarado, ese borrado falla con `IntegrityError` en cuanto
      exista un pago. La lista de columnas es obligatoria: un `SET NULL` a
      secas sobre una FK compuesta intentaría anular también
      `organization_id`, que es `NOT NULL` (Postgres 16, `infra/docker-compose.yml:9`,
      admite `SET NULL (column_list)`; PG15+). El registro económico
      sobrevive al borrado de la persona sin conservar ningún dato personal:
      `event_payments` no guarda email ni nombre.
    - FK compuestas contra `event_ticket_types` y `event_discount_codes` sin
      `ondelete` (no se borra un tipo ni un código con pagos hechos).
      `UNIQUE(id, organization_id)`. Índices `(event_id, status)` (consulta
      del panel) y `(discount_code_id)` (consumo derivado del código).
  - `event_payment_refunds` — `id`, `organization_id`, `payment_id`,
    `amount_cents`, `reason` (`CHECK IN ('cancellation','manual')`),
    `revoke_ticket` (`Boolean NOT NULL`), `status` (`CHECK IN
    ('pending','submitted','succeeded','failed')`), `stripe_refund_id`
    (`String(255)`, nullable, `UNIQUE`), `attempts` (`Integer NOT NULL DEFAULT
    0`), `error` (`Text`, nullable), `submitted_at` (nullable), más
    `TimestampMixin`. FK compuesta `(payment_id, organization_id) →
    event_payments (id, organization_id)` `ondelete=CASCADE`.
    `UNIQUE(id, organization_id)`. Índice `(status)`.
    - Es la **intención de reembolso persistida antes de llamar a Stripe**
      (hallazgos #11 y #12): sin ella, un reembolso que Stripe acepta y cuya
      transacción de base de datos falla después es dinero devuelto sin
      ninguna fila que lo registre. La `idempotency_key` que se envía a Stripe
      se **deriva** de esta PK (`refund_{id}`), no se guarda en otra columna:
      así un reintento de la tarea no puede generar una clave distinta.
  - `stripe_webhook_events` — `id` (`String(255)` PK: el `evt_...` de Stripe),
    `event_type` (`String(80)`), `stripe_account_id` (`String(255)`,
    nullable), `organization_id` (nullable), `payload` (`JSONB NOT NULL`,
    **recortado**, ver más abajo), `status` (`CHECK IN
    ('received','processed','ignored','failed')`), `attempts` (`Integer NOT
    NULL DEFAULT 0`), `last_attempt_at` (nullable), `error` (`Text`,
    nullable), `received_at`, `processed_at` (nullable). Tabla de
    instalación: **sin RLS, con `REVOKE ALL ON stripe_webhook_events FROM
    app_user`** y sin ningún `GRANT` de vuelta (Decisión #11 del plan;
    precedente exacto en `apps/api/alembic/versions/
    0012_patrocinio_legal_auditoria.py:278-291`).
    - `payload` **no es el evento crudo de Stripe** (hallazgo #15): un
      `checkout.session.completed` incluye `customer_details.email` y
      `customer_details.address`. Se persiste una proyección con lista blanca
      de campos: `id`, `type`, `account`, `created`, `livemode` y, de
      `data.object`, solo `id`, `payment_status`, `status`, `amount_total`,
      `currency`, `payment_intent`, `charges`/`refunds` agregados y las tres
      claves de `metadata` que escribe la plataforma. Lo que no se procesa no
      se guarda.
  - Columna nueva `event_registrations.payment_expires_at`
    (`DateTime(timezone=True)`, nullable), hermana de
    `waitlist_promotion_expires_at` (`apps/api/app/modules/registrations/
    models.py:140-142`).
  <!-- Updated: Validation Session 1 - la ventana de pago pasa de ajuste global de `core/config.py` a columna del evento -->
  - **Columna nueva `events.payment_checkout_window_minutes`** (`Integer NOT
    NULL DEFAULT 30`), junto a `capacity` y `registration_mode`
    (`apps/api/app/modules/events/models.py:73-75`). Es **la ventana que tiene
    un comprador para pagar antes de que su `pending_payment` caduque y libere
    la plaza**, decidida por evento y no por instalación (validación, sesión 1).
    - **Vive en `events`, no en `event_ticket_types`.** Justificación: la
      ventana es una política sobre la **plaza reservada**, y la plaza es un
      recurso del evento — el aforo (`events.capacity`) y la fila que la
      retiene (`event_registrations.payment_expires_at`, una por
      `(event_id, email)`, `registrations/models.py:113`) son ambos de nivel
      evento. Un valor por tipo de entrada dejaría dos ventanas posibles para
      una misma fila de inscripción y para un mismo aforo, sin ninguna regla
      que dijera cuál gana.
    - `CHECK (payment_checkout_window_minutes BETWEEN 30 AND 1439)` (hallazgo
      #16, que sigue aplicando igual de por-evento que de global). Stripe
      admite un `expires_at` de Checkout Session **entre 30 minutos y 24 horas
      desde la creación de la sesión**; la fase 4 envía `now + ventana + 60 s`
      de margen técnico, así que 30 es el mínimo seguro y 1439 el máximo que no
      se pasa de las 24 horas. El margen se añade siempre, sin ramas: la
      ventana real de la plataforma se toma de la respuesta de Stripe, nunca
      es más corta que la configurada.
    - `EventCreate`/`EventUpdate`/`EventResponse`
      (`apps/api/app/modules/events/schemas.py:70-81`, `105-116`, `134`) ganan
      el campo con `Field(ge=30, le=1439)` y `= 30` por defecto en el alta, de
      forma que el rango se rechaza en el schema **y** en la base de datos.
  - **Estado nuevo `pending_payment` y toda su superficie de lectura, en el
    mismo cambio** (hallazgo #6):
    - `EventRegistration.status` sigue siendo `String(30)` libre
      (`registrations/models.py:135`): no hay constraint de base de datos que
      actualizar, solo el comentario del enum (líneas 133-134).
    - `RegistrationStatus` (`registrations/schemas.py:10-17`) gana
      `"pending_payment"`.
    - `RegistrationStats` (`registrations/schemas.py:141-153`) gana
      `pending_payment: int`, y `get_registration_stats`
      (`registrations/service.py:618-628`) lo informa desde el `dict` que ya
      devuelve `count_registrations_by_status`.
    - `_MENSAJES_POR_ESTADO` (`registrations/public_router.py:44-48`) gana la
      entrada `"pending_payment"` («Tu plaza está reservada; completa el pago
      para confirmarla.»). Sin ella, la respuesta pública de verificación o de
      confirmación de promoción se quedaría sin mensaje para un estado que sí
      puede devolver.
    - Frontend: `apps/web/src/app/features/admin/events/
      registration-types.ts:13,21` (el `Literal` y la lista de estados
      filtrables) y regeneración del cliente TypeScript, que hoy fija los seis
      valores en tres ficheros generados
      (`src/app/core/api/generated/models/registration-list-item.ts:14`,
      `registration-detail.ts:21`, y el `fn/` del listado).
  - Permisos `PAYMENTS_READ = "payments:read"` y `PAYMENTS_WRITE =
    "payments:write"` en `app/core/permissions.py`, retirando `payments:*` de
    la lista de prefijos reservados del docstring (línea 7).
  - Configuración nueva en `app/core/config.py`:
    - `stripe_secret_key: str = ""` y `stripe_webhook_secret: str = ""`
      (**con valor por defecto vacío**, hallazgo #14): una instalación que no
      vende nada, y el CI que escribe su propio `.env`, no deben dejar de
      arrancar por dos secretos de una pasarela que no usan.
    - Propiedad derivada `payments_enabled` = ambos secretos informados. Los
      endpoints de pagos devuelven 503 con mensaje explícito cuando es
      `False`, y un evento `paid` no se puede publicar.
    <!-- Updated: Validation Session 1 - `payment_checkout_window_minutes` deja de ser un ajuste de instalación -->
    - **No hay ningún ajuste de ventana de checkout en `core/config.py`.** La
      ventana es la columna `events.payment_checkout_window_minutes` descrita
      arriba; no queda ningún valor de instalación equivalente al que caer,
      porque la columna es `NOT NULL DEFAULT 30`.
    - `payment_refund_cutoff_hours: int = 24` (hallazgo #13: plazo del
      reembolso automático, se consume en la fase 5).
    - `stripe_webhook_retention_days: int = 90` (purga de
      `stripe_webhook_events`, hallazgo #15).
  - Dependencia `stripe[async]` en `apps/api/pyproject.toml` con rango
    `>=15.6,<16.0` (hallazgo #18): la última estable publicada es 15.6.1 y el
    extra `async` existe (`httpx; extra == "async"`). El rango anterior del
    plan («mínimo v13») era correcto pero el plan pedía capturar
    `stripe.error.StripeError`, que **no existe desde la v13**: su changelog
    dice literalmente «Removed deprecated module shims […] we removed:
    `stripe.stripe_response`, `stripe.stripe_object`, `stripe.error_object`,
    `stripe.error`». La excepción a capturar es `stripe.StripeError`, del
    módulo raíz.
- Non-functional:
  - RLS `tenant_<tabla>` (`organization_id = app_current_organization()`, con
    `FORCE ROW LEVEL SECURITY`) en las **cinco** tablas de dominio
    (`organization_stripe_accounts`, `event_ticket_types`,
    `event_discount_codes`, `event_payments`, `event_payment_refunds`), misma
    forma que `0012_patrocinio_legal_auditoria.py:268-276`. Test de
    aislamiento de lectura **y de escritura cruzada** para las cinco.
  - `REVOKE ALL ON stripe_webhook_events FROM app_user` en la misma migración,
    con comprobación **negativa** en test (`has_table_privilege(...)` = `false`
    para `SELECT` y `DELETE`).
  - `PAYMENTS_READ`/`PAYMENTS_WRITE` por las **dos** vías (Decisión #16 del
    plan): backfill idempotente (`WHERE NOT EXISTS`, anclado al permiso
    `organizations:write`, no al nombre del rol — mismo SQL que
    `0012_patrocinio_legal_auditoria.py:296-322`) **y** ambos añadidos a
    `ORGANIZER.permissions` (`apps/api/app/modules/roles/
    system_roles.py:51-79`). `OWNER` los hereda solo por
    `permissions=tuple(Permission)` (línea 41).
  - Validación de modo test/live: `_validar_produccion`
    (`app/core/config.py:128-145`) aborta el arranque si `app_env ==
    "production"` y `stripe_secret_key` está informada y empieza por
    `sk_test_`. La validación de longitud mínima reutiliza `_validar_secreto`
    (líneas 116-121) **solo cuando el valor no está vacío** — el validador
    actual es incondicional, así que se le añade la guarda de vacío en vez de
    encadenar los campos nuevos a la lista tal cual.
  - Regla de lint que confina `import stripe` a
    `app/modules/payments/stripe_client.py`: `flake8-tidy-imports`
    (`[tool.ruff.lint.flake8-tidy-imports.banned-api]`) más
    `per-file-ignores` para ese único fichero, sobre la configuración ya
    existente en `pyproject.toml:51-62`.
  - Las **seis** tablas nuevas se añaden a `TABLAS` de
    `apps/api/tests/conftest.py:78-97`. `stripe_webhook_events` es obligatoria
    por el mismo motivo documentado allí para `audit_log`/`cookie_consents`:
    no tiene ninguna FK con `CASCADE` hacia una tabla ya listada, así que el
    `TRUNCATE ... CASCADE` no la alcanza y un `evt_...` escrito por un test
    haría que el siguiente lo tomara por duplicado.
  - `payments/models.py` estimado ~300 líneas (solo modelos, sin lógica).
    Ningún fichero de la fase supera las 1000.

## Implementation Steps

1. Paquete `apps/api/app/modules/payments/` con `__init__.py` vacío y
   `models.py` (las seis tablas, con el porqué de cada decisión en el
   comentario del propio modelo, como hace el resto del esquema).
2. Migración `0013_pagos_stripe_connect` (`down_revision =
   "0012_patrocinio_legal_auditoria"`): `create_table` de las seis tablas,
   índice único parcial de la cuenta activa, `add_column` de
   `event_registrations.payment_expires_at`, `add_column` de
   `events.payment_checkout_window_minutes` (`server_default="30"` para que la
   columna `NOT NULL` se aplique sobre eventos existentes, retirando después el
   `server_default` si el modelo fija el valor por defecto en Python — el mismo
   criterio que el resto del esquema) con su `CHECK` de rango, y `downgrade()`
   simétrico.
   <!-- Updated: Validation Session 1 - la migración añade la ventana de pago por evento -->
   También `events/models.py` y `events/schemas.py` con el campo nuevo.
3. En la misma migración: RLS + política `tenant_<tabla>` en las cinco tablas
   de dominio; `REVOKE ALL ON stripe_webhook_events FROM app_user`.
4. En la misma migración: backfill idempotente de `payments:read`/
   `payments:write` a los roles con `organizations:write`.
5. `app/core/permissions.py` y `app/modules/roles/system_roles.py`.
6. `app/core/config.py`: secretos con default vacío, `payments_enabled`,
   plazo de reembolso, retención de webhooks (**sin** ajuste de ventana de
   checkout: es columna del evento); guarda de vacío en `_validar_secreto`; regla `sk_test_` en
   `_validar_produccion`. Documentar todo en `.env.example`.
7. Superficie del estado `pending_payment`: `RegistrationStatus`,
   `RegistrationStats`, `get_registration_stats`, `_MENSAJES_POR_ESTADO`,
   `registration-types.ts` y regeneración del cliente TypeScript.
8. `pyproject.toml`: `stripe[async]>=15.6,<16.0` y la regla `banned-api`.
9. `tests/conftest.py`: las seis tablas nuevas en `TABLAS`.
10. Tests: ciclo de migración, privilegios (positivos en las cinco de dominio,
    **negativos** en `stripe_webhook_events`), aislamiento RLS de lectura y
    escritura cruzada, permisos por las dos vías, arranque con `sk_test_` en
    `production`, arranque **sin** secretos de Stripe, borrado de una
    inscripción con pago asociado, listado de inscripciones con una fila en
    `pending_payment`, y **rango y valor por defecto de
    `events.payment_checkout_window_minutes`** (schema y `CHECK`).

## Success Criteria

- [ ] `alembic upgrade head` → `downgrade -1` → `upgrade head` limpio, y
      también `downgrade base` → `upgrade head` desde cero, sin duplicar ni
      perder filas de permisos
- [ ] Dos organizaciones no pueden leer ni escribir `organization_stripe_accounts`,
      `event_ticket_types`, `event_discount_codes`, `event_payments` ni
      `event_payment_refunds` de la otra — test de lectura y de escritura
      cruzada para las cinco (diez casos)
- [ ] `has_table_privilege('app_user', 'stripe_webhook_events', 'SELECT')` y
      `'DELETE'` son `false`; comprobación positiva sobre las cinco tablas de
      dominio
- [ ] Una organización con `deauthorized_at` informado puede tener una
      **segunda** fila activa en `organization_stripe_accounts`; dos filas
      activas (`deauthorized_at IS NULL`) para la misma organización son
      rechazadas por el índice único parcial — test de ambos casos
- [ ] Borrar una `event_registrations` que tiene un `event_payments` asociado
      **no falla** y deja el pago con `registration_id IS NULL` y su
      `organization_id` intacto — test que ejecuta el borrado RGPD real
      (`admin.service.borrar_inscrito_por_email`), no un `DELETE` suelto
- [ ] Una organización de una fase anterior tiene `payments:read`/`write` en
      su rol `owner` tras la migración, sin intervención manual
- [ ] Una organización **creada después** de la migración tiene
      `payments:read`/`payments:write` en su rol `organizer` clonado — test
      que crea la organización tras aplicar la migración
- [ ] `GET /events/{id}/registrations` y `/registrations/stats` responden 200
      con una inscripción en `pending_payment` en la base de datos, y el
      contador `pending_payment` aparece en las estadísticas — test explícito
      (es el 500 del hallazgo #6)
- [ ] Insertar un `event_ticket_type` con `price_cents < 0`, un
      `event_discount_code` `percentage` con `discount_value = 150`, o uno
      `fixed_amount` con `discount_value = 0` es rechazado por la base de
      datos, no solo por el servicio
- [ ] No existe ninguna columna `used_count` en `event_discount_codes` —
      verificado sobre el esquema aplicado, no sobre el modelo
- [ ] Arrancar con `APP_ENV=production` y `STRIPE_SECRET_KEY=sk_test_...`
      aborta con mensaje explícito; arrancar **sin** ninguna variable de
      Stripe arranca con normalidad y `payments_enabled` es `False`; un
      secreto informado por debajo de la longitud mínima aborta
<!-- Updated: Validation Session 1 - la ventana de pago se valida por evento, no por variable de entorno -->
- [ ] Un evento existente antes de la migración queda con
      `payment_checkout_window_minutes = 30` sin intervención manual; crear un
      evento sin enviar el campo también da 30
- [ ] `POST`/`PATCH` de un evento con `payment_checkout_window_minutes = 29` o
      `= 1440` devuelve 422 citando el rango; `30` y `1439` se aceptan. Un
      `UPDATE` directo en base de datos con 29 es rechazado por el `CHECK`, no
      solo por el schema
- [ ] `grep -rn "payment_checkout_window_minutes" apps/api/app/core/` no
      devuelve nada: la ventana no es un ajuste de instalación
- [ ] `import stripe` en cualquier fichero de `app/` distinto de
      `payments/stripe_client.py` hace fallar el lint — verificado ejecutando
      ruff sobre un fichero de prueba con ese import
- [ ] Un test que escribe en `stripe_webhook_events` y otro que asume la tabla
      vacía, en el mismo run de la suite completa, no se contaminan
- [ ] `openapi.json` y el cliente TypeScript generado al día (el `Literal` de
      estados incluye `pending_payment` en los tres ficheros generados)

## Risk & Rollback

- Riesgo: `ondelete="SET NULL (registration_id)"` es sintaxis de Postgres 15+
  que SQLAlchemy emite literalmente. Si la cadena se escribiera mal, el fallo
  aparece al aplicar la migración, no en tiempo de ejecución — y el test de
  borrado RGPD lo cubre de todos modos. Nota: el esquema actual ya tiene un
  `ondelete="SET NULL"` sobre una FK compuesta cuyo segundo miembro es `NOT
  NULL` (`apps/api/app/modules/tickets/models.py:49-54`); ese caso solo
  fallaría al borrar un `event_members`, y queda **fuera del alcance de esta
  fase** (se anota aquí porque es el mismo error que este diseño evita, no
  para arreglarlo de paso).
- Riesgo: retirar `used_count` mueve el control de usos de un contador a un
  `COUNT` derivado. El riesgo se traslada a la fase 3/4: ese `COUNT` **debe**
  ejecutarse con la fila del código bloqueada (`FOR UPDATE`), o dos compras
  concurrentes leerán el mismo total. El test de concurrencia de la fase 4 es
  lo único que lo demuestra, y por eso es criterio de éxito allí.
- Riesgo: `stripe_account_id` es `UNIQUE` en toda la instalación, no por
  organización — intencionado (el webhook resuelve el tenant por ese valor),
  y significa que dos organizaciones no pueden compartir cuenta de Stripe. Es
  la semántica correcta de Connect; se documenta en el modelo para que no se
  «corrija» a un único compuesto que rompería la resolución del webhook.
- Riesgo: el ciclo `downgrade` → `upgrade` del backfill devuelve `payments:*`
  a todo rol con `organizations:write`, incluso si alguien lo había revocado a
  mano. Es el patrón ya aceptado en las fases 2-5, no se rediseña aquí.
<!-- Updated: Validation Session 1 - rollback de la columna de ventana por evento -->
- Riesgo: `events.payment_checkout_window_minutes` es `NOT NULL` sobre una
  tabla con filas. Mitigación: `server_default="30"` en el `add_column`, que
  rellena los eventos existentes en la propia migración; el `downgrade` es un
  `drop_column` sin pérdida de nada consumido (ninguna fase anterior lee la
  columna).
- Rollback: las seis tablas son aditivas y sin consumidor todavía. De las dos
  columnas añadidas a tablas existentes, `payment_expires_at` es nullable y
  `payment_checkout_window_minutes` tiene valor por defecto.
  Los cambios en la superficie de API son aditivos: un valor más en un
  `Literal` y un contador más en las estadísticas, ambos compatibles hacia
  atrás para un cliente que no los conozca.
