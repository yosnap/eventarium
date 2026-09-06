#!/bin/sh
# Crea los roles de aplicación en el primer arranque del contenedor de PostgreSQL.
# El SQL vive fuera de /docker-entrypoint-initdb.d para que el entrypoint no intente
# ejecutarlo sin las variables psql necesarias.
set -eu

: "${POSTGRES_APP_USER_PASSWORD:?falta POSTGRES_APP_USER_PASSWORD}"
: "${POSTGRES_MAINTAINER_PASSWORD:?falta POSTGRES_MAINTAINER_PASSWORD}"

psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  --set ON_ERROR_STOP=1 \
  --set "app_user_password=$POSTGRES_APP_USER_PASSWORD" \
  --set "maintainer_password=$POSTGRES_MAINTAINER_PASSWORD" \
  --set "dbname=$POSTGRES_DB" \
  --file /opt/postgres-sql/roles.sql
