---
title: "PRD Fase 3 — Inscripción tipo Luma"
description: "Formulario público de inscripción sin cuenta obligatoria, verificación de email, preguntas personalizadas, consentimientos, aprobación bajo demanda, lista de espera con promoción automática y estadísticas."
status: validated
priority: P1
effort: "9-11d"
tags: [inscripcion, registro, verificacion, aprobacion, lista-de-espera, emails]
created: 2026-09-08
prd_phase: 3
blockedBy: [2]
blocks: [4]
---

# PRD Fase 3 — Inscripción tipo Luma

## Overview

La fase 2 dejó el evento y su agenda configurables, incluidos los campos de
inscripción (`registration_mode`, `email_verification_required`, `capacity`) como
mera configuración sin lógica detrás. Esta fase construye esa lógica: el
formulario público de inscripción, la verificación de email, las preguntas
personalizadas por evento, los consentimientos auditables, la aprobación bajo
demanda cuando el aforo es limitado, la lista de espera con promoción automática,
y las estadísticas de conversión del embudo. Es la base de la fase 4 (entradas
QR y check-in): sin una inscripción `confirmed` no hay a qué emitir una entrada.

Alcance según `docs/prd.md` §4.3, únicamente lo marcado **M** (MVP IAWIC
Valencia). Reutiliza infraestructura ya existente de la fase 1: envío de correo
(`app/core/email.py`), cola de tareas y scheduler cron (`app/core/tasks.py`,
Taskiq + Redis Streams), verificación Cloudflare Turnstile
(`app/core/turnstile.py`) y el patrón de token firmado de un solo uso ya usado
para verificación de correo y recuperación de contraseña.

## Non-goals

Entradas QR, control de acceso y app de escaneo (fase 4). Pagos, tipos de
entrada de pago y Stripe Checkout (fase 5 — nótese que `registration_mode:
paid` ya existe como valor de configuración desde la fase 2, pero esta fase
solo implementa los modos `free` y `approval`; un evento `paid` queda fuera de
alcance hasta que exista cobro). Patrocinadores (fase 6). Contabilidad (fase
7). CfP, reviews de ponencias y escaneo automático de cookies (todos **S**/**P**
en el PRD). Plantillas de email editables por el organizador (esta fase entrega
las plantillas fijas necesarias; la edición por organización es una mejora
posterior no pedida en el PRD para el MVP).

## Decisiones tomadas — Sesión de validación 2026-09-08

| # | Pregunta | Decisión |
|---|---|---|
| 1 | Duplicados: mismo email, mismo evento | Una única inscripción por `(event_id, email)`. Reenviar el formulario con el mismo email no crea una segunda fila: reenvía el email correspondiente al estado actual (verificación pendiente, ya confirmada, etc.), igual que el patrón ya usado en `users` para no filtrar si un correo existe |
| 2 | Lista de espera | Automática con ventana de confirmación: al liberarse una plaza (cancelación o rechazo de una inscripción confirmada), se promueve automáticamente a la primera persona de la lista de espera y se le da un plazo fijo para confirmar; si no confirma a tiempo, pasa a la siguiente persona. El barrido de expiración corre en el scheduler cron ya existente (`app/core/tasks.py`), mismo patrón que `sweep_unverified_accounts_task` |
| 3 | Tipos de pregunta personalizada | Texto corto, selección única y selección múltiple (checkbox), las tres desde el MVP |
| 4 | Confirmación sin entrada QR | La fase 3 entrega el flujo completo de inscripción y un email de confirmación de texto (sin QR). La fase 4 añade el QR reutilizando la misma plantilla/estado `confirmed`, sin tocar la máquina de estados de esta fase |
| 5 | Autocancelación por el asistente | Sí: el email de confirmación (y el de lista de espera/promoción) incluye un enlace de cancelación con token firmado de un solo uso, mismo patrón que verificación de correo. Cancelar libera la plaza y dispara la promoción de lista de espera si aplica |
| 6 | Edición de preguntas con respuestas ya guardadas | Solo se permite añadir preguntas nuevas una vez que el evento tiene inscripciones; borrar o cambiar el tipo de una pregunta con respuestas asociadas se bloquea en la API (409), para no dejar respuestas huérfanas o de un tipo distinto al declarado |

## Requirements

- Functional:
  - `event_registration_questions`: preguntas personalizadas por evento
    (`short_text` / `single_choice` / `multiple_choice`), con opciones para los
    dos últimos tipos, orden y si son obligatorias.
  - `event_registrations`: email, nombre, respuestas a preguntas
    personalizadas (`event_registration_answers`, `jsonb` por pregunta),
    estado (`pending_verification` → `pending_approval` → `confirmed` /
    `rejected` / `cancelled` / `waitlisted`), enlace opcional a un `user_id` si
    el email coincide con una cuenta existente, timestamps de cada transición,
    token de cancelación.
  - `event_registration_consents`: consentimiento de tratamiento (obligatorio),
    marketing (opcional) y grabación de imagen/voz (opcional), cada uno con su
    timestamp — nunca una sola casilla genérica.
  - Formulario público de inscripción (SSR, en la página del evento):
    email + nombre + preguntas personalizadas + consentimientos + Turnstile.
  - Verificación de email por enlace, token firmado de un solo uso, caducidad
    24h — mismo patrón que `send_verification_email`. Configurable por evento
    vía `email_verification_required`; si está desactivada, la inscripción pasa
    directamente a evaluar aforo/aprobación.
  - Aprobación bajo demanda cuando `registration_mode = approval`: el
    organizador ve el email, nombre, respuestas y consentimientos, y
    acepta/rechaza con notificación personalizada.
  - Control de aforo (`capacity`): al confirmarse una inscripción que agotaría
    el aforo, las siguientes pasan automáticamente a `waitlisted` en vez de
    `confirmed`/`pending_approval`.
  - Lista de espera con promoción automática (ver decisión #2): tarea cron que
    expira promociones no confirmadas a tiempo y promueve a la siguiente
    persona.
  - Autocancelación por el asistente con token firmado (ver decisión #5) y
    cancelación manual por el organizador desde el panel.
  - Estadísticas por evento: iniciados, verificados, pendientes de aprobación,
    aprobados, rechazados, cancelados, en lista de espera, conversión
    (verificados/iniciados, confirmados/verificados).
  - Panel de organizador: listado de inscripciones con filtro por estado,
    detalle de una inscripción, gestión de preguntas personalizadas (con la
    restricción de la decisión #6), acciones de aprobar/rechazar/cancelar.
  - Emails transaccionales: verificación, confirmación, aprobación, rechazo,
    entrada en lista de espera, promoción desde lista de espera, cancelación
    confirmada. Reutilizan `app/core/email.py` y se encolan con Taskiq como
    las ya existentes.
- Non-functional:
  - RLS y FK compuestas `(id, organization_id)` en toda tabla nueva, mismo
    patrón que la fase 2 (`events`, `event_sessions`…) — ver
    `apps/api/app/modules/events/models.py`.
  - Permisos nuevos `registrations:read` / `registrations:write` (prefijo ya
    reservado en `app/core/permissions.py`), con el mismo backfill anclado a
    capacidad (`organizations:write`) que usó la fase 2 para `events:*`.
  - Turnstile obligatorio en el formulario público (`turnstile_enabled` ya
    existe); rate limiting sobre el endpoint de envío del formulario.
  - Endpoints públicos de inscripción/verificación/cancelación no deben
    filtrar si un email existe o no (mismo principio que registro de cuentas
    en la fase 1).
  - Accesibilidad WCAG 2.1 AA en el formulario público y en el panel — mismo
    estándar que el resto de la aplicación.
  - Migraciones encadenadas tras `0009_eventos_agenda_y_ponentes`, con
    `downgrade()` explícito.

## Fases de trabajo

1. **Modelo de datos, RLS y permisos** — tablas, migración, permisos,
   máquina de estados a nivel de base de datos (constraints de transición).
2. **Formulario público, verificación y consentimientos** — SSR del
   formulario, Turnstile, verificación de email, alta de la inscripción con
   control de aforo básico (confirmed vs waitlisted en el momento del alta).
3. **Aprobación, lista de espera automática y panel de organizador** —
   flujo de aprobación, cron de expiración/promoción de lista de espera,
   listado y acciones del panel, estadísticas, gestión de preguntas.
4. **Emails transaccionales, autocancelación y cierre de fase** — las
   plantillas de email restantes, el enlace de autocancelación firmado,
   pruebas end-to-end del embudo completo y cierre de la fase 3 del PRD.

## Riesgos

- La promoción automática de lista de espera con ventana de confirmación
  añade una tarea cron nueva (patrón ya probado con
  `sweep_unverified_accounts_task`, pero es concurrencia real sobre `capacity`:
  dos promociones simultáneas no deben poder confirmar más plazas que el
  aforo disponible). Mitigación: bloqueo a nivel de fila (`SELECT ... FOR
  UPDATE`) sobre el evento al recalcular aforo, igual que cualquier
  operación de aforo compartido.
- Los tres tipos de pregunta personalizada con validación de respuesta y
  bloqueo de edición cuando ya hay respuestas (decisión #6) es la pieza de
  UI/API más propensa a casos límite; se detalla en la fase 2 y se revisa en
  el red-team del plan antes de implementar.

## Red Team Review

Red-team ejecutado el 2026-09-08 contra el código real (`apps/api/app`,
migraciones). Hallazgos bloqueantes, ya aplicados a las fases correspondientes:

- **Tokens en Redis, no en columnas:** el plan original proponía
  `verification_token_hash`/`cancellation_token_hash` como columnas de
  `event_registrations`. Todo token de un solo uso del proyecto (verificación
  de correo, cambio de correo, recuperación de contraseña, refresh) vive en
  Redis con TTL y `GETDEL` atómico (`app/modules/auth/verification.py`,
  `app/modules/auth/service.py`), nunca como columna Postgres. Corregido en
  la Fase 1 (columnas eliminadas) y Fase 2/4 (tokens vía dos propósitos
  nuevos en `verification.py`).
- **Resolución de `user_id` bajo RLS:** el endpoint público no tiene
  organización en contexto, y `users` está bajo RLS que exige compartir
  organización. La resolución de `user_id` por email reutiliza la función
  `SECURITY DEFINER` ya existente `app_find_user_by_email`
  (`0004_correo_y_verificacion.py`), no una consulta directa. Corregido en
  Fase 1 y Fase 2.
- **Inconsistencia interna en la Decisión #5:** el email de lista de espera
  también debía llevar enlace de cancelación, pero la Fase 4 solo generaba el
  token "al confirmar". Corregido: el token se genera cada vez que se envía
  un email que lo ofrece, no una sola vez.
- **No-filtrado de email — precisión de redacción:** "reenvía el email
  correspondiente al estado actual" se aclaró para no confundir "la
  respuesta pública es siempre idéntica" (lo que de verdad exige el
  requisito) con "el email interno enviado es siempre el mismo" (que
  contradiría las seis plantillas distintas de la Fase 4).
- **Alcance no cubierto y documentado:** "emails enviados/entregados/
  abiertos" (PRD §4.3) queda fuera de esta fase por falta de webhooks del
  proveedor de email — anotado explícitamente en la Fase 3, no omitido en
  silencio.

Confirmado sin cambios: FK compuestas y RLS coherentes con `events`/
`event_sessions`; backfill de permisos por capacidad (`organizations:write`),
igual que el backfill real de `events:*` en `0009`; prefijo `registrations:*`
sin colisión; ningún solape con el alcance de las fases 4 (QR) o 5 (pagos)
del PRD.

## Predict / Debate (5 personas) — 2026-09-08

**Verdict: CAUTION** — sin bloqueantes; tres puntos a resolver antes de la
fase 3 de trabajo (aprobación + lista de espera), el resto es ejecutable tal
cual.

**Acuerdos (4-5 personas):**
- El modelo de datos (fase 1) es sólido: FK compuestas, RLS, tokens en Redis
  tras el red-team. Ninguna persona objeta el esquema.
- Reutilizar infraestructura existente (Turnstile, Taskiq/cron, email,
  `app_find_user_by_email`) en vez de construir de cero es la decisión
  correcta — menos superficie nueva, patrones ya probados en producción con
  la fase 1 del PRD.
- El endpoint público de alta y el de verificación necesitan rate limiting
  real (no solo mencionado) antes de exponerse: es la puerta de entrada más
  barata de abusar de todo el sistema.

**Conflictos y resolución:**

| Tema | Architect | Security | Performance | UX | Devil's Advocate | Resolución |
|---|---|---|---|---|---|---|
| Bloqueo de fila `SELECT...FOR UPDATE` sobre `events` al confirmar/aprobar/promover | Correcto para exactitud de aforo, pero es un único punto de serialización por evento — con 500 inscripciones en ráfaga (IAWIC) puede convertirse en cola de espera de locks | Sin objeción — es la única forma segura contra doble reserva de aforo | Riesgo real bajo carga: el PRD exige 1.000 inscripciones/hora sin degradación; un lock por evento serializa toda escritura de estado de ese evento, no solo el conteo | Un pico de tráfico (email de última hora "quedan 10 plazas") podría hacer que el formulario tarde perceptiblemente | ¿Hace falta bloqueo pesimista si el volumen real (500 personas, no 5.000) nunca va a generar contención real? | Mantener el bloqueo tal como está diseñado para la fase 2/3 (correctitud primero), pero añadir a la Fase 2 una nota de validación: medir contención con un test de carga simple antes de cerrar la fase 4, no rediseñar a ciegas |
| Ventana de confirmación de lista de espera fija a nivel de aplicación (no por evento) | Aceptable para MVP de un solo evento (IAWIC) | Sin objeción de seguridad | Sin impacto de rendimiento | Un organizador con varios eventos simultáneos y aforos muy distintos no puede ajustar la ventana por evento — mencionado ya como riesgo aceptado en la Fase 3 | Es exactamente el tipo de generalización prematura que YAGNI pide evitar: no se pidió configurabilidad por evento | Confirmado: dejarlo fijo por ahora, tal como ya decide el plan; no añadir campo nuevo sin que se pida |
| Preguntas personalizadas: "solo añadir, no borrar/cambiar tipo" tras la primera respuesta | Restricción de integridad correcta y simple | Sin objeción | Sin impacto | Puede frustrar a un organizador que se equivocó en el enunciado de una pregunta el primer día del evento, antes de que llegue tráfico real | ¿Y si el bloqueo se aplica desde la primera respuesta, no desde que el evento está "en producción"? Un typo corregido a los 5 minutos de la primera prueba interna ya quedaría bloqueado | Aclarar en la Fase 3 (gestión de preguntas): permitir borrar/cambiar tipo de una pregunta **sin respuestas asociadas**, tal como ya dice el plan — no cambiar la regla, solo confirmar que cubre el caso de "typo corregido a tiempo" porque la condición es "con respuestas", no "tras publicar el evento" |
| Confirmación del promovido de lista de espera: si no confirma a tiempo, ¿qué le llega? | Coherente con el resto de la máquina de estados | El token de confirmación de promoción no está descrito con el mismo detalle (Redis vs columna) que los otros tres tokens | Sin impacto | El plan no especifica si a la persona que "pierde" su turno de promoción se le notifica igual, o simplemente vuelve al final de la cola en silencio | Vale la pena decidirlo explícitamente para no descubrirlo a medio implementar | **Acción**: en la Fase 3, el token de `confirm-waitlist-promotion` debe seguir el mismo patrón Redis (`waitlist_promotion_confirm`, payload `registration_id`, TTL = ventana de promoción) que los demás — añadir esta línea a la Fase 3 antes de implementarla. Notificar al reasignado al final de la cola queda fuera de alcance explícito de esta fase (ya hay 6 plantillas de email en la Fase 4; no añadir una séptima sin que se pida) |

**Resumen de riesgos:**

| Riesgo | Severidad | Señal temprana | Mitigación |
|---|---|---|---|
| Contención del lock de aforo bajo ráfaga real | Medium | Latencia del endpoint de verificación/aprobación creciendo en el entorno de staging con tráfico simulado | Test de carga simple antes del cierre de la Fase 4; si aparece contención, acotar el `FOR UPDATE` a una fila de contador dedicada en vez de la fila completa de `events` |
| Token de confirmación de promoción sin especificar en el plan | Low | Se descubre a medio implementar la Fase 3 que falta decidir dónde vive | Añadir la línea de Redis al plan de la Fase 3 antes de empezar esa fase (ver tabla de arriba) |
| Rate limiting "mencionado" pero no diseñado con detalle (umbral, ventana, clave) | Medium | Un solo IP puede saturar el endpoint de alta en pruebas de aceptación | Al implementar la Fase 2, fijar umbral concreto (p. ej. mismo que ya usa el registro de cuentas) en vez de "rate limiting" genérico |

**Recomendaciones:**
1. Añadir a `phase-03-aprobacion-lista-de-espera-y-panel.md` que el token de
   `confirm-waitlist-promotion` usa el mismo mecanismo Redis que los demás
   (propósito `waitlist_promotion_confirm`, payload `registration_id`, TTL
   igual a la ventana de promoción) — evita descubrirlo a medio implementar.
2. Antes de cerrar la Fase 4, ejecutar una prueba de carga ligera sobre el
   endpoint de verificación/confirmación para confirmar que el bloqueo de
   fila no degrada por debajo del objetivo de 1.000 inscripciones/hora del
   PRD; si degrada, acotar el lock a un contador dedicado en vez de la fila
   de `events`.
3. Mantener la ventana de promoción fija a nivel de aplicación (no por
   evento) y la restricción de preguntas tal como están — ambas
   confirmadas correctas para el alcance del MVP, no ampliar sin que se
   pida.
