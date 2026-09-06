#!/usr/bin/env bash
# Copia de seguridad: volcado de PostgreSQL y sincronización del bucket de objetos.
#
# Un backup que no se ha restaurado nunca no es un backup. El procedimiento de
# restauración está en restore.sh y su prueba se documenta en docs/despliegue.md.
#
#   DESTINO=/var/backups/eventarium infra/scripts/backup.sh
set -euo pipefail

DESTINO="${DESTINO:-./backups}"
FECHA="$(date +%Y%m%d-%H%M%S)"
RETENCION_DIAS="${RETENCION_DIAS:-14}"
COMPOSE="${COMPOSE:-docker compose --env-file infra/env/.env -f infra/docker-compose.prod.yml}"

: "${POSTGRES_DB:=ia_week}"
: "${POSTGRES_SUPERUSER:=postgres}"
: "${POSTGRES_SUPERUSER_PASSWORD:?falta POSTGRES_SUPERUSER_PASSWORD}"

mkdir -p "$DESTINO"

VOLCADO="$DESTINO/postgres-$FECHA.dump"
echo "→ Volcando $POSTGRES_DB en $VOLCADO"
# Formato custom (-Fc): permite restaurar tablas sueltas y va comprimido.
$COMPOSE exec -T -e PGPASSWORD="$POSTGRES_SUPERUSER_PASSWORD" postgres \
	pg_dump -U "$POSTGRES_SUPERUSER" -d "$POSTGRES_DB" -Fc > "$VOLCADO"

if [ ! -s "$VOLCADO" ]; then
	echo "El volcado está vacío: se aborta sin borrar copias antiguas." >&2
	exit 1
fi

OBJETOS="$DESTINO/objetos-$FECHA"
mkdir -p "$OBJETOS"
echo "→ Sincronizando el bucket en $OBJETOS"
# El cliente S3 se ejecuta dentro de la red de Compose: así usa el mismo endpoint
# interno que la API y no hace falta exponer SeaweedFS al exterior ni instalar
# aws-cli en el servidor.
docker run --rm \
	--network "${COMPOSE_NETWORK:-eventarium_default}" \
	-v "$(cd "$OBJETOS" && pwd)":/copia \
	-e AWS_ACCESS_KEY_ID="${S3_ACCESS_KEY:?falta S3_ACCESS_KEY}" \
	-e AWS_SECRET_ACCESS_KEY="${S3_SECRET_KEY:?falta S3_SECRET_KEY}" \
	-e AWS_DEFAULT_REGION="${S3_REGION:-us-east-1}" \
	amazon/aws-cli:2.31.9 \
	--endpoint-url "${S3_ENDPOINT:-http://seaweedfs:8333}" \
	s3 sync "s3://${S3_BUCKET:-media}" /copia

echo "→ Eliminando copias de más de $RETENCION_DIAS días"
find "$DESTINO" -maxdepth 1 -name 'postgres-*.dump' -mtime "+$RETENCION_DIAS" -delete
find "$DESTINO" -maxdepth 1 -type d -name 'objetos-*' -mtime "+$RETENCION_DIAS" -exec rm -rf {} +

echo "Copia completada: $VOLCADO"
