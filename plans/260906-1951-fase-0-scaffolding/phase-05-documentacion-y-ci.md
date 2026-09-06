---
phase: 5
title: "Fase 5: Documentación y CI"
status: pending
priority: P1
effort: "1-1.5d"
dependencies: [1, 2, 3, 4]
---

# Fase 5: Documentación y CI

## Overview
Puertas de calidad automatizadas en GitHub Actions (incluidas auditoría de dependencias, detección de secretos y accesibilidad), Compose de producción con paso de migración, Caddy y etiquetas inmutables, y documentación de arquitectura, desarrollo, modelo de datos y accesibilidad verificada contra el código real.

## Requirements
- Functional: workflow `ci.yml` con jobs `api` (uv, ruff, mypy, pip-audit, pytest contra Postgres/Redis/SeaweedFS reales, exportación de `openapi.json` como artefacto) y `web` (`needs: api`, pnpm `--frozen-lockfile`, `pnpm audit`, regeneración de tipos desde el artefacto + `git diff --exit-code`, lint, test con axe, build SSR) y job `secrets` (gitleaks); `build-images.yml` que publica en GHCR con tags `sha-<commit>` y `latest` solo en `main`; `docker-compose.prod.yml` con `migrate` (one-shot, `app_maintainer`, corre antes de `api`/`worker` mediante `depends_on: service_completed_successfully`), `api`, `worker`, `web`, `postgres`, `redis`, `seaweedfs`, `caddy`; `infra/caddy/Caddyfile` de producción (mismo host: `/api/*` → api, `/media/*` → bucket con cache, resto → web SSR; `X-Forwarded-Host`/`X-Forwarded-For`; bloque TLS on-demand documentado y desactivado), coherente con `Caddyfile.dev` de la fase 1; `infra/scripts/backup.sh` y `infra/scripts/ensure-roles.sh`; `docs/arquitectura.md`, `docs/desarrollo.md`, `docs/modelo-de-datos.md`, `docs/accesibilidad.md` (completo), `docs/despliegue.md`, `CONTRIBUTING.md`; README enlazando todo.
- Non-functional: docs en español de España, ≤ 800 líneas, Mermaid; afirmaciones verificadas contra el código; imágenes sin secretos (`docker history` limpio); rollback documentado (tag anterior + `alembic downgrade` probado en staging).

## Architecture
- CI: `api` levanta Postgres 16 y Redis como `services:` y SeaweedFS con `docker run` + espera activa; aplica `infra/postgres/init/01-roles.sql` antes de las migraciones; exporta `openapi.json` con `python -m app.cli export-openapi` y lo sube como artefacto; `web` lo descarga con `needs: api`.
- Producción: `migrate` es un servicio one-shot con la imagen de `api`; `api` y `worker` esperan a que termine; tags de imagen por SHA; `docs/despliegue.md` describe actualización (pull tag → migrate → api/worker/web) y rollback.
- Backups: `backup.sh` (`pg_dump` custom + sincronización del bucket a destino S3 secundario) con `cron` de ejemplo en Compose (`ofelia` o `cron` del host); restauración documentada y **probada una vez** como criterio de esta fase.

## Related Code Files
- Create: `.github/workflows/ci.yml`, `.github/workflows/build-images.yml`, `.gitleaks.toml`
- Create: `infra/docker-compose.prod.yml`, `infra/caddy/Caddyfile`, `infra/scripts/backup.sh`, `infra/scripts/restore.sh`, `infra/scripts/ensure-roles.sh`
- Create: `docs/arquitectura.md`, `docs/desarrollo.md`, `docs/modelo-de-datos.md`, `docs/despliegue.md`, `CONTRIBUTING.md`
- Modify: `README.md`, `docs/accesibilidad.md`, `apps/api/app/cli.py` (`export-openapi`)

## Implementation Steps
1. `ci.yml`: jobs `api`, `web` (`needs: api`), `secrets`; caches de `uv`/`pnpm`; lockfiles congelados; fallo si `git diff --exit-code` detecta tipos desactualizados.
2. `build-images.yml`: build y push de `api` y `web` a GHCR con tags `sha-…` y `latest` en `main`; verificación `docker history` sin `.env`.
3. `docker-compose.prod.yml` + `Caddyfile`; probar en local con dominio `localhost`: migrate → api → web; `/media/*` sirve el logo.
4. `backup.sh` / `restore.sh`; ejecutar un ciclo backup → restauración en un volumen limpio y anotar el resultado en `docs/despliegue.md`.
5. `docs/arquitectura.md`: monorepo, multi-tenant/RLS con los dos roles, resolución por host, theming, auth con cookie, permisos y anti-escalada, storage con namespacing, tareas durables; diagrama Mermaid.
6. `docs/desarrollo.md`: requisitos (incl. `libmagic`), arranque paso a paso probado en limpio, comandos Make, convenciones, tests, migraciones, tipos, accesibilidad.
7. `docs/modelo-de-datos.md`: ER Mermaid + roles clonados, campos, RLS.
8. `docs/despliegue.md`: actualización, rollback, backups, variables.
9. `docs/accesibilidad.md`: checklist WCAG 2.1 AA completado para todas las pantallas de la fase 0.
10. `CONTRIBUTING.md`: flujo de ramas, checklist de PR (tests, a11y, docs, sin secretos), código de conducta breve.
11. Verificar enlaces y comandos; actualizar `README.md`.

## Success Criteria
- [ ] CI en verde en un PR de prueba; falla ante: rotura de RLS, lint, tipos, a11y, tipos generados desactualizados, dependencia vulnerable, secreto en el diff
- [ ] `docker compose -f infra/docker-compose.prod.yml up` ejecuta `migrate` y sirve web y api tras Caddy en `localhost`; `/media/*` funciona
- [ ] Ciclo backup → restore probado y documentado
- [ ] Una persona ajena levanta el entorno siguiendo solo `docs/desarrollo.md` (protocolo: sin preguntas al equipo, anotando bloqueos)
- [ ] Diagramas Mermaid renderizan en GitHub; ningún doc > 800 líneas

## Risk Assessment
- SeaweedFS en CI inestable → contenedor con espera activa y reintentos; si persiste, cachear imagen y aislar en job propio.
- `migrate` concurrente en despliegues con varias réplicas → un único servicio `migrate`; `api`/`worker` no migran nunca por sí mismos.
- Docs desactualizadas → esta fase se escribe la última verificando contra código; regla en `CONTRIBUTING.md`.
