#!/usr/bin/env bash
# Restauración de una copia de seguridad.
#
#   infra/scripts/restore.sh backups/postgres-20260907-013000.dump [backups/objetos-...]
#
# Destruye el contenido actual de la base de datos indicada. Pide confirmación salvo
# que se pase --si-estoy-seguro.
#
# Modo de restauración aislada (RESTAURACION_AISLADA=1): pensado para revalidar la
# restauración contra una base de datos de prueba, nunca contra producción. En este
# modo el script:
#   - crea la base de datos de destino si no existe (`pg_restore -d` no lo hace);
#   - NO para/arranca los servicios `api`/`worker` (no son ese destino, nadie escribe
#     en él salvo esta prueba);
#   - NO reaplica `roles.sql`, que incluye `ALTER ROLE ... PASSWORD` y rotaría las
#     contraseñas de los roles del clúster entero, no solo de la base de prueba.
# El comportamiento por defecto (`RESTAURACION_AISLADA` sin definir o "0") es
# exactamente el de siempre, sin ninguna rama nueva.
set -euo pipefail

VOLCADO="${1:?Uso: restore.sh <fichero.dump> [directorio-de-objetos]}"
OBJETOS="${2:-}"
COMPOSE="${COMPOSE:-docker compose --env-file infra/env/.env -f infra/docker-compose.prod.yml}"
RESTAURACION_AISLADA="${RESTAURACION_AISLADA:-0}"

: "${POSTGRES_DB:=ia_week}"
: "${POSTGRES_SUPERUSER:=postgres}"
: "${POSTGRES_SUPERUSER_PASSWORD:?falta POSTGRES_SUPERUSER_PASSWORD}"

[ -s "$VOLCADO" ] || { echo "El fichero $VOLCADO no existe o está vacío." >&2; exit 1; }

if [ "$RESTAURACION_AISLADA" = "1" ] && [ "$POSTGRES_DB" = "ia_week" ]; then
	echo "RESTAURACION_AISLADA=1 con POSTGRES_DB=ia_week (la base de producción)." >&2
	echo "El modo aislado exige un POSTGRES_DB de prueba explícito, nunca la base real." >&2
	exit 1
fi

if [ "${3:-}" != "--si-estoy-seguro" ] && [ "${2:-}" != "--si-estoy-seguro" ]; then
	echo "Se va a SOBRESCRIBIR la base de datos «${POSTGRES_DB}» con $VOLCADO."
	printf 'Escribe «restaurar» para continuar: '
	read -r respuesta
	[ "$respuesta" = "restaurar" ] || { echo "Cancelado."; exit 1; }
fi

if [ "$RESTAURACION_AISLADA" = "1" ]; then
	echo "→ Modo aislado: creando «${POSTGRES_DB}» si no existe (sin tocar servicios de producción)"
	existe="$($COMPOSE exec -T -e PGPASSWORD="$POSTGRES_SUPERUSER_PASSWORD" postgres \
		psql -U "$POSTGRES_SUPERUSER" -d postgres -tA -c \
		"SELECT 1 FROM pg_database WHERE datname = '$POSTGRES_DB'")"
	if [ "$existe" != "1" ]; then
		$COMPOSE exec -T -e PGPASSWORD="$POSTGRES_SUPERUSER_PASSWORD" postgres \
			psql -U "$POSTGRES_SUPERUSER" -d postgres -v ON_ERROR_STOP=1 -c \
			"CREATE DATABASE \"$POSTGRES_DB\""
	fi
else
	echo "→ Parando api y worker para que nadie escriba durante la restauración"
	$COMPOSE stop api worker || true
fi

echo "→ Restaurando $VOLCADO"
# --clean --if-exists deja la base en el estado del volcado, sin restos anteriores.
#
# Se conserva la propiedad de los objetos (sin --no-owner): las tablas pertenecen a
# app_maintainer y, si se restauran a nombre del superusuario, ese rol pierde el acceso
# y las migraciones fallan con «permission denied for table alembic_version».
$COMPOSE exec -T -e PGPASSWORD="$POSTGRES_SUPERUSER_PASSWORD" postgres \
	pg_restore -U "$POSTGRES_SUPERUSER" -d "$POSTGRES_DB" --clean --if-exists < "$VOLCADO"

if [ "$RESTAURACION_AISLADA" = "1" ]; then
	echo "→ Modo aislado: se omite reaplicar roles.sql (no se rotan contraseñas del clúster)"
else
	echo "→ Reaplicando los roles y sus privilegios"
	POSTGRES_APP_USER_PASSWORD="${POSTGRES_APP_USER_PASSWORD:?falta POSTGRES_APP_USER_PASSWORD}" \
	POSTGRES_MAINTAINER_PASSWORD="${POSTGRES_MAINTAINER_PASSWORD:?falta POSTGRES_MAINTAINER_PASSWORD}" \
		$COMPOSE exec -T -e PGPASSWORD="$POSTGRES_SUPERUSER_PASSWORD" postgres \
		psql -U "$POSTGRES_SUPERUSER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 \
		-v app_user_password="$POSTGRES_APP_USER_PASSWORD" \
		-v maintainer_password="$POSTGRES_MAINTAINER_PASSWORD" \
		-v dbname="$POSTGRES_DB" \
		-f /opt/postgres-sql/roles.sql
fi

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

if [ "$RESTAURACION_AISLADA" = "1" ]; then
	echo "→ Modo aislado: no se arrancan servicios (nunca se pararon)"
else
	echo "→ Arrancando api y worker"
	$COMPOSE start api worker
fi

echo "Restauración completada. Comprueba /api/v1/health antes de dar por buena la operación."
