---
title: "Fase 0 — Scaffolding de la plataforma de eventos"
description: "Monorepo FastAPI + Angular, PostgreSQL con RLS multi-organización, SeaweedFS, Redis/Taskiq, theming dinámico, CI y docs de desarrollo. Cimientos sin funcionalidad de negocio."
status: pending
priority: P1
effort: "7-10d"
tags: [scaffolding, fastapi, angular, postgresql, rls, seaweedfs, multi-tenant]
created: 2026-09-06
blockedBy: []
blocks: []
---

# Fase 0 — Scaffolding de la plataforma de eventos

## Overview

Primera fase de entrega del PRD (`docs/prd.md` §9, fase 0). Construye los cimientos sobre los que se implementarán las fases 1-9: monorepo, entorno Docker (PostgreSQL 16, SeaweedFS, Redis), backend FastAPI modular con autenticación, resolución de organización por host y Row-Level Security, esquema mínimo de organizaciones/usuarios/roles para poder probar el aislamiento multi-tenant, frontend Angular único (público + admin) con theming dinámico por design tokens, CI con puertas de calidad (lint, tipos, tests, accesibilidad, auditoría de dependencias y secretos) y documentación de desarrollo.

**Sin funcionalidad de negocio**: eventos, inscripciones, QR, patrocinadores, pagos, contabilidad, emails y legal llegan en sus propias fases. Todo lo que se construye aquí debe reutilizarse tal cual por esas fases.

Fuentes de decisión: `docs/prd.md` §6-7 y `docs/investigacion.md` §3-4. Revisión adversarial aplicada: ver «Red Team Review».

## Decisiones de arquitectura aplicadas

| Área | Decisión (PRD) | Cómo se materializa en esta fase |
|---|---|---|
| Multi-tenant | Tabla compartida + `organization_id` + RLS de PostgreSQL | Dos roles de BD creados por script de init (fuera de Alembic): `app_user` (sin `BYPASSRLS`, uso de la API) y `app_maintainer` (`BYPASSRLS`, uso exclusivo de migraciones, seed y operaciones de superadmin/alta de organización). RLS `FORCE` en todas las tablas de dominio, incluida `users`. Contexto fijado con `SET LOCAL app.organization_id` en un único punto; **fail-closed** si no hay contexto |
| Resolución de organización | Por `Host` exacto contra `organization_domains` | Sin fallback en producción; `token.org` debe coincidir con la organización resuelta (403 si no); cabecera `X-Organization-Slug` y `DEFAULT_ORGANIZATION_SLUG` solo con `APP_ENV=development`; `X-Forwarded-Host` aceptado solo desde el proxy de confianza |
| Roles | Por defecto con campos predefinidos + personalizados | **Clonación**: `system_roles.py` define plantillas en código; al crear una organización se clonan como filas con `organization_id NOT NULL` y campos `is_locked`. Regla anti-escalada: solo se conceden permisos que el actor posee |
| Almacenamiento | SeaweedFS por defecto tras `StorageProvider` S3 | `aioboto3`; claves con namespace `orgs/{organization_id}/…`; validación de tipo (png/jpg/webp), tamaño y `Content-Type`; públicos servidos vía `S3_PUBLIC_BASE_URL` (proxy Caddy), sin depender de bucket policy |
| Tareas async | Taskiq + Redis | `RedisStreamBroker` (durable, con reintentos) + result backend; worker en Compose |
| Auth | PyJWT (HS256 fijado) + Argon2 | Access token en memoria; **refresh en cookie `HttpOnly` `Secure` `SameSite=Lax`** con rotación y revocación en Redis con TTL; Redis caído → 503 (fail-closed) |
| Permisos | Catálogo fijo en código | `core/permissions.py` (Enum) + `role_permissions` |
| Frontend | Angular última estable, standalone + Signals, SSR solo en rutas públicas, Tailwind v4 sobre CSS vars, Transloco, Vitest | Dos shells (público/admin), `ThemingService`, `TemplateRegistry`; SSR reenvía `X-Forwarded-Host` |
| Accesibilidad | WCAG 2.1 AA en toda la app | 0 violaciones axe de cualquier impacto + checklist manual WCAG por fase (`docs/accesibilidad.md`) |
| Seguridad de la cadena | ASVS L2 (PRD §6) | `.dockerignore`, secretos solo en runtime, `pip-audit` + `pnpm audit`, gitleaks, lockfiles congelados, imágenes etiquetadas por SHA |
| Licencia | MIT | `LICENSE` en la raíz |
| Idioma | Código en inglés; UI/docs/comentarios en español de España | Transloco con `es-ES` por defecto |
| Gestores | `uv` (Python 3.12), `pnpm` (Node LTS) | Lockfiles versionados |

## Goals

| # | Goal | Priority |
|---|------|----------|
| 1 | Entorno levantable con `docker compose up` + `make dev` en macOS/Linux | P1 |
| 2 | Backend con auth, organización por host, RLS fail-closed y health-check de BD/storage/redis | P1 |
| 3 | Aislamiento multi-organización demostrado por tests automáticos, incluida `users` | P1 |
| 4 | Angular con layouts público/admin, guard de auth y branding aplicado en runtime desde la API | P1 |
| 5 | CI en verde con lint, tipos, tests, build, auditoría a11y, dependencias y secretos | P1 |
| 6 | `docs/desarrollo.md` y `docs/arquitectura.md` suficientes para que un tercero levante el proyecto | P2 |

## Phases

| # | Phase | Status |
|---|-------|--------|
| 1 | [Fase 1: Monorepo y entorno](./phase-01-monorepo-y-entorno.md) | Pending |
| 2 | [Fase 2: Backend FastAPI base](./phase-02-backend-fastapi-base.md) | Pending |
| 3 | [Fase 3: Multi-tenant con RLS y modelos base](./phase-03-multi-tenant-rls-y-modelos-base.md) | Pending |
| 4 | [Fase 4: Frontend Angular y theming](./phase-04-frontend-angular-y-theming.md) | Pending |
| 5 | [Fase 5: Documentación y CI](./phase-05-documentacion-y-ci.md) | Pending |

Dependencias: **estrictamente secuencial** 1 → 2 → 3 → 4 → 5. La fase 4 necesita el contrato real de branding, el seed y el login de la fase 3; no se ejecuta en paralelo.

## Estructura de directorios objetivo

```
ia-week/
├── apps/
│   ├── api/                      # FastAPI
│   │   ├── app/
│   │   │   ├── core/             # config, database, security, storage, tenant, permissions, deps, tasks
│   │   │   ├── modules/          # health, auth, tenant, organizations, users, roles
│   │   │   ├── shared/           # errors, pagination, dynamic_fields
│   │   │   ├── seed/
│   │   │   ├── cli.py
│   │   │   └── main.py
│   │   ├── alembic/
│   │   ├── tests/
│   │   ├── .dockerignore
│   │   ├── Dockerfile
│   │   └── pyproject.toml
│   └── web/                      # Angular
│       ├── .dockerignore
│       └── src/app/
│           ├── core/             # api, auth, theming, tenant, i18n
│           ├── layouts/          # public, admin
│           ├── features/         # public/*, admin/*
│           └── shared/ui/
├── infra/
│   ├── docker-compose.yml        # desarrollo: postgres, seaweedfs, redis
│   ├── docker-compose.prod.yml   # producción: + migrate, api, worker, web, caddy
│   ├── postgres/init/            # 01-roles.sql (app_user, app_maintainer, default privileges)
│   ├── caddy/Caddyfile
│   ├── scripts/backup.sh
│   └── env/.env.example
├── docs/
├── plans/
├── .github/workflows/ci.yml
├── Makefile
├── LICENSE                       # MIT
└── README.md
```

## Non-goals

Eventos, sesiones, inscripciones, entradas/QR, patrocinadores, pagos, contabilidad, plantillas de email reales, banner de cookies, páginas legales, dominios propios con TLS on-demand (solo se deja el Caddyfile base), superadmin UI, inglés. Ver PRD §9 para su fase.

## Success Criteria

- [ ] `docker compose -f infra/docker-compose.yml up -d` deja PostgreSQL (con roles `app_user`/`app_maintainer`), SeaweedFS (con bucket `media`) y Redis healthy
- [ ] `GET /api/v1/health` responde `{"database":"ok","storage":"ok","redis":"ok"}`
- [ ] `alembic upgrade head` + `make db-seed` (idempotente, ejecutable dos veces) crean organización demo, dominio `localhost`, roles clonados con campos predefinidos y usuario owner
- [ ] Login JWT funciona con refresh en cookie `HttpOnly`; endpoint protegido → 401 sin token, 403 sin permiso, 403 si `token.org` ≠ organización del host
- [ ] Tests de aislamiento: con RLS activa, una sesión fijada en A no lee ni escribe filas de B (incluida `users`) aunque el repositorio omita el filtro; sin contexto fijado no se lee nada
- [ ] No es posible crear un rol con permisos que el actor no posee, ni escalar a `owner`
- [ ] `GET /api/v1/tenant/branding` devuelve el branding de la organización resuelta por host; host desconocido → 404
- [ ] Angular muestra layout público con colores/logo del branding y layout admin tras login; cambiar colores en BD cambia la UI sin rebuild; SSR resuelve la organización correcta tras Caddy
- [ ] CI: `ruff`, `mypy`, `pytest` (contra Postgres real), `pip-audit`, `pnpm audit`, gitleaks, `ng lint`, `ng test`, `ng build`, tipos OpenAPI sin diff, 0 violaciones axe
- [ ] Ningún fichero fuente supera 1000 líneas (objetivo ≤ 300)
- [ ] `docs/desarrollo.md` permite levantar el entorno sin ayuda; `docs/accesibilidad.md` con checklist WCAG completado para la fase

## Red Team Review

### Session — 2026-09-06
**Findings:** 32 brutos → 15 consolidados (15 aceptados, 0 rechazados)
**Severity breakdown:** 7 Critical, 7 High, 1 Medium (agrupado)
**Informes:** `plans/reports/redteam-260906-1951-{seguridad,supuestos,fallos}-fase-0.md`

| # | Finding | Severity | Disposition | Applied To |
|---|---------|----------|-------------|------------|
| 1 | Bypass de RLS por GUC `app.bypass` sin control | Critical | Accept | Fase 3 (rol `app_maintainer`, sin GUC) |
| 2 | Seed y alta de organización imposibles bajo `FORCE RLS`; seed no idempotente | Critical | Accept | Fase 3 |
| 3 | Roles del sistema compartidos vs clonados sin decidir; esquema contradictorio | Critical | Accept | Fase 3 (clonación) |
| 4 | Escalada de privilegios al crear roles/membresías | Critical | Accept | Fase 3 |
| 5 | Suplantación de tenant por `Host` (sin allowlist, sin contraste con token, fail-open) | Critical | Accept | Fase 2 |
| 6 | Subida de ficheros sin validación ni namespacing; SVG → XSS | Critical | Accept | Fases 2-3 |
| 7 | `GRANT` no cubre tablas futuras; `CREATE ROLE` en Alembic irreversible | Critical | Accept | Fases 1-2 (init SQL) |
| 8 | `users`/`user_social_links` sin RLS | High | Accept | Fase 3 |
| 9 | Refresh en `localStorage`; Redis fail-open; rate limiting insuficiente | High | Accept | Fases 2, 4 |
| 10 | Contexto RLS indefinido sin organización; `current_setting` inconsistente | High | Accept | Fases 2-3 (fail-closed) |
| 11 | Fixture rollback incompatible con tests de RLS | High | Accept | Fases 2-3 |
| 12 | SSR resuelve tenant por `Host` interno; timeout enmascara fallo | High | Accept | Fases 4-5 (`X-Forwarded-Host`) |
| 13 | Fase 4 declarada paralela a la 3 | High | Accept | plan.md, Fase 4 |
| 14 | WCAG 2.1 AA degradado a axe | High | Accept | Fases 4-5 |
| 15 | Cadena de suministro y despliegue: secretos en imágenes, sin `.dockerignore`, sin auditorías, CI `web` sin `needs:`/exportación OpenAPI, deploy sin migración ni tags inmutables, broker no durable, bucket policy no verificada, estimación sin margen | High/Medium | Accept | Fases 1, 2, 5, plan.md |

### Whole-Plan Consistency Sweep
- Decisiones delta: (a) sin GUC de bypass → rol `app_maintainer`; (b) clonación de roles con `organization_id NOT NULL`; (c) `users` con RLS; (d) refresh en cookie HttpOnly; (e) fail-closed en tenant, RLS y Redis; (f) secuencia 1→2→3→4→5; (g) WCAG: 0 violaciones axe + checklist manual; (h) `RedisStreamBroker`; (i) roles y privilegios en `infra/postgres/init`; (j) `X-Forwarded-Host` desde proxy de confianza.
- Barrido realizado sobre `plan.md` y las cinco fases: eliminadas las menciones a `app.bypass`, a `organization_id NULL` en roles/campos, al paralelismo 3‖4, al fallback `localStorage`, al "timeout 2 s → tokens por defecto" silencioso, a "axe sin violaciones críticas" y a la migración `0001_roles_de_base_de_datos`.
- Contradicciones sin resolver: **ninguna**.

<!-- slug: fase-0-scaffolding -->
