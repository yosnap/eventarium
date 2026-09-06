# Eventarium

Plataforma open source de registro y gestión de eventos, multi-organización, con
branding propio por organizador. Cualquier organización puede instalarla y servir sus
eventos bajo su propio dominio y su propia marca.

Primer despliegue: **IAWIC** (IA Week Valencia).

- **Licencia:** MIT
- **Backend:** FastAPI (Python 3.12) + PostgreSQL 16 con Row-Level Security
- **Frontend:** Angular 21 LTS (SSR en rutas públicas) + Tailwind v4
- **Almacenamiento:** SeaweedFS (API S3) tras una interfaz `StorageProvider`
- **Tareas async:** Taskiq sobre Redis Streams
- **Proxy:** Caddy sirve `/`, `/api/*` y `/media/*` bajo el mismo host

## Arranque rápido

```bash
make setup      # crea infra/env/.env y infra/seaweedfs/s3.json
# ajusta las credenciales en ambos ficheros
make up         # postgres + seaweedfs + redis + caddy
make db-migrate
make db-seed    # muestra por consola la contraseña del usuario owner
make dev        # instrucciones para arrancar api, web y worker
```

Accede siempre por `http://localhost:8080` (Caddy). Entrar directamente por
`:4200` rompe la cookie de sesión, que es first-party por diseño.

`make help` lista todos los comandos.

## Estructura

```
apps/api/     API FastAPI (core, modules, seed, alembic, tests)
apps/web/     Aplicación Angular (público + admin)
infra/        Compose, PostgreSQL init, Caddy, SeaweedFS, scripts
docs/         Investigación, PRD y documentación técnica
plans/        Planes de implementación por fase
```

## Documentación

| Documento | Contenido |
|---|---|
| [`docs/prd.md`](docs/prd.md) | Requisitos de producto |
| [`docs/investigacion.md`](docs/investigacion.md) | Investigación previa y decisiones de stack |
| [`docs/arquitectura.md`](docs/arquitectura.md) | Arquitectura del sistema |
| [`docs/desarrollo.md`](docs/desarrollo.md) | Puesta en marcha del entorno |
| [`docs/modelo-de-datos.md`](docs/modelo-de-datos.md) | Esquema y RLS |
| [`docs/accesibilidad.md`](docs/accesibilidad.md) | Checklist WCAG 2.1 AA |
| [`docs/despliegue.md`](docs/despliegue.md) | Despliegue, backups y rollback |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Flujo de trabajo y checklist de PR |

## Notas de infraestructura

- Los roles de PostgreSQL (`app_user` sin `BYPASSRLS`, `app_maintainer` con él) se
  crean con `infra/postgres/init/01-roles.sh`, fuera de Alembic. Sobre una base ya
  existente se reaplican con `infra/scripts/ensure-roles.sh`.
- El acceso público de lectura al bucket lo concede la identidad `anonymous` de
  `infra/seaweedfs/s3.json`; no se depende de `PutBucketPolicy`. Comprobado en
  SeaweedFS 3.97: la operación existe pero rechaza políticas estándar de AWS
  (`InvalidPolicyDocument`), así que no es una vía fiable.
- Caddy expone `/media/*` como proxy directo al bucket: como el bucket se llama
  `media`, la ruta coincide con la clave path-style del objeto en S3.
