---
phase: 3
title: "Fase 3: Aprobación, lista de espera automática y panel de organizador"
status: done
priority: P1
effort: "3-3.5d"
dependencies: [2]
---

## Estado — implementado 2026-09-08

Rama `feat/0.15.0-aprobacion-lista-de-espera-y-panel` (desde `develop`, sin
mergear todavía).

**Archivos backend:**
- `apps/api/app/modules/registrations/router.py` (nuevo) — panel de
  organizador: listado/detalle/estadísticas, aprobar/rechazar/cancelar,
  CRUD de preguntas personalizadas
- `apps/api/app/modules/registrations/service.py` — `approve_registration`,
  `reject_registration`, `cancel_registration`, `_promote_next_waitlisted`,
  `confirm_waitlist_promotion`, `expire_waitlist_promotions`,
  `get_registration_stats`, CRUD de preguntas; refactor de
  `_evaluar_estado_por_aforo` para extraer `_evaluar_estado_por_capacidad`
  (reutilizada por `approve_registration` sin repetir la regla de aforo)
- `apps/api/app/modules/registrations/repository.py` — consultas del panel,
  lista de espera (`get_oldest_waitlisted`, `requeue_to_back_of_waitlist`,
  `events_with_expired_waitlist_promotions`), estadísticas, preguntas
- `apps/api/app/modules/registrations/schemas.py` — esquemas del panel
- `apps/api/app/modules/registrations/public_router.py` —
  `POST /public/registrations/confirm-waitlist-promotion`
- `apps/api/app/modules/auth/verification.py` — `generate_token` admite
  `ttl` variable; nuevo propósito `waitlist_promotion_confirm`
- `apps/api/app/core/config.py` — `waitlist_promotion_window_hours` (48h por
  defecto, fija a nivel de aplicación según el predict/debate del plan)
- `apps/api/app/core/tasks.py` — `expire_waitlist_promotions_task`, cron
  cada 15 min
- `apps/api/app/core/ratelimit.py` — `CONFIRMACION_PROMOCION_POR_IP`
- `apps/api/app/main.py` — router del panel montado
- `apps/api/tests/test_registrations_organizer.py` (nuevo, 32 tests)

**Archivos frontend:**
- `apps/web/src/app/features/admin/events/registration-types.ts` (nuevo) —
  tipos compartidos del dominio de inscripciones
- `apps/web/src/app/features/admin/events/event-registrations.ts` +
  `.spec.ts` (nuevo) — tarjetas de estadísticas, listado filtrable,
  aprobar/rechazar/cancelar; incrustado en `event-form.ts` junto a
  `event-agenda`
- `apps/web/src/app/features/admin/events/registration-detail-page.ts` +
  `.spec.ts` (nuevo) — ruta `admin/events/:id/registrations/:registrationId`
- `apps/web/src/app/features/admin/events/registration-questions.ts` +
  `.spec.ts` (nuevo) — CRUD de preguntas personalizadas
- `apps/web/src/app/app.routes.ts`, `public/assets/i18n/es-ES.json` — ruta y
  textos nuevos
- `apps/web/src/app/features/admin/events/event-form.spec.ts` — actualizado
  para las 3 peticiones HTTP nuevas que dispara el componente incrustado

**Decisión de diseño, no un hallazgo del plan:** el requisito de `reject`
("si liberaba una plaza que ya estaba `confirmed`, dispara la promoción")
no es alcanzable en la práctica — el propio requisito restringe `reject` a
partir únicamente de `pending_approval`, estado que nunca ocupó una plaza
`confirmed`. Se implementó `reject_registration` sin lógica de promoción,
con un docstring que explica por qué esa cláusula del requisito no aplica
dado el resto de la máquina de estados ya cerrada en la fase 1. `cancel`
(la única vía real desde `confirmed`) sí dispara la promoción.

**Verificado (comandos ejecutados en esta sesión):**
- `uv run pytest -q` (API completa): **264 passed** (232 previos + 32 nuevos; el runner de este proyecto no imprime el recuento final "N passed", contado por recolección con `--collect-only -q`).
- `uv run ruff check .` / `ruff format` (API): sin hallazgos tras formatear.
- `uv run mypy app/modules/registrations app/core/tasks.py app/core/ratelimit.py app/modules/auth/verification.py app/core/config.py`: sin errores.
- `pnpm test` (web completo, Vitest + axe): **116 passed** (106 previos + 10
  nuevos), sin violaciones de accesibilidad en listado/tabla/formularios
  nuevos.
- `pnpm build` (web, browser + SSR): compila sin errores nuevos (2
  advertencias NG8102 preexistentes en `event-agenda.ts`/`member-form.ts`,
  ajenas a esta fase).
- `pnpm lint` (web): sin hallazgos.
- `prettier --check` sobre los ficheros nuevos: **5 ficheros con formato
  incorrecto** entregados por el agente de frontend (`event-registrations.ts`
  y su spec, `registration-detail-page.ts` y su spec,
  `registration-questions.ts`) — corregido con `prettier --write` y
  reverificado (tests y build siguen en verde tras el formateo).
- `openapi.json` y los tipos generados del cliente Angular, regenerados
  (`make api-types`).

**Huecos reales, no maquillados:**
- No hay prueba manual en navegador real del panel completo
  (aprobar/rechazar, ver moverse la lista de espera) — cubierto por tests de
  integración HTTP (backend) y de componente con axe (frontend), no por una
  sesión de navegador real. Mismo hueco ya declarado en la fase 2; queda
  pendiente antes de cerrar la fase 4.
- El email de promoción de lista de espera **no se envía** en esta fase: el
  token de confirmación (`waitlist_promotion_confirm`) ya se genera y la
  ventana ya se marca, pero la plantilla de email es explícitamente fase 4
  de trabajo (`phase-04-emails-autocancelacion-y-cierre.md`), que reutilizará
  este mismo token.
- Prueba de carga (1.000 inscripciones/hora, PRD) no ejecutada — pendiente
  antes de cerrar la fase 4, según ya advertía el predict/debate del plan.

### Checklist de criterios de aceptación (Requirements/Validation de esta fase)

Functional:
- [x] `GET .../registrations` paginado con filtro por `status`, `registrations:read` — `router.list_registrations`, `test_listar_inscripciones_filtra_por_estado` (passed)
- [x] `GET .../registrations/{id}` con respuestas y consentimientos, `registrations:read` — `router.get_registration`, `test_detalle_incluye_respuestas_y_consentimiento` (passed)
- [x] `POST .../approve`: solo desde `pending_approval`, revalúa aforo bajo el mismo bloqueo de fila que la Fase 2 — `service.approve_registration`, `test_aprobar_con_aforo_libre_confirma`, `test_aprobar_con_aforo_agotado_deja_en_lista_de_espera`, `test_aprobar_una_inscripcion_que_no_esta_pendiente_falla_409` (passed)
- [x] `POST .../reject`: solo desde `pending_approval` → `rejected` — `service.reject_registration`, `test_rechazar_una_pendiente_de_aprobacion`, `test_rechazar_una_inscripcion_confirmada_falla_409` (passed). Promoción al rechazar: no aplica, ver nota de diseño arriba
- [x] `POST .../cancel`: si liberaba una `confirmed`, dispara la promoción — `service.cancel_registration`, `test_cancelar_una_confirmada_promueve_a_la_primera_en_espera`, `test_cancelar_sin_lista_de_espera_no_promueve_a_nadie`, `test_cancelar_una_ya_cancelada_falla_409` (passed)
- [x] Promoción de lista de espera: `waitlist_promoted_at`/`waitlist_promotion_expires_at`, token Redis `waitlist_promotion_confirm` con TTL = ventana — `service._promote_next_waitlisted`, verificado en `test_cancelar_una_confirmada_promueve_a_la_primera_en_espera`
- [x] `POST /public/registrations/confirm-waitlist-promotion`: `GETDEL` contra Redis, `confirmed` si no caducó, mensaje genérico si caducó/no existe — `service.confirm_waitlist_promotion`, `test_confirmar_promocion_con_token_valido`, `test_confirmar_promocion_con_token_invalido_falla`, `test_confirmar_promocion_caducada_falla_y_no_consume_dos_veces` (passed)
- [x] Tarea cron `expire_waitlist_promotions_task` (`*/15 * * * *`): reasigna promociones caducadas al final de la cola y promueve a la siguiente — `service.expire_waitlist_promotions`, `test_tarea_cron_reasigna_una_promocion_caducada` (passed)
- [x] `GET .../registrations/stats`: iniciados/verificados/pendientes/confirmados/rechazados/cancelados/en espera + dos tasas de conversión, `registrations:read` — `service.get_registration_stats`, `test_estadisticas_cuadran_con_un_escenario_sembrado` (passed). "Emails enviados/entregados/abiertos" fuera de alcance, documentado en el docstring de `get_registration_stats` (falta de webhooks del proveedor de email)
- [x] Gestión de preguntas: añadir siempre permitido; `PATCH` de tipo/`DELETE` con respuestas asociadas → 409; edición de `label`/`sort_order`/`required` siempre permitida — `service.create_registration_question`/`update_registration_question`/`delete_registration_question`, `test_crear_editar_y_borrar_una_pregunta_sin_respuestas`, `test_cambiar_tipo_de_una_pregunta_con_respuestas_falla_409`, `test_editar_label_de_una_pregunta_con_respuestas_funciona` (passed)
- [x] Páginas del panel (Angular): listado con filtro, detalle con acciones, editor de preguntas, tarjetas de estadísticas — `event-registrations.ts`, `registration-detail-page.ts`, `registration-questions.ts`, 10/10 tests passed

Non-functional:
- [x] Todo endpoint de escritura exige `registrations:write`; lectura exige `registrations:read` — `dependencies=[require_permission(...)]` en cada ruta de `router.py`, mismo patrón que `events:*`
- [x] Revaluación de aforo en `approve` y promoción comparten la sección crítica de la Fase 2 (`lock_event_for_capacity`) — sin segunda implementación de la regla de aforo (`_evaluar_estado_por_capacidad` única)
- [x] Accesibilidad WCAG 2.1 AA en el panel — `esperarSinViolacionesDeAccesibilidad` (axe) en los specs nuevos, 0 violaciones

Validation:
- [~] Test: rechazar una `confirmed` promueve a la primera en `waitlisted` — no aplica tal como está escrito el requisito (`reject` solo existe desde `pending_approval`, ver nota de diseño arriba); la promoción real al liberar una `confirmed` está cubierta por `cancel`, que es el único camino alcanzable
- [x] Test: la tarea de expiración devuelve a `waitlisted` una promoción vencida y promueve a la siguiente — `test_tarea_cron_reasigna_una_promocion_caducada` (passed)
- [x] Test: `PATCH` de tipo/`DELETE` con respuestas → 409; sin respuestas funciona — `test_cambiar_tipo_de_una_pregunta_con_respuestas_falla_409`, `test_crear_editar_y_borrar_una_pregunta_sin_respuestas` (passed)
- [x] Test: estadísticas cuadran con un escenario sembrado — `test_estadisticas_cuadran_con_un_escenario_sembrado` (passed)
- [ ] Prueba manual del panel (navegador real): aprobar/rechazar, ver la lista de espera moverse tras cancelar una confirmada — no ejecutada, ver "Huecos reales" arriba

# Fase 3: Aprobación, lista de espera automática y panel de organizador

## Overview

El organizador necesita ver quién se ha inscrito, aprobar o rechazar cuando
el evento lo requiere, y que la lista de espera se mueva sola cuando se libera
una plaza. Esta fase entrega el panel (listado, detalle, acciones) y la
mecánica de lista de espera con promoción automática por cron, además de las
estadísticas y la gestión de preguntas personalizadas.

## Requirements

- Functional:
  - `GET /api/v1/organizations/{org}/events/{event}/registrations`: listado
    paginado con filtro por `status`, requiere `registrations:read`.
  - `GET /api/v1/organizations/{org}/events/{event}/registrations/{id}`:
    detalle con respuestas y consentimientos, requiere `registrations:read`.
  - `POST .../registrations/{id}/approve` y `.../reject`: solo válido desde
    `pending_approval`; `approve` revalúa aforo en ese momento (bloqueo de
    fila igual que la Fase 2) y decide entre `confirmed` y `waitlisted`;
    `reject` termina en `rejected` y, si liberaba una plaza que ya estaba
    `confirmed`, dispara la promoción de lista de espera. Requiere
    `registrations:write`.
  - `POST .../registrations/{id}/cancel` (panel del organizador): termina en
    `cancelled`; si la inscripción cancelada estaba `confirmed`, dispara la
    promoción de lista de espera. Requiere `registrations:write`.
  - Promoción de lista de espera: al liberar una plaza (cancelación o
    rechazo de una `confirmed`), se toma la inscripción `waitlisted` más
    antigua (`waitlist_position` o `created_at`), se marca
    `waitlist_promoted_at = now()` y
    `waitlist_promotion_expires_at = now() + intervalo configurable` (config
    de aplicación, no por evento, para el MVP). El enlace de confirmación
    lleva un token opaco de propósito `waitlist_promotion_confirm` en Redis
    (mismo mecanismo que `email_verify_registration`/`registration_cancel`),
    payload `registration_id`, TTL igual a la ventana de promoción — no una
    columna de tabla. Se envía el email de promoción (fase 4) con ese
    enlace.
  - `POST /api/v1/public/registrations/confirm-waitlist-promotion`: resuelve
    el token con `GETDEL` contra Redis, marca la inscripción `confirmed` si
    `waitlist_promotion_expires_at` no ha pasado; si el token ya caducó o no
    existe, responde que caducó (sin filtrar más detalle) y deja que el cron
    la reasigne.
  - Tarea cron nueva en `app/core/tasks.py`
    (`expire_waitlist_promotions_task`, `schedule=[{"cron": "*/15 * * *
    *"}]` o similar): busca inscripciones con `waitlist_promoted_at`
    establecido y `waitlist_promotion_expires_at` vencido sin confirmar,
    las devuelve a `waitlisted` (al final de la cola) y promueve a la
    siguiente — mismo patrón que `sweep_unverified_accounts_task`.
  - `GET .../registrations/stats`: iniciados, verificados, pendientes de
    aprobación, confirmados, rechazados, cancelados, en lista de espera,
    conversión verificados/iniciados y confirmados/verificados. Requiere
    `registrations:read`. **Fuera de alcance explícito de esta fase:**
    "emails enviados/entregados/abiertos" (PRD §4.3) — exige webhooks del
    proveedor de email, infraestructura que no existe todavía en
    `app/core/email.py`; se deja como decisión de alcance documentada, no
    como omisión.
  - Gestión de preguntas (`POST`/`PATCH`/`DELETE` sobre
    `event_registration_questions`): añadir siempre permitido; `PATCH` de
    tipo o `DELETE` de una pregunta con `event_registration_answers`
    asociadas responde `409` (decisión de la Fase 1 del plan). Editar
    `label`/`order`/`required` de una pregunta existente sí se permite
    siempre (no cambia la forma de la respuesta ya guardada).
  - Páginas del panel (Angular): listado de inscripciones con filtro,
    detalle con acciones, editor de preguntas del evento, tarjetas de
    estadísticas — dentro del área de administración de eventos ya existente
    de la fase 2 del PRD.
- Non-functional:
  - Todo endpoint de escritura sobre inscripciones exige
    `registrations:write`; lectura exige `registrations:read` — mismo
    patrón de dependencias de FastAPI que `events:*`.
  - La revaluación de aforo en `approve` y la promoción de lista de espera
    comparten la misma sección crítica (bloqueo de fila del evento) que la
    Fase 2, para no confirmar por encima de `capacity` desde dos caminos
    distintos (verificación automática vs aprobación manual).
  - Accesibilidad WCAG 2.1 AA en el panel (tablas, filtros, formularios de
    pregunta).

## Validation

- Test: rechazar una inscripción `confirmed` promueve a la primera persona en
  `waitlisted` y le pone `waitlist_promotion_expires_at`.
- Test: la tarea de expiración devuelve a `waitlisted` una promoción vencida
  sin confirmar y promueve a la siguiente persona.
- Test: `PATCH` de tipo o `DELETE` de una pregunta con respuestas asociadas
  responde `409`; sobre una pregunta sin respuestas, funciona.
- Test: estadísticas cuadran con un escenario sembrado (fixtures) con
  inscripciones en cada estado.
- Prueba manual del panel: aprobar/rechazar, ver lista de espera moverse tras
  cancelar una confirmada.

## Risk & Rollback

- Riesgo: la ventana de confirmación fija a nivel de aplicación (no por
  evento) puede no ajustarse a todos los organizadores; aceptable para el
  MVP de IAWIC según el alcance de esta fase — configurable por evento queda
  fuera si no se pide explícitamente.
- Riesgo: dos rutas a `confirmed` (verificación automática y aprobación
  manual) duplicando la lógica de aforo — mitigar extrayendo una única
  función de dominio `evaluar_estado_al_confirmar(evento, cupo_actual)`
  reutilizada por ambas, no dos implementaciones paralelas.
- Rollback: la tarea cron se puede desactivar sin migración (quitar el
  `schedule` o parar el worker de scheduler) dejando la promoción solo
  manual como red de seguridad.
