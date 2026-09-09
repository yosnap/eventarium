---
phase: 2
title: "Fase 2: Conexión Stripe Connect (onboarding, reconexión y bloqueo de venta)"
status: completed
priority: P1
effort: "2.5-3d"
dependencies: [1]
---

# Fase 2: Conexión Stripe Connect (onboarding, reconexión y bloqueo de venta)

## Overview

La organización conecta su cuenta de Stripe desde el panel, puede
**reconectarla** si la desconectó, y un evento de pago no se puede publicar
—ni por alta ni por edición— sin `charges_enabled`.

Aquí nace `stripe_client.py`, el único punto del código que habla con Stripe.
Cambio respecto a la versión anterior (hallazgo #20): **esta fase escribe el
wrapper completo**, incluidas las funciones que consumen las fases 4 y 5
(checkout, reembolso, verificación de firma). Son envoltorios de una línea
sobre el SDK; repartirlos entre tres fases era justo la propiedad disputada
que el red-team señaló, y además dejaba la traducción de errores del SDK
implementada tres veces.

**Ficheros creados en esta fase:**
`apps/api/app/modules/payments/stripe_client.py`,
`apps/api/app/modules/payments/repository.py`,
`apps/api/app/modules/payments/service.py`,
`apps/api/app/modules/payments/schemas.py`,
`apps/api/app/modules/payments/router.py`,
`apps/web/src/app/core/payments/payments.service.ts`,
`apps/web/src/app/features/admin/organization/stripe-connection.ts` (+ spec).

**Ficheros existentes que amplía:** `apps/api/app/modules/events/service.py`
(la guarda compartida), `apps/api/app/main.py` (registro del router),
`apps/web/src/app/app.routes.ts`,
<!-- Updated: Validation Session 1 - el formulario de evento expone la ventana de pago -->
`apps/web/src/app/features/admin/events/event-form.ts` (+ su spec y los textos
de Transloco): campo de la ventana de pago. Ninguna otra fase toca ese fichero
(la fase 3 solo lo cita como patrón de fecha/hora accesible y la fase 4 toca el
formulario **público** `features/public/events/event-registration-form.ts`).

Las fases 3, 4 y 5 **amplían** `repository.py`, `schemas.py`, `service.py` y
`router.py`, cada una con secciones propias; no hay propiedad disputada porque
las fases son estrictamente secuenciales (3 depende de 2, 4 de 3, 5 de 4).

## Requirements

- Functional:
  - `stripe_client.py` — wrapper único y completo sobre el SDK:
    - `crear_cuenta_conectada()`, `crear_enlace_onboarding()`,
      `consultar_cuenta()`, `crear_sesion_checkout()`, `crear_reembolso()`,
      `verificar_firma_webhook()`.
    - **Firma tipada, no `str`** (hallazgo #8): toda función que opera sobre
      una cuenta conectada recibe un `OrganizationStripeAccount` (o el
      `stripe_account_id` ya leído de una fila de `event_payments`), nunca un
      `acct_id` suelto proveniente de un parámetro del cliente. El único
      resolutor es `repository.get_cuenta_activa(session, organization_id)`,
      que devuelve la fila activa (`deauthorized_at IS NULL`) o `None`. Esto
      cubre también los dos caminos **sin petición HTTP** (webhook y tareas de
      fondo, ambos sobre `maintenance_session`, `apps/api/app/core/
      database.py:114-123`), donde no hay contexto RLS que actúe de barrera:
      allí el `organization_id` sale de la fila del pago y la cuenta se
      resuelve igual, con la misma función.
    - Todas las llamadas usan variantes `*_async` del SDK.
    - Toda llamada **mutante** acepta un `idempotency_key` obligatorio
      (hallazgo #11); las fases 4 y 5 lo derivan de una PK persistida.
    - Traduce `stripe.StripeError` (**del módulo raíz**: `stripe.error` no
      existe desde la v13, hallazgo #18) y sus subclases a errores de dominio
      del proyecto, para que ningún router devuelva el mensaje crudo de
      Stripe. `app/shared/errors.py` ya tiene `ServiceUnavailableError`
      (línea 66), que cubre el «pagos no configurados»; para el fallo de la
      pasarela se añade `ExternalServiceError` en el mismo módulo, siguiendo
      la forma de las seis clases existentes (líneas 41-66).
    - Timeout explícito en el cliente del SDK: una llamada sin timeout dentro
      de una tarea de fondo bloquea un worker indefinidamente.
  - `POST /organizations/{id}/stripe/onboarding` (`PAYMENTS_WRITE`):
    - Si no hay fila activa **o la única fila está `deauthorized_at`**
      (hallazgo #17), crea un `Account` Standard y persiste una **fila nueva**
      antes de pedir el `AccountLink`. El índice único parcial de la fase 1
      permite exactamente esto: una cuenta activa por organización, con el
      histórico de las desconectadas intacto para poder reembolsar pagos
      antiguos.
    - Si ya hay fila activa, genera un `AccountLink` nuevo sobre la **misma**
      cuenta. Nunca crea una segunda cuenta activa: un `acct_id` huérfano no
      se puede borrar desde la API.
    - Devuelve la URL de un solo uso. No se persiste, no se cachea, no se
      envía por correo.
    - 503 si `payments_enabled` es `False` (fase 1).
  - `GET /organizations/{id}/stripe` (`PAYMENTS_READ`) — estado **persistido**
    (`connected`, `charges_enabled`, `payouts_enabled`, `details_submitted`,
    `deauthorized_at`, `last_synced_at`). No llama a Stripe (Decisión #13 del
    plan).
  - `POST /organizations/{id}/stripe/sync` (`PAYMENTS_WRITE`) — consulta el
    `Account` real y refresca las banderas. Lo invoca el frontend al volver del
    `return_url` y el botón manual «actualizar estado». `limit_per_ip` propio
    (`STRIPE_SYNC_POR_IP` en `app/core/ratelimit.py`): es la única ruta del
    panel que provoca una llamada de red a Stripe por petición.
  - **Guarda de venta compartida, invocada desde el alta y desde la edición**
    (hallazgo #4). `apps/api/app/modules/events/service.py:33-47`
    (`create_event`) **no valida nada de estado**: acepta `status` en `datos` y
    hace `Event(**datos)` directamente, así que un evento se puede crear ya
    `published` con `registration_mode="paid"`. `update_event` (líneas 55-82)
    solo llama a `_validar_transicion_de_estado` (líneas 50-52), que únicamente
    protege `archived`.
    - Se añade `_asegurar_venta_posible(session, organization_id, *, status,
      registration_mode)` en `events/service.py`, invocada por **ambas**.
    - Se evalúa sobre el **evento resultante**: en `update_event`, con
      `datos.get("status", evento.status)` y
      `datos.get("registration_mode", evento.registration_mode)`, para que un
      `PATCH` que cambia los dos campos a la vez quede bloqueado igual.
    - Condición: si el resultante es `published` **y** `paid`, exige
      `payments_enabled` y una cuenta activa con `charges_enabled = true`; si
      no, `ConflictError` con mensaje accionable.
    - Crear y editar un evento `paid` en borrador sigue permitido (Decisión
      #13 del plan): el KYC de Stripe tarda días y el organizador prepara el
      evento mientras tanto.
  <!-- Updated: Validation Session 1 - ventana de pago editable por evento en el formulario del organizador -->
  - **Campo «ventana de pago» en el formulario de evento**
    (`apps/web/src/app/features/admin/events/event-form.ts`): entrada numérica
    en minutos, **precargada a 30** al crear un evento y con el valor guardado
    al editarlo, con texto de ayuda que explica que es el tiempo que tiene un
    comprador para pagar antes de que su plaza se libere, y que solo se aplica
    a eventos de pago.
    - Validación de rango en el cliente (`min="30"`, `max="1439"`,
      `inputmode="numeric"`, error asociado por `aria-describedby` como el
      resto de campos del formulario) **espejo** de la del backend. La
      validación autoritativa es la de `EventCreate`/`EventUpdate` y el `CHECK`
      de la columna, ambos entregados en la fase 1 junto al modelo: aquí no se
      duplica la regla en Python, solo se refleja en la UI.
    - El campo se muestra siempre en el formulario, no condicionado a
      `registration_mode`: el formulario de evento actual (`event-form.ts`, 478
      líneas) **no gestiona hoy `registration_mode` ni `capacity`**, así que
      condicionarlo exigiría añadir a esta fase un control que nadie ha pedido.
      El texto de ayuda basta para explicar cuándo aplica.
  - Panel: pantalla de conexión con tres estados visuales (sin conectar /
    conectada sin `charges_enabled` / operativa), un cuarto estado
    «desconectada» con acción de reconectar, y el aviso de que la plataforma no
    cobra comisión y no custodia el dinero.
- Non-functional:
  - Ningún fichero fuera de `stripe_client.py` importa `stripe` (regla de lint
    de la fase 1). Ningún servicio acepta un `acct_id` desde el body o la
    query.
  - `return_url`/`refresh_url` se construyen con el dominio propio de la
    organización, reutilizando el helper `_base_url_de_organizacion`
    (`apps/api/app/core/tasks.py:125-148`), no con `web_base_url` a secas: en
    multi-tenant por `Host`, devolver al organizador al dominio equivocado le
    saca de su sesión. El helper es privado del módulo de tareas: se extrae a
    `app/core/tenant.py` (que ya existe) y `tasks.py` pasa a importarlo desde
    allí, en vez de duplicarlo.
  - Los secretos de Stripe no aparecen en ningún log ni en ninguna respuesta.
  - `openapi.json` + cliente TypeScript regenerados.
  - WCAG 2.1 AA: el cambio de estado tras volver del onboarding se anuncia en
    una región `aria-live`; el botón que redirige a Stripe advierte de que se
    abandona el sitio.
  - Tamaños estimados: `stripe_client.py` ~230, `repository.py` ~180 (crece
    en fases posteriores), `service.py` ~200 (crece en la fase 3),
    `router.py` ~150, `schemas.py` ~120. Muy por debajo de 1000.

## Implementation Steps

1. `payments/stripe_client.py` completo, con la traducción de errores y el
   timeout, y las seis funciones (las de checkout/reembolso/firma quedan
   escritas aquí aunque se llamen en las fases 4 y 5).
2. `payments/repository.py`: `get_cuenta_activa`,
   `get_cuenta_por_stripe_account_id`, `crear_cuenta`, `actualizar_estado`,
   `marcar_desautorizada`.
3. `payments/service.py`: crear o recuperar cuenta, reconectar tras
   desautorización, generar enlace, sincronizar estado.
4. `payments/schemas.py` + `payments/router.py` + registro en `app/main.py`
   (tras `sponsors_router`, siguiendo el orden de las líneas 84-103).
5. Extraer `_base_url_de_organizacion` a `app/core/tenant.py` y ajustar
   `tasks.py`.
6. `events/service.py`: `_asegurar_venta_posible` invocada desde
   `create_event` y `update_event`, con sus tests.
7. Frontend: `payments.service.ts`, pantalla `stripe-connection.ts` y su ruta.
   <!-- Updated: Validation Session 1 - campo de ventana de pago en el formulario de evento -->
8. Frontend: campo de ventana de pago en `event-form.ts` (precargado a 30,
   rango 30-1439, texto de ayuda y traducciones), con su spec.
9. `openapi.json` + cliente TypeScript regenerados.

## Success Criteria

- [x] Un `owner`/`organizer` completa el onboarding hosted en modo test y al
      volver el panel muestra `charges_enabled = true` leído del `Account`
      consultado, no asumido por el retorno a `return_url` — verificado con
      el cliente Stripe simulado (`test_payments_router.py`, la pantalla
      sincroniza siempre al volver del onboarding, nunca asume éxito)
- [x] Llamar dos veces al endpoint de onboarding genera dos enlaces distintos
      sobre **el mismo** `stripe_account_id` — sin crear una segunda cuenta
      (`test_doble_onboarding_no_crea_segunda_cuenta_pero_genera_dos_urls`)
- [x] Tras marcar la cuenta como desautorizada, un onboarding nuevo **crea una
      cuenta nueva y deja la organización operativa otra vez**, sin ninguna
      intervención manual en base de datos, y la fila antigua se conserva con
      su `deauthorized_at` (hallazgo #17) —
      `test_reconexion_tras_desautorizacion_crea_cuenta_nueva_sin_intervencion_manual`
- [x] **Crear** un evento directamente con `status = "published"` y
      `registration_mode = "paid"` sin `charges_enabled` devuelve 409 —
      test explícito sobre `POST /events`, no solo sobre `PATCH` (hallazgo #4)
      — `test_crear_evento_paid_publicado_sin_stripe_da_409`
- [x] **Editar** un evento a `published` + `paid` en el mismo `PATCH` devuelve
      409; con `charges_enabled = true` devuelve 200; la guarda evalúa el
      evento resultante, no el actual —
      `test_publicar_editando_a_paid_sin_stripe_da_409` /
      `test_publicar_evento_paid_con_charges_enabled_funciona`
- [x] Crear y editar un evento `paid` en borrador funciona sin Stripe
      conectado; solo la publicación está bloqueada —
      `test_crear_evento_paid_en_borrador_sin_stripe_funciona` /
      `test_editar_evento_paid_en_borrador_sin_stripe_funciona`
- [x] Con `payments_enabled = False` (sin secretos configurados), los tres
      endpoints de Stripe devuelven 503 con mensaje explícito y publicar un
      evento `paid` devuelve 409 — la instalación sigue funcionando para todo
      lo demás — `test_pagos_deshabilitados_devuelve_503_en_los_tres_endpoints`,
      `test_publicar_evento_paid_sin_payments_enabled_da_409`
- [x] `GET /organizations/{id}/stripe` no produce ninguna llamada de red a
      Stripe — verificado contando llamadas al cliente simulado
      (`test_get_status_no_produce_ninguna_llamada_de_red_a_stripe`)
- [x] Un organizador de la organización A recibe 404/403 al pedir el estado de
      Stripe de B, y no puede iniciar un onboarding sobre el `acct_id` de B
      aunque lo envíe en el cuerpo — las funciones del wrapper no aceptan un
      `acct_id` de tipo `str` proveniente de la petición (verificado por firma
      de tipos y por test) —
      `test_una_organizacion_no_puede_leer_ni_conectar_el_stripe_de_otra`
- [x] Un error del SDK (`stripe.StripeError`) llega al panel como mensaje
      claro con código 502, nunca como 500 con el texto crudo de Stripe — test
      que lo lanza desde el cliente simulado —
      `test_error_del_sdk_en_onboarding_llega_como_502` y
      `test_error_del_sdk_se_traduce_a_external_service_error`
- [x] `grep -rn "stripe.error" app/` no devuelve nada; `import stripe` no
      aparece fuera de `payments/stripe_client.py` (lint en verde) —
      verificado con `grep` y con `ruff check app/`
<!-- Updated: Validation Session 1 - criterios del campo de ventana de pago -->
- [x] El formulario de alta de evento muestra la ventana de pago precargada a
      **30 minutos**; el de edición muestra el valor guardado del evento —
      `event-form.spec.ts`
- [x] Guardar el formulario con 29 o con 1440 minutos se bloquea en el cliente
      con error asociado al campo y, si se fuerza la petición, el backend
      devuelve 422 — test de ambos lados (`event-form.spec.ts` +
      `test_events_payment_checkout_window.py`, entregado en la fase 1)
- [x] Un evento creado sin tocar el campo queda con 30 en base de datos
      (`test_un_evento_nuevo_toma_30_minutos_por_defecto`, fase 1)
- [x] Cero violaciones de axe en la pantalla de conexión y en el formulario de
      evento con el campo nuevo; el cambio de estado
      al volver del onboarding se anuncia en una región `aria-live` —
      `stripe-connection.spec.ts` y `event-form.spec.ts`
- [x] `openapi.json` y el cliente TypeScript generado al día

## Risk & Rollback

- Riesgo: crear un `Account` en Stripe **no es reversible desde la
  plataforma**. Si la cuenta se crea y falla la persistencia del `acct_id`,
  queda huérfana en el Dashboard del organizador y el siguiente intento
  crearía otra. Mitigación: persistir la fila con el `acct_id` **antes** de
  pedir el `AccountLink`, y tolerar una fila con `acct_id` sin onboarding
  completado — que es exactamente el estado «conectada sin `charges_enabled`»
  que la UI ya contempla.
- Riesgo: el estado persistido puede quedar obsoleto si el webhook
  `account.updated` (fase 4) no llega. Por eso el endpoint de sincronización
  manual existe desde esta fase y no se difiere.
- Riesgo: el `AccountLink` caduca en minutos. La pantalla debe ofrecer
  «generar un enlace nuevo» en vez de dejar al organizador en un callejón sin
  salida.
- Riesgo: escribir en esta fase funciones del wrapper que nadie llama todavía
  (checkout, reembolso, firma) es código sin consumidor durante dos fases. Se
  acepta a propósito: la alternativa medida por el red-team era peor
  (propiedad disputada del mismo fichero por tres fases y la traducción de
  errores duplicada). Cada función lleva su test unitario contra el cliente
  simulado desde esta fase, así que no queda sin cobertura.
- Rollback: la guarda de venta es la única modificación sobre código de fases
  anteriores; es una condición añadida que solo puede afectar a eventos
  `paid`, que hoy no existen porque el modo está bloqueado en
  `registrations/service.py:294-297`. El resto es aditivo y su router se
  retira de `main.py` en un commit.
