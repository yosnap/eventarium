---
phase: 2
title: "Fase 2: Formulario público, verificación y consentimientos"
status: done
priority: P1
effort: "2.5-3d"
dependencies: [1]
---

## Estado — implementado 2026-09-08

Rama `feat/0.14.0-formulario-publico-verificacion-consentimientos` (desde
`develop`, sin mergear todavía).

**Archivos backend:**
- `apps/api/app/modules/registrations/repository.py`, `service.py`, `schemas.py`, `public_router.py` (nuevos)
- `apps/api/app/core/tasks.py` — `send_registration_verification_email` + `_base_url_de_organizacion` (dominio primario de la organización, no `web_base_url` genérico — hallazgo real durante la implementación, ver abajo)
- `apps/api/app/core/ratelimit.py` — `INSCRIPCION_POR_IP`, `VERIFICACION_INSCRIPCION_POR_IP`
- `apps/api/app/modules/auth/verification.py` — `PROPOSITO_VERIFICACION_INSCRIPCION`
- `apps/api/app/main.py` — router montado
- `apps/api/tests/test_registrations_public.py` (nuevo, 17 tests)

**Archivos frontend:**
- `apps/web/src/app/core/registrations/registrations.service.ts` (nuevo)
- `apps/web/src/app/features/public/events/registration-page.ts` + `.spec.ts` (nuevo) — ruta `/eventos/:slug/inscribirse`
- `apps/web/src/app/features/public/events/verify-registration-page.ts` + `.spec.ts` (nuevo) — ruta `/verificar-inscripcion`
- `apps/web/src/app/features/public/events/event-page.ts` — enlace "Inscribirme"
- `apps/web/src/app/app.routes.ts`, `public/assets/i18n/es-ES.json` — rutas y textos nuevos

**Hallazgo de diseño real, no anticipado en el plan:** el enlace de
verificación no puede usar `settings.web_base_url` (genérico para toda la
instalación) porque cada organización resuelve su propio tenant por `Host` —
un enlace al host equivocado no encontraría la inscripción al volver. Se
añadió `_base_url_de_organizacion()` en `tasks.py`, que resuelve el dominio
primario de `organization_domains` con `maintenance_session()` (sin
`Request` del que partir, igual que `sweep_unverified_accounts`). Esto
también resuelve solo: `/public/registrations/verify` no necesita el
`organization_id` en el token porque la petición ya llega con el `Host`
correcto — mismo mecanismo `OrganizationDep`/`DbDep` que cualquier otro
endpoint público.

**Verificado (comandos ejecutados en esta sesión):**
- `pytest -q` (API completa): **214 passed**.
- `ruff check .` / `ruff format --check .` (API): sin hallazgos.
- `mypy app/modules/registrations app/core/tasks.py app/core/ratelimit.py`: sin errores.
- `ng test` (web completo, incluye axe): **106 passed**, sin violaciones de accesibilidad en las 2 páginas nuevas.
- `ng lint` / `prettier --check` (web): sin hallazgos.
- `ng build` (web): compila sin errores.
- `openapi.json` y los tipos generados del cliente Angular, regenerados y verificados contra el diff exacto que exige el CI.

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

### Checklist de criterios de aceptación (Requirements/Validation de esta fase)

Functional:
- [x] `POST /public/events/{slug}/registrations` con validación de respuestas y consentimientos, Turnstile — `public_router.py::create_registration`
- [x] Respuesta HTTP siempre idéntica, no crea segunda fila, reencola verificación si procede — `test_el_mismo_email_no_crea_una_segunda_inscripcion_y_responde_igual`, `test_reenviar_a_un_email_ya_inscrito_reencola_el_correo_de_verificacion` (passed)
- [x] `user_id` resuelto con `app_find_user_by_email` — `repository.find_user_id_by_email`
- [x] `pending_verification` + token Redis (`GETDEL`, TTL 24h) cuando `email_verification_required` — `test_alta_con_verificacion_obligatoria_queda_pendiente_de_verificacion` (passed)
- [x] `POST /public/registrations/verify` con evaluación de estado siguiente — `test_verificar_con_aforo_libre_confirma`, `test_evento_con_aprobacion_queda_pendiente_de_aprobacion_aunque_haya_aforo` (passed)
- [x] `free`+aforo agotado → `waitlisted` — `test_segunda_verificacion_tras_agotar_aforo_queda_en_lista_de_espera` (passed)
- [x] Sin verificación exigida, estado evaluado al enviar el formulario — `test_evento_sin_verificacion_evalua_el_estado_al_enviar_el_formulario` (passed)
- [x] Bloqueo de fila (`SELECT...FOR UPDATE`) durante la evaluación de aforo — `repository.lock_event_for_capacity`, usado por `submit_registration` y `verify_registration`
- [x] Página pública del formulario, con preguntas por tipo — `registration-page.ts`, 3/3 tests de axe/render passed
- [x] Página de resultado de verificación — `verify-registration-page.ts`, 3/3 tests passed

Non-functional:
- [x] Rate limiting en alta y verificación — `INSCRIPCION_POR_IP`, `VERIFICACION_INSCRIPCION_POR_IP` aplicados en `public_router.py`
- [x] Mensajes genéricos, sin filtrar aforo ni existencia de email — verificado por los tests de no-filtrado
- [x] Validación estricta de `value` contra `options` — `test_una_opcion_invalida_falla`, `test_una_pregunta_obligatoria_sin_respuesta_falla`, `test_una_respuesta_a_pregunta_ajena_falla` (passed)
- [x] Accesibilidad — `ng test` con axe: 0 violaciones en las 6 pruebas de las 2 páginas nuevas

- [x] Test de concurrencia real: `test_dos_verificaciones_simultaneas_no_superan_el_aforo`, dos `POST /verify` concurrentes (`asyncio.gather`) contra el último hueco de aforo → exactamente un `confirmed` y un `waitlisted`, nunca dos `confirmed`. Ejecutado 5 veces seguidas sin fallar (no es una pasada por suerte).

**Hueco real, no maquillado:** no hay prueba manual en navegador real
(Playwright) del flujo completo — cubierto por los tests de integración
HTTP + los tests de accesibilidad del componente (axe), pero no es lo mismo
que una sesión de navegador real. Queda para antes de cerrar la fase 4,
junto con la prueba de carga que exige el PRD (1.000 inscripciones/hora).

## Risk & Rollback

- Riesgo principal: condición de carrera de aforo — cubierta por el bloqueo
  de fila explícito en Requirements. Si el bloqueo introduce contención
  inaceptable bajo carga real, revisar en la fase 4 antes del cierre (el PRD
  exige 1.000 inscripciones/hora sin degradación).
- Rollback: feature está detrás de rutas nuevas; deshabilitar el enlace al
  formulario en la página pública basta para desactivarla sin migración.
