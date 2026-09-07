---
phase: 1
title: "Fase 1: Correo y verificación"
status: pending
priority: P1
effort: "1.5-2d"
dependencies: []
---

# Fase 1: Correo y verificación

## Overview

Infraestructura de envío de correo, adelantada desde la fase 3 del PRD porque el
registro de la fase 2 la necesita para verificar la propiedad del correo antes de crear
una organización. Solo lo mínimo para verificar: proveedor, plantilla y cola. Las
plantillas de inscripción (confirmación, aprobación, entrada QR) siguen en su fase.

## Decisión validada — Sesión 2026-09-07

Proveedor de correo en desarrollo: **Mailpit**, añadido a `infra/docker-compose.yml`,
sin salir a Internet. En producción, un proveedor real tras la interfaz
`EmailProvider` (SMTP genérico; si el usuario decide una API concreta en su lugar, se
ajusta en esta misma fase sin afectar al resto del plan).

## Requirements

- Functional: interfaz `EmailProvider` (protocolo) con una implementación SMTP;
  plantilla de verificación con el branding de la organización cuando exista (durante
  el registro, con el branding por defecto porque la organización aún no existe); tarea
  Taskiq `send_verification_email`; endpoint `POST /api/v1/auth/register` que crea el
  usuario sin verificar y encola el correo; endpoint
  `GET /api/v1/auth/verify-email?token=…` que verifica y consume el token una sola vez;
  `POST /api/v1/auth/resend-verification` con límite de reenvíos.
- Non-functional: el token de verificación es opaco, de un solo uso y expira (24 h);
  fail-closed si Redis no responde, igual que el resto de la autenticación; sin
  plantillas HTML complejas todavía (texto plano o HTML mínimo, sin motor de plantillas
  nuevo).

## Architecture

- `apps/api/app/core/email.py`: `EmailProvider` (Protocol) + `SmtpEmailProvider`.
- `apps/api/app/modules/auth/verification.py`: generación y verificación del token,
  reutilizando el patrón de Redis con TTL que ya usan los refresh tokens.
- El usuario se crea con `is_active=false` (o un nuevo `email_verified_at` nulo, a
  decidir contra el modelo actual de `User`) hasta verificar. Revisar si `is_active`
  ya se usa con otro sentido (desactivación por un admin) antes de reutilizarlo: si es
  así, añadir columna nueva en vez de sobrecargar la existente.
- Mailpit (o similar) en `infra/docker-compose.yml`, con su UI expuesta en desarrollo
  para leer los correos capturados sin salir del entorno.

## Related Code Files

- Create: `apps/api/app/core/email.py`
- Create: `apps/api/app/modules/auth/verification.py`
- Create: `apps/api/tests/test_email_verification.py`
- Modify: `apps/api/app/modules/users/models.py` (columna de verificación)
- Modify: `apps/api/app/modules/auth/router.py`, `service.py`, `schemas.py`
- Modify: `apps/api/alembic/versions/` (nueva migración)
- Modify: `infra/docker-compose.yml`, `infra/env/.env.example`

## Implementation Steps

1. Resolver la decisión de proveedor con el usuario si Mailpit no es su preferencia.
2. Migración: columna de verificación en `users` (sin romper el seed ni los tests
   existentes, que crean usuarios ya verificados).
3. `EmailProvider` + implementación SMTP; en desarrollo apunta a Mailpit.
4. Tarea Taskiq de envío, con reintentos como `ping`.
5. Endpoints de registro (solo el usuario, sin organización todavía — eso es la fase 2),
   verificación y reenvío, con límite de peticiones como el resto de `/auth/*`.
6. Tests: registro crea usuario no verificado; el enlace verifica una vez y falla la
   segunda; expiración; reenvío respeta el límite; Redis caído → 503.
7. Actualizar `docs/desarrollo.md` con el paso de leer correos en Mailpit.

## Success Criteria

- [ ] `POST /api/v1/auth/register` crea un usuario no verificado y encola un correo
- [ ] El correo llega a Mailpit en desarrollo con un enlace de verificación
- [ ] Verificar dos veces con el mismo token: la segunda falla
- [ ] Un token de más de 24 h no verifica
- [ ] `pytest` en verde incluyendo los casos de fallo de Redis

## Risk Assessment

- Sobrecargar `is_active` con dos significados distintos → columna nueva si ya se usa
  para otra cosa; verificar antes de tocarla.
- Mailpit añade un contenedor más al Compose de desarrollo → documentar su puerto y que
  no forma parte de producción.
