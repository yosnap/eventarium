---
title: "PRD Fase 4 — Entradas QR y control de acceso"
description: "Entrada QR firmada por inscripción confirmada, escaneo de check-in con app PWA offline-first para el rol voluntariado/staff, y búsqueda manual de respaldo."
status: validated
priority: P1
effort: "6-8d"
tags: [entradas, qr, check-in, pwa, offline]
created: 2026-09-08
prd_phase: 4
blockedBy: [3]
blocks: [5]
---

# PRD Fase 4 — Entradas QR y control de acceso

## Overview

La fase 3 dejó el embudo de inscripción completo: una persona llega a
`confirmed` (por verificación automática, aprobación manual o promoción desde
lista de espera). Esta fase construye lo que hace falta para que esa
inscripción confirmada se convierta en una entrada real el día del evento:
emitir un QR firmado por inscripción, y dar al equipo de voluntariado una
aplicación de escaneo que funcione con conectividad intermitente (típico en
un pabellón o sala con mucha gente y wifi saturado).

Alcance según `docs/prd.md` §4.4, únicamente lo marcado **M** (MVP IAWIC
Valencia). Wallet de Apple/Google es **S**, fuera de alcance.

## Non-goals

Apple/Google Wallet (S). Pagos y tipos de entrada de pago (fase 5 — esta fase
solo emite entradas para inscripciones `confirmed` gratuitas o aprobadas, el
concepto de "tipo de entrada" con precio no existe todavía). Reviews de
ponencias condicionadas a check-in (fase 7, PRD §4.7 — esta fase solo deja el
campo `checked_in`/`used_at` disponible para que esa fase lo consuma después,
no construye nada de reviews). Recordatorio y email post-evento (PRD §4.9,
fuera del alcance M explícito de esta fase — el email de entrada con el QR sí
entra, es el único correo nuevo que esta fase necesita).

## Decisiones de diseño (ingeniería, no interview de producto)

El PRD es prescriptivo en este punto (formato ya decidido: HMAC/JWT,
intransferible, un solo uso, PWA offline). Las decisiones de abajo son de
implementación, tomadas siguiendo los patrones ya establecidos en fases
anteriores; se listan para que el red-team las pueda impugnar con motivo, no
como pregunta abierta al usuario.

| # | Decisión | Razonamiento |
|---|---|---|
| 1 | Entrada en tabla propia `event_tickets`, no columnas nuevas en `event_registrations` | El ciclo de vida de una entrada (emitida, usada, revocada, quién la escaneó) es distinto del de una inscripción, y la fase 5 (pagos) necesitará campos de entrada (tipo, precio) que no tienen sentido en `event_registrations`. Permiso `tickets:*` ya reservado desde la fase 0 (`app/core/permissions.py`), separado de `registrations:*` |
| 2 | Un `event_ticket` por inscripción `confirmed`, 1:1, emitido automáticamente al confirmarse (no bajo demanda) | Menos estados que gestionar; "emitida" y "confirmada" coinciden siempre salvo revocación explícita |
| 3 | JWT firmado (HS256, `PyJWT`, ya usado en `app/core/security.py` para los access tokens) con secreto **propio** (`ticket_qr_secret`, nueva variable), no el `jwt_secret` de autenticación | Aislar el radio de un posible leak: comprometer el secreto de entradas no debe permitir forjar tokens de sesión, y viceversa |
| 4 | Payload del JWT: `tid` (id de la entrada), `eid` (evento), `exp` = `event.ends_at` + margen fijo de 48h, `nonce` (aleatorio, ver más abajo) | Un QR que deja de ser válido nada más terminar el evento rompe el check-in de última hora; el margen absorbe desajustes de reloj y cierres tardíos |
| 5 | Tabla `event_ticket_scans` para cada intento de escaneo (válido, duplicado, caducado, firma inválida, revocado), no solo el último resultado en `event_tickets.used_at` | Es la fuente de verdad para "quién escaneó qué y cuándo" (auditoría) y resuelve la sincronización offline: dos dispositivos pueden encolar el mismo escaneo sin conexión: el primero que sincroniza gana (`used_at` se fija una vez), el resto queda registrado como `duplicate` con referencia a quién ganó, no como error |
| 6 | Idempotencia de sincronización por `client_scan_id` (UUID generado en el dispositivo al escanear, no al sincronizar) | La cola offline puede reintentar el mismo envío tras un corte de red; sin una clave idempotente seguiría contando como un segundo escaneo |
| 7 | Permisos `tickets:read`/`tickets:write` a nivel de organización, igual que `events:*`/`registrations:*` — **no** restringido al roster (`event_members`) del evento concreto | Consistente con el modelo de autorización ya existente (todo permiso es de organización, ninguno está acotado a un evento concreto todavía); acotar el escaneo a "solo tu evento" sería el primer caso de ACL por evento del proyecto, una generalización no pedida. Riesgo aceptado y documentado abajo, no una omisión |
| 8 | Backfill de permisos: `tickets:read`+`tickets:write` a cualquier rol con `organizations:write` (patrón ya usado en fases 2 y 3 para `events:*`/`registrations:*`); además `tickets:write` a la plantilla de sistema `volunteer` y a los roles ya clonados de esa plantilla en organizaciones existentes | El voluntariado solo necesita escanear, no ver estadísticas ni gestionar preguntas — de ahí que no reciba `tickets:read` salvo que ya tuviera `organizations:write` |
| 9 | PWA: se añade `@angular/service-worker` a la app ya existente (no una segunda aplicación) sobre una ruta nueva `/admin/events/:id/check-in`, instalable de forma independiente vía manifest con `start_url` en esa ruta | Un solo despliegue, un solo dominio, reutiliza sesión/autenticación ya existente; instalarla como PWA es una propiedad del manifest, no exige un proyecto Angular separado |
| 10 | Decodificación de QR: API nativa `BarcodeDetector` cuando el navegador la soporta (Chrome/Android), con librería JS de respaldo (`@zxing/browser` o `jsQR`) para iOS Safari y navegadores sin soporte nativo | Cobertura real de dispositivos de voluntariado sin depender de una sola vía |
| 11 | Cola offline en IndexedDB (no `localStorage`, por tamaño y por poder consultarla con índices para deduplicar por `client_scan_id`) | Volumen esperado (cientos de escaneos en una jornada) y necesidad de consulta estructurada |

## Requirements

- Functional:
  - `event_tickets`: `id`, `event_id`+`organization_id` (FK compuesta a
    `events`), `registration_id`+`organization_id` (FK compuesta a
    `event_registrations`, `UNIQUE`), `issued_at`, `used_at` (nullable),
    `used_by_event_member_id` (nullable, quién lo marcó), `revoked_at`
    (nullable).
  - `event_ticket_scans`: `id`, `ticket_id`+`organization_id` (FK compuesta),
    `event_id` (denormalizado, mismo criterio que el resto del esquema),
    `scanned_by_event_member_id`, `client_scan_id` (`UNIQUE`, idempotencia),
    `client_scanned_at` (hora del dispositivo), `scanned_at` (hora del
    servidor al sincronizar), `result` (`valid` / `duplicate` / `expired` /
    `invalid_signature` / `revoked` / `not_found`), `device_label` (texto
    libre opcional, para que el staff identifique el dispositivo en la
    auditoría).
  - Emisión automática: al transicionar una inscripción a `confirmed`
    (verificación, aprobación, promoción de lista de espera — los tres
    caminos ya centralizados en `_enviar_email_por_estado` de la fase 3), se
    crea el `event_ticket` y se encola el email de entrada con el QR
    incrustado (imagen PNG generada en el momento, `qrcode` + `Pillow` ya
    disponibles o añadidos como dependencia).
  - Revocación: cancelar una inscripción (organizador o autocancelación,
    `_cancelar_inscripcion` de la fase 3) revoca su entrada (`revoked_at`) si
    existía. Una entrada revocada nunca es válida al escanear, aunque el JWT
    no haya caducado.
  - `POST /api/v1/organizations/{org}/events/{event}/tickets/scan`: recibe el
    JWT del QR, `client_scan_id`, `client_scanned_at` y `device_label`
    opcional. Verifica firma y caducidad, resuelve la entrada, aplica la
    regla de duplicado/revocado/no-encontrado, y devuelve el resultado más
    los datos a mostrar (nombre, email, estado) — nunca el JWT de vuelta.
    Requiere `tickets:write`.
  - `POST .../tickets/scan/batch`: variante para sincronizar varios escaneos
    encolados sin conexión en una sola petición (mismo procesamiento, uno por
    uno, en el orden de `client_scanned_at`), devolviendo el resultado de
    cada uno por su `client_scan_id`.
  - `GET .../tickets/search?q=`: búsqueda manual por nombre o email entre las
    inscripciones `confirmed` del evento, para el respaldo sin cámara.
    Requiere `tickets:write` (es parte del mismo flujo de check-in, no una
    lectura administrativa separada).
  - `GET .../tickets/{registration_id}`: recupera los datos de una entrada
    para reenviar el email o mostrar su QR desde el panel. Requiere
    `tickets:read`.
  - Página pública `/mi-entrada?token=...` (token de autocancelación
    reutilizado, no uno nuevo — ver fase de trabajo 4) donde la persona
    inscrita puede volver a ver su QR si perdió el email.
  - App PWA de escaneo (`/admin/events/:id/check-in`): cámara con
    `BarcodeDetector`/librería de respaldo, resultado inmediato en pantalla
    (válido/duplicado/revocado/caducado con los datos de la persona), cola
    offline en IndexedDB que sincroniza sola al recuperar conexión (con
    reintento) y permite seguir escaneando sin conexión, búsqueda manual
    integrada, contador de escaneados/total visible.
- Non-functional:
  - RLS y FK compuestas `(id, organization_id)` en las dos tablas nuevas,
    mismo patrón que el resto del esquema desde la fase 2.
  - El JWT del ticket nunca incluye datos personales (nombre, email) en el
    payload — solo identificadores; los datos a mostrar en el escaneo se
    resuelven en el servidor contra la inscripción, no se decodifican del
    QR. Así un QR interceptado no filtra datos personales por sí solo, solo
    un identificador opaco.
  - Accesibilidad WCAG 2.1 AA en la app de escaneo (incluida la que usa una
    persona con el móvil en la mano, con foco visible y feedback no solo por
    color: el resultado de un escaneo lleva icono + texto, no solo un fondo
    verde/rojo) y en `/mi-entrada`.
  - El endpoint de escaneo es idempotente por `client_scan_id`: reenviar la
    misma petición (reintento de red) nunca cuenta como un segundo escaneo.

## Fases de trabajo

1. **Modelo de datos, permisos y emisión automática** — `event_tickets`,
   `event_ticket_scans`, migración con RLS, permisos `tickets:*` y su
   backfill, generación del JWT, emisión automática al confirmar y revocación
   al cancelar.
2. **Escaneo y check-in (API)** — endpoints de escaneo (individual y en
   lote), búsqueda manual, detalle de entrada, la lógica de duplicado/
   revocado/caducado/no-encontrado.
3. **App PWA de escaneo (frontend)** — manifest, service worker, cámara y
   decodificación de QR, cola offline en IndexedDB con sincronización,
   búsqueda manual integrada, contador en vivo.
4. **Email de entrada, página pública y cierre de fase** — tarea de email con
   QR incrustado (reutilizando `send_registration_confirmed_email` o una
   nueva tarea dedicada, a decidir en esa fase según cuánto se parezca al
   patrón ya usado), página pública `/mi-entrada`, pruebas end-to-end del
   flujo completo (confirmar → recibir entrada → escanear → duplicado →
   revocar por cancelación) y cierre de la fase 4 del PRD.

## Riesgos

- **Aceptado y documentado** (decisión #7): el escaneo no está acotado al
  roster del evento — un voluntario con `tickets:write` puede escanear
  entradas de cualquier evento de la organización, no solo el suyo. Aceptable
  para el MVP de un evento único (IAWIC); revisar si la instalación empieza a
  alojar varios eventos simultáneos con equipos de voluntariado distintos y
  no confiables entre sí.
- Decodificación de QR en navegador con conectividad intermitente y cámaras
  de gama variable (móviles del propio voluntariado, no dispositivos
  dedicados) — mitigar con `BarcodeDetector` nativo primero y una librería de
  respaldo probada, no una implementación propia de decodificación.
- Generación de imagen QR en servidor añade una dependencia nueva
  (`qrcode`/`Pillow` o equivalente) — mitigar comprobando primero si el
  proyecto ya tiene una vía de generación de imágenes reutilizable antes de
  añadir una dependencia paralela.
- Sincronización offline con reloj de dispositivo potencialmente desajustado
  (`client_scanned_at`) — el servidor nunca confía en esa hora para decidir
  quién "ganó" un duplicado (usa `scanned_at`, hora de servidor, como
  desempate real); `client_scanned_at` es solo para ordenar la cola antes de
  enviarla y para mostrar en la auditoría.

## Red Team Review

Red-team ejecutado el 2026-09-08 contra el código real
(`apps/api/app/modules/registrations/service.py`,
`app/modules/roles/system_roles.py`, `app/modules/events/models.py`,
`alembic/versions/0010_inscripcion_de_asistentes.py`, `pyproject.toml`).
Hallazgos, ya aplicados a las fases correspondientes:

- **El punto de enganche real es una sola función, no "tres caminos":**
  `_enviar_email_por_estado` tiene **cinco** llamadores (alta directa,
  verificación, aprobación, promoción de lista de espera, y el reenvío al
  resubmitir con un email ya `confirmed`), no tres. Enganchar
  `emitir_entrada` ahí en vez de en cada llamador cubre los cinco de una vez
  y aprovecha que ya es la función que decide "esto está confirmado, hay que
  actuar" — sin repetir la condición por quinta vez. Corregido en la fase 1.
- **`emitir_entrada` no puede asumir que el evento ya está cargado:** algunos
  llamadores de `_enviar_email_por_estado` (`confirm_waitlist_promotion`) no
  tienen el `Event` en variable local. `emitir_entrada` debe cargarlo por su
  cuenta (`session.get`) en vez de exigir un parámetro adicional que
  obligaría a tocar la firma de los cinco llamadores. Corregido en la fase 1.
- **Enmascarado de email en la búsqueda manual era una invención, no un
  requisito:** el PRD no pide ocultar el email en `tickets/search`, y el
  propio caso de uso (confirmar la identidad de alguien en la puerta) exige
  verlo completo — mismo criterio que ya usa el panel de organizador con
  `registrations:read`. Corregido en la fase 2 (quitado el enmascarado).
- **Backfill de `tickets:write` a `volunteer` verificado contra el esquema
  real:** `roles.key` existe y tiene `UNIQUE(organization_id, key)`
  (`roles/models.py`), así que anclar el backfill a `roles.key = 'volunteer'`
  además de al ancla habitual `organizations:write` es viable tal como se
  describe en la fase 1 — mismo patrón exacto que la migración `0010` ya usa
  para `registrations:*` (verificado línea a línea).
- **`PyJWT` ya es una dependencia real** (`pyjwt>=2.13,<3.0` en
  `pyproject.toml`), pero **`qrcode`/`Pillow` no lo son** — la fase 4 tiene
  que añadir una dependencia nueva para generar la imagen, no asumir que ya
  existe una vía. Ya reflejado como riesgo explícito en la fase 4, no una
  omisión.

Confirmado sin cambios: FK compuestas y RLS coherentes con el resto del
esquema desde la fase 2; `event_registrations` no tiene relación ORM cargada
al `Event`, consistente con que `emitir_entrada` lo resuelva por su cuenta;
ningún solape con el alcance de la fase 5 (pagos) ni la fase 7 (ponencias/
reviews) del PRD — ambas quedan como no-goals explícitos.

## Predict / Debate (5 personas)

**Verdict: CAUTION** — sin bloqueantes, dos puntos a decidir explícitamente
antes de la fase 2 de trabajo (el resto es ejecutable tal cual).

**Acuerdos (4-5 personas):**
- Separar `event_tickets` de `event_registrations` (decisión #1) es correcto:
  el ciclo de vida y los permisos (`tickets:*` vs `registrations:*`) ya
  estaban pensados como cosas distintas desde la fase 0.
- Registrar cada intento de escaneo en `event_ticket_scans` en vez de solo el
  último resultado es la decisión más importante del plan: sin esa tabla, la
  sincronización offline no tiene forma honesta de resolver "¿quién llegó
  primero de verdad?" ni de dar auditoría al organizador.
- Reutilizar `BarcodeDetector` nativo con librería de respaldo, en vez de
  escribir un decodificador propio o exigir una única vía, es la elección
  correcta dado el hardware real (móviles del voluntariado, no dispositivos
  dedicados).

**Conflictos y resolución:**

| Tema | Architect | Security | Performance | UX | Devil's Advocate | Resolución |
|---|---|---|---|---|---|---|
| Permisos de escaneo sin acotar al roster del evento (decisión #7) | Consistente con el resto del modelo de autorización, que es 100% de organización | Un voluntario con `tickets:write` puede escanear entradas de eventos en los que no participa — aceptable con un evento único, pero es una superficie real si la instalación crece a multi-evento simultáneo con equipos que no se conocen entre sí | Sin impacto | Un voluntario asignado a un evento pequeño no debería poder "curiosear" el check-in de otro evento de la misma organización en el mismo día | Acotar al roster sería el primer ACL por evento del proyecto — ¿vale la pena la complejidad nueva para un riesgo que hoy, con un solo evento (IAWIC), no existe? | Mantener sin acotar para el MVP, tal como ya decide el plan (decisión #7); si la instalación aloja eventos simultáneos con equipos de voluntariado no confiables entre sí, esa es la señal concreta para añadir el ACL por roster — no antes |
| Margen de 48h tras `ends_at` para la caducidad del QR (decisión #4) | Razonable, absorbe cierres tardíos | Una entrada que sigue siendo válida 48h después de terminado el evento es una ventana de uso indebido más larga de lo estrictamente necesario, aunque el `used_at` ya la invalide tras el primer uso real | Sin impacto | Un evento de varios días (como IAWIC, "10/09/2026-16/09/2026" en los fixtures de prueba) con `ends_at` al final necesita que el QR siga sirviendo el último día, no solo el primero — 48h de margen sobre el fin, no sobre el inicio, ya lo cubre | ¿Por qué 48h y no 24 o 72? Es un número sin justificar más allá de "parece razonable" | Mantener 48h como valor por defecto configurable (`ticket_qr_expiry_margin_hours`, ya así en la fase 1) — no hace falta acertar el número exacto en el plan si es una variable de configuración, no una constante en código; ajustar después de la primera edición real si hace falta |
| Generar la imagen del QR en el servidor (fase 4) vs. que el cliente/email la genere a partir de un dato ya en el HTML | El QR tiene que decodificar a un JWT completo (no una URL corta), así que generarlo como imagen en servidor es más simple que depender de que el cliente de correo ejecute JS | Sin objeción — el JWT no lleva datos personales (decisión no-funcional ya en el plan), así que la imagen tampoco filtra nada nuevo | Generar una imagen PNG por email añade trabajo de CPU al encolar el email, pero el volumen (cientos de confirmaciones, no miles por segundo) no lo hace un problema real | Un QR como imagen adjunta/incrustada es lo único que funciona de forma fiable en clientes de correo (nada de JS ni SVG interactivo) | ¿Hace falta que el email tenga QR incrustado, o basta un enlace a `/mi-entrada` que sí lo muestre? | Confirmado: imagen incrustada en el email (mejor UX, no depende de que la persona haga clic en nada más), con `/mi-entrada` como respaldo si el email falla o se pierde — ambas cosas ya estaban en la fase 4, no se cambia nada |

**Resumen de riesgos:**

| Riesgo | Severidad | Señal temprana | Mitigación |
|---|---|---|---|
| Escaneo no acotado al roster del evento (decisión #7) | Low (con un solo evento activo) | La organización empieza a gestionar varios eventos simultáneos con equipos de voluntariado distintos que no deberían verse entre sí | Añadir ACL por roster (`event_members`) sobre `tickets:*` cuando aparezca ese caso real, no antes |
| Dependencia nueva para generar la imagen del QR (fase 4) | Low | Ya identificado como riesgo explícito en la fase 4 | Elegir la librería más ligera que cubra PNG a partir de texto, sin funciones adicionales |
| Soporte desigual de `BarcodeDetector` en dispositivos reales del voluntariado (fase 3) | Medium | Un dispositivo concreto no detecta ningún QR ni con la librería de respaldo | La búsqueda manual (fase 2/3) es un respaldo real, no solo teórico — probarla explícitamente en la prueba manual de la fase 3, no solo la cámara |

**Recomendaciones:**
1. Mantener la decisión #7 (sin ACL por roster) tal como está para el MVP;
   no ampliar sin que aparezca el caso real de multi-evento simultáneo con
   equipos no confiables entre sí.
2. `ticket_qr_expiry_margin_hours` queda como configuración, no como
   constante — no bloquear el plan por acertar el número exacto.
3. Confirmado: QR incrustado en el email + `/mi-entrada` como respaldo,
   ambos ya en el alcance de la fase 4, sin cambios.
