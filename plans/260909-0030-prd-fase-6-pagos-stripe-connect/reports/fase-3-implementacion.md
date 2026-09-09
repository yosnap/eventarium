# Fase 3 de trabajo: tipos de entrada, códigos de descuento y cálculo de precio

Rama `feature/0.19.0-pagos-stripe-connect`. Estado: `completed`.

## Qué se creó/modificó

### Backend (`apps/api`)

- `app/modules/payments/repository.py` (ampliado): consultas de catálogos de
  `EventTicketType`/`EventDiscountCode`, variantes `lock_ticket_type`/
  `lock_discount_code` con `SELECT ... FOR UPDATE` (contrato de bloqueo para
  la fase 4), y los dos `COUNT` derivados (`count_used_ticket_type`,
  `count_used_discount_code`) sobre `ESTADOS_CONSUMIBLES` — nunca un contador
  denormalizado.
- `app/modules/payments/service.py` (ampliado): tres funciones puras sin BD
  (`calcular_precio_final`, `validar_tipo_vigente`, `validar_codigo_vigente`),
  CRUD de tipos de entrada y códigos de descuento, y `calcular_presupuesto`
  (lectura pura, nunca reserva cupo ni consume uso). Docstring del módulo
  documenta el orden único de bloqueo del módulo:
  `event_registrations → events → event_ticket_types → event_discount_codes`.
- `app/modules/payments/schemas.py` (ampliado): `TicketTypeCreate/Update/Response`,
  `DiscountCodeCreate/Update/Response` (con `used_count` derivado),
  `CheckoutQuoteRequest/Response`. Validación de rango de descuento
  (1-100 % / >0 fijo) espejo del `CHECK` de la fase 1.
- `app/modules/payments/router.py` (ampliado): dos routers nuevos en el mismo
  fichero (`router_ticket_types`, `router_discount_codes`), mismo patrón que
  `sponsors/router.py`.
- `app/modules/payments/public_router.py` (nuevo): `POST
  /public/events/{slug}/checkout/quote`, con Turnstile y `limit_per_ip`
  (`CHECKOUT_QUOTE_POR_IP`, 30/min).
- `app/core/ratelimit.py` (ampliado): `CHECKOUT_QUOTE_POR_IP`.
- `app/main.py` (ampliado): registro de los tres routers nuevos.
- Tests nuevos: `test_payments_pricing.py` (17 casos, funciones puras sin BD),
  `test_payments_ticket_types_router.py` (5), `test_payments_discount_codes_router.py`
  (6), `test_payments_checkout_quote_public.py` (6). Total +34 tests backend.

### Frontend (`apps/web`)

- `event-ticket-types.ts`/`.spec.ts` (nuevo): CRUD de tipos de entrada con
  reordenación por flechas arriba/abajo (intercambian `sort_order` con el
  vecino), activar/desactivar, precio en euros con `inputmode="decimal"`.
- `event-discount-codes.ts`/`.spec.ts` (nuevo): CRUD de códigos, con
  desplegable de tipo de entrada (o "todos"), `used_count`/`max_uses`
  mostrados de solo lectura.
- `event-form.ts` (ampliado): añade `registration_mode` a `EventDetail`,
  renderiza ambas pantallas nuevas solo si `registrationMode() === 'paid'`,
  con aviso enlazando a `/admin/stripe`.
- `event-form.spec.ts` (ampliado): dos tests nuevos comprobando la
  visibilidad condicionada a `registration_mode`.
- `public/assets/i18n/es-ES.json` (ampliado): claves `admin.events.pagos`,
  `admin.events.ticketTypes`, `admin.events.discountCodes`.
- `openapi.json` + cliente TypeScript regenerados (`make api-types`).

## Decisiones tomadas

1. **Reordenación por intercambio de `sort_order` vecino** (no un campo
   numérico libre en el formulario): más natural para el organizador y evita
   que dos tipos queden con el mismo orden por accidente. Al dar de alta un
   tipo nuevo se le asigna `sort_order = tipos().length` (al final de la
   lista) — sin esto, todos los tipos nuevos compartirían el `0` por defecto
   y las flechas no tendrían ningún efecto visible entre ellos.
2. **Mensaje único de rechazo de código** centralizado en
   `service.MENSAJE_CODIGO_NO_VALIDO`, usado en los cuatro motivos
   (inexistente, caducado, agotado, de otro tipo); el motivo exacto se
   registra con `logger.info` solo en el servidor.
3. **El presupuesto público no depende de `registration_mode`** a nivel de
   API (solo la visibilidad de las pantallas del panel lo hace) — así los
   tests no necesitan una cuenta de Stripe conectada para publicar un evento
   de prueba.
4. **`ticket_type_id` en el desplegable de códigos** se resuelve con una
   petición propia a `GET .../ticket-types` desde `EventDiscountCodes`
   (independiente de `EventTicketTypes`), igual que `event-sponsors.ts`
   resuelve sus niveles de patrocinio con su propia petición.

## Resultado de tests

- Backend: **492 tests, 0 fallos** (458 previos + 34 nuevos de esta fase).
  Ejecutado con `uv run pytest -q` completo, sin `-k`.
- Frontend: **178 tests, 0 fallos** (172 previos + 6 nuevos: 4 de los
  componentes nuevos + 2 de `event-form.spec.ts`). Ejecutado con
  `ng test --watch=false` completo. Axe limpio en ambas pantallas nuevas y en
  `event-form` con `registration_mode: paid`.
- `ruff check`/`ruff format`/`mypy` limpios en todo `payments/`.
- `tsc --noEmit`/`ng lint` limpios en todo `apps/web`.

## Desviaciones con justificación

- El test "50 presupuestos sobre un código de 1 uso" llama a
  `service.calcular_presupuesto` directamente 50 veces en vez de hacer 50
  peticiones HTTP: `CHECKOUT_QUOTE_POR_IP` es 30/min, así que 50 peticiones
  HTTP reales chocarían con el propio límite de peticiones (que tiene su
  propio test dedicado, `test_el_presupuesto_tiene_limite_de_peticiones_por_ip`).
  Lo que el criterio de éxito pide comprobar — que un presupuesto no escribe
  en `event_payments` — se verifica igual de bien a nivel de servicio.
- No se añadió un campo de moneda (`currency`) en el formulario de tipos de
  entrada: el plan no lo pide explícitamente y el backend ya fija `eur` por
  defecto; añadir un selector sin caso de uso real habría sido alcance no
  solicitado.

## Problema de borrado de ficheros

**Sí volvió a ocurrir, tres veces**, siempre sobre
`apps/api/app/modules/payments/stripe_client.py` (nunca sobre ningún fichero
creado en esta fase): una vez a mitad de la implementación (detectado al
intentar `uv run pytest` y ver `ImportError`), y dos veces más durante
ejecuciones largas de la suite completa en segundo plano. Las tres veces se
restauró con `git checkout -- apps/api/app/modules/payments/stripe_client.py`
(el fichero seguía intacto en el índice de git de la fase 2) y se volvió a
lanzar la suite. Se hicieron `git add -A` periódicos para detectarlo pronto,
tal como pedía el aviso operativo. El fichero está presente y sin cambios al
cierre de esta fase.

## Commit

Pendiente: se hace `git add` de los ficheros propios de esta fase (los backend
`M`/`A` listados arriba, los frontend nuevos/ampliados, y los generados de
`openapi.json`/cliente TS) y commit convencional en español, sin tocar nada
fuera de la fase 3.
