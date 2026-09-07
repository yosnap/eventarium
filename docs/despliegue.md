# Despliegue

Producción con **EasyPanel**. `infra/docker-compose.prod.yml` define los servicios
—PostgreSQL, Redis, SeaweedFS, la API, el worker y el frontend SSR— y EasyPanel pone el
proxy (Traefik), el TLS y el enrutado.

Caddy es **solo para desarrollo**: en local resuelve el requisito de un único host sin
depender de nada externo.

## Principios

- **Imágenes por SHA.** `IMAGE_TAG` referencia `sha-<commit>`, nunca `latest`. Un
  rollback debe volver al artefacto exacto que estaba corriendo, y `latest` se mueve.
- **Un único servicio migra.** `migrate` es de un solo uso y corre antes que `api` y
  `worker`, que esperan a que termine. Ni la API ni el worker migran por su cuenta: con
  varias réplicas, dos migraciones simultáneas competirían por el mismo esquema.
- **Los secretos solo existen en tiempo de ejecución.** Están en `infra/env/.env` en el
  servidor, nunca dentro de una imagen. La publicación de imágenes lo verifica.
- **Un solo dominio, enrutado por rutas.** No es un capricho: la sesión se sostiene en
  una cookie first-party. Si `web` y `api` viven en subdominios distintos, el navegador
  deja de enviarla y habría que abrir CORS y ampliar el alcance de la cookie.

## Primer despliegue con EasyPanel

### 1. Crear el proyecto y los servicios

En EasyPanel, crea un proyecto y dentro estos servicios:

| Servicio | Tipo | Imagen o plantilla | Puerto interno |
|---|---|---|---|
| `postgres` | Plantilla PostgreSQL 16 | — | 5432 |
| `redis` | Plantilla Redis 7 | — | 6379 |
| `seaweedfs` | App | `chrislusf/seaweedfs:3.97` | 8333 |
| `api` | App | `ghcr.io/yosnap/eventarium/api:sha-<commit>` | 8000 |
| `worker` | App | la misma imagen que `api` | — |
| `web` | App | `ghcr.io/yosnap/eventarium/web:sha-<commit>` | 4000 |

Comandos de arranque:

- `seaweedfs`: `server -dir=/data -s3 -s3.port=8333 -s3.config=/etc/seaweedfs/s3.json -ip=seaweedfs`
- `worker`: `taskiq worker app.core.tasks:broker`
- `api` y `web` usan el comando por defecto de su imagen.

### 2. Enrutar el dominio por rutas

Apunta el dominio al servicio `web` y añade las reglas por ruta:

| Ruta | Servicio | Puerto |
|---|---|---|
| `/` | `web` | 4000 |
| `/api` | `api` | 8000 |
| `/media` | `seaweedfs` | 8333 |

Las tres rutas **tienen que estar en el mismo dominio**. Es la base del diseño de
sesión: la cookie de refresco es first-party y no lleva atributo `Domain`.

Deja que EasyPanel gestione el certificado TLS.

### 3. Variables de entorno

En cada servicio que las necesite (`api`, `worker` y `migrate`):

```bash
APP_ENV=production
DATABASE_URL=postgresql+asyncpg://app_user:<contraseña>@postgres:5432/eventarium
DATABASE_MIGRATIONS_URL=postgresql+asyncpg://app_maintainer:<contraseña>@postgres:5432/eventarium
REDIS_URL=redis://redis:6379/0
S3_ENDPOINT=http://seaweedfs:8333
S3_ACCESS_KEY=<clave>
S3_SECRET_KEY=<secreto>
S3_BUCKET=media
S3_PUBLIC_BASE_URL=https://eventos.tu-dominio.org/media
WEB_BASE_URL=https://eventos.tu-dominio.org
JWT_SECRET=<openssl rand -base64 48>
DEFAULT_ORGANIZATION_SLUG=
TRUSTED_PROXY_CIDRS=10.0.0.0/8,172.16.0.0/12
```

Y en `web`:

```bash
PORT=4000
API_INTERNAL_URL=http://api:8000
NG_ALLOWED_HOSTS=tu-dominio.org,*.tu-dominio.org
```

Dos que suelen dar problemas:

- **`TRUSTED_PROXY_CIDRS`** decide desde dónde se acepta `X-Forwarded-Host`, que es lo
  que determina la organización. Tiene que cubrir la red del proxy de EasyPanel y nada
  más: abrirlo a `0.0.0.0/0` permitiría a cualquiera elegir organización con una
  cabecera. Comprueba el rango real con `docker network inspect` en el servidor.
- **`DEFAULT_ORGANIZATION_SLUG`** debe quedar vacío. La API se niega a arrancar en
  producción si tiene valor: es un atajo de desarrollo que saltaría la resolución por
  host.

### 4. Roles de base de datos y migraciones

Los roles se crean **antes** de la primera migración. Desde una consola en el servidor,
con `infra/postgres/sql/roles.sql` disponible:

```bash
POSTGRES_APP_USER_PASSWORD=... POSTGRES_MAINTAINER_PASSWORD=... \
  infra/scripts/ensure-roles.sh "postgresql://postgres:<contraseña>@localhost:5432/eventarium"
```

Después, migra con la imagen de la API:

```bash
docker run --rm --network <red-del-proyecto> --env-file .env \
  ghcr.io/yosnap/eventarium/api:sha-<commit> alembic upgrade head
```

En EasyPanel esto se automatiza como *pre-deploy command* del servicio `api`. Que sea
un paso aparte es deliberado: si `api` y `worker` migraran al arrancar, dos réplicas
competirían por el mismo esquema.

### 5. Primeros datos

```bash
docker run --rm --network <red-del-proyecto> --env-file .env \
  ghcr.io/yosnap/eventarium/api:sha-<commit> \
  python -m app.cli create-superadmin admin@tu-dominio.org

docker run --rm --network <red-del-proyecto> --env-file .env \
  ghcr.io/yosnap/eventarium/api:sha-<commit> \
  python -m app.cli create-organization mi-org "Mi Organización" eventos.tu-dominio.org
```

Comprueba `https://eventos.tu-dominio.org/api/v1/health`: los tres valores deben ser
`ok`.

## Despliegue con Docker Compose (alternativa)

`infra/docker-compose.prod.yml` sirve tal cual si prefieres no usar EasyPanel, pero
**no incluye proxy**: tendrás que poner uno delante que enrute `/`, `/api` y `/media` al
mismo dominio. El `Caddyfile` de desarrollo (`infra/caddy/Caddyfile.dev`) muestra el
enrutado que hace falta.

## Actualización

En EasyPanel: cambia la etiqueta de imagen de `api`, `worker` y `web` a
`sha-<commit-nuevo>` y despliega. El *pre-deploy command* de `api` ejecuta la migración
antes de levantar la versión nueva.

Con Docker Compose:

```bash
# 1. Fijar la nueva imagen
sed -i 's/^IMAGE_TAG=.*/IMAGE_TAG=sha-<commit-nuevo>/' infra/env/.env

# 2. Descargar antes de parar nada
docker compose --env-file infra/env/.env -f infra/docker-compose.prod.yml pull

# 3. Migrar
docker compose --env-file infra/env/.env -f infra/docker-compose.prod.yml up migrate

# 4. Reemplazar los servicios
docker compose --env-file infra/env/.env -f infra/docker-compose.prod.yml up -d
```

Haz una copia de seguridad **antes** de una actualización con migraciones (abajo).

## Rollback

En EasyPanel: vuelve a poner la etiqueta anterior en `api`, `worker` y `web` y
despliega. Con Compose:

```bash
sed -i 's/^IMAGE_TAG=.*/IMAGE_TAG=sha-<commit-anterior>/' infra/env/.env
docker compose --env-file infra/env/.env -f infra/docker-compose.prod.yml up -d --force-recreate api worker web
```

Si la versión nueva traía una migración incompatible, revierte también el esquema:

```bash
docker compose -f infra/docker-compose.prod.yml run --rm api alembic downgrade -1
```

Prueba el `downgrade` en un entorno de preproducción antes de necesitarlo en serio: no
todas las migraciones son reversibles sin pérdida de datos, y ese es el peor momento
para descubrirlo.

## Copias de seguridad

```bash
DESTINO=/var/backups/eventarium infra/scripts/backup.sh
```

Vuelca PostgreSQL en formato *custom* (comprimido y restaurable por partes) y sincroniza
el bucket. Conserva 14 días por defecto (`RETENCION_DIAS`). Aborta si el volcado sale
vacío, para no borrar copias buenas por una copia fallida.

Ejemplo de programación diaria:

```cron
15 3 * * * cd /opt/eventarium && DESTINO=/var/backups/eventarium infra/scripts/backup.sh >> /var/log/eventarium-backup.log 2>&1
```

### Restauración

```bash
infra/scripts/restore.sh /var/backups/eventarium/postgres-20260907-031500.dump \
                         /var/backups/eventarium/objetos-20260907-031500
```

Para `api` y `worker`, restaura con `--clean --if-exists`, **reaplica los roles y sus
privilegios** (un `pg_restore` no los recrea) y vuelve a arrancar los servicios.

El cliente S3 se ejecuta dentro de la red de Compose, así que usa el mismo endpoint
interno que la API: no hace falta exponer SeaweedFS al exterior ni instalar `aws-cli`
en el servidor. Si tu proyecto de Compose no se llama `eventarium`, indica la red con
`COMPOSE_NETWORK`.

### Prueba de restauración

**Ejecutada el 2026-09-07** sobre el stack de producción completo en local.

Procedimiento: copia con datos reales (una organización y un objeto en el bucket) →
`TRUNCATE` de `organizations` y `users` y borrado del objeto → restauración. Resultado:
la organización y el objeto vuelven, `/api/v1/health` responde `ok` en las tres
dependencias y una migración posterior corre sin errores.

Dos fallos encontrados y corregidos durante la prueba, que ilustran por qué un backup
sin restaurar no cuenta como backup:

1. `pg_restore --no-owner` dejaba las tablas a nombre del superusuario, así que
   `app_maintainer` perdía el acceso y la siguiente migración fallaba con
   «permission denied for table alembic_version». Se restaura conservando la propiedad.
2. La copia de objetos usaba `aws-cli` del host contra el endpoint interno, que desde el
   host no resuelve. Ahora se ejecuta dentro de la red de Compose.

Repite esta prueba tras cualquier cambio en el esquema de roles o en el almacenamiento,
y actualiza la fecha de arriba.

## Integración continua

| Workflow | Cuándo | Qué hace |
|---|---|---|
| `ci.yml` | push y PR a `main` o `develop` | API (ruff, mypy, pytest contra servicios reales, pip-audit, OpenAPI al día), web (`needs: api`; tipos regenerados sin diferencias, lint, formato, tests con axe, build) y detección de secretos |
| `build-images.yml` | push a `main` y tags `v*` | Publica `api` y `web` en GHCR con tag por SHA y verifica que no llevan ficheros `.env` |

CI falla ante: RLS rota, lint, tipos, violaciones de accesibilidad, tipos generados
desactualizados, dependencia vulnerable o secreto en el diff.

## Operación

```bash
# Estado y registros
docker compose -f infra/docker-compose.prod.yml ps
docker compose -f infra/docker-compose.prod.yml logs -f api

# Añadir un dominio a una organización
docker compose -f infra/docker-compose.prod.yml run --rm api \
  python -m app.cli add-domain mi-org otro.dominio.org

# Rotar las contraseñas de los roles de base de datos
POSTGRES_APP_USER_PASSWORD=... POSTGRES_MAINTAINER_PASSWORD=... \
  infra/scripts/ensure-roles.sh "postgresql://postgres:...@localhost:5432/ia_week"
# y actualiza DATABASE_URL y DATABASE_MIGRATIONS_URL en infra/env/.env
```

## Varias organizaciones: un subdominio para cada una

Cada organización vive en su propio subdominio del dominio de la instalación:
`iawic.tu-dominio.org`, `otra.tu-dominio.org`. La API resuelve la organización por el
host exacto de la petición, contrastado contra `organization_domains`.

Se eligió así frente a repartir por ruta (`/o/mi-org`) porque no toca la resolución por
host, que ya está implementada y cubierta por tests de aislamiento, y porque deja el
branding y las cookies limpiamente separados por organización.

Lo que hay que preparar en el despliegue:

1. **DNS comodín**: un registro `*.tu-dominio.org` apuntando al servidor.
2. **Certificado comodín** para `*.tu-dominio.org` en EasyPanel, o TLS bajo demanda.
3. **`NG_ALLOWED_HOSTS`**: incluir el comodín, por ejemplo
   `tu-dominio.org,*.tu-dominio.org`. El SSR valida `Host` y `X-Forwarded-Host` contra
   esta lista.

Al dar de alta una organización se registra su subdominio:

```bash
python -m app.cli create-organization mi-org "Mi Organización" mi-org.tu-dominio.org
```

Cuando exista el registro libre de usuarios, ese alta la hará la propia aplicación.

Quien quiera una instalación aparte hace fork del repositorio y la despliega.

El TLS bajo demanda para dominios de terceros (fase 9 del PRD) no está implementado:
sin un endpoint que compruebe que el dominio está registrado, cualquiera podría forzar
la emisión de certificados apuntando su dominio al servidor.

## Variables de entorno

Todas están documentadas en `infra/env/.env.example`. Las que solo aplican a producción:

| Variable | Para qué |
|---|---|
| `IMAGE_TAG` | Imagen a desplegar (`sha-<commit>`), solo con Docker Compose |
| `NG_ALLOWED_HOSTS` | Hosts que acepta el SSR; vacío = cualquiera |
| `API_INTERNAL_URL` | URL de la API en la red interna, para el SSR |
| `GITHUB_REPOSITORY` | Origen de las imágenes en GHCR |
