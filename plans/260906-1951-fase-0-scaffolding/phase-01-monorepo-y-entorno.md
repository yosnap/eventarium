---
phase: 1
title: "Fase 1: Monorepo y entorno"
status: completed
priority: P1
effort: "0.5-1d"
dependencies: []
---

# Fase 1: Monorepo y entorno

## Overview
Estructura del monorepo, licencia, entorno Docker de dependencias (PostgreSQL 16 con roles de aplicación, SeaweedFS, Redis), variables de entorno documentadas y `Makefile`. Objetivo: clonar y levantar dependencias con un comando.

## Requirements
- Functional: `docker compose up -d` levanta PostgreSQL (con roles `app_user` y `app_maintainer` creados por script de init), SeaweedFS (API S3 + bucket `media`) y Redis con healthchecks y volúmenes persistentes; `.env.example` documenta todas las variables; `Makefile` con targets `dev`, `api`, `web`, `worker`, `db-migrate`, `db-seed`, `lint`, `test`, `audit`.
- Non-functional: sin secretos en el repo; contraseñas de los roles de BD tomadas de variables de entorno por el script de init; puertos configurables; README y comentarios en español de España; licencia MIT; `.dockerignore` en cada app desde el inicio.

## Architecture
- Monorepo plano `apps/api` + `apps/web` + `infra/` (sin Nx/Turborepo).
- Compose de desarrollo solo con dependencias; las apps corren en local con hot reload. `docker-compose.prod.yml` (fase 5) añade migrate, api, worker, web y Caddy.
- **Roles de BD fuera de Alembic** (hallazgo red-team #7): `infra/postgres/init/01-roles.sql` (montado en `/docker-entrypoint-initdb.d/`) crea `app_maintainer` (propietario del esquema, `BYPASSRLS`) y `app_user` (`NOBYPASSRLS`, sin `CREATE`), y ejecuta `ALTER DEFAULT PRIVILEGES FOR ROLE app_maintainer IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_user` (y `USAGE, SELECT ON SEQUENCES`) para que toda tabla futura sea accesible sin grants manuales. Alembic corre siempre como `app_maintainer`. En producción el mismo script se aplica en el primer arranque; su idempotencia se garantiza con `DO $$ … IF NOT EXISTS`.
- SeaweedFS single-node (`weed server -s3`) con `s3.json` de credenciales. `storage-init` solo crea el bucket `media`; **no se depende de bucket policy pública** (hallazgo #15): los objetos públicos se sirven a través de `S3_PUBLIC_BASE_URL` (en desarrollo, el propio endpoint S3 con presigned GET de larga duración; en producción, ruta `/media/*` en Caddy que hace proxy al bucket). Se verifica explícitamente en esta fase si la versión fijada soporta `PutBucketPolicy`; si sí, se puede usar como optimización, nunca como requisito.
- Redis 7 para Taskiq, revocación de refresh tokens y rate limiting.
- **Caddy también en desarrollo** (validación #1): servicio `caddy` con `infra/caddy/Caddyfile.dev` que sirve `http://localhost:8080` → `/api/*` a `host.docker.internal:8000` (uvicorn), `/media/*` al bucket de SeaweedFS y el resto a `host.docker.internal:4200` (dev server de Angular). Así web y API comparten host desde el primer día (cookie first-party, sin CORS) y se prueba `X-Forwarded-Host` en local. <!-- Updated: Validation Session 1 - Caddy en dev -->

## Related Code Files
- Create: `README.md`, `LICENSE` (MIT), `.gitignore`, `.editorconfig`, `Makefile`
- Create: `infra/docker-compose.yml`, `infra/env/.env.example`, `infra/seaweedfs/s3.json.example`, `infra/postgres/init/01-roles.sql`, `infra/caddy/Caddyfile.dev`
- Create: `apps/api/.dockerignore`, `apps/web/.dockerignore`, `apps/api/.gitkeep`, `apps/web/.gitkeep`

## Implementation Steps
1. Ficheros raíz: `README.md`, `LICENSE` MIT, `.gitignore` (Python, Node, `.env*`, IDE, `*.pem`), `.editorconfig`.
2. `infra/postgres/init/01-roles.sql` con creación idempotente de roles (contraseñas desde `POSTGRES_APP_USER_PASSWORD` y `POSTGRES_MAINTAINER_PASSWORD` mediante `\set` en el entrypoint o `envsubst` en un script `.sh` de init) y `ALTER DEFAULT PRIVILEGES`.
3. `infra/docker-compose.yml`: `postgres:16-alpine` (init montado, healthcheck `pg_isready`), `chrislusf/seaweedfs:<tag fijo>` (`server -s3 -dir=/data`, puertos 8333/9333, healthcheck HTTP en `/status` del master), `storage-init` con `depends_on: service_healthy` y reintentos, `redis:7-alpine` (healthcheck `redis-cli ping`, `--appendonly yes`), `caddy:2` con `Caddyfile.dev` en el puerto `WEB_PORT` (8080). Puertos parametrizados.
4. `infra/env/.env.example`: `APP_ENV`, `DATABASE_URL` (app_user), `DATABASE_MIGRATIONS_URL` (app_maintainer), `POSTGRES_*`, `S3_ENDPOINT`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET`, `S3_PUBLIC_BASE_URL`, `REDIS_URL`, `JWT_SECRET`, `COOKIE_DOMAIN`, `TRUSTED_PROXY_CIDRS`, `CORS_ORIGINS`, `DEFAULT_ORGANIZATION_SLUG` (solo development), `WEB_BASE_URL`.
5. `.dockerignore` en `apps/api` y `apps/web` excluyendo `.env*`, `node_modules`, `.venv`, `tests`, `.git`.
6. `Makefile` con los targets listados; `make dev` levanta Compose y muestra cómo arrancar api/web/worker.
7. Verificar en limpio: `docker compose down -v && up -d`, todos healthy, `psql` como `app_user` no puede `CREATE TABLE`, bucket `media` listado vía `aws s3 ls --endpoint-url`; anotar en el README si `PutBucketPolicy` está soportado.

## Success Criteria
- [x] Compose levanta los cuatro servicios (postgres, seaweedfs, redis, caddy) healthy desde cero en < 2 min
- [x] `http://localhost:8080/api/v1/health` y `http://localhost:8080/media/<objeto>` responden a través de Caddy cuando api y web están arrancados
- [x] Roles `app_user` (sin `BYPASSRLS`, sin `CREATE`) y `app_maintainer` existen; `ALTER DEFAULT PRIVILEGES` verificado con `\ddp`
- [x] Bucket `media` existe tras el arranque; capacidad de bucket policy documentada
- [x] `.env.example` completo, sin valores reales; `.dockerignore` presentes
- [x] `make help` lista los targets

## Risk Assessment
- Puertos ocupados → variables de puerto; identificar el proceso (`lsof -i :PORT`), no incrementar a ciegas.
- Script de init solo corre con volumen vacío → documentar `make db-reset`; en producción, `infra/scripts/ensure-roles.sh` reaplicable.
- Imagen de SeaweedFS cambia flags entre versiones → tag fijo; señal: reinicio en bucle; respuesta: consultar docs de la versión fijada.
