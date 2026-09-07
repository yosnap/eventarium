---
phase: 2
title: "Fase 2: Formulario público, verificación y consentimientos"
status: pending
priority: P1
effort: "2.5-3d"
dependencies: [1]
---

# Fase 2: Formulario público, verificación y consentimientos

## Overview

El asistente rellena el formulario en la página pública del evento, pasa por
Turnstile, recibe un email de verificación y, al confirmar, la inscripción
queda en el estado que le corresponda (`confirmed`, `pending_approval` o
`waitlisted` según `registration_mode` y aforo). Esta fase entrega el alta
completa hasta ese punto; aprobación manual y lista de espera con promoción
llegan en la fase 3.

## Requirements

- Functional:
  - `POST /api/v1/public/events/{slug}/registrations`: email, nombre,
    respuestas a `event_registration_questions` (validadas contra el tipo de
    cada pregunta y las obligatorias), los tres consentimientos, token de
    Turnstile. Reutiliza `verify_turnstile_token` de `app/core/turnstile.py`.
    La **respuesta HTTP es siempre idéntica** para no filtrar hacia el
    llamador anónimo si el email ya estaba inscrito (mismo principio que
    `resend_verification` en `auth/service.py`): si `(event_id, email)` ya
    existe, no crea una segunda fila, y por dentro reencola el email que le
    corresponda a su estado actual (verificación, confirmación, lista de
    espera…) — esto no es una fuga hacia terceros, solo el propio dueño del
    email ve esa bandeja de entrada; lo que nunca varía es la respuesta
    pública. Resuelve `user_id` con `app_find_user_by_email` (ver Fase 1).
  - Si `email_verification_required` es verdadero: la inscripción nace en
    `pending_verification` y se genera un token opaco de propósito
    `email_verify_registration` en Redis (`app/modules/auth/verification.py`,
    mismo TTL de 24h que la verificación de cuentas) con payload
    `registration_id`; se encola el email de verificación con ese token.
  - `POST /api/v1/public/registrations/verify`: recibe el token, lo resuelve
    con `GETDEL` (un solo uso) contra Redis, marca `verified_at`, y evalúa
    el siguiente estado:
    - `registration_mode = free` y hay aforo libre → `confirmed` (dispara
      email de confirmación, fase 4).
    - `registration_mode = free` y no hay aforo libre → `waitlisted`.
    - `registration_mode = approval` → `pending_approval` (haya o no aforo;
      la disponibilidad se revalúa en el momento de aprobar, fase 3).
  - Si `email_verification_required` es falso: el alta evalúa el estado
    anterior directamente al enviar el formulario, sin paso de verificación.
  - Cálculo de aforo: `COUNT(*) FROM event_registrations WHERE event_id = ?
    AND status = 'confirmed'` con bloqueo de fila sobre el evento
    (`SELECT ... FOR UPDATE` de la fila de `events`) durante la transición a
    `confirmed`, para que dos verificaciones simultáneas no superen
    `capacity`.
  - Página pública del formulario (Angular, SSR): añadida a
    `apps/web/src/app/features/public/events/event-page.ts` o como ruta
    propia enlazada desde ella — reutiliza el layout/branding público ya
    existente de la fase 2 del PRD. Renderiza las preguntas según su tipo
    (texto corto, radio, checkboxes) y los tres consentimientos como
    casillas independientes con su texto de finalidad.
  - Página de resultado de verificación (`/verificar-inscripcion?token=...`),
    mismo patrón que `/verificar-correo`.
- Non-functional:
  - Rate limiting sobre el endpoint de alta (mismo mecanismo que ya protege
    otros formularios públicos, vía Redis).
  - Mensajes de error genéricos que no filtren si un email existe, aforo
    exacto restante, ni detalles internos.
  - Validación estricta de `value` contra `options` para preguntas
    `single_choice`/`multiple_choice`: un valor fuera de las opciones
    declaradas se rechaza (400), no se guarda "tal cual".
  - Accesibilidad WCAG 2.1 AA en el formulario: etiquetas asociadas, orden de
    foco, mensajes de error anunciados.

## Validation

- Test de alta: evento `free` con aforo 1 → primera inscripción verificada
  queda `confirmed`, la segunda queda `waitlisted`.
- Test de alta: evento `approval` → toda inscripción verificada queda
  `pending_approval` independientemente del aforo.
- Test de no filtrado: dar de alta el mismo email dos veces no crea una
  segunda fila y responde con el mismo código/formato que un alta nueva.
- Test de concurrencia (o revisión de diseño si no es viable en CI):
  dos verificaciones simultáneas contra el último hueco de aforo no dejan
  `confirmed` a más personas que `capacity`.
- Prueba manual en navegador (Playwright/webapp-testing) del formulario
  público: envío, email de verificación (log/mailhog local), clic, estado
  final visible.

## Risk & Rollback

- Riesgo principal: condición de carrera de aforo — cubierta por el bloqueo
  de fila explícito en Requirements. Si el bloqueo introduce contención
  inaceptable bajo carga real, revisar en la fase 4 antes del cierre (el PRD
  exige 1.000 inscripciones/hora sin degradación).
- Rollback: feature está detrás de rutas nuevas; deshabilitar el enlace al
  formulario en la página pública basta para desactivarla sin migración.
