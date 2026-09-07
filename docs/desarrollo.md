# Puesta en marcha del entorno

Objetivo: que alguien que acaba de clonar el repositorio tenga el proyecto corriendo
sin preguntar a nadie.

## Requisitos

| Herramienta | Versión | Para qué |
|---|---|---|
| Docker | 24+ con Compose v2 | PostgreSQL, SeaweedFS, Redis y Caddy |
| [uv](https://docs.astral.sh/uv/) | 0.5+ | Dependencias y ejecución de Python |
| Python | 3.12 | Lo instala `uv` si no lo tienes |
| Node.js | 22 LTS | Frontend |
| pnpm | 11+ | Dependencias del frontend |
| `libmagic` | — | `python-magic` identifica los ficheros subidos por sus bytes |
| `psql` | 16 | Solo para los comandos de base de datos del Makefile |

`libmagic` no viene con Python y hay que instalarlo aparte:

```bash
# macOS
brew install libmagic
# Debian o Ubuntu
sudo apt-get install libmagic1
```

Sin él, la API arranca pero falla al validar cualquier subida con
`ImportError: failed to find libmagic`.

## Arranque

```bash
git clone https://github.com/yosnap/eventarium.git
cd eventarium

make setup      # crea infra/env/.env y infra/seaweedfs/s3.json desde los ejemplos
```

Edita los dos ficheros creados. Como mínimo:

- `infra/env/.env`: sustituye todos los valores `cambiame_…`. Genera el secreto de
  JWT con `openssl rand -base64 48` (mínimo 32 caracteres).
- `infra/seaweedfs/s3.json`: pon las **mismas** credenciales que `S3_ACCESS_KEY` y
  `S3_SECRET_KEY` del `.env`. Si no coinciden, la API no podrá escribir en el bucket.
- `DATABASE_URL` y `DATABASE_MIGRATIONS_URL` llevan las contraseñas de
  `POSTGRES_APP_USER_PASSWORD` y `POSTGRES_MAINTAINER_PASSWORD`: cámbialas también ahí.

Después:

```bash
make up          # postgres, seaweedfs (bucket incluido), redis y caddy
make db-migrate  # esquema y políticas RLS
make db-seed     # organización de demostración; muestra la contraseña del propietario
```

Guarda esa contraseña: solo se muestra una vez. Para regenerarla,
`make db-seed` con `--reset-password`, o define `SEED_OWNER_PASSWORD` en el `.env`.

Y para arrancar la aplicación:

```bash
make dev      # dependencias + API + worker + frontend, todo en una terminal
```

Los tres procesos comparten terminal con los logs prefijados (`[api]`, `[web]`,
`[worker]`) y `Ctrl+C` los para todos. Si prefieres una terminal por proceso:

```bash
make api      # solo la API, en :8000
make web      # solo el frontend, en :4200
make worker   # solo el worker de tareas
```

Cualquiera de esos comandos **libera antes su puerto**. Un dev server olvidado de una
sesión anterior lo deja ocupado, y la salida habitual —arrancar en otro puerto— acaba
con varios procesos zombis y una sesión rota, porque la cookie deja de coincidir con el
host. Solo se cierran procesos que escuchan en los puertos del proyecto, nunca por
nombre: un `pkill node` se llevaría por delante trabajo ajeno.

```bash
make status   # qué hay escuchando en 8000, 4200 y 8080
make stop     # libera los puertos sin tocar los contenedores
make down     # para las dependencias en Docker
```

## Accede siempre por http://localhost:8080

Caddy sirve la web, la API y los ficheros bajo el mismo host. Entrar directamente por
`:4200` **rompe la sesión**: la cookie de refresco es first-party por diseño y el
navegador no la enviará a un origen distinto del que la emitió.

| Ruta | Va a |
|---|---|
| `http://localhost:8080/` | Angular |
| `http://localhost:8080/api/v1/…` | FastAPI |
| `http://localhost:8080/api/v1/health` | Estado de BD, almacenamiento y Redis |
| `http://localhost:8080/docs` (vía `:8000`) | OpenAPI interactivo |
| `http://localhost:8080/media/…` | Objetos públicos del bucket |

## Comandos

`make help` los lista todos. Los que más se usan:

| Comando | Qué hace |
|---|---|
| `make up` / `make down` | Levanta o para las dependencias |
| `make reset` | Para y **borra los volúmenes** |
| `make db-migrate` | Aplica las migraciones |
| `make db-revision m="mensaje"` | Crea una migración a partir de los modelos |
| `make db-seed` | Datos de demostración (idempotente) |
| `make db-test-create` | Crea la base de datos de tests |
| `make lint` | ruff, mypy, ESLint y Prettier |
| `make test` | pytest y Vitest |
| `make audit` | pip-audit, pnpm audit y gitleaks |
| `make api-types` | Exporta OpenAPI y regenera el cliente del frontend |

## Tests

Corren contra PostgreSQL, Redis y SeaweedFS **reales**: RLS, las cookies y los
presigned URL son justo lo que hay que verificar, y un doble no reproduce ninguno.

```bash
make db-test-create   # una sola vez
make test-api
make test-web
```

El aislamiento entre tests se hace con `TRUNCATE`, no envolviendo cada test en una
transacción: los tests de RLS necesitan abrir sus propias transacciones y fijar el
contexto en cada una.

## Migraciones

Se ejecutan siempre con el rol `app_maintainer` (`DATABASE_MIGRATIONS_URL`). Con el rol
de la API fallan a propósito: no tiene permiso de creación en el esquema.

```bash
make db-revision m="añadir tabla de eventos"
# revisa el fichero generado en apps/api/alembic/versions/
make db-migrate
```

Al añadir una tabla con `organization_id`, **añade también su política RLS** en una
migración. Una tabla sin política queda visible para todas las organizaciones.

## Tipos del frontend

El cliente HTTP se genera desde `apps/api/openapi.json`, que está versionado:

```bash
make api-types
```

CI regenera y comprueba `git diff --exit-code`. Si cambias un endpoint y no
regeneras, la integración continua falla.

## Convenciones

- Código, nombres de fichero e identificadores en **inglés**.
- Interfaz, documentación, comentarios y mensajes de commit en **español de España**.
- Ficheros de máximo 1000 líneas, con 300 como objetivo.
- Python: `ruff` (línea de 100) y `mypy --strict`.
- TypeScript: ESLint con reglas de accesibilidad, Prettier, componentes `OnPush`.
- Commits en formato *Conventional Commits*.

## Accesibilidad

WCAG 2.1 AA es una puerta de calidad, no una recomendación: `pnpm test` falla ante
cualquier violación de axe. Antes de dar por terminada una pantalla, recórrela solo con
teclado y añade su fila al checklist de [`accesibilidad.md`](accesibilidad.md).

## Problemas frecuentes

| Síntoma | Causa y solución |
|---|---|
| `ImportError: failed to find libmagic` | Falta `libmagic`. Instálalo (arriba) |
| `password authentication failed for user "app_maintainer"` | Las URL de base de datos del `.env` no llevan la contraseña de los roles |
| El bucket no existe o da 403 | Las credenciales de `s3.json` no coinciden con las del `.env`. Corrígelas y `docker compose restart seaweedfs` |
| Los roles no existen | El script de init solo corre con el volumen vacío. Usa `make reset`, o `infra/scripts/ensure-roles.sh` sobre una base ya creada |
| La sesión se pierde al recargar | Estás entrando por `:4200` en lugar de por `:8080` |
| El puerto está ocupado | Identifica el proceso con `lsof -i :8080` y páralo; no cambies el puerto a ciegas |
| SSR no renderiza y cae a cliente | El host no está en `NG_ALLOWED_HOSTS`, o llega una cabecera `x-forwarded-*` no declarada como de confianza |
