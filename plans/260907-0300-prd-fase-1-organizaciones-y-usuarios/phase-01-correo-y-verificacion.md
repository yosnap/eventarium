---
phase: 1
title: "Fase 1: Correo y verificación"
status: done
priority: P1
effort: "2-2.5d"
dependencies: []
---

# Fase 1: Correo y verificación

## Overview

Infraestructura de envío de correo, adelantada desde la fase 3 del PRD porque el
registro de la fase 2 la necesita para verificar la propiedad del correo antes de crear
una organización. Solo lo mínimo para verificar: proveedor, plantilla, cola, Turnstile
y anti-bruteforce. Las plantillas de inscripción (confirmación, aprobación, entrada QR)
siguen en su fase.

Incluye las páginas públicas de registro y verificación: sin ellas el criterio de éxito
del plan («una persona ajena se registra sin ayuda») es inalcanzable.

## Decisiones validadas — Sesión 2026-09-07

- Proveedor de correo en desarrollo: **Mailpit**, añadido a `infra/docker-compose.yml`,
  sin salir a Internet. En producción, un proveedor real tras la interfaz
  `EmailProvider` (SMTP genérico).
- **Correo verificado obligatorio antes de crear organización.** El borrado por
  caducidad de la decisión #6 del plan se predica de la **cuenta de usuario**, no de la
  organización: una organización solo existe si su creador ya verificó su correo (no
  hay estado intermedio «organización no verificada»).
- Turnstile obligatorio en producción sobre `POST /api/v1/auth/register`, desactivable
  por variable en desarrollo y tests. Esta fase implementa el módulo compartido; las
  fases 2 y 5 lo reutilizan sin reimplementarlo.

## Hallazgos aplicados en esta fase

### Red-team (seguridad y supuestos no verificados)

| # | Hallazgo | Corrección |
|---|---|---|
| — | `is_active` en `users` ya gatea el login (`core/deps.py`, `modules/auth/service.py`); reutilizarlo para «correo verificado» rompería el alta de miembros invitados, que se crean con `is_active=true` sin verificación | Columna nueva `email_verified_at: datetime \| None`. `is_active` no se toca |
| — | El registro y el reenvío de verificación no tenían requisito de respuesta anti-enumeración | Ambos devuelven siempre la misma respuesta y con tiempo equivalente, exista o no la cuenta |
| — | Turnstile no aparecía en esta fase pese a que la decisión de producto lo exige en el registro | `core/turnstile.py` (módulo compartido) + integración en `/auth/register` |
| — | La variable que desactiva Turnstile no tenía salvaguarda contra producción | El arranque falla si `APP_ENV=production` y la variable de desactivación está activa (mismo patrón que `DOMINIO_BASE` vacío) |
| — | Sin definir el comportamiento si el servicio de contraseñas filtradas no responde | Fail-open documentado: el registro continúa y se registra un aviso; no es un control de sesión crítico como el refresh token |
| — | Sin flujo de recuperación de contraseña en el plan original | Se añade en la fase 5, reutilizando el mecanismo de token de esta fase |

### Predict/debate (5 personas, sobre el plan ya endurecido)

| # | Quién | Hallazgo | Corrección |
|---|---|---|---|
| Importante | Seguridad | `resend-verification` solo tenía límite por IP, sin Turnstile: vector de *email bombing* trivial con proxies rotativos | Turnstile también en `resend-verification` |
| Importante | Rendimiento | El barrido horario de cuentas no verificadas (fase 2) haría *sequential scan* de `users` sin índice | Índice parcial sobre `created_at` para filas con `email_verified_at IS NULL` |
| Importante | Rendimiento | Límites de peticiones descritos como «propio» sin cifra, riesgo de heredar por descuido un límite demasiado permisivo | Constantes explícitas en `core/ratelimit.py` |
| Bloqueante | UX | Ninguna fase incluía las páginas web de registro/verificación: sin ellas el flujo completo no es alcanzable | Páginas añadidas a esta fase |
| Importante | Accesibilidad | Turnstile es un iframe de terceros que axe no audita | Prueba manual con lector de pantalla y teclado, documentada aparte del barrido automático |
| Importante | Accesibilidad | Sin requisito de cómo se comunica un enlace de verificación caducado | Anuncio con `aria-live="assertive"`, explicación y botón de reenvío directo |

## Requirements

- Functional:
  - `POST /api/v1/auth/register` (email, contraseña, verificación de Turnstile): crea
    el usuario con `email_verified_at=null`, exige la política de composición
    (mínimo 8 caracteres, mayúscula, minúscula, número y carácter especial —
    `core/security.py:password_meets_complexity`, validada también en el cliente con
    el mismo criterio antes de enviar) y valida la contraseña contra la lista de
    filtradas (fail-open si el servicio no responde), encola el correo de
    verificación, y devuelve siempre la misma respuesta genérica exista ya el correo
    o no.
  - `GET /api/v1/auth/verify-email?token=…`: verifica y consume el token una sola vez;
    fija `email_verified_at`.
  - `POST /api/v1/auth/resend-verification` (email, token de Turnstile): misma
    respuesta genérica siempre; solo encola si la cuenta existe y no está verificada;
    Turnstile obligatorio (mismo motivo que en el registro: es otro endpoint público
    que envía correo).
  - `EmailProvider` (Protocol) + `SmtpEmailProvider`; tarea Taskiq
    `send_verification_email`, con reintentos como `ping`.
  - `core/turnstile.py`: cliente `httpx` contra `siteverify`, verificación server-side,
    desactivable por `TURNSTILE_ENABLED=false` solo fuera de producción.
  - Páginas públicas (CSR, ver Architecture): `/registro`, `/verificar-correo`.
- Non-functional: el token de verificación es opaco, de un solo uso y expira (24 h),
  con el mismo patrón de Redis+TTL que los refresh tokens; fail-closed si Redis no
  responde (igual que el resto de `/auth/*`); Turnstile fail-closed (si el servicio de
  Turnstile no responde, la petición se rechaza — a diferencia del chequeo de
  contraseñas filtradas, que no es crítico); límites de peticiones con cifra fija (ver
  Architecture); sin plantillas HTML complejas todavía.

## Architecture

- `apps/api/app/core/email.py`: `EmailProvider` (Protocol) + `SmtpEmailProvider`.
- `apps/api/app/core/turnstile.py`: `verify_turnstile_token(token, remote_ip) -> bool`,
  con su propia configuración (`TURNSTILE_SECRET_KEY`, `TURNSTILE_ENABLED`) en
  `core/config.py`. Módulo compartido: las fases 2 y 5 lo importan, no lo
  reimplementan.
- `apps/api/app/modules/auth/verification.py`: generación y verificación del token de
  verificación de correo, reutilizando el patrón de Redis con TTL que ya usan los
  refresh tokens, con **propósito** incluido en la clave (`email_verify` en esta fase;
  la fase 5 añade `email_change` y `password_reset` sobre el mismo módulo, sin que
  sean intercambiables entre sí).
- Migración: `email_verified_at` en `users` (nullable), más un **índice parcial**
  `ix_users_unverified_created_at ON users (created_at) WHERE email_verified_at IS
  NULL`, para que el barrido periódico de la fase 2 no recorra la tabla entera.
  `is_active` mantiene su significado actual sin cambios.
- `core/ratelimit.py`: nuevas constantes `REGISTRO_POR_IP`, `REENVIO_VERIFICACION_POR_IP`
  (valores iniciales a fijar en el PR, en línea con `LOGIN_POR_IP=5`: registro algo más
  permisivo por ser de un solo uso por persona, reenvío más estricto por reutilizable).
- Mailpit en `infra/docker-compose.yml`, con su UI expuesta en desarrollo.
- Tarea de limpieza (`core/cleanup.py`, fase 2) que borra cuentas con
  `email_verified_at=null` tras 7 días, con aviso a los 5. Esta fase solo define la
  columna y el índice; el barrido en sí vive en la fase 2, donde se decide el mecanismo
  de *scheduling*.
- Páginas públicas: `register-page.ts` (formulario con Turnstile) y
  `verify-email-page.ts` (lee el token de la URL, llama a `verify-email`, ofrece
  reenviar si caducó). **Decisión de renderizado**: CSR, siguiendo el precedente de
  `admin/login` (son flujos transaccionales, no contenido público indexable) — no usan
  `PublicShell` con SSR.

## Related Code Files

- Create: `apps/api/app/core/email.py`
- Create: `apps/api/app/core/turnstile.py`
- Create: `apps/api/app/modules/auth/verification.py`
- Create: `apps/api/tests/test_email_verification.py`
- Create: `apps/api/tests/test_turnstile.py`
- Modify: `apps/api/app/modules/users/models.py` (columna `email_verified_at`)
- Modify: `apps/api/app/modules/auth/router.py`, `service.py`, `schemas.py`
- Modify: `apps/api/app/core/config.py` (`TURNSTILE_SECRET_KEY`, `TURNSTILE_ENABLED`,
  validación de producción)
- Modify: `apps/api/app/core/ratelimit.py` (constantes nuevas)
- Modify: `apps/api/alembic/versions/` (nueva migración con el índice parcial)
- Modify: `infra/docker-compose.yml`, `infra/env/.env.example`, `docs/desarrollo.md`
- Create: `apps/web/src/app/features/public/register/register-page.ts`
- Create: `apps/web/src/app/features/public/verify-email/verify-email-page.ts`
- Modify: `apps/web/src/app/app.routes.ts` (rutas `/registro`, `/verificar-correo`)

## Implementation Steps

1. Migración: `email_verified_at` nullable en `users` + índice parcial; verificar que
   no rompe el seed ni los tests existentes (los usuarios de test se crean ya
   verificados).
2. `core/turnstile.py` + configuración; test de que el arranque falla en producción con
   la variable de desactivación activa.
3. `EmailProvider` + `SmtpEmailProvider`; en desarrollo apunta a Mailpit.
4. Tarea Taskiq de envío, con reintentos.
5. `modules/auth/verification.py`: generación/verificación de token con propósito
   `email_verify`.
6. Endpoints de registro (con Turnstile y chequeo de contraseña filtrada fail-open),
   verificación y reenvío (ambos con Turnstile y respuesta anti-enumeración), con las
   constantes de límite de peticiones definidas en `core/ratelimit.py`.
7. `register-page.ts` y `verify-email-page.ts`, con el widget de Turnstile integrado y
   la pantalla de enlace caducado con `aria-live="assertive"` y botón de reenvío.
8. Tests: registro crea usuario no verificado y siempre responde igual; el enlace
   verifica una vez y falla la segunda; expiración a 24 h; reenvío respeta el límite,
   exige Turnstile y responde igual exista o no la cuenta; Redis caído → 503; Turnstile
   inválido → 422, caído → 503 (fail-closed); servicio de contraseñas filtradas caído →
   el registro continúa (fail-open).
9. Prueba manual del widget de Turnstile con lector de pantalla y navegación por
   teclado; documentar el resultado en `docs/accesibilidad.md` (aparte del barrido de
   axe, que no cubre el iframe de terceros).
10. Actualizar `docs/desarrollo.md` con el paso de leer correos en Mailpit y las
    variables de Turnstile.

## Success Criteria

- [x] `POST /api/v1/auth/register` crea un usuario no verificado y encola un correo
- [x] El correo llega a Mailpit en desarrollo con un enlace de verificación
- [x] Verificar dos veces con el mismo token: la segunda falla
- [x] Un token de más de 24 h no verifica, y la UI lo comunica con `aria-live` y un
      botón de reenvío directo
- [x] Registro y reenvío responden igual exista o no la cuenta
- [x] Turnstile inválido rechaza el registro y el reenvío; Turnstile caído devuelve 503
      en ambos
- [x] El arranque falla en producción si la variable de desactivación de Turnstile
      está activa
- [x] El índice parcial existe y `EXPLAIN` sobre la consulta del barrido (fase 2) no
      muestra *sequential scan*
- [~] Turnstile verificado manualmente con lector de pantalla y teclado, documentado en
      `docs/accesibilidad.md` — **parcial**: no hay clave de sitio real en este entorno
      (`TURNSTILE_ENABLED=false` en desarrollo), así que el iframe de Cloudflare nunca
      se ha renderizado. Queda documentado como pendiente explícito en
      `docs/accesibilidad.md`, a completar antes de activar Turnstile en producción.
- [x] `pytest` en verde incluyendo los casos de fallo de Redis y de Turnstile
- [x] Una contraseña sin mayúscula, minúscula, número o carácter especial rechaza el
      registro (422), tanto en cliente (indicador de fuerza en vivo) como en servidor

## Nota de implementación: tres funciones `SECURITY DEFINER` no previstas en el plan

Verificado contra el código real de `0003_politicas_rls.py`: la política `tenant_users`
exige compartir organización con quien pregunta. En el registro público esa condición
no se cumple —la persona no ha iniciado sesión ni pertenece a ninguna organización—, así
que el router de registro no podía ver, crear ni actualizar su propia fila de `users`
por la vía normal. Sin corregirlo, el registro fallaba en silencio: la comprobación de
duplicados no veía nunca una fila y el `INSERT` violaba una restricción `NOT NULL` no
cubierta por los valores por defecto del ORM (`locale`, `is_superadmin`), que el
`except IntegrityError` end-to-end interpretaba como «correo ya registrado» sin encolar
el correo ni devolver ningún error visible.

Se resolvió con el mismo patrón ya usado para `app_resolve_organization` (alcance
mínimo, `REVOKE ALL FROM PUBLIC` + `GRANT EXECUTE TO app_user`) en vez de dar
`BYPASSRLS` al rol de la API: `app_find_user_by_email`, `app_create_unverified_user` y
`app_verify_user_email`, en la migración `0004_correo_y_verificacion`. Detalle en
`docs/modelo-de-datos.md`. No se preguntó porque la corrección deriva directamente del
código de RLS ya existente, no de una decisión de producto nueva.

## Nota de implementación: política de contraseña con composición

El usuario pidió adaptar el patrón de validación de formularios de otro proyecto
(`securitycoet`) a los campos de este: validación en vivo al perder el foco (no en
cada pulsación ni solo al enviar) y un indicador de fuerza de contraseña con checklist
de requisitos. Al llevarlo, salió a la luz que su política de contraseña (mayúscula +
minúscula + número + carácter especial) no coincidía con la decisión #5 original del
plan (solo longitud mínima + lista de filtradas). Se preguntó explícitamente y el
usuario decidió adoptar también la política de complejidad, no solo el estilo visual:
la decisión #5 de `plan.md` queda actualizada en consecuencia.

Implementación: `core/security.py:password_meets_complexity` (servidor, fuente de
verdad) y `shared/ui/password-strength.ts` (cliente, mismo criterio, para no aceptar
en el formulario lo que el servidor rechazaría después). El indicador de fuerza no
depende solo del color para comunicar el estado (1.4.1): cada requisito lleva texto de
«cumplido»/«pendiente» además del icono. No lleva `aria-live`: anunciar en cada
pulsación sería disruptivo para un lector de pantalla.

## Risk Assessment

- Sobrecargar `is_active` con dos significados distintos → descartado: columna nueva
  `email_verified_at`, verificado contra el código real que `is_active` ya tiene otro
  uso.
- Mailpit añade un contenedor más al Compose de desarrollo → documentar su puerto y que
  no forma parte de producción.
- Confundir el token de verificación de correo con el de recuperación de contraseña
  (fase 5) → cada uno lleva su propio propósito en la clave de Redis, no son
  intercambiables aunque compartan el mismo mecanismo de generación.
- Barrido sin índice degradaría con el tiempo → índice parcial incluido en esta misma
  migración, no aplazado a la fase 2.
