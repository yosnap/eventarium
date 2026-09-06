#!/usr/bin/env bash
# Restauración de una copia de seguridad.
#
#   infra/scripts/restore.sh backups/postgres-20260907-013000.dump [backups/objetos-...]
#
# Destruye el contenido actual de la base de datos indicada. Pide confirmación salvo
# que se pase --si-estoy-seguro.
set -euo pipefail

VOLCADO="${1:?Uso: restore.sh <fichero.dump> [directorio-de-objetos]}"
OBJETOS="${2:-}"
COMPOSE="${COMPOSE:-docker compose --env-file infra/env/.env -f infra/docker-compose.prod.yml}"

: "${POSTGRES_DB:=ia_week}"
: "${POSTGRES_SUPERUSER:=postgres}"
: "${POSTGRES_SUPERUSER_PASSWORD:?falta POSTGRES_SUPERUSER_PASSWORD}"

[ -s "$VOLCADO" ] || { echo "El fichero $VOLCADO no existe o está vacío." >&2; exit 1; }

if [ "${3:-}" != "--si-estoy-seguro" ] && [ "${2:-}" != "--si-estoy-seguro" ]; then
	echo "Se va a SOBRESCRIBIR la base de datos «$POSTGRES_DB» con $VOLCADO."
	printf 'Escribe «restaurar» para continuar: '
	read -r respuesta
	[ "$respuesta" = "restaurar" ] || { echo "Cancelado."; exit 1; }
fi

echo "→ Parando api y worker para que nadie escriba durante la restauración"
$COMPOSE stop api worker || true

echo "→ Restaurando $VOLCADO"
# --clean --if-exists deja la base en el estado del volcado, sin restos anteriores.
#
# Se conserva la propiedad de los objetos (sin --no-owner): las tablas pertenecen a
# app_maintainer y, si se restauran a nombre del superusuario, ese rol pierde el acceso
# y las migraciones fallan con «permission denied for table alembic_version».
$COMPOSE exec -T -e PGPASSWORD="$POSTGRES_SUPERUSER_PASSWORD" postgres \
	pg_restore -U "$POSTGRES_SUPERUSER" -d "$POSTGRES_DB" --clean --if-exists < "$VOLCADO"

echo "→ Reaplicando los roles y sus privilegios"
POSTGRES_APP_USER_PASSWORD="${POSTGRES_APP_USER_PASSWORD:?falta POSTGRES_APP_USER_PASSWORD}" \
POSTGRES_MAINTAINER_PASSWORD="${POSTGRES_MAINTAINER_PASSWORD:?falta POSTGRES_MAINTAINER_PASSWORD}" \
	$COMPOSE exec -T -e PGPASSWORD="$POSTGRES_SUPERUSER_PASSWORD" postgres \
	psql -U "$POSTGRES_SUPERUSER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 \
	-v app_user_password="$POSTGRES_APP_USER_PASSWORD" \
	-v maintainer_password="$POSTGRES_MAINTAINER_PASSWORD" \
	-v dbname="$POSTGRES_DB" \
	-f /opt/postgres-sql/roles.sql

if [ -n "$OBJETOS" ] && [ -d "$OBJETOS" ]; then
	echo "→ Restaurando los objetos desde $OBJETOS"
	docker run --rm \
		--network "${COMPOSE_NETWORK:-eventarium_default}" \
		-v "$(cd "$OBJETOS" && pwd)":/copia:ro \
		-e AWS_ACCESS_KEY_ID="${S3_ACCESS_KEY:?falta S3_ACCESS_KEY}" \
		-e AWS_SECRET_ACCESS_KEY="${S3_SECRET_KEY:?falta S3_SECRET_KEY}" \
		-e AWS_DEFAULT_REGION="${S3_REGION:-us-east-1}" \
		amazon/aws-cli:2.31.9 \
		--endpoint-url "${S3_ENDPOINT:-http://seaweedfs:8333}" \
		s3 sync /copia "s3://${S3_BUCKET:-media}"
fi

echo "→ Arrancando api y worker"
$COMPOSE start api worker

echo "Restauración completada. Comprueba /api/v1/health antes de dar por buena la operación."
