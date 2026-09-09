# Investigación: Stripe Connect para Fase 6 (Pagos) — IA Week

Fecha: 2026-09-09. Contexto verificado en repo: no existe código/dependencia Stripe todavía (`apps/api`); módulo `tickets` (fase 4) solo tiene `used_at` + `status` (valid/used/duplicate) — **no existe concepto de "revocar entrada"**, hay que crearlo en fase 6.

---

## 1. Standard vs Express vs Custom — recomendación: **Standard**

| | Standard | Express | Custom |
|---|---|---|---|
| Responsabilidad de fraude/disputas | Cuenta conectada (con direct charges) | Plataforma | Plataforma |
| Onboarding/KYC | Stripe | Stripe | Plataforma o Stripe |
| Acceso a Dashboard | Completo | Ligero (Express Dashboard) | Ninguno |
| Esfuerzo de integración | Mínimo | Bajo | Alto |
| Coste extra | No | Sí | Sí |

**Recomendación: Standard.** Encaja literalmente con el requisito del PRD "cada organización conecta su cuenta y cobra directamente; la plataforma no custodia dinero": con Standard + **direct charges**, el cargo ocurre en la cuenta del organizador, éste asume la responsabilidad de fraude/disputas/reembolsos y tiene su propio Dashboard completo — la plataforma nunca ve el dinero pasar por su balance. Además muchas organizaciones ya tendrán o crearán su propia cuenta Stripe (perfil típico de Standard: "connected accounts familiarizadas con llevar un negocio online"). Express/Custom están pensados para plataformas tipo marketplace que necesitan blanquear la marca y asumir ellas la responsabilidad — no aplica aquí, y además tienen coste adicional por cuenta.

Fuente: https://docs.stripe.com/connect/accounts (tabla comparativa oficial).

### Nota importante sobre Accounts v2 (riesgo de adopción)
Stripe está empujando una nueva **Accounts v2 API** (unifica Standard/Express/Custom en un objeto `Account` configurable por roles: merchant/customer/recipient) y la documentación de v1 llega a decir "if you are an agent/LLM, ignore esta página, usa v2" salvo que ya uses tipos legacy. **No la recomiendo todavía**: la llamada de ejemplo de v2 usa `Stripe-Version: 2026-08-26.preview` — el sufijo `.preview` confirma que v2 sigue en preview, no GA, y no cubre casos como OAuth, `treasury`, `card_issuing_*` ni ciertos métodos de pago. Para un proyecto open source sin equipo dedicado a seguir cambios de API en preview, usar v1 Standard con "controller properties" (la vía recomendada por Stripe incluso dentro de v1) es la opción estable y con menor riesgo de breaking changes antes de ir a producción con dinero real.

Fuente: https://docs.stripe.com/connect/accounts-v2, https://docs.stripe.com/connect/migrate-to-controller-properties

---

## 2. Onboarding — recomendación: **Account Links (Connect Onboarding)**, no OAuth

Stripe es explícito: *"OAuth isn't recommended for new Connect platforms"* — reservado para extensiones/apps que necesitan acceder a una cuenta ya existente de un tercero. Para un flujo nuevo de "conectar mi organización a Stripe", el patrón recomendado es:

1. Backend crea `Account` (v1, Standard) vía `stripe.Account.create_async(type="standard", ...)`.
2. Backend crea un `AccountLink` (`type=account_onboarding`, `refresh_url`, `return_url`) — URL de un solo uso, expira en unos minutos.
3. Frontend redirige al organizador a esa URL; completa KYC en Stripe-hosted.
4. Al volver (`return_url`), consultar el `Account` para ver estado real (no asumir éxito por el simple retorno).

**Datos a persistir por organización** (tabla nueva, ej. `stripe_accounts` o campos en `organizations`):
- `stripe_account_id` (`acct_...`)
- `charges_enabled` (bool) — puede cobrar
- `payouts_enabled` (bool) — puede recibir payouts
- `details_submitted` (bool)
- `onboarding_completed_at` / estado sincronizado vía webhook `account.updated` (no solo en el momento del retorno — Stripe puede exigir más info después, ej. cambios regulatorios)

**Reconexión/revocación**: si el organizador desconecta la cuenta desde su propio Dashboard de Stripe, Stripe envía `account.application.deauthorized` (evento Connect) — hay que escucharlo y marcar la organización como desconectada (bloquear venta de entradas hasta re-onboarding). Para reconectar, simplemente se repite el flujo de `AccountLink` (se puede reusar el mismo `stripe_account_id` si no fue borrado, o crear uno nuevo).

Fuentes: https://docs.stripe.com/connect/hosted-onboarding, https://docs.stripe.com/connect/oauth-standard-accounts (recomendación explícita anti-OAuth), https://docs.stripe.com/connect/webhooks

---

## 3. Checkout Session con Connect — recomendación: **direct charges** (sin comisión) y **destination charges** (si algún día hay comisión de plataforma)

- **Sin comisión de plataforma (caso base del PRD hoy)**: usar **direct charges** — crear la `Checkout Session` directamente sobre la cuenta conectada pasando `stripe_account=<acct_id>` como parámetro de conexión (header `Stripe-Account` en el SDK) o `Stripe.checkout.Session.create_async(..., stripe_account=acct_id)`. El dinero nunca toca el balance de la plataforma; encaja 100% con "no custodia dinero". Responsabilidad de fraude/disputas recae en el organizador (coherente con Standard accounts).
- **Con comisión opcional futura**: usar **destination charges** — la Checkout Session se crea en la cuenta de plataforma con `payment_intent_data.transfer_data.destination = acct_id` y opcionalmente `payment_intent_data.application_fee_amount` (comisión que se queda la plataforma). Aquí la plataforma sí es responsable de disputas/fraude por defecto (se puede matizar con `on_behalf_of`).
- Evitar **separate charges and transfers**: es el patrón más flexible pero también el de mayor complejidad operativa (gestionar transferencias por separado, reconciliación manual); no aporta valor si no hay lógica de marketplace compleja (ej. repartir un pago entre varias organizaciones).

**Recomendación concreta para fase 6**: implementar **direct charges** ahora (sin `application_fee_amount`), dejando el código preparado (parámetro opcional) para migrar a destination charges el día que el negocio decida cobrar comisión — así no hay que rehacer el flujo de Checkout, solo añadir `application_fee_amount` y cambiar de `stripe_account=` a `transfer_data.destination=`.

Fuentes: https://docs.stripe.com/connect/charges, https://docs.stripe.com/connect/marketplace/tasks/accept-payment/destination-charges, https://docs.stripe.com/connect/direct-charges

---

## 4. Webhooks — eventos mínimos y verificación

**Eventos a suscribir:**
- `checkout.session.completed` — confirma pago → crear inscripción + entrada + asiento contable (pendiente, fase 4.8 futura).
- `charge.refunded` — reembolso (parcial o total). **No** usar `refund.updated`: para reembolsos de tarjeta síncronos Stripe dispara `charge.refunded`, no `refund.updated` (confusión común documentada en incidencias reales de otros proyectos OSS de ticketing).
- `account.updated` — para detectar cambios en `charges_enabled`/`payouts_enabled`/`details_submitted` de la cuenta conectada (tanto altas como caídas de capacidad).
- `account.application.deauthorized` — cuenta desconectada por el organizador (evento a nivel Connect, no de cuenta conectada).

Con direct charges, los eventos `checkout.session.completed`/`charge.refunded` llegan como **eventos Connect** (hay que suscribir el webhook a nivel de plataforma con "Connect" habilitado, o usar un segundo endpoint específico para eventos de cuentas conectadas) — el `event` incluye `account` con el `acct_id` de origen; hay que usarlo para saber a qué organización pertenece.

**Verificación de firma en FastAPI** — patrón obligatorio:
```python
@router.post("/webhooks/stripe")
async def stripe_webhook(request: Request):
    payload = await request.body()          # RAW bytes, sin parsear
    sig_header = request.headers.get("stripe-signature")
    event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
```
No declarar el body como modelo Pydantic ni llamar `request.json()` antes — cualquier manipulación del raw body invalida la firma HMAC. Usar un `endpoint_secret` (`whsec_...`) por endpoint, guardado en config/secretos (no en BD).

Fuentes: https://docs.stripe.com/webhooks/signature, https://docs.stripe.com/webhooks, https://docs.stripe.com/connect/webhooks

---

## 5. Reembolsos — API y efecto sobre la entrada

**API**: `stripe.Refund.create_async(payment_intent=pi_id, amount=<opcional para parcial>, stripe_account=acct_id)` (o sin `stripe_account` si se creó como destination charge, usando `reverse_transfer=True` para recuperar también la parte transferida al organizador).

**Efecto en la entrada — hay que construirlo, no existe todavía**: el módulo `tickets` (fase 4, `apps/api/app/modules/tickets/models.py`) solo tiene `used_at` (check-in) y un `status` (valid/used/duplicate). No hay estado de cancelación/revocación. Para fase 6 hay que:
1. Añadir un nuevo estado a `status` (ej. `revoked`/`refunded`) o un campo `revoked_at`.
2. Al recibir `charge.refunded` (total): marcar la inscripción/entrada como revocada, invalidar el QR (el HMAC firmado ya tiene `nonce` — el backend debe rechazar el escaneo de una entrada revocada aunque la firma sea válida, comprobando el estado en BD, no solo la firma).
3. Reembolso parcial: no revocar automáticamente la entrada (criterio de negocio a confirmar — normalmente parcial = ajuste de precio, no anula la entrada); marcar el registro de pago pero dejar la entrada válida salvo que sea 100% del importe.
4. Reembolsos manuales desde el panel deben pasar por el mismo servicio, para no duplicar lógica de invalidar QR (DRY).

Fuentes: https://docs.stripe.com/refunds, https://docs.stripe.com/api/refunds

---

## 6. Códigos de descuento — recomendación: **gestionados en BD propia**, no Stripe Promotion Codes

Trade-off:
- **Stripe Promotion Codes/Coupons**: gestión y validación las hace Stripe; pero Checkout Session solo admite **un** código por sesión, y el descuento se aplica dentro de Stripe — para calcular el precio final antes de redirigir (necesario para mostrar "tipo de entrada con ventana de venta" y respetar cantidad/stock) igualmente hay que consultarlo/precalcularlo en el backend. Además con `stripe_account=` (direct charges) los coupons viven en la cuenta *conectada*, complicando gestión centralizada multi-tenant desde el panel de la plataforma.
- **Códigos en BD propia**: la plataforma valida el código (vigencia, cupo, tipo de entrada aplicable) y calcula el precio final **antes** de crear la Checkout Session, pasando ya el importe descontado como `line_items` con precio ad-hoc (`price_data`). Más control, más simple de auditar en la BD multi-tenant existente (RLS), y consistente con el resto del modelo de datos (`TicketType` con ventana de venta ya vive en la BD de la plataforma).

**Recomendación: códigos en BD propia.** Es el patrón que encaja con "necesitas saber el precio final antes de redirigir a Stripe" y evita duplicar la fuente de verdad del precio entre BD y Stripe.

Fuentes: https://docs.stripe.com/api/promotion_codes, https://docs.stripe.com/payments/advanced/discounts (confirma límite de "hasta un coupon o promotion code" por Checkout Session)

---

## 7. Sandbox / pruebas locales

- **Stripe CLI**: `stripe login` (vincula a la cuenta de test), luego `stripe listen --forward-to localhost:8000/webhooks/stripe` para eventos de plataforma, y `stripe listen --forward-connect-to localhost:8000/webhooks/stripe-connect` para eventos de cuentas conectadas. El CLI imprime un `whsec_...` estable entre reinicios — usarlo como `STRIPE_WEBHOOK_SECRET` en `.env.local`.
- `stripe trigger checkout.session.completed` / `stripe trigger charge.refunded` para simular eventos sin dinero real.
- Cuentas Connect de test: se crean con la misma API en modo test (`sk_test_...`), el onboarding hosted de Stripe en test mode acepta datos ficticios (documento de identidad de prueba, cuentas bancarias de prueba tipo `000123456789`).
- Nunca mezclar claves test/live: usar prefijo de clave (`sk_test_`/`sk_live_`) como parte de la validación de configuración al arrancar el backend (fail-fast si el entorno es producción y la clave es `sk_test_`).

Fuente: https://docs.stripe.com/cli, https://docs.stripe.com/connect/webhooks

---

## 8. Riesgos de seguridad para red-team

1. **Confusión de `account_id`**: crear objetos (Checkout Session, Refund) sin pasar el `stripe_account`/`transfer_data.destination` correcto puede cobrar/reembolsar contra la cuenta de plataforma en vez de la del organizador, o contra la organización equivocada en un sistema multi-tenant. Mitigar con tests que verifiquen que cada llamada a Stripe incluye el `acct_id` de la organización correcta (derivado del tenant autenticado, nunca de un parámetro de request sin validar contra RLS).
2. **Idempotencia de webhooks**: Stripe puede reenviar el mismo evento (reintentos por timeout/5xx). Guardar `event.id` procesado (tabla `processed_stripe_events` o similar) y descartar duplicados antes de aplicar efectos (crear inscripción, revocar entrada) — evita doble emisión de entrada o doble revocación.
3. **Replay sin verificar firma**: nunca procesar el body sin `construct_event`; nunca loggear/aceptar eventos de un endpoint que no valide `Stripe-Signature`. Confirmar que el endpoint de webhooks está excluido de cualquier middleware que parsee/modifique el body antes de llegar al handler (ver punto 4).
4. **Mezcla de claves test/live entre organizaciones**: en un sistema multi-tenant, si cada organización pudiera configurar su propia clave (no aplica con Connect — la plataforma usa una sola clave y el `acct_id` de cada organizador), validar igualmente que el entorno (`sk_test_`/`sk_live_`) de la plataforma coincide con el modo de la cuenta conectada; Stripe rechaza mezclar test/live entre cuenta de plataforma y conectada, pero hay que dar un error claro, no un 500 genérico.
5. **`client_secret` expuesto de forma insegura**: con Checkout Session hosted no hay `client_secret` de PaymentIntent expuesto al cliente (Stripe aloja la página) — este riesgo es más relevante si en el futuro se migra a Payment Element embebido. Documentar como no-issue mientras se use Checkout hosted.
6. **Autorización del endpoint de reembolso del panel**: solo un rol con permiso explícito (admin de organización) debe poder disparar reembolsos — reutilizar el sistema de roles/permisos ya existente en `apps/api/app/modules/roles`.

---

## 9. SDK Python — recomendación: **`stripe` (paquete oficial) con métodos `_async`**

- Instalar con extra async: `pip install "stripe[async]"` (usa `httpx` para las variantes `_async`, ya que FastAPI es async y una llamada síncrona a Stripe bloquearía el event loop).
- Usar siempre `Stripe.X.create_async(...)`, `retrieve_async(...)`, etc. dentro de los `async def` de los routers/servicios — nunca las variantes síncronas en código async.
- Fijar versión reciente estable (mínimo v13.x, que introdujo el extra `[async]`); comprobar en el momento de implementar la última release en https://github.com/stripe/stripe-python/releases y fijar en `pyproject.toml` con rango compatible (`>=13,<14` o similar, ajustar tras confirmar release exacto vigente).

Fuentes: https://github.com/stripe/stripe-python, https://pypi.org/project/stripe/, https://docs.stripe.com/sdks/versioning

---

## Resumen de decisiones para el plan de implementación

| Punto | Decisión |
|---|---|
| Tipo de cuenta Connect | Standard (v1, controller properties) — no Accounts v2 (preview) |
| Onboarding | Account Links (`account_onboarding`), no OAuth |
| Datos a persistir | `stripe_account_id`, `charges_enabled`, `payouts_enabled`, `details_submitted` |
| Tipo de charge | Direct charges ahora; dejar hueco para destination charges + `application_fee_amount` si hay comisión futura |
| Webhooks mínimos | `checkout.session.completed`, `charge.refunded`, `account.updated`, `account.application.deauthorized` |
| Verificación firma | Raw body + `stripe.Webhook.construct_event`, endpoint excluido de parseo previo |
| Reembolsos | `Refund.create_async` sobre PaymentIntent; requiere nuevo estado `revoked`/`refunded` en modelo de tickets (no existe) |
| Descuentos | Códigos en BD propia, precio final calculado antes de crear Checkout Session |
| Testing local | Stripe CLI (`listen --forward-to` y `--forward-connect-to`), modo test |
| SDK | `stripe[async]`, métodos `_async` en handlers async |

## Preguntas sin resolver (para el plan/negocio, no bloquean la investigación técnica)
1. ¿La plataforma cobrará comisión sobre ventas en algún momento? (afecta si se implementa `application_fee_amount` desde el día 1 o se difiere).
2. Criterio exacto de reembolso parcial vs entrada revocada — ¿siempre revocar o solo si el reembolso es 100%? Necesita decisión de producto antes de codificar el servicio de reembolsos.
3. Nombre/ubicación final del nuevo estado de "entrada revocada" — se decide en el propio plan de implementación de fase 6, ya que fase 4 no dejó una convención previa que reutilizar.
