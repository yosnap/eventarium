#!/usr/bin/env bash
# Reaplica los roles de aplicación sobre una base de datos ya existente.
# El script de init solo corre con el volumen vacío; en producción o tras un cambio de
# contraseña se usa este comando.
#
#   POSTGRES_APP_USER_PASSWORD=... POSTGRES_MAINTAINER_PASSWORD=... \
#     infra/scripts/ensure-roles.sh postgresql://postgres:pass@localhost:5432/ia_week
set -euo pipefail

DSN="${1:-${POSTGRES_SUPERUSER_URL:-}}"
if [ -z "$DSN" ]; then
  echo "Uso: ensure-roles.sh <DSN de superusuario>" >&2
  exit 2
fi

: "${POSTGRES_APP_USER_PASSWORD:?falta POSTGRES_APP_USER_PASSWORD}"
: "${POSTGRES_MAINTAINER_PASSWORD:?falta POSTGRES_MAINTAINER_PASSWORD}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DBNAME="$(basename "${DSN%%\?*}")"

psql "$DSN" \
  --set ON_ERROR_STOP=1 \
  --set "app_user_password=$POSTGRES_APP_USER_PASSWORD" \
  --set "maintainer_password=$POSTGRES_MAINTAINER_PASSWORD" \
  --set "dbname=$DBNAME" \
  --file "$SCRIPT_DIR/../postgres/sql/roles.sql"

echo "Roles app_user y app_maintainer verificados en $DBNAME."
