---
phase: 1
title: "Implementación — Fase 1: Modelo de datos, permisos y configuración de pagos"
status: completed
---

# Reporte de implementación — Fase 1 (Pagos Stripe Connect)

## Qué se creó

**Ficheros nuevos:**
- `apps/api/app/modules/payments/__init__.py` (vacío)
- `apps/api/app/modules/payments/models.py` (~300 líneas): `OrganizationStripeAccount`,
  `EventTicketType`, `EventDiscountCode`, `EventPayment`, `EventPaymentRefund`,
  `StripeWebhookEvent`.
- `apps/api/alembic/versions/0013_pagos_stripe_connect.py`: crea las seis
  tablas, añade `event_registrations.payment_expires_at` y
  `events.payment_checkout_window_minutes`, activa RLS `tenant_<tabla>` en
  las cinco de dominio, `REVOKE ALL ON stripe_webhook_events FROM app_user`,
  backfill de `payments:read`/`payments:write`.
- Nueve ficheros de test nuevos (ver más abajo).

**Ficheros ampliados** (todos los previstos en el plan, más tres necesarios
por consecuencia directa no listados explícitamente en el plan — ver
Desviaciones):
- `app/core/permissions.py`, `app/modules/roles/system_roles.py`,
  `app/core/config.py`, `apps/api/pyproject.toml`, `apps/api/tests/conftest.py`
- `app/modules/events/models.py`, `app/modules/events/schemas.py`
- `app/modules/registrations/schemas.py`, `public_router.py`, `service.py`
- `apps/web/.../registration-types.ts` + cliente TS regenerado
- `infra/env/.env.example` (documentación de las nuevas variables)

## Desviaciones del plan (justificadas)

1. **`alembic/env.py`**: se añadió el import de `app.modules.payments.models`
   al bloque que registra módulos en `Base.metadata`. No estaba en la lista
   de ficheros de la fase, pero es la misma plomería que ya existe para
   `sponsors`/`tickets`/etc.; sin ella `alembic revision --autogenerate`
   vería las seis tablas nuevas como "a borrar". Verificado con
   `alembic check`: sin drift respecto al modelo salvo dos índices
   preexistentes ajenos a esta fase (`organization_members`, `users`),
   confirmados como deuda técnica anterior (no introducida aquí).
2. **`app/modules/events/router.py`**: `_event_response` necesitaba pasar el
   nuevo campo `payment_checkout_window_minutes`; sin este cambio, cualquier
   respuesta de `EventResponse` habría lanzado `ValidationError` (campo
   obligatorio sin valor). No estaba en la lista del plan pero es
   consecuencia directa e inevitable de añadir el campo al schema.
3. **`app/modules/registrations/models.py`**: el plan describe la columna
   `payment_expires_at` en Requirements/Implementation Steps pero no incluye
   este fichero en la lista de "ficheros existentes que amplía esta fase".
   Sin el `Mapped[...]` correspondiente, el ORM no vería la columna
   (`alembic check` lo confirmó como drift real). Añadido.

Ninguna de las tres desviaciones toca lógica de negocio ni decisiones de
diseño del plan; son plomería estructural obligatoria para que el propio
plan funcione.

## Decisiones tomadas donde el plan dejaba margen

- **TimestampMixin**: aplicado a las cinco tablas de dominio
  (`organization_stripe_accounts`, `event_ticket_types`,
  `event_discount_codes`, `event_payments`, `event_payment_refunds`), no
  solo a las dos que el plan mencionaba explícitamente — es la convención
  universal del resto del esquema. `stripe_webhook_events` no la lleva:
  su lista de campos (`received_at`/`processed_at`) ya es completa y
  distinta del par `created_at`/`updated_at`.
- **FK `event_payments.event_id → events`**: el plan no especifica
  `ondelete` para esta FK (solo detalla la de `registration_id`). Se usó
  `ondelete=CASCADE`, igual que el resto de tablas hijas de `events`
  (`event_ticket_types`, `event_discount_codes`) — consistente y sin riesgo
  real: no existe ningún endpoint que borre un evento (solo se archivan).
- **`event_payments.ticket_type_id`**: NOT NULL (toda compra tiene un tipo
  de entrada); `discount_code_id` nullable, como especifica el plan.

## Tests añadidos (9 ficheros nuevos, 49 tests)

- `tests/test_payments_migracion.py`: ciclo `upgrade`/`downgrade`/`upgrade`
  (con `-1` y desde `base`), privilegios positivos/negativos, evento
  preexistente a la migración recibe `payment_checkout_window_minutes = 30`.
- `tests/test_payments_permisos.py`: backfill + plantilla `ORGANIZER`
  (las dos vías), idempotencia del backfill.
- `tests/test_payments_rls_isolation.py`: lectura y escritura cruzada para
  las cinco tablas de dominio (10 casos).
- `tests/test_payments_schema_constraints.py`: índice único parcial
  (reconexión + rechazo de doble activa), `CHECK` de `price_cents`/
  `discount_value`, ausencia de `used_count`.
- `tests/test_payments_config.py`: secretos vacíos por defecto,
  `payments_enabled`, longitud mínima, `sk_test_` en producción.
- `tests/modules/test_events_payment_checkout_window.py`: default 30,
  límites 30/1439, 422 fuera de rango (alta y edición), `CHECK` directo en
  BD, ausencia de la variable en `app/core/`.
- `tests/modules/test_registrations_pending_payment_surface.py`: listado y
  `/stats` no dan 500 con una fila `pending_payment`.
- `tests/test_admin_rgpd_borrado_con_pago.py`: borrado RGPD real con pago
  asociado, vía `admin.service.borrar_inscrito_por_email`.
- `tests/test_payments_lint_import_stripe.py`: regla `TID251` verificada
  ejecutando `ruff` sobre ficheros de prueba (positivo y negativo).

## Resultado de verificación

- `alembic upgrade head` → `downgrade -1` → `upgrade head`: limpio.
- `alembic downgrade base` → `upgrade head` desde cero: limpio.
- `alembic check`: sin drift introducido por esta fase (dos índices
  preexistentes ajenos, confirmados no relacionados).
- `ruff check .`: sin errores; regla `TID251` confirmada operativa.
- `mypy app` (modo `strict`): sin errores, 95 ficheros.
- Suite completa `apps/api`: **416 tests, todos en verde** (línea base
  ~367 + 49 nuevos).
- `openapi.json` y cliente TypeScript regenerados
  (`make api-openapi && pnpm api:types` equivalente): `pending_payment`
  presente en `registration-list-item.ts`, `registration-detail.ts`, el
  `fn/` del listado, y `registration-stats.ts`; `payments:read`/
  `payments:write` presentes en `permission.ts`. Ningún `client_secret` de
  Stripe en ningún fichero generado (no aplica en esta fase, Checkout
  hosted se implementa en fases posteriores).

## Alcance respetado

No se creó `payments/stripe_client.py` ni ninguna llamada a Stripe. No se
tocó `events/service.py` (la guarda de publicación/checkout es de la fase 2).
Ningún fichero de la fase supera las 1000 líneas (`payments/models.py`
≈300, la migración ≈430).
