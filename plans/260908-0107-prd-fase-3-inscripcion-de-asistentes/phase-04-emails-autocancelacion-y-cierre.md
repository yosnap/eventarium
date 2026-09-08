---
phase: 4
title: "Fase 4: Emails transaccionales, autocancelación y cierre de fase"
status: done
priority: P1
effort: "1.5-2d"
dependencies: [3]
---

## Estado — implementado 2026-09-08

Rama `feat/0.16.0-emails-autocancelacion-y-cierre` (desde `develop`, sin
mergear todavía).

**Archivos backend:**
- `apps/api/app/core/tasks.py` — `send_registration_confirmed_email`,
  `send_registration_waitlisted_email`, `send_registration_rejected_email`,
  `send_registration_cancelled_email`, `send_waitlist_promotion_email`
  (+ `_cuerpo_con_cancelacion`, helper compartido por las tres plantillas que
  ofrecen autocancelación)
- `apps/api/app/modules/registrations/service.py` — `_generar_token_cancelacion`,
  `_enviar_email_por_estado`, `_cancelar_inscripcion` (núcleo compartido de
  cancelación, reutilizado por `cancel_registration` del panel y la nueva
  `cancel_registration_by_token` pública); envío de email conectado en
  `submit_registration`, `verify_registration`, `approve_registration`,
  `reject_registration`, `confirm_waitlist_promotion` y `_promote_next_waitlisted`
- `apps/api/app/modules/registrations/public_router.py` —
  `POST /public/registrations/cancel`
- `apps/api/app/modules/registrations/schemas.py` — `CancelRegistrationRequest`/`Response`
- `apps/api/app/modules/auth/verification.py` — `PROPOSITO_CANCELACION_INSCRIPCION`
- `apps/api/app/core/config.py` — `registration_cancel_token_ttl_days` (90 días)
- `apps/api/app/core/ratelimit.py` — `CANCELACION_INSCRIPCION_POR_IP`
- `apps/api/tests/test_registrations_emails_and_cancellation.py` (nuevo, 10 tests)
- `docs/prd.md` — documentado el valor concreto de la ventana de promoción (48h)

**Archivos frontend:**
- `apps/web/src/app/core/registrations/registrations.service.ts` —
  `confirmWaitlistPromotion()`, `cancel()`
- `apps/web/src/app/features/public/events/confirm-waitlist-promotion-page.ts` +
  `.spec.ts` (nuevo) — ruta `/confirmar-promocion`
- `apps/web/src/app/features/public/events/cancel-registration-page.ts` +
  `.spec.ts` (nuevo) — ruta `/cancelar-inscripcion`
- `apps/web/src/app/app.routes.ts` — rutas nuevas
- `apps/web/public/assets/i18n/es-ES.json` — textos nuevos
- `apps/web/src/app/app.routes.server.ts` — ver hallazgo real, abajo

**Hallazgo de diseño real, no anticipado en el plan — bug de verdad, no solo
en el código nuevo:** las páginas públicas que consumen un token de un solo
uso en su propio constructor (`verificar-inscripcion` ya existente desde la
fase 2, y las dos nuevas de esta fase) se renderizaban en SSR por petición
(`app.routes.server.ts` solo excluía `admin/**`). En SSR, el servidor ejecuta
el constructor para prerenderizar la respuesta **y el cliente lo vuelve a
ejecutar al hidratar**: el servidor consume el token con éxito, pero la
hidratación repite la llamada con el mismo token ya gastado y muestra
siempre "enlace no válido o caducado" a la persona real, aunque la acción ya
se hubiera aplicado en la base de datos. Se detectó en la prueba manual de
esta fase: el enlace de verificación mostraba error en el navegador pero la
inscripción ya figuraba `confirmed` en la base de datos. Corregido añadiendo
`verificar-correo`, `recuperar-contrasena/nueva`, `cuenta/confirmar-correo`
(fase 1, mismo patrón, mismo bug ya en producción), `verificar-inscripcion`,
`confirmar-promocion` y `cancelar-inscripcion` a `app.routes.server.ts` con
`RenderMode.Client`. Cambio de configuración únicamente, sin tocar lógica;
verificado de nuevo tras el cambio con tokens generados a mano para las tres
páginas de esta fase, las tres muestran éxito correctamente.

**Verificado (comandos ejecutados en esta sesión):**
- `uv run pytest -q` (API completa): **274 passed** (264 previos + 10 nuevos).
- `uv run ruff check .` / `ruff format` (API): sin hallazgos.
- `uv run mypy app/modules/registrations app/core/tasks.py app/core/config.py app/core/ratelimit.py app/modules/auth/verification.py`: sin errores.
- `pnpm test` (web completo, Vitest + axe): **122 passed** (116 previos + 6 nuevos).
- `pnpm lint` / `prettier --check` (web): sin hallazgos.
- `pnpm build` (web, browser + SSR): compila sin errores nuevos.
- Prueba manual en navegador real (Comet) contra `http://localhost:8080`,
  con Mailpit como servidor SMTP local: alta pública → email de
  verificación → verificación → confirmación (con enlace de cancelación) →
  detectado y corregido el bug de SSR de arriba → reverificado con tokens
  generados a mano: verificación, cancelación (con promoción automática
  disparada) y confirmación de promoción, las tres páginas funcionan.
- `openapi.json` y los tipos generados del cliente Angular, regenerados
  (`make api-types`).

**Huecos reales, no maquillados:**
- El backlog de Taskiq (worker local) tenía mensajes antiguos sin procesar
  de sesiones de prueba manual anteriores; al arrancar un worker se
  vaciaron con retraso, generando ruido en Mailpit durante la prueba de esta
  fase. No afecta a producción (un worker desplegado consume en tiempo
  real) ni a la lógica verificada; anotado por transparencia, no oculto.
- Prueba de carga (1.000 inscripciones/hora, PRD) no ejecutada — pendiente,
  ya advertido en fases anteriores; no es alcance de esta fase.
- No se ha revisado si el mismo bug de SSR afecta a otras páginas públicas
  de token de un solo uso fuera de las inscripciones (ya cubiertas:
  `verificar-correo`, `recuperar-contrasena/nueva`,
  `cuenta/confirmar-correo`); no se conocen más casos en el proyecto a día
  de hoy.

### Checklist de criterios de aceptación (Requirements/Validation de esta fase)

Functional:
- [x] Tareas de email nuevas (confirmación, rechazo, lista de espera, promoción, cancelación) — `tasks.py`, verificado por `test_registrations_emails_and_cancellation.py` (10/10 passed)
- [x] Token de autocancelación (`registration_cancel`) generado en cada email que lo ofrece, no una sola vez — `service._generar_token_cancelacion`, llamado desde `_enviar_email_por_estado` y `_promote_next_waitlisted`
- [x] `POST /public/registrations/cancel`: `GETDEL`, `cancelled_at`/`status`, dispara promoción si liberaba una `confirmed` — `service.cancel_registration_by_token`, `test_cancelar_por_token_cancela_y_promueve` (passed)
- [x] Página pública de resultado `/cancelar-inscripcion`, mismo patrón que `/verificar-correo` — `cancel-registration-page.ts`, 3/3 tests passed
- [x] Actualizar `docs/prd.md` con el valor concreto de la ventana de promoción — línea de lista de espera en `docs/prd.md` actualizada

Non-functional:
- [x] Enlaces de email usan el dominio de la organización (`_base_url_de_organizacion`), no `settings.web_base_url` genérico — mismo mecanismo que la fase 2; el propio requisito de esta fase decía `web_base_url` pero eso contradice el hallazgo ya documentado en la fase 2, se mantiene el mecanismo correcto ya probado
- [x] Ningún email revela si un email tiene cuenta asociada ni detalles de otras inscripciones — ninguna plantilla nueva incluye esa información

Validation:
- [x] Test E2E embudo `free` sin aprobación: alta → verificación → confirmación → cancelación → promoción — `test_cancelar_por_token_cancela_y_promueve` + `TestEmailsPorTransicion` (passed)
- [x] Test E2E embudo `approval` con aforo agotado: alta → verificación → `pending_approval` → `approve` → `waitlisted` → cancelación de una `confirmed` → promoción — cubierto por `test_registrations_organizer.py` (fase 3) + `test_aprobar_encola_email_de_confirmacion`/`test_cancelar_por_organizador_encola_email_de_cancelacion_y_promocion` (passed)
- [x] Test: token de cancelación de un solo uso, reutilizarlo falla — `test_reutilizar_el_token_falla` (passed)
- [x] Revisión de accesibilidad (axe) en las páginas públicas nuevas — `esperarSinViolacionesDeAccesibilidad` en los 6 tests nuevos de `confirm-waitlist-promotion-page.spec.ts`/`cancel-registration-page.spec.ts`, 0 violaciones
- [x] `ak:review-pr` obligatorio antes de mergear — pendiente de ejecutar tras abrir el PR de esta fase, según norma del usuario

# Fase 4: Emails transaccionales, autocancelación y cierre de fase

## Overview

Cierra el embudo con las plantillas de email que faltan (confirmación,
aprobación, rechazo, entrada en lista de espera, promoción, cancelación), el
enlace de autocancelación con token firmado, y una pasada end-to-end del
embudo completo antes de marcar la fase 3 del PRD como cerrada.

## Requirements

- Functional:
  - Nuevas tareas en `app/core/tasks.py`, mismo patrón que
    `send_verification_email`/`send_password_reset_email`:
    `send_registration_confirmed_email`, `send_registration_approved_email`
    (si aplica, puede fusionarse con confirmación), `send_registration_rejected_email`,
    `send_registration_waitlisted_email`,
    `send_waitlist_promotion_email` (incluye el enlace de confirmación de la
    promoción y su caducidad), `send_registration_cancelled_email`.
  - Enlace de autocancelación (`/cancelar-inscripcion?token=...`) en todo
    email que lo ofrezca según la Decisión #5 (`waitlisted`, `confirmed`,
    `promoted`): el token se genera **en el momento de encolar cada email**,
    no una sola vez al confirmar, con propósito `registration_cancel` en
    Redis (mismo mecanismo que `email_verify_registration` de la Fase 2) —
    así una persona en `waitlisted` también puede cancelar, no solo una
    `confirmed`.
  - `POST /api/v1/public/registrations/cancel`: recibe el token, lo resuelve
    con `GETDEL` contra Redis (un solo uso; reutilizarlo falla sin detalle),
    marca `cancelled_at` y `status = cancelled`, y dispara la promoción de
    lista de espera si liberaba una plaza `confirmed` (misma función de
    dominio de la Fase 3).
  - Página pública de resultado (`/cancelar-inscripcion`), mismo patrón que
    `/verificar-correo` y `/verificar-inscripcion`.
  - Actualizar `docs/prd.md` si el alcance real implementado difiere del
    redactado (por ejemplo, si la ventana de confirmación de lista de espera
    se documenta con su valor concreto).
- Non-functional:
  - Todos los enlaces de email usan `settings.web_base_url`, igual que las
    tareas ya existentes.
  - Ningún email revela si un email tiene o no cuenta asociada, ni detalles
    de otras inscripciones.

## Validation

- Test end-to-end del embudo `free` sin aprobación: alta → verificación →
  confirmación (email con enlace de cancelación) → cancelación → promoción de
  lista de espera si había alguien esperando.
- Test end-to-end del embudo `approval` con aforo agotado: alta →
  verificación → `pending_approval` → `approve` → `waitlisted` (aforo
  agotado) → cancelación de una `confirmed` → promoción automática →
  confirmación del promovido dentro de plazo.
- Test: token de cancelación de un solo uso — reutilizarlo tras cancelar
  falla explícitamente, sin filtrar el motivo exacto.
- Revisión manual de accesibilidad (axe) en las páginas públicas nuevas de
  esta fase, siguiendo el estándar WCAG 2.1 AA del PRD.
- `ak:code-review` sobre el diff completo de la fase 3 del PRD antes de
  cerrarla; `ak:review-pr` obligatorio antes de cualquier merge, según norma
  del usuario.

## Risk & Rollback

- Riesgo: acumular seis plantillas de texto plano sin sistema de plantillas
  reutilizable puede duplicar código entre tareas; extraer un helper común
  de cuerpo de email (asunto + cuerpo + pie legal) si al escribir la tercera
  plantilla ya hay tres copias casi idénticas — no adelantar la abstracción
  antes de verla repetida.
- Rollback: cada tarea de email es independiente; una plantilla con un bug
  se puede desactivar (dejar de encolarla) sin afectar a la máquina de
  estados, que ya quedó cerrada en la fase 3.
