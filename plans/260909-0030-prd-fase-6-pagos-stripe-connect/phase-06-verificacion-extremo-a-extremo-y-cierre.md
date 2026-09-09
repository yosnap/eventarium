---
phase: 6
title: "Fase 6: Verificación de extremo a extremo y cierre de fase"
status: pending
priority: P1
effort: "1-1.5d"
dependencies: [1, 2, 3, 4, 5]
---

# Fase 6: Verificación de extremo a extremo y cierre de fase

## Overview

Fase sin funcionalidad nueva: recorre la fase 6 del PRD completa contra
Stripe en modo test, revisa una por una las seis superficies de riesgo de la
investigación, cierra accesibilidad y documentación, y pasa `ak:code-review`
(high) sobre el diff completo antes de dar la fase por terminada.

Existe como fase propia porque los riesgos de pagos no se verifican por
partes: la idempotencia, la confusión de `account_id` y la coherencia entre
la base de datos y Stripe solo se comprueban de verdad con el flujo entero
montado.

**Ficheros propios de esta fase:** `docs/arquitectura.md`,
`docs/modelo-de-datos.md`, `docs/accesibilidad.md`, `docs/desarrollo.md`, y
el reporte de fase en
`plans/260909-0030-prd-fase-6-pagos-stripe-connect/reports/`.

## Requirements

- Functional:
  - **Recorrido completo en modo test con Stripe CLI**, documentado paso a
    paso. El endpoint es **único y de ámbito «cuentas conectadas»** (fase 4,
    hallazgo #10), así que en local se usa `stripe listen
    --forward-connect-to localhost:8000/api/v1/webhooks/stripe` —con el
    prefijo `/api/v1`, que es la ruta real: todos los routers, incluido el de
    webhooks, se montan bajo `API_PREFIX` (`apps/api/app/main.py:36,84-103`)—
    y `stripe trigger --stripe-account <acct_id> <evento>`. El recorrido
    cubre: conectar cuenta → crear evento de pago con dos tipos de entrada y
    un código → intentar publicar sin `charges_enabled` **desde el alta y
    desde la edición** (409 en ambos) → completar KYC → publicar → comprar con
    descuento → confirmar por webhook → escanear el QR → reembolsar
    parcialmente → reembolsar el resto → comprobar que el QR queda rechazado
    como `revoked` → desconectar la cuenta (`account.application.deauthorized`)
    → **reconectarla** y comprobar que la organización vuelve a vender.
  - **Recorrido de los cuatro caminos de confirmación en un evento de pago**
    (hallazgo #1, la corrección estructural del plan): alta directa,
    verificación de email, aprobación manual y promoción de lista de espera
    terminan en `pending_payment` con su enlace de pago, y **ninguno** emite
    entrada hasta que el webhook confirma el cobro. Se verifica en el recorrido
    manual, además de los tests de la fase 4.
  - **Repaso explícito de las superficies de riesgo**, cada una con la
    evidencia `file:line` de dónde queda cubierta: las seis de la
    investigación (confusión de `account_id`, idempotencia de eventos
    duplicados, replay sin firma, mezcla test/live, `client_secret` expuesto
    —documentado como no aplicable con Checkout hosted, con su `grep`— y
    autorización del endpoint de reembolso) **más las cuatro añadidas por el
    red-team**: verificación cruzada de organización en los handlers
    (hallazgo #2), `payment_status == "paid"` como única prueba de cobro
    (hallazgo #3), idempotencia medida sobre el proceso y no sobre la
    recepción (hallazgo #9), y ausencia de llamadas de red a Stripe con
    bloqueos de fila abiertos (hallazgo #12).
  - `docs/arquitectura.md`: flujo de pago completo (formulario →
    `pending_payment` → Checkout → webhook → `confirmed` → entrada), el
    porqué del wrapper único de Stripe, y por qué el endpoint de webhooks es
    la única ruta sin tenant por `Host`.
  - `docs/modelo-de-datos.md`: las **seis** tablas nuevas
    (`organization_stripe_accounts`, `event_ticket_types`,
    `event_discount_codes`, `event_payments`, `event_payment_refunds`,
    `stripe_webhook_events`), el estado `pending_payment` y la columna
    `payment_expires_at`, el consumo **derivado** de cupos y códigos (sin
    contadores denormalizados), y la nota de que la revocación de entradas es
    la de la fase 4 del PRD, no una nueva.
  - `docs/desarrollo.md`: cómo levantar Stripe CLI en local con
    `--forward-connect-to` y la ruta con prefijo, qué variables de entorno
    hacen falta (`STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`,
    `PAYMENT_REFUND_CUTOFF_HOURS`, `STRIPE_WEBHOOK_RETENTION_DAYS`), que
    **todas son opcionales** y qué deja de funcionar cuando no están, y las
    tarjetas/cuentas de prueba.
    <!-- Updated: Validation Session 1 - la ventana de pago no es variable de entorno, es campo del evento -->
    La ventana de pago **no** es una variable de entorno: se configura por
    evento en el formulario del organizador (30 minutos por defecto), y así se
    documenta.
  - `docs/arquitectura.md` incluye además: los cuatro caminos de confirmación
    y dónde vive la guarda de pago; por qué el endpoint de webhooks es de
    ámbito «cuentas conectadas» con un solo secreto; el patrón outbox de los
    reembolsos; y `checkout.session.async_payment_succeeded/failed` como
    trabajo pendiente antes de habilitar métodos de pago diferidos
    (hallazgo #3).
  - `docs/accesibilidad.md`: checklist WCAG de las cinco superficies nuevas
    (conexión Stripe, tipos de entrada, códigos de descuento, pagos y
    reembolsos, paso de compra público + pantalla de retorno).
  - `ak:code-review` (high) sobre el diff completo de la fase 6 del PRD, con
    los hallazgos corregidos y verificados, no solo anotados.
- Non-functional:
  - Suites completas en verde: `pytest` de `apps/api`, `pnpm test` de
    `apps/web`, `ruff`, `mypy`, build de producción.
  - `wc -l` sobre todo el repositorio: ningún fichero supera las 1000
    líneas.
  - `openapi.json` y el cliente TypeScript sin diff pendiente tras
    regenerarlos.
  - Ninguna clave de Stripe, ningún `whsec_`, ningún `acct_` real en el
    repositorio ni en los ficheros de test (solo valores de prueba
    evidentemente falsos).
  - Los `docs/` no repiten detalle que ya viva en el código o en las
    migraciones: enlazan a la fuente en vez de copiarla.

## Implementation Steps

1. Ejecutar el recorrido completo con Stripe CLI y dejar constancia (qué se
   probó, con qué eventos, qué resultado) en el reporte de fase.
2. Repasar las seis superficies de riesgo y anotar para cada una el test o
   la comprobación que la cubre, con su `file:line`.
3. Ejecutar las suites completas, lint, tipos y build; corregir lo que falle
   sin debilitar ningún test.
4. `grep` de comprobación: `client_secret` (cero apariciones), `import
   stripe` fuera del wrapper (cero), `emitir_entrada` en
   `app/modules/payments/` (cero), claves reales (cero).
5. Actualizar los cuatro documentos de `docs/`.
6. Pasar `ak:code-review` (high) sobre el diff completo; corregir hallazgos
   con test de regresión donde aplique.
7. Escribir el reporte de fase, incluyendo la deuda conocida aceptada si la
   hubiera (formato de la fase 5: qué es, por qué no bloquea, y en qué
   momento deja de ser aceptable).

## Success Criteria

- [ ] Recorrido completo ejecutado en modo test con Stripe CLI, con los doce
      pasos del requisito verificados y documentados en el reporte de fase,
      incluida la reconexión tras `account.application.deauthorized`
- [ ] Los cuatro caminos de confirmación verificados a mano sobre un evento de
      pago: ninguno emite entrada sin cobro (hallazgo #1)
- [ ] Las diez superficies de riesgo (seis de la investigación + cuatro del
      red-team) tienen cada una su cobertura anotada con `file:line`; el
      `client_secret` queda documentado como no aplicable con la evidencia del
      `grep`
- [ ] `pytest` (apps/api), `pnpm test` (apps/web), `ruff`, `mypy` y el build
      de producción, todos en verde
- [ ] Ningún fichero del repositorio supera las 1000 líneas (`wc -l`
      verificado, no estimado)
- [ ] `openapi.json` y el cliente TypeScript generado sin diff pendiente tras
      regenerarlos
- [ ] Cero apariciones de `client_secret`; cero `import stripe` fuera de
      `payments/stripe_client.py`; cero `stripe.error` en todo `app/`; cero
      `emitir_entrada` en `app/modules/payments/`; cero claves de Stripe
      reales en el repositorio
- [ ] Cero llamadas de red a Stripe dentro de una transacción con bloqueos de
      fila abiertos, revisadas camino por camino (compra, enlaces de pago,
      barrido de caducados, reembolsos) con su `file:line`
- [ ] Cero violaciones de axe en las cinco superficies nuevas; checklist WCAG
      completado en `docs/accesibilidad.md`
- [ ] `docs/arquitectura.md`, `docs/modelo-de-datos.md`,
      `docs/desarrollo.md` y `docs/accesibilidad.md` actualizados y con sus
      afirmaciones verificadas contra el código, no contra el plan
- [ ] `ak:code-review` (high) pasado sobre el diff completo, con los
      hallazgos corregidos y verificados (no solo anotados como pendientes)
- [ ] Reporte de fase escrito, con la deuda conocida aceptada explicitada si
      la hay

## Risk & Rollback

- Riesgo: el recorrido de extremo a extremo depende de una cuenta de Stripe
  en modo test y del CLI instalado; si no están disponibles en el entorno de
  quien ejecute la fase, la tentación es dar los criterios por buenos con
  tests simulados. No es equivalente: los tests con cliente simulado no
  detectan un `expires_at` por debajo del mínimo de Stripe, ni un parámetro
  mal nombrado en la creación de la Checkout Session, ni que los eventos
  Connect necesiten `--forward-connect-to`. Si el CLI no está disponible, la
  fase queda **bloqueada**, no aprobada con reservas.
- Riesgo: `ak:code-review` sobre un diff de seis fases es grande; conviene
  ejecutarlo por áreas (esquema/permisos, Stripe/webhooks, frontend) en vez
  de en una sola pasada que diluya los hallazgos.
- Riesgo (documentación): los `docs/` se escriben al final, cuando el plan
  ya se ha desviado en algún detalle. Deben verificarse contra el código
  final, no contra este plan — una afirmación de arquitectura equivocada en
  `docs/` sobrevive mucho más que un plan cerrado.
- Rollback: esta fase no cambia comportamiento; revertirla es revertir
  documentación. Si el recorrido de extremo a extremo descubre un fallo de
  producto, el rollback es el de la fase de trabajo correspondiente, no el de
  esta.
