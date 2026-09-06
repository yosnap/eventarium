# Comandos de desarrollo de la plataforma IA Week.
# Requisitos: docker, uv, pnpm, libmagic (ver docs/desarrollo.md).

SHELL := /bin/bash
COMPOSE := docker compose --env-file infra/env/.env -f infra/docker-compose.yml
COMPOSE_PROD := docker compose --env-file infra/env/.env -f infra/docker-compose.prod.yml
API_DIR := apps/api
WEB_DIR := apps/web

# Carga infra/env/.env en los targets que ejecutan procesos locales.
ifneq (,$(wildcard infra/env/.env))
include infra/env/.env
export
endif

.DEFAULT_GOAL := help
.PHONY: help setup dev up down logs ps reset api worker web \
        db-migrate db-revision db-seed db-reset db-test-create \
        lint lint-api lint-web test test-api test-web audit \
        api-openapi api-types

help: ## Lista los targets disponibles
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

setup: ## Crea infra/env/.env y infra/seaweedfs/s3.json a partir de los ejemplos
	@test -f infra/env/.env || (cp infra/env/.env.example infra/env/.env && echo "creado infra/env/.env")
	@test -f infra/seaweedfs/s3.json || (cp infra/seaweedfs/s3.json.example infra/seaweedfs/s3.json && echo "creado infra/seaweedfs/s3.json")
	@echo "Ajusta las credenciales en ambos ficheros antes de 'make up'."

up: ## Levanta las dependencias (postgres, seaweedfs, redis, caddy)
	$(COMPOSE) up -d --wait postgres seaweedfs redis caddy
	$(COMPOSE) up storage-init

down: ## Para las dependencias (conserva los datos)
	$(COMPOSE) down

reset: ## Para las dependencias y BORRA los volúmenes
	$(COMPOSE) down -v

logs: ## Sigue los logs de las dependencias
	$(COMPOSE) logs -f

ps: ## Estado de los servicios
	$(COMPOSE) ps

dev: up ## Levanta dependencias y explica cómo arrancar las apps
	@echo ""
	@echo "Dependencias listas. Abre tres terminales:"
	@echo "  make api      # FastAPI en :8000"
	@echo "  make web      # Angular en :4200"
	@echo "  make worker   # worker de Taskiq"
	@echo ""
	@echo "Accede SIEMPRE por http://localhost:$(WEB_PORT) (Caddy), nunca por :4200."

api: ## Arranca la API con recarga automática
	cd $(API_DIR) && uv run uvicorn app.main:app --reload --port 8000

worker: ## Arranca el worker de Taskiq
	cd $(API_DIR) && uv run taskiq worker app.core.tasks:broker --reload

web: ## Arranca el dev server de Angular
	cd $(WEB_DIR) && pnpm start

db-migrate: ## Aplica las migraciones (rol app_maintainer)
	cd $(API_DIR) && uv run alembic upgrade head

db-revision: ## Crea una migración: make db-revision m="mensaje"
	cd $(API_DIR) && uv run alembic revision --autogenerate -m "$(m)"

db-seed: ## Carga los datos de demostración (idempotente)
	cd $(API_DIR) && uv run python -m app.cli seed

db-reset: ## Borra el volumen de PostgreSQL y vuelve a migrar y sembrar
	$(COMPOSE) rm -sf postgres
	docker volume rm -f ia-week_postgres-data
	$(COMPOSE) up -d --wait postgres
	$(MAKE) db-migrate db-seed

db-test-create: ## Crea la base de datos de tests
	$(COMPOSE) exec -T postgres psql -U $(POSTGRES_SUPERUSER) -d postgres \
		-c "SELECT 'CREATE DATABASE $(POSTGRES_DB)_test OWNER app_maintainer' \
		WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '$(POSTGRES_DB)_test')\gexec"
	POSTGRES_APP_USER_PASSWORD=$(POSTGRES_APP_USER_PASSWORD) \
	POSTGRES_MAINTAINER_PASSWORD=$(POSTGRES_MAINTAINER_PASSWORD) \
	$(COMPOSE) exec -T -e PGPASSWORD=$(POSTGRES_SUPERUSER_PASSWORD) postgres \
		psql -U $(POSTGRES_SUPERUSER) -d $(POSTGRES_DB)_test \
		-v ON_ERROR_STOP=1 \
		-v app_user_password=$(POSTGRES_APP_USER_PASSWORD) \
		-v maintainer_password=$(POSTGRES_MAINTAINER_PASSWORD) \
		-v dbname=$(POSTGRES_DB)_test \
		-f /opt/postgres-sql/roles.sql

lint: lint-api lint-web ## Lint y formato de todo el monorepo

lint-api: ## ruff + mypy
	cd $(API_DIR) && uv run ruff check . && uv run ruff format --check . && uv run mypy app

lint-web: ## ESLint + Prettier
	cd $(WEB_DIR) && pnpm lint && pnpm format:check

test: test-api test-web ## Tests de API y web

test-api: ## pytest contra PostgreSQL real
	cd $(API_DIR) && uv run pytest

test-web: ## Vitest (incluye axe)
	cd $(WEB_DIR) && pnpm test

audit: ## Auditoría de dependencias y secretos
	cd $(API_DIR) && uv run pip-audit
	cd $(WEB_DIR) && pnpm audit --audit-level moderate
	gitleaks detect --no-banner --redact

api-openapi: ## Exporta apps/api/openapi.json
	cd $(API_DIR) && uv run python -m app.cli export-openapi

api-types: api-openapi ## Regenera los tipos del cliente desde openapi.json
	cd $(WEB_DIR) && pnpm api:types
