#!/bin/sh
# Migra la base de datos del PostgreSQL 16 al 18 copiando de servidor a servidor.
#
# Se ejecuta DENTRO del contenedor del Postgres nuevo (`postgres18`), que alcanza al
# viejo (`postgres`) por la red del compose. Así no depende de `infra/env/.env`, del
# nombre del proyecto ni de la red, y funciona igual con `docker exec` en local que
# con una tarea de Dokploy (que ejecuta un `docker exec` sobre un servicio):
#
#   docker exec -i -e CONFIRMO_MIGRAR=si <contenedor-postgres18> sh -s < infra/scripts/upgrade-postgres.sh
#
# Solo ESCRIBE en el servidor nuevo; el viejo se lee y no se toca. Antes hay que parar
# `api`, `worker` y `scheduler` para que nadie escriba durante la copia.
#
# Pasos: comprueba que el destino es la 18 y está vacío → compara codificación y
# ordenación → crea los roles con `roles.sql` → copia con pg_dump | pg_restore en una
# sola transacción y abortando al primer error → ANALYZE → compara tabla a tabla y termina con error si algo no coincide.
#
# Variables (las del propio contenedor, salvo las marcadas):
#   POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB     del contenedor nuevo
#   POSTGRES_APP_USER_PASSWORD, POSTGRES_MAINTAINER_PASSWORD
#   CONFIRMO_MIGRAR=si      (obligatoria)
#   ORIGEN_HOST             servidor viejo (por defecto `postgres`)
#   ROLES_SQL               ruta de roles.sql (por defecto /opt/postgres-sql/roles.sql
#                           y, si no existe, /tmp/roles.sql: en Dokploy el bind llega vacío)
set -eu

: "${POSTGRES_USER:?falta POSTGRES_USER}"
: "${POSTGRES_PASSWORD:?falta POSTGRES_PASSWORD}"
: "${POSTGRES_DB:?falta POSTGRES_DB}"
: "${POSTGRES_APP_USER_PASSWORD:?falta POSTGRES_APP_USER_PASSWORD}"
: "${POSTGRES_MAINTAINER_PASSWORD:?falta POSTGRES_MAINTAINER_PASSWORD}"
ORIGEN_HOST="${ORIGEN_HOST:-postgres}"
BASE="$POSTGRES_DB"

if [ "${CONFIRMO_MIGRAR:-}" != "si" ]; then
	echo "Pon CONFIRMO_MIGRAR=si para continuar (escribe en este servidor, no en el de origen)." >&2
	exit 1
fi

if [ -z "${ROLES_SQL:-}" ]; then
	if [ -s /opt/postgres-sql/roles.sql ]; then
		ROLES_SQL=/opt/postgres-sql/roles.sql
	else
		ROLES_SQL=/tmp/roles.sql
	fi
fi
[ -s "$ROLES_SQL" ] || { echo "No existe $ROLES_SQL: déjalo en el contenedor antes de migrar." >&2; exit 1; }

# `psql -h` contra el origen necesita contraseña; contra el socket local no.
# Con la opción `-w` no se pregunta nunca, se falla.
destino() { psql -w -U "$POSTGRES_USER" -d "$BASE" -v ON_ERROR_STOP=1 -X "$@"; }
origen() { PGPASSWORD="$POSTGRES_PASSWORD" psql -w -h "$ORIGEN_HOST" -U "$POSTGRES_USER" -d "$BASE" -v ON_ERROR_STOP=1 -X "$@"; }
aplicar_roles() {
	destino -q \
		-v app_user_password="$POSTGRES_APP_USER_PASSWORD" \
		-v maintainer_password="$POSTGRES_MAINTAINER_PASSWORD" \
		-v dbname="$BASE" \
		-f "$ROLES_SQL"
}

echo "→ Comprobando servidores"
version_destino="$(destino -Atc "show server_version_num")"
version_origen="$(origen -Atc "show server_version_num")"
[ "$version_destino" -ge 180000 ] || { echo "El destino no es PostgreSQL 18 ($version_destino)." >&2; exit 1; }
[ "$version_origen" -lt 180000 ] || { echo "El origen ya es 18 ($version_origen): nada que migrar." >&2; exit 1; }
[ "$(origen -Atc "select pg_is_in_recovery()")" = "f" ] || { echo "El origen está en recuperación." >&2; exit 1; }
tablas_destino="$(destino -Atc "select count(*) from pg_tables where schemaname not in ('pg_catalog','information_schema')")"
[ "$tablas_destino" = "0" ] || { echo "El destino ya tiene $tablas_destino tablas: se niega a sobrescribirlas." >&2; exit 1; }
echo "   origen $version_origen → destino $version_destino (la base «$BASE» del destino está vacía)"

otras="$(origen -Atc "select count(*) from pg_stat_activity where datname = current_database() and pid <> pg_backend_pid() and backend_type = 'client backend'")"
[ "$otras" = "0" ] || { echo "Hay $otras conexiones abiertas en el origen: para api, worker y scheduler antes de migrar." >&2; exit 1; }

echo "→ Comparando codificación y ordenación"
regional="select datcollate||' | '||datctype||' | '||pg_encoding_to_char(encoding)||' | '||datlocprovider::text from pg_database where datname = current_database()"
regional_origen="$(origen -Atc "$regional")"
regional_destino="$(destino -Atc "$regional")"
echo "   origen : $regional_origen"
echo "   destino: $regional_destino"
# Solo se exige que collate, ctype y codificación coincidan; el proveedor se muestra.
[ "$(echo "$regional_origen" | cut -d'|' -f1-3)" = "$(echo "$regional_destino" | cut -d'|' -f1-3)" ] \
	|| { echo "La ordenación o la codificación no coinciden: pueden romper índices de texto." >&2; exit 1; }

echo "→ Creando roles y privilegios (roles.sql)"
aplicar_roles

echo "→ Copiando con pg_dump | pg_restore (una transacción, aborta al primer error)"
# Primero a un fichero y luego a la base: `sh` no tiene `pipefail` y un fallo del
# volcado quedaría oculto dentro de una tubería. El fichero lleva datos personales:
# se borra al terminar, también con Ctrl-C o si la tarea se mata
# (salvo `SIGKILL`, que ningún script puede atrapar).
VOLCADO="$(mktemp /tmp/migracion.XXXXXX)"
trap 'rm -f "$VOLCADO"' EXIT
trap 'rm -f "$VOLCADO"; exit 130' INT TERM HUP
PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -w -h "$ORIGEN_HOST" -U "$POSTGRES_USER" -d "$BASE" -Fc -f "$VOLCADO"
pg_restore -w -U "$POSTGRES_USER" -d "$BASE" --exit-on-error --single-transaction "$VOLCADO"

# NO se reaplica roles.sql tras restaurar: su `GRANT ... ON ALL TABLES TO app_user` devolvería
# permisos de escritura a tablas a las que las migraciones se los quitaron a propósito
# (catálogos, auditoría). Los privilegios de tablas viajan en el volcado tal cual estaban.

echo "→ ANALYZE (el volcado no trae las estadísticas del planificador)"
destino -q -c "ANALYZE"

echo "→ Comparando origen y destino"
fallos=0
tablas="$(origen -Atc "select tablename from pg_tables where schemaname='public' order by 1")"
for tabla in $tablas; do
	a="$(origen -Atc "select count(*) from public.\"$tabla\"")"
	b="$(destino -Atc "select count(*) from public.\"$tabla\"")"
	if [ "$a" != "$b" ]; then
		echo "   DIFERENTE public.$tabla: origen=$a destino=$b" >&2
		fallos=$((fallos + 1))
	fi
done
[ -n "$tablas" ] || { echo "El origen no tiene tablas en public: algo va mal." >&2; exit 1; }
echo "   tablas comparadas: $(echo "$tablas" | wc -l | tr -d ' ')"

comparar() { # descripción, consulta
	a="$(origen -Atc "$2")"
	b="$(destino -Atc "$2")"
	if [ "$a" = "$b" ]; then
		echo "   igual  $1: $a"
	else
		echo "   DIFERENTE $1: origen=[$a] destino=[$b]" >&2
		fallos=$((fallos + 1))
	fi
}
comparar "revisión de Alembic" "select coalesce(string_agg(version_num, ','), 'ninguna') from alembic_version"
comparar "políticas RLS" "select count(*) from pg_policies"
comparar "funciones SECURITY DEFINER" "select count(*) from pg_proc p join pg_namespace n on n.oid = p.pronamespace where p.prosecdef and n.nspname = 'public'"
comparar "tablas con RLS forzada" "select count(*) from pg_class where relforcerowsecurity and relnamespace = 'public'::regnamespace"
comparar "índices" "select count(*) from pg_indexes where schemaname = 'public'"
comparar "secuencias y sus valores" "select coalesce(string_agg(sequencename||':'||coalesce(last_value::text, '-'), ',' order by sequencename), 'ninguna') from pg_sequences where schemaname = 'public'"
comparar "atributos de los roles" "select string_agg(rolname||':'||rolsuper::int||rolbypassrls::int||rolcanlogin::int||rolcreatedb::int||rolcreaterole::int, ',' order by rolname) from pg_roles where rolname in ('app_user','app_maintainer')"
comparar "propietario del esquema public" "select nspowner::regrole::text from pg_namespace where nspname = 'public'"
comparar "privilegios de la base" "select coalesce(datacl::text, 'sin-acl') from pg_database where datname = current_database()"
comparar "privilegios por defecto" "select count(*) from pg_default_acl"
# PostgreSQL 17 añadió el privilegio MAINTAIN (letra `m`): el propietario lo recibe en la 18 y no
# en la 16. Se ignora esa letra; el resto de privilegios tiene que coincidir exactamente.
comparar "privilegios de tablas y secuencias" "select md5(coalesce(string_agg(c.relname || ':' || coalesce((select string_agg(regexp_replace(x::text, '=([A-Za-z*]*)m([A-Za-z*]*)/', '=\\1\\2/'), ',' order by x::text) from unnest(c.relacl) x), '-'), '|' order by c.relname), '')) from pg_class c where c.relnamespace = 'public'::regnamespace and c.relkind in ('r','S','v','m','p')"
comparar "privilegios de funciones" "select md5(coalesce(string_agg(p.proname || ':' || coalesce((select string_agg(x::text, ',' order by x::text) from unnest(p.proacl) x), '-'), '|' order by p.proname, p.oid::text), '')) from pg_proc p where p.pronamespace = 'public'::regnamespace"
comparar "app_user puede escribir en event_categories" "select has_table_privilege('app_user', 'public.event_categories', 'INSERT')::text" 
comparar "propietarios de tablas" "select string_agg(distinct tableowner, ',') from pg_tables where schemaname = 'public'"

if [ "$fallos" -ne 0 ]; then
	echo "✗ $fallos diferencias: NO se corta. El servidor de origen sigue intacto." >&2
	exit 1
fi
echo "✓ Migración verificada: datos, roles y privilegios coinciden."
