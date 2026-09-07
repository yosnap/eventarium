#!/usr/bin/env bash
# Arranque del entorno de desarrollo.
#
#   infra/scripts/dev.sh all       API + worker + web, con los logs entremezclados
#   infra/scripts/dev.sh api       solo la API
#   infra/scripts/dev.sh web       solo el frontend
#   infra/scripts/dev.sh worker    solo el worker de tareas
#   infra/scripts/dev.sh stop      libera todos los puertos del proyecto
#   infra/scripts/dev.sh status    qué hay escuchando en cada puerto
#
# Antes de arrancar, cada puerto se libera. Es deliberado: un dev server olvidado de
# una sesión anterior deja el puerto ocupado, y la alternativa habitual —arrancar en
# otro puerto -– acaba con varios procesos zombis y una cookie que no viaja porque el
# host ya no coincide.
#
# Solo se matan procesos que escuchan en los puertos de este proyecto, nunca por
# nombre: un `pkill node` se llevaría por delante trabajo ajeno.
set -euo pipefail

RAIZ="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$RAIZ"

FICHERO_ENV="infra/env/.env"
PUERTO_API="${API_PORT:-8000}"
PUERTO_WEB="${WEB_DEV_PORT:-4200}"

if [ -f "$FICHERO_ENV" ]; then
	# shellcheck disable=SC1090
	set -a && . "$FICHERO_ENV" && set +a
fi
PUERTO_CADDY="${WEB_PORT:-8080}"

rojo() { printf '\033[31m%s\033[0m\n' "$*"; }
verde() { printf '\033[32m%s\033[0m\n' "$*"; }
azul() { printf '\033[36m%s\033[0m\n' "$*"; }

# ---------------------------------------------------------------------- puertos

liberar_puerto() {
	local puerto="$1" etiqueta="$2" pids
	pids="$(lsof -ti "tcp:$puerto" -sTCP:LISTEN 2>/dev/null || true)"
	[ -z "$pids" ] && return 0

	for pid in $pids; do
		local comando
		comando="$(ps -p "$pid" -o comm= 2>/dev/null || echo desconocido)"
		azul "  puerto $puerto ($etiqueta) ocupado por $comando [$pid]: se cierra"
		kill "$pid" 2>/dev/null || true
	done

	# Se da margen para que cierre limpio antes de insistir.
	for _ in 1 2 3 4 5 6 7 8 9 10; do
		sleep 0.3
		[ -z "$(lsof -ti "tcp:$puerto" -sTCP:LISTEN 2>/dev/null || true)" ] && return 0
	done

	for pid in $(lsof -ti "tcp:$puerto" -sTCP:LISTEN 2>/dev/null || true); do
		azul "  puerto $puerto: no responde a la señal de cierre, se fuerza [$pid]"
		kill -9 "$pid" 2>/dev/null || true
	done
	sleep 0.5
}

estado_puerto() {
	local puerto="$1" etiqueta="$2" pids
	pids="$(lsof -ti "tcp:$puerto" -sTCP:LISTEN 2>/dev/null || true)"
	if [ -z "$pids" ]; then
		printf '  %-6s %-22s libre\n' "$puerto" "$etiqueta"
	else
		printf '  %-6s %-22s ocupado por %s\n' "$puerto" "$etiqueta" \
			"$(ps -p "$(echo "$pids" | head -1)" -o comm= 2>/dev/null || echo '?')"
	fi
}

# ------------------------------------------------------------------ requisitos

comprobar_entorno() {
	if [ ! -f "$FICHERO_ENV" ]; then
		rojo "Falta $FICHERO_ENV. Ejecuta «make setup» y ajusta las credenciales."
		exit 1
	fi
	for herramienta in docker uv pnpm; do
		command -v "$herramienta" > /dev/null || {
			rojo "Falta «$herramienta». Consulta docs/desarrollo.md."
			exit 1
		}
	done
}

levantar_dependencias() {
	azul "→ Dependencias (postgres, seaweedfs, redis, caddy)"
	make --no-print-directory up > /dev/null
	verde "  listas"
}

# -------------------------------------------------------------------- procesos

PIDS=()

parar_hijos() {
	trap - INT TERM EXIT
	echo ""
	azul "→ Parando los procesos arrancados"
	for pid in "${PIDS[@]:-}"; do
		[ -n "${pid:-}" ] && kill "$pid" 2> /dev/null || true
	done
	wait 2> /dev/null || true
	verde "  hecho"
}

# Cada línea se prefija con el nombre del proceso para poder seguir tres logs a la vez.
# Se usa un bucle de lectura en lugar de `sed`: sed almacena la salida cuando no escribe
# a una terminal, así que al redirigir a un fichero los logs no aparecían.
arrancar_en_segundo_plano() {
	local etiqueta="$1"
	shift
	(
		"$@" 2>&1 | while IFS= read -r linea; do
			printf '[%s] %s\n' "$etiqueta" "$linea"
		done
	) &
	PIDS+=("$!")
}

# PYTHONUNBUFFERED: sin esto, Python almacena la salida al escribir en una tubería
# en lugar de en una terminal, y los logs no aparecen hasta que el proceso muere.
comando_api() { cd "$RAIZ/apps/api" && PYTHONUNBUFFERED=1 uv run uvicorn app.main:app --reload --port "$PUERTO_API"; }
# Sin --reload: esa bandera exige el extra taskiq[reload], que no instalamos.
comando_worker() { cd "$RAIZ/apps/api" && PYTHONUNBUFFERED=1 uv run taskiq worker app.core.tasks:broker; }
# El puerto y el host viven en angular.json; aquí solo se sobrescribe el puerto
# cuando quien llama lo ha cambiado con WEB_DEV_PORT.
comando_web() { cd "$RAIZ/apps/web" && pnpm start --port "$PUERTO_WEB"; }

# ---------------------------------------------------------------------- acción

accion="${1:-all}"

case "$accion" in
	status)
		echo "Puertos del proyecto:"
		estado_puerto "$PUERTO_API" "API"
		estado_puerto "$PUERTO_WEB" "frontend (dev server)"
		estado_puerto "$PUERTO_CADDY" "Caddy"
		exit 0
		;;

	stop)
		azul "→ Liberando los puertos del proyecto"
		liberar_puerto "$PUERTO_API" "API"
		liberar_puerto "$PUERTO_WEB" "frontend"
		verde "Puertos libres. Las dependencias en Docker siguen arriba; párralas con «make down»."
		exit 0
		;;

	api | web | worker | all) ;;

	*)
		rojo "Acción desconocida: $accion"
		echo "Uso: dev.sh [all|api|web|worker|stop|status]"
		exit 2
		;;
esac

comprobar_entorno
levantar_dependencias

trap parar_hijos INT TERM EXIT

case "$accion" in
	api)
		liberar_puerto "$PUERTO_API" "API"
		azul "→ API en http://localhost:$PUERTO_API"
		arrancar_en_segundo_plano api comando_api
		;;
	web)
		liberar_puerto "$PUERTO_WEB" "frontend"
		azul "→ Frontend en http://localhost:$PUERTO_WEB"
		arrancar_en_segundo_plano web comando_web
		;;
	worker)
		azul "→ Worker de tareas"
		arrancar_en_segundo_plano worker comando_worker
		;;
	all)
		liberar_puerto "$PUERTO_API" "API"
		liberar_puerto "$PUERTO_WEB" "frontend"
		azul "→ Arrancando API, worker y frontend"
		arrancar_en_segundo_plano api comando_api
		arrancar_en_segundo_plano worker comando_worker
		arrancar_en_segundo_plano web comando_web
		;;
esac

echo ""
verde "Abre http://localhost:$PUERTO_CADDY"
echo "Entrar por :$PUERTO_WEB rompe la sesión: la cookie de refresco es first-party."
echo "Ctrl+C para parar."
echo ""

wait
