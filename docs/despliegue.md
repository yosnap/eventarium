# Despliegue

Producción con `infra/docker-compose.prod.yml`: PostgreSQL, Redis, SeaweedFS, la API,
el worker, el frontend SSR y Caddy delante de todo.

## Principios

- **Imágenes por SHA.** `IMAGE_TAG` referencia `sha-<commit>`, nunca `latest`. Un
  rollback debe volver al artefacto exacto que estaba corriendo, y `latest` se mueve.
- **Un único servicio migra.** `migrate` es de un solo uso y corre antes que `api` y
  `worker`, que esperan a que termine. Ni la API ni el worker migran por su cuenta: con
  varias réplicas, dos migraciones simultáneas competirían por el mismo esquema.
- **Los secretos solo existen en tiempo de ejecución.** Están en `infra/env/.env` en el
  servidor, nunca dentro de una imagen. La publicación de imágenes lo verifica.

## Primer despliegue

```bash
git clone https://github.com/yosnap/eventarium.git && cd eventarium
make setup
```

Edita `infra/env/.env` con los valores de producción y añade:

```bash
APP_ENV=production
SITE_ADDRESS=eventos.tu-dominio.org      # dominio que sirve Caddy
ACME_EMAIL=admin@tu-dominio.org          # avisos de Let's Encrypt
IMAGE_TAG=sha-<commit>                   # imagen a desplegar
S3_PUBLIC_BASE_URL=https://eventos.tu-dominio.org/media
WEB_BASE_URL=https://eventos.tu-dominio.org
DEFAULT_ORGANIZATION_SLUG=               # debe quedar vacío; la API lo rechaza si no
TRUSTED_PROXY_CIDRS=172.16.0.0/12        # red interna de Docker, no 0.0.0.0/0
```

`TRUSTED_PROXY_CIDRS` decide desde dónde se acepta `X-Forwarded-Host`. Abrirlo a
`0.0.0.0/0` permitiría a cualquiera elegir organización con una cabecera.

Ajusta `infra/seaweedfs/s3.json` con las mismas credenciales que el `.env` y arranca:

```bash
docker compose --env-file infra/env/.env -f infra/docker-compose.prod.yml up -d
```

Compose ejecuta `migrate` y, cuando termina, levanta `api`, `worker`, `web` y `caddy`.
Caddy pide el certificado TLS solo al arrancar con un dominio público apuntando al
servidor.

Crea el superadministrador y la primera organización:

```bash
docker compose -f infra/docker-compose.prod.yml run --rm api \
  python -m app.cli create-superadmin admin@tu-dominio.org
docker compose -f infra/docker-compose.prod.yml run --rm api \
  python -m app.cli create-organization mi-org "Mi Organización" eventos.tu-dominio.org
```

Comprueba `https://eventos.tu-dominio.org/api/v1/health`: los tres valores deben ser
`ok`.

## Actualización

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

## Dominios propios por organización

El bloque `on_demand_tls` del `Caddyfile` está escrito pero **desactivado**. Sin un
endpoint de autorización, cualquiera podría forzar la emisión de certificados apuntando
su dominio a este servidor. Se activará en la fase 9 del PRD, junto con el endpoint que
compruebe que el dominio está registrado en `organization_domains`.

Mientras tanto, para servir varios dominios hay que añadirlos al `Caddyfile` y, si se
define `NG_ALLOWED_HOSTS`, también ahí.

## Variables de entorno

Todas están documentadas en `infra/env/.env.example`. Las que solo aplican a producción:

| Variable | Para qué |
|---|---|
| `IMAGE_TAG` | Imagen a desplegar (`sha-<commit>`) |
| `SITE_ADDRESS` | Dominio que sirve Caddy |
| `ACME_EMAIL` | Contacto para Let's Encrypt |
| `NG_ALLOWED_HOSTS` | Hosts que acepta el SSR; vacío = cualquiera |
| `GITHUB_REPOSITORY` | Origen de las imágenes en GHCR |
