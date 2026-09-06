---
phase: 2
title: "Fase 2: Backend FastAPI base"
status: completed
priority: P1
effort: "2d"
dependencies: [1]
---

# Fase 2: Backend FastAPI base

## Overview
Aplicación FastAPI con arquitectura modular por dominios, configuración tipada, BD async con dos engines (aplicación y mantenimiento), `StorageProvider` S3 con validación y namespacing por organización, Taskiq durable + Redis, autenticación JWT con refresh en cookie `HttpOnly`, resolución de organización por host **fail-closed** y health-check. Sin modelos de dominio todavía (fase 3), pero con toda la infraestructura transversal lista y probada.

## Requirements
- Functional: `GET /api/v1/health`; `POST /api/v1/auth/login`, `POST /api/v1/auth/refresh`, `POST /api/v1/auth/logout`; dependencias `get_db`, `get_current_user`, `get_current_organization`, `require_permission()`; `GET /api/v1/tenant/branding` público; tarea Taskiq `ping`; `StorageProvider` con `put_object`, `presigned_get_url`, `presigned_put_url`, `delete_object`, `public_url`, siempre bajo prefijo `orgs/{organization_id}/`.
- Non-functional: Python 3.12; `mypy --strict`; `ruff`; tests con `pytest` + `httpx.AsyncClient` contra PostgreSQL real; OpenAPI en español; ficheros ≤ 300 líneas; algoritmo JWT fijado en `decode`; ASVS L2 (PRD §6): rate limiting con límites definidos, cookies seguras, sin fail-open ante Redis caído.

## Architecture
```
apps/api/app/
├── main.py                 # create_app(): routers, CORS, handlers, lifespan (comprueba BD/storage/redis)
├── core/
│   ├── config.py           # Settings (pydantic-settings)
│   ├── database.py         # engine_app (app_user), engine_maintenance (app_maintainer), Base, mixins
│   ├── security.py         # argon2, tokens, decode_token(algorithms=["HS256"])
│   ├── storage.py          # StorageProvider (Protocol) + S3StorageProvider (aioboto3) + validación
│   ├── tenant.py           # resolve_organization(host) fail-closed
│   ├── permissions.py      # Enum Permission (catálogo fijo)
│   ├── tasks.py            # RedisStreamBroker + result backend, tarea ping
│   ├── ratelimit.py        # fastapi-limiter, identificación de cliente tras proxy de confianza
│   └── deps.py             # get_db, get_current_user, get_current_organization, require_permission
├── modules/
│   ├── health/router.py
│   ├── auth/{router,schemas,service}.py
│   └── tenant/{router,schemas}.py
└── shared/
    ├── errors.py           # DomainError → problem+json
    └── pagination.py
```
- **Resolución de organización (hallazgo #5)**: `host` = `X-Forwarded-Host` solo si la IP origen está en `TRUSTED_PROXY_CIDRS`, si no `Host`. Se normaliza (minúsculas, sin puerto) y se busca coincidencia **exacta** en `organization_domains`; sin coincidencia → 404 antes de tocar ninguna otra tabla. `X-Organization-Slug` y `DEFAULT_ORGANIZATION_SLUG` solo se consultan con `APP_ENV=development`. `get_current_user` comprueba `token.org == organización resuelta`; si no, 403.
- **Contexto RLS (hallazgo #10)**: `get_db` abre transacción con `engine_app` y ejecuta `SET LOCAL app.organization_id = :id` **dentro de ella**; único punto de fijación. Las políticas RLS (fase 3) usan `NULLIF(current_setting('app.organization_id', true), '')::uuid`, de modo que sin contexto no se devuelve ninguna fila (fail-closed, sin error 500). `engine_maintenance` (`app_maintainer`) se usa solo desde `cli.py`, Alembic y el servicio de alta de organizaciones; nunca desde routers.
- **Auth (hallazgo #9, validación #1)**: access token JWT (15 min) en respuesta JSON; refresh token opaco (7 días) en cookie `HttpOnly; Secure; SameSite=Lax; Path=/api/v1/auth` **sin atributo `Domain`** (web y API comparten host tras Caddy, la cookie es first-party por construcción; `Secure` se relaja solo con `APP_ENV=development`); rotación en cada uso; <!-- Updated: Validation Session 1 - mismo host --> familia de tokens en Redis con TTL igual a la caducidad; reutilización de un refresh rotado invalida la familia. Redis no disponible → `503` en refresh/logout (fail-closed).
- **Rate limiting (hallazgo #9)**: `fastapi-limiter` con Redis; identificación por IP real (`X-Forwarded-For` solo desde proxy de confianza) + host; límites iniciales: `/auth/login` 5/min por IP y 20/min por host, `/auth/refresh` 30/min, resto público 120/min. Redis caído → `503` en `/auth/*` y en endpoints públicos de escritura; lectura pública sin límite pero con log de alerta.
- **Storage (hallazgo #6)**: toda clave se construye con `build_object_key(org_id, kind, filename)` → `orgs/{org_id}/{kind}/{uuid}.{ext}`; `validate_upload()` comprueba tipo real (magic bytes) ∈ {png, jpeg, webp}, tamaño ≤ 5 MB para imágenes, y fuerza `Content-Type` y `Content-Disposition: inline` solo para esos tipos; SVG queda prohibido hasta que exista saneado. Presigned PUT con condiciones de tamaño y tipo.
- **Tareas (hallazgo #15)**: `RedisStreamBroker` con `RedisAsyncResultBackend`, reintentos con backoff y dead-letter en log; el worker confirma (`ack`) tras completar.
- Alembic async ejecutado con `DATABASE_MIGRATIONS_URL`; migración inicial vacía que solo verifica la existencia de los roles (falla con mensaje claro si no existen).
- CLI Typer `python -m app.cli` (`seed`, `create-owner`, `create-organization`) usando `engine_maintenance`.

## Related Code Files
- Create: `apps/api/pyproject.toml` (fastapi, uvicorn[standard], sqlalchemy[asyncio], asyncpg, alembic, pydantic-settings, pyjwt>=2.13, argon2-cffi, aioboto3, python-magic, taskiq, taskiq-redis, redis, fastapi-limiter, typer, python-multipart; dev: pytest, pytest-asyncio, httpx, ruff, mypy, pip-audit, types-*)
- Create: `apps/api/app/main.py`, `apps/api/app/core/*.py`, `apps/api/app/shared/*.py`, `apps/api/app/cli.py`
- Create: `apps/api/app/modules/health/`, `apps/api/app/modules/auth/`, `apps/api/app/modules/tenant/`
- Create: `apps/api/alembic.ini`, `apps/api/alembic/env.py`, `apps/api/alembic/versions/0001_verificar_roles.py`
- Create: `apps/api/tests/conftest.py` (BD real; limpieza por `TRUNCATE … CASCADE` entre tests, no rollback — hallazgo #11), `apps/api/tests/test_health.py`, `test_auth.py`, `test_tenant.py`, `test_storage.py`, `test_ratelimit.py`
- Create: `apps/api/Dockerfile` (multi-stage con uv; sin secretos ni `.env` en la imagen; mismo contenedor sirve api y worker por comando)
- Modify: `Makefile` (`api`, `worker`, `db-migrate`, `db-seed`, `lint`, `test`, `audit`)

## Implementation Steps
1. `uv init`; `pyproject.toml` con rangos, `ruff` (line-length 100, reglas `E,F,I,B,UP,S`) y `mypy --strict`.
2. `core/config.py`: `Settings` con validaciones (`JWT_SECRET` ≥ 32, `APP_ENV`, `CORS_ORIGINS`, `TRUSTED_PROXY_CIDRS`, `COOKIE_DOMAIN` opcional); en `production` se rechaza `DEFAULT_ORGANIZATION_SLUG` no vacío.
3. `core/database.py`: dos engines, `async_sessionmaker` por engine, `Base`, mixins; helper `set_organization_context(session, org_id)`.
4. `core/security.py`: argon2; access JWT con `sub`, `org`, `type`, `exp`, `jti`; refresh opaco (`secrets.token_urlsafe`) + hash en Redis.
5. `core/storage.py`: `StorageProvider`, `S3StorageProvider` (path-style), `build_object_key`, `validate_upload`; `ensure_bucket()` en lifespan.
6. `core/tasks.py`: `RedisStreamBroker`, result backend, `@broker.task(retry_on_error=True, max_retries=5) ping`.
7. `core/tenant.py` + `core/ratelimit.py` + `core/deps.py` según Arquitectura; `require_permission` con interfaz y stub que niega todo hasta la fase 3.
8. Módulos `health`, `auth` (login, refresh con rotación, logout con revocación de familia), `tenant` (branding por defecto hasta la fase 3, 404 si host desconocido).
9. `main.py`: `create_app()`, CORS **solo** con `APP_ENV=development` y `CORS_ORIGINS` explícito (en producción web y API comparten host tras Caddy y no hay CORS), handlers `problem+json` sin trazas de BD, rate limiting.
10. Alembic async con `0001_verificar_roles`.
11. Tests (BD real, `TRUNCATE` entre tests): health; login válido/inválido; refresh con rotación y detección de reutilización; logout revoca; Redis caído → 503; tenant por host exacto, host desconocido → 404, subdominio no registrado → 404, `X-Forwarded-Host` ignorado desde IP no confiable, cabecera de desarrollo ignorada con `APP_ENV=test`; `token.org` ≠ host → 403; storage: clave con prefijo de organización, rechazo de SVG y de > 5 MB, presigned PUT real contra SeaweedFS; rate limit devuelve 429.
12. `Dockerfile` multi-stage; verificar con `docker history` que no hay `.env`.

## Success Criteria
- [x] `uv run uvicorn app.main:app --reload` arranca; `/docs` visible
- [x] `/api/v1/health` → `database`, `storage`, `redis` en `ok`
- [x] Login devuelve access + cookie `HttpOnly` de refresh; refresh rota; reutilización invalida la familia; 401/403 según tabla de tests
- [x] Host desconocido → 404; `X-Forwarded-Host` solo desde proxy confiable; `token.org` ≠ organización → 403
- [x] `uv run taskiq worker app.core.tasks:broker` ejecuta `ping` y reintenta al fallar
- [x] `ruff check`, `ruff format --check`, `mypy app`, `pytest`, `pip-audit` en verde
- [x] `alembic upgrade head` / `downgrade base` funcionan con `DATABASE_MIGRATIONS_URL`

## Risk Assessment
- `SET LOCAL` fuera de transacción no tiene efecto → `get_db` abre la transacción explícitamente; test que verifica `current_setting` dentro de la sesión y que dos sesiones consecutivas del pool no comparten contexto.
- Cookie sin `Domain` depende de que web y API compartan host → Caddy obligatorio también en desarrollo (fase 1); test de auth ejecutado a través de Caddy con dos hosts.
- aioboto3 contra SeaweedFS → `addressing_style: path`; verificar `python-magic` requiere `libmagic` (documentar en Dockerfile y docs).
- Redis como punto único de fallo para auth → aceptado (fail-closed documentado); `--appendonly` y healthcheck en Compose.
