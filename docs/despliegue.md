# Despliegue

Producción con **Dokploy** (o EasyPanel). `infra/docker-compose.prod.yml` define los
servicios —PostgreSQL, Redis, SeaweedFS, la API, el worker, el scheduler, el frontend SSR
y un Caddy interno— y el orquestador pone el proxy de entrada (Traefik) y el TLS.

El enrutado por ruta **no** lo hace el panel: el dominio se apunta entero al servicio
`caddy` y es `infra/caddy/Caddyfile` quien reparte `/api`, `/media` y el resto. Así la
regla que bloquea los justificantes de gasto en `/media` (ver el comentario largo en ese
fichero) vive en el repo, versionada, y no depende de que alguien la replique a mano en el
panel. `infra/caddy/Caddyfile.dev` es el equivalente para desarrollo local.

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
| `scheduler` | App | la misma imagen que `api` | — |
| `web` | App | `ghcr.io/yosnap/eventarium/web:sha-<commit>` | 4000 |
| `caddy` | Compose (no App suelta) | `caddy:2.10-alpine` | 80 |

Comandos de arranque:

- `seaweedfs`: `server -dir=/data -s3 -s3.port=8333 -s3.config=/etc/seaweedfs/s3.json -ip=seaweedfs`
- `worker`: `taskiq worker app.core.tasks:broker`
- `scheduler`: `taskiq scheduler app.core.tasks:scheduler`. Es un proceso aparte del
  `worker` (desde Taskiq 0.12 uno consume la cola y el otro dispara las tareas con
  `schedule`): sin este servicio, el barrido de cuentas sin verificar no se ejecuta nunca,
  aunque el `worker` esté sano.
- `api` y `web` usan el comando por defecto de su imagen.
- `caddy` necesita `infra/caddy/Caddyfile` montado en `/etc/caddy/Caddyfile`, y un
  servicio «App» desde imagen no tiene checkout del repo: despliégalo desde
  `infra/docker-compose.prod.yml` (recurso Compose del panel), que ya lo monta. Con la
  imagen sola, el dominio mostraría la página de bienvenida de Caddy.

### 2. Enrutar el dominio

Una sola regla: el dominio, con TLS del panel (Let's Encrypt), apuntando al servicio
`caddy`, puerto `80`, ruta `/`, sin `stripPath`. Nada más.

`caddy` es quien enruta por dentro del stack (`infra/caddy/Caddyfile`):

| Ruta | Servicio | Puerto |
|---|---|---|
| `/api/*` | `api` | 8000 |
| `/media/orgs/<id>/accounting-receipts/*` | — | 403 |
| `/media/*` | `seaweedfs` | 8333 |
| resto | `web` | 4000 |

Las rutas **tienen que estar en el mismo dominio**. Es la base del diseño de sesión: la
cookie de refresco es first-party y no lleva atributo `Domain`.

Caddy conserva `X-Forwarded-Host` y `X-Forwarded-Proto` tal como las pone el Traefik del
panel (llega desde una red privada, declarada en `trusted_proxies`), así que la API y el
SSR ven `https` y el host real aunque el tramo Traefik→Caddy vaya sin TLS.

**No enrutes `/api` y `/media` como reglas directas del panel** saltándote `caddy`:
dejarías todo `/media/*` abierto sin la regla `@justificantes`, y cualquiera con la clave
del objeto (`orgs/<id>/accounting-receipts/…`) descargaría un justificante de gasto sin
sesión. El único camino legítimo a un justificante es
`GET /api/v1/accounting/receipts/{clave}`, con sesión y como adjunto.

### 3. Variables de entorno

En cada servicio que las necesite (`api`, `worker`, `scheduler` y `migrate`):

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
TRUSTED_PROXY_CIDRS=172.16.0.0/12,192.168.0.0/16
```

Y en `web`:

```bash
PORT=4000
API_INTERNAL_URL=http://api:8000
NG_ALLOWED_HOSTS=tu-dominio.org
```

Una que suele dar problemas:

- **`TRUSTED_PROXY_CIDRS`** decide desde qué redes se acepta `X-Forwarded-For` al
  calcular la IP real del cliente (limitadores de tasa). El peer TCP de la API es el
  servicio `caddy`, que vive en la red del proyecto Compose (no en la red del Traefik
  del panel): el CIDR tiene que cubrir esa red, y nada más. Si se queda fuera, la API
  toma la IP de `caddy` como cliente para todo el mundo y el limitador colapsa en un
  solo contador: un puñado de intentos de cualquiera daría 429 a toda la plataforma.
  Docker asigna esas subredes dentro de `172.16.0.0/12` y, cuando ese pool se agota en
  un host con muchos proyectos, dentro de `192.168.0.0/16`; incluye los dos rangos o
  comprueba el real con `docker network inspect <proyecto>_default`. Abrirlo a
  `0.0.0.0/0` dejaría a cualquiera falsear su IP contra los límites.

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
  python -m app.cli create-organization mi-org "Mi Organización"
```

Comprueba `https://eventos.tu-dominio.org/api/v1/health`: los tres valores deben ser
`ok`.

## Despliegue con Docker Compose (alternativa)

`infra/docker-compose.prod.yml` sirve tal cual si prefieres no usar un panel: el
servicio `caddy` ya enruta `/`, `/api` y `/media` por dentro, pero escucha en HTTP plano
(puerto 80, sin certificados) porque cuenta con un proxy delante que termine TLS. Sin
panel, publica ese puerto solo a un proxy propio con TLS (otro Caddy, Traefik, nginx) que
reenvíe todo el dominio a `caddy:80` **y ponga `X-Forwarded-Proto: https` y
`X-Forwarded-Host` con el dominio**: el Caddy interno ya no las escribe, las conserva del
proxy frontal, y sin ellas el SSR renderizaría URLs absolutas en `http`. Un `proxy_pass`
de nginx por defecto no las añade.

Los servicios `migrate`, `api`, `worker` y `scheduler` leen su configuración por
`environment:` con interpolación `${VAR}`, no por `env_file:` — así el fichero no tiene
que existir dentro del *checkout* que hace el orquestador (Dokploy, o cualquier CI que
clona el repo y construye ahí mismo), solo en el entorno con el que se invoca `docker
compose`. En el flujo manual eso sigue siendo `infra/env/.env` vía `--env-file`, igual
que antes; un orquestador como Dokploy pasa esas mismas variables por su propio panel de
entorno, sin tocar el checkout.

Los servicios `migrate`, `api`, `worker` y `scheduler` leen su configuración por
`environment:` con interpolación `${VAR}`, no por `env_file:` — así el fichero no tiene
que existir dentro del *checkout* que hace el orquestador (Dokploy, o cualquier CI que
clona el repo y construye ahí mismo), solo en el entorno con el que se invoca `docker
compose`. En el flujo manual eso sigue siendo `infra/env/.env` vía `--env-file`, igual
que antes; un orquestador como Dokploy pasa esas mismas variables por su propio panel de
entorno, sin tocar el checkout.

## Actualización

En EasyPanel: cambia la etiqueta de imagen de `api`, `worker`, `scheduler` y `web` a
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

En EasyPanel: vuelve a poner la etiqueta anterior en `api`, `worker`, `scheduler` y `web`
y despliega. Con Compose:

```bash
sed -i 's/^IMAGE_TAG=.*/IMAGE_TAG=sha-<commit-anterior>/' infra/env/.env
docker compose --env-file infra/env/.env -f infra/docker-compose.prod.yml up -d --force-recreate api worker scheduler web
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
y añade una entrada nueva abajo (no sustituyas esta).

### Revalidación — 2026-09-07 + esquema fase 5 del PRD (2026-09-08)

**Ejecutada el 2026-09-08** contra el esquema ampliado por la fase 5 del PRD
(`sponsor_tiers`, `sponsors`, `audit_log`, `cookie_consents`), en el entorno de
desarrollo (`infra/docker-compose.yml`, sin tocar el stack de producción).

**Corrección previa de `restore.sh`.** El script solo sabía restaurar sobre el
proyecto `docker-compose.prod.yml`: no creaba la base de destino si no existía, paraba
siempre `api`/`worker` y reaplicaba `roles.sql` (que rota las contraseñas de los roles
del **clúster entero**, no solo de la base de destino). Ninguna de las tres cosas es
aceptable para una restauración de prueba aislada. Se añadió el modo
`RESTAURACION_AISLADA=1` (aditivo, sin tocar el camino por defecto): crea la base de
datos de destino si no existe, omite parar/arrancar `api`/`worker`, y omite reaplicar
`roles.sql`. El script rechaza explícitamente `RESTAURACION_AISLADA=1` con
`POSTGRES_DB=ia_week` (la base de producción), para que el modo aislado no pueda
apuntar a producción por un `POSTGRES_DB` olvidado. La misma guarda existe para el
bucket de objetos: `RESTAURACION_AISLADA=1` con `S3_BUCKET` sin definir o
`S3_BUCKET=media` (el bucket de producción) aborta antes de tocar nada, para que un
`S3_BUCKET` olvidado no sobrescriba el bucket real durante una restauración de prueba.
Verificado manualmente el 2026-09-08: con `S3_BUCKET` sin definir y con
`S3_BUCKET=media` el script aborta con el mensaje esperado sin llegar a crear la base
de datos ni invocar `docker compose`; con `S3_BUCKET=media-restore-test` la guarda deja
pasar la ejecución con normalidad. De paso se corrigió un bug latente
de la confirmación interactiva (`«$POSTGRES_DB»` inmediatamente pegado a la variable
rompía el `set -u` de Bash con el carácter multibyte de la comilla angular — reproducible
con `bash -c 'set -u; V=x; echo "«$V»"'`), presente también en el camino por defecto.

Procedimiento:

1. Siembra de datos reales en la base de desarrollo (`ia_week`): organización, evento
   con portada subida a SeaweedFS, un `sponsor_tier`, un `sponsor` con logo subido, una
   inscripción `confirmed` con su entrada (`event_tickets`), un `cookie_consents` y una
   fila de `audit_log`.
2. `infra/scripts/backup.sh` contra `ia_week` (`COMPOSE` apuntando al compose de
   desarrollo, `COMPOSE_NETWORK=ia-week_default`): vuelca PostgreSQL y sincroniza el
   bucket `media` completo a un directorio local.
3. `RESTAURACION_AISLADA=1 POSTGRES_DB=ia_week_restore_test S3_BUCKET=media-restore-test
   infra/scripts/restore.sh <volcado> <objetos> --si-estoy-seguro`, contra una base de
   datos y un bucket nombrados explícitamente para la prueba (nunca `ia_week` ni
   `ia_week_test`).
4. Recuento de filas por tabla entre `ia_week` e `ia_week_restore_test`.
5. Comprobación uno a uno (`s3api head-object`) de cada `cover_object_key`/
   `logo_object_key` de las filas restauradas contra el bucket `media-restore-test`.

**Resultado:** recuento de filas idéntico en las 8 tablas clave (`organizations`: 5,
`events`: 4, `event_registrations`: 1, `event_tickets`: 1, `sponsor_tiers`: 1,
`sponsors`: 1, `audit_log`: 1, `cookie_consents`: 2 — origen y restaurada coinciden
exactamente en las ocho). Los tres objetos referenciados (dos portadas de evento y un
logo de patrocinador) existen en el bucket restaurado, verificados individualmente con
`head-object`, no solo por la ausencia de error de `aws s3 sync`. `/api/v1/health` del
entorno de desarrollo respondió `200` de forma continua durante toda la prueba: en
ningún momento se paró `api`, `worker` ni ningún otro servicio.

Un hallazgo del entorno, no del código: la primera ejecución del `s3 sync` de
restauración falló con `InternalError` en todos los objetos porque el SeaweedFS de
desarrollo tiene `-volume.max=10` y ya estaba en `Free: 0` (los volúmenes del bucket
`media` de meses de uso de desarrollo agotaron el cupo) — una colección S3 nueva
(`media-restore-test`) no tenía dónde alojar su primer volumen. Se subió temporalmente
a `-volume.max=30`, se recreó solo el contenedor `seaweedfs` (sin afectar a `postgres`,
`api`, `worker` ni `web`), se repitió la prueba de punta a punta con éxito, y se
revirtió `-volume.max` a 10 al terminar (`git diff infra/docker-compose.yml` limpio).
Esto no es un defecto de `restore.sh`: en un servidor de producción real el bucket ya
tiene cupo de volúmenes acorde a su uso real, y el propio mensaje de error de SeaweedFS
(`InternalError`, sin detalle) es lo primero a mirar si esta prueba vuelve a fallar así.

Datos de prueba y bucket de prueba eliminados tras la verificación
(`DROP DATABASE ia_week_restore_test`, `s3 rb s3://media-restore-test --force`); las
filas sembradas en `ia_week` para la prueba también se retiraron para no dejar datos
ficticios en el entorno de desarrollo compartido.

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

# Rotar las contraseñas de los roles de base de datos
POSTGRES_APP_USER_PASSWORD=... POSTGRES_MAINTAINER_PASSWORD=... \
  infra/scripts/ensure-roles.sh "postgresql://postgres:...@localhost:5432/ia_week"
# y actualiza DATABASE_URL y DATABASE_MIGRATIONS_URL en infra/env/.env
```

## Varias organizaciones: una sola instalación, un solo dominio

Sin dominio por organización (plan «organización sin dominio», 2026-09-14), todas
las organizaciones viven bajo el mismo dominio de la instalación. La organización
activa la decide la sesión (claim `org` del access token, cambiable con
`POST /auth/switch-organization`), y las páginas públicas resuelven cada recurso
por su propio slug — nunca por el host. No hay DNS comodín, ni certificado
comodín, ni `DOMINIO_BASE`, ni `add-domain`: el despliegue es el de un único
sitio.

Dar de alta una organización no toca el despliegue: por CLI (`python -m app.cli
create-organization mi-org "Mi Organización"`), por superadmin desde el panel, o
por el alta libre de la propia aplicación (`POST /organizations`, que además deja
la sesión activa en la organización recién creada). El identificador interno
(`slug`) se genera a partir del nombre; no aparece en ninguna URL pública.

Quien quiera una instalación aparte hace fork del repositorio y la despliega.

## Variables de entorno

Todas están documentadas en `infra/env/.env.example`. Las que solo aplican a producción:

| Variable | Para qué |
|---|---|
| `IMAGE_TAG` | Imagen a desplegar (`sha-<commit>`), solo con Docker Compose |
| `NG_ALLOWED_HOSTS` | Hosts que acepta el SSR; vacío = cualquiera |
| `API_INTERNAL_URL` | URL de la API en la red interna, para el SSR |
| `GITHUB_REPOSITORY` | Origen de las imágenes en GHCR |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_USE_TLS`, `SMTP_FROM` | Proveedor de correo real para la verificación de cuentas. Mailpit solo existe en desarrollo |
| `TURNSTILE_ENABLED`, `TURNSTILE_SECRET_KEY` | Anti-bot en el registro, el reenvío de verificación y el alta de organización. **`TURNSTILE_ENABLED` no puede ser `false` en producción**: el arranque de la API falla si lo es |
| `AI_SETTINGS_ENCRYPTION_KEY` | Clave Fernet con la que se cifran en reposo las claves de los proveedores de IA. Opcional: sin ella la instalación arranca y funciona, pero no se puede guardar ninguna configuración de IA. Ver abajo |

### Pasarela de IA: cifrado y orden de despliegue

La configuración de IA vive en la base de datos (proveedor, modelo, techo de gasto
y clave del proveedor **cifrada**), no en variables de entorno. La única variable
es la clave de cifrado:

```bash
# Genera la clave (una sola vez por instalación)
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
AI_SETTINGS_ENCRYPTION_KEY=<la clave generada>
```

Orden de despliegue de la configuración de plataforma:

1. fija `AI_SETTINGS_ENCRYPTION_KEY` en `api`, `worker` y `scheduler` (las tres
   la necesitan: el worker también resuelve credenciales) y arranca. Un formato
   inválido **impide arrancar**, a propósito, en vez de fallar al guardar;
2. entra como superadministrador y guarda la configuración de plataforma en
   `PUT /api/v1/admin/ai-settings`: proveedor, modelo, clave y techo de gasto.
   La clave no se puede volver a leer nunca — el panel solo muestra sus últimos
   caracteres;
3. opcionalmente, cada organización sobrescribe la suya con su propia clave y su
   límite, que nunca puede superar el techo de la plataforma.

Rotación de la clave de cifrado (parada corta; la clave es de aplicación, así que
rotarla obliga a re-cifrar todas las filas):

```bash
# 1. Para api, worker y scheduler
# 2. Re-cifra con la clave antigua y la nueva
python -m app.cli rotate-ai-encryption-key --old-key <antigua> --new-key <nueva>
# 3. Cambia AI_SETTINGS_ENCRYPTION_KEY por la nueva y vuelve a arrancar
```

Sin la variable, guardar una configuración de IA devuelve un error explícito
(`cifrado_no_configurado`) y el resto de la plataforma funciona con normalidad.

La clave pública de Turnstile (`turnstileSiteKey`) no es un secreto de la API: se
compila en el bundle del frontend (`apps/web/src/environments/environment.ts`) antes de
construir la imagen de producción.
