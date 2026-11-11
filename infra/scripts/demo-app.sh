#!/usr/bin/env bash
# Arranca la app completa en modo demo: infraestructura Docker + los cuatro procesos de host
# (mock-marketplace, browser-worker, orchestrator y web), con datos de demo ya sembrados.
#
# Uso:
#   pnpm demo:app              arranca (idempotente: lo que ya está vivo se respeta)
#   pnpm demo:app --reset      borra volúmenes y vuelve a migrar/sembrar. ¡BORRA DATOS LOCALES!
#   pnpm demo:app --dry-run    imprime cada paso sin ejecutarlo
#   pnpm demo:app:stop         para los cuatro procesos de host (Docker sigue levantado)
#
# Todos los valores son placeholders de desarrollo ya documentados en .env.example y
# infra/docker-compose.yml. Nunca se usa nada real. Ver DEMO.md, sección 8.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

# Los logs y los PID viven fuera del repo. APEX_DEMO_DIR permite cambiarlo en tests o en otra máquina.
DEMO_DIR="${APEX_DEMO_DIR:-/tmp/apex-demo}"
PID_DIR="$DEMO_DIR/pids"
WAIT_SECONDS="${APEX_DEMO_WAIT_S:-180}"

# Puertos de los procesos de host. 8001 lo publica el contenedor llm-stub.
ORCHESTRATOR_PORT=8000
LLM_STUB_PORT=8001
MARKETPLACE_PORT=8002
WORKER_PORT=4010
WEB_PORT=3000

# Placeholders de desarrollo. Los mismos valores están en .env.example, compose y dev-reset.
OWNER_DATABASE_URL="postgresql://apex:apex@127.0.0.1:5432/apex"
APP_DATABASE_URL="postgresql+asyncpg://apex_app_login:apex_app_dev@127.0.0.1:5432/apex"
APEX_APP_DB_PASSWORD="apex_app_dev"
BROWSER_WORKER_TOKEN="apex-dev-browser-worker-token-0123456789"
UNLEASH_ADMIN_TOKEN="*:*.apex-dev-unleash-admin"
UNLEASH_CLIENT_TOKEN="default:development.apex-dev-unleash-client"
UNLEASH_API="http://127.0.0.1:4242/api"

MODE="start"
DRY_RUN=0
RESET=0

usage() {
  cat <<EOF
Uso: bash infra/scripts/demo-app.sh [stop] [--reset] [--dry-run]

  (sin argumentos)  Arranca la app completa en http://localhost:3000.
  stop              Para mock-marketplace, browser-worker, orchestrator y web.
  --reset           Antes de arrancar, ejecuta 'pnpm dev:reset' (BORRA volúmenes y datos locales).
  --dry-run         Imprime cada paso sin ejecutarlo.
  -h, --help        Muestra esta ayuda.

Logs: $DEMO_DIR/*.log    PIDs: $DEMO_DIR/pids/
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    stop) MODE="stop" ;;
    --reset) RESET=1 ;;
    --dry-run) DRY_RUN=1 ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      printf '[demo-app] ERROR: opción desconocida: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

log() { printf '[demo-app] %s\n' "$*"; }
warn() { printf '[demo-app] AVISO: %s\n' "$*" >&2; }
die() {
  printf '[demo-app] ERROR: %s\n' "$*" >&2
  exit 1
}

# Ejecuta (o imprime, en dry-run). Pensado para comandos sin redirecciones ni stdin.
run_cmd() {
  if [ "$DRY_RUN" = 1 ]; then
    printf '[dry-run] %s\n' "$*"
    return 0
  fi
  "$@"
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "no encuentro '$1' en el PATH. $2"
}

# -----------------------------------------------------------------------------
# Puertos y procesos
# -----------------------------------------------------------------------------

# PID que escucha en el puerto, o vacío. ss primero; lsof como alternativa.
port_pid() {
  local port="$1"
  if command -v ss >/dev/null 2>&1; then
    ss -lptnH "sport = :$port" 2>/dev/null |
      sed -n 's/.*pid=\([0-9][0-9]*\).*/\1/p' | head -n 1
    return 0
  fi
  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null | head -n 1
  fi
}

pid_pgid() {
  ps -o pgid= -p "$1" 2>/dev/null | tr -d '[:space:]'
}

pid_desc() {
  local pid="$1" cmd
  cmd="$(tr '\0' ' ' <"/proc/$pid/cmdline" 2>/dev/null | cut -c 1-120)"
  [ -n "$cmd" ] || cmd="$(ps -o comm= -p "$pid" 2>/dev/null || true)"
  printf '%s (pid %s)' "${cmd:-desconocido}" "$pid"
}

# PID guardado para un servicio, solo si sigue vivo.
managed_pid() {
  local name="$1" pidfile="$PID_DIR/$name.pid" pid
  [ -f "$pidfile" ] || return 1
  pid="$(cat "$pidfile" 2>/dev/null || true)"
  [ -n "$pid" ] || return 1
  kill -0 "$pid" 2>/dev/null || return 1
  printf '%s' "$pid"
}

# ¿El listener del puerto pertenece al grupo de procesos que arrancamos nosotros?
# setsid hace que el PID guardado sea el líder del grupo; pnpm/node/uv heredan ese PGID.
port_is_managed() {
  local name="$1" port="$2" listener pgid owner
  listener="$(port_pid "$port")"
  [ -n "$listener" ] || return 1
  owner="$(managed_pid "$name")" || return 1
  pgid="$(pid_pgid "$listener")"
  [ -n "$pgid" ] && [ "$pgid" = "$owner" ]
}

# El 8001 lo ocupa el llm-stub de Docker, que es lo esperado (no es un proceso de host).
llm_stub_container_owns_port() {
  command -v docker >/dev/null 2>&1 || return 1
  [ "$(docker inspect -f '{{.State.Running}}' apex-llm-stub 2>/dev/null || true)" = "true" ] ||
    return 1
  docker port apex-llm-stub 8001 2>/dev/null | grep -q ':8001'
}

# Se niega a seguir si otro proceso ocupa el puerto. Si el ocupante es nuestro (ejecución
# anterior) o el llm-stub de Docker, lo informa y continúa: el script es idempotente.
assert_port_available() {
  local name="$1" port="$2" listener
  if [ "$DRY_RUN" = 1 ]; then
    log "[dry-run] comprobaría que el puerto $port está libre (o es nuestro: $name)"
    return 0
  fi
  listener="$(port_pid "$port")"
  if [ -z "$listener" ]; then
    return 0
  fi
  if [ "$port" -eq "$LLM_STUB_PORT" ] && llm_stub_container_owns_port; then
    log "puerto $port: lo ocupa el contenedor llm-stub (esperado)"
    return 0
  fi
  if port_is_managed "$name" "$port"; then
    log "puerto $port: ya lo ocupa $name, de una ejecución anterior nuestra"
    return 0
  fi
  die "el puerto $port ($name) está ocupado por: $(pid_desc "$listener").
  Páralo y vuelve a intentarlo, o ejecuta 'pnpm demo:app:stop' si quedó algo de una ejecución anterior.
  Para ver el ocupante: ss -lptn 'sport = :$port'"
}

# -----------------------------------------------------------------------------
# Parada de los procesos de host
# -----------------------------------------------------------------------------

# ¿Sigue vivo el grupo que creó setsid? (los hijos pnpm/node/uv cuentan aunque el líder muera).
group_alive() {
  kill -0 -- "-$1" 2>/dev/null || kill -0 "$1" 2>/dev/null
}

# Marca que identifica el proceso de cada servicio en /proc/<pid>/cmdline. Evita matar un PID
# reciclado por otro programa cuando el fichero de PID es viejo.
service_marker() {
  case "$1" in
    orchestrator) printf 'uvicorn' ;;
    worker) printf '@apex/browser-worker' ;;
    marketplace) printf '@apex/mock-marketplace' ;;
    web) printf '@apex/web' ;;
    *) printf '' ;;
  esac
}

pid_looks_like_service() {
  local name="$1" pid="$2" marker cmdline
  marker="$(service_marker "$name")"
  [ -n "$marker" ] || return 0
  cmdline="$(tr '\0' ' ' <"/proc/$pid/cmdline" 2>/dev/null || true)"
  printf '%s' "$cmdline" | grep -q -- "$marker"
}

stop_all() {
  local name pid pidfile
  for name in web orchestrator worker marketplace; do
    pidfile="$PID_DIR/$name.pid"
    if [ ! -f "$pidfile" ]; then
      continue
    fi
    pid="$(cat "$pidfile" 2>/dev/null || true)"
    if [ -z "$pid" ] || ! kill -0 "$pid" 2>/dev/null; then
      [ "$DRY_RUN" = 1 ] || rm -f "$pidfile"
      continue
    fi
    if ! pid_looks_like_service "$name" "$pid"; then
      warn "el PID $pid guardado para $name no parece ese servicio; no lo mato"
      [ "$DRY_RUN" = 1 ] || rm -f "$pidfile"
      continue
    fi
    if [ "$DRY_RUN" = 1 ]; then
      log "[dry-run] pararía $name (grupo de procesos $pid)"
      continue
    fi
    log "parando $name (grupo de procesos $pid)"
    # Negativo = todo el grupo (setsid lo creó). Si no fuese el líder, se cae al PID suelto.
    kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
    local waited=0
    while group_alive "$pid" && [ "$waited" -lt 15 ]; do
      sleep 1
      waited=$((waited + 1))
    done
    if group_alive "$pid"; then
      warn "$name no paró con SIGTERM; enviando SIGKILL"
      kill -KILL -- "-$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null || true
    fi
    rm -f "$pidfile"
  done
  if [ "$DRY_RUN" = 0 ]; then
    log "procesos de host parados. Docker sigue levantado: 'pnpm dev:down' lo para todo."
  fi
}

# -----------------------------------------------------------------------------
# Esperas de salud
# -----------------------------------------------------------------------------

tail_log() {
  local name="$1"
  if [ -n "$name" ] && [ -f "$DEMO_DIR/$name.log" ]; then
    warn "últimas líneas de $DEMO_DIR/$name.log:"
    tail -n 20 "$DEMO_DIR/$name.log" >&2 || true
  elif [ -n "$name" ]; then
    warn "últimas líneas de 'docker compose logs $name':"
    docker compose logs --tail 20 "$name" >&2 2>/dev/null || true
  fi
}

# wait_http <etiqueta> <url> <log o vacío> [args de curl...]
wait_http() {
  local label="$1" url="$2" logname="$3"
  shift 3
  if [ "$DRY_RUN" = 1 ]; then
    log "[dry-run] esperaría a $label en $url (máx. ${WAIT_SECONDS}s)"
    return 0
  fi
  local waited=0
  while :; do
    if curl -fsS -m 3 "$@" "$url" >/dev/null 2>&1; then
      log "$label responde"
      return 0
    fi
    if [ "$waited" -ge "$WAIT_SECONDS" ]; then
      tail_log "$logname"
      die "$label no respondió en ${WAIT_SECONDS}s ($url)"
    fi
    sleep 2
    waited=$((waited + 2))
  done
}

# La web puede responder 3xx/4xx/5xx y seguir siendo "está levantada": basta con que conteste HTTP.
wait_web() {
  local url="http://127.0.0.1:$WEB_PORT/"
  if [ "$DRY_RUN" = 1 ]; then
    log "[dry-run] esperaría a la web en $url (máx. ${WAIT_SECONDS}s)"
    return 0
  fi
  local waited=0
  while :; do
    if curl -sS -m 3 -o /dev/null "$url" 2>/dev/null; then
      log "web responde"
      return 0
    fi
    if [ "$waited" -ge "$WAIT_SECONDS" ]; then
      tail_log web
      die "la web no respondió en ${WAIT_SECONDS}s ($url)"
    fi
    sleep 2
    waited=$((waited + 2))
  done
}

# Los one-shot de compose (vault-init, rustfs-init) deben terminar con código 0. Sus
# container_name son estables porque compose fija el nombre del proyecto ("apex").
wait_one_shot() {
  local svc="$1" name="apex-$1" state waited=0
  while :; do
    state="$(docker inspect -f '{{.State.Status}}:{{.State.ExitCode}}' "$name" 2>/dev/null || true)"
    case "$state" in
      exited:0)
        log "$svc terminó correctamente"
        return 0
        ;;
      exited:*)
        docker compose logs --tail 20 "$svc" >&2 2>/dev/null || true
        die "$svc falló (estado $state)"
        ;;
      '')
        if [ "$waited" -ge 30 ]; then
          die "no encuentro el contenedor $name para $svc"
        fi
        ;;
    esac
    if [ "$waited" -ge 60 ]; then
      docker compose logs --tail 20 "$svc" >&2 2>/dev/null || true
      die "$svc no terminó en 60s (estado $state)"
    fi
    sleep 1
    waited=$((waited + 1))
  done
}

wait_postgres() {
  if [ "$DRY_RUN" = 1 ]; then
    log "[dry-run] esperaría a PostgreSQL (pg_isready)"
    return 0
  fi
  local waited=0
  while :; do
    if docker compose exec -T postgres pg_isready -U apex -d apex >/dev/null 2>&1; then
      log "postgres responde"
      return 0
    fi
    if [ "$waited" -ge "$WAIT_SECONDS" ]; then
      docker compose logs --tail 20 postgres >&2 2>/dev/null || true
      die "PostgreSQL no respondió en ${WAIT_SECONDS}s"
    fi
    sleep 2
    waited=$((waited + 2))
  done
}

# -----------------------------------------------------------------------------
# Base de datos: migraciones (solo si faltan), seed y rol de login con RLS
# -----------------------------------------------------------------------------

app_schema_ready() {
  docker compose exec -T postgres psql -U apex -d apex -tAc \
    "SELECT 1 FROM pg_roles WHERE rolname = 'apex_app'" 2>/dev/null |
    tr -d '[:space:]' | grep -qx '1'
}

ensure_app_role() {
  if [ "$DRY_RUN" = 1 ]; then
    log "[dry-run] docker compose exec -T postgres sh -s < infra/postgres/bootstrap-app-role.sh"
    return 0
  fi
  log "asegurando el rol de login de la aplicación (apex_app_login, sujeto a RLS)"
  if ! docker compose exec -T \
    -e PGUSER=apex -e PGDATABASE=apex \
    -e APEX_APP_DB_PASSWORD="$APEX_APP_DB_PASSWORD" \
    postgres sh -s <"$ROOT_DIR/infra/postgres/bootstrap-app-role.sh" >/dev/null; then
    die "no se pudo crear/actualizar apex_app_login. Revisa que las migraciones estén aplicadas."
  fi
}

# En una máquina limpia el esquema no existe: se aplica lo mismo que 'dev:reset' hace después de
# borrar volúmenes, pero SIN borrar nada. Si el esquema ya está, solo se asegura el rol de login.
ensure_database() {
  if [ "$DRY_RUN" = 1 ]; then
    log "[dry-run] comprobaría si el esquema está migrado y aplicaría migrate deploy + seed + load_defaults si falta"
    log "[dry-run] aseguraría el rol apex_app_login"
    return 0
  fi
  if ! app_schema_ready; then
    log "la base no está migrada todavía (falta el rol apex_app): aplico migraciones y seed"
    log "esto no borra datos; para empezar de cero usa 'pnpm demo:app --reset'"
    (
      export DATABASE_URL="$OWNER_DATABASE_URL?schema=public"
      export MIGRATE_DATABASE_URL="$OWNER_DATABASE_URL"
      pnpm --filter @apex/web exec prisma migrate deploy ||
        die "falló 'prisma migrate deploy'. Revisa la salida de arriba."
      pnpm --filter @apex/web exec prisma db seed ||
        die "falló el seed de Prisma. Revisa la salida de arriba."
    )
    if [ -f "$ROOT_DIR/apps/orchestrator/src/apex/tenant_config/load_defaults.py" ]; then
      log "cargando configuración demo de tenant-a y tenant-b (ADR-900 Q7)"
      (
        cd "$ROOT_DIR/apps/orchestrator"
        uv run python -m apex.tenant_config.load_defaults tenant-a tenant-b --demo-values
      )
    fi
  else
    log "el esquema ya está migrado; no toco migraciones ni seed"
  fi
  ensure_app_role
}

# -----------------------------------------------------------------------------
# Feature flags de Unleash (idempotente)
# -----------------------------------------------------------------------------

unleash_curl() {
  curl -sS -m 10 -H "Authorization: $UNLEASH_ADMIN_TOKEN" "$@"
}

default_strategy_exists() {
  local flag="$1" result
  result="$(
    unleash_curl "$UNLEASH_API/admin/projects/default/features/$flag/environments/development/strategies" 2>/dev/null |
      node -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{try{const a=JSON.parse(s);process.stdout.write(Array.isArray(a)&&a.some(x=>x.name==="default")?"1":"0")}catch{process.stdout.write("0")}})'
  )"
  [ "$result" = "1" ]
}

development_enabled() {
  local flag="$1" result
  result="$(
    unleash_curl "$UNLEASH_API/admin/projects/default/features/$flag" 2>/dev/null |
      node -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{try{const j=JSON.parse(s);const e=(j.environments||[]).find(x=>x.name==="development");process.stdout.write(e&&e.enabled?"1":"0")}catch{process.stdout.write("0")}})'
  )"
  [ "$result" = "1" ]
}

ensure_flag() {
  local flag="$1" code body="$DEMO_DIR/.unleash-last.json"
  if [ "$DRY_RUN" = 1 ]; then
    log "[dry-run] crearía/activaría la flag $flag en el entorno development (si falta)"
    return 0
  fi
  code="$(curl -sS -m 10 -o "$body" -w '%{http_code}' -X POST \
    "$UNLEASH_API/admin/projects/default/features" \
    -H "Authorization: $UNLEASH_ADMIN_TOKEN" \
    -H 'Content-Type: application/json' \
    -d "{\"name\":\"$flag\",\"type\":\"release\",\"description\":\"dev demo\"}")"
  case "$code" in
    200 | 201) log "flag $flag creada" ;;
    409) log "flag $flag ya existía" ;;
    *)
      cat "$body" >&2 2>/dev/null || true
      die "Unleash devolvió HTTP $code al crear la flag $flag"
      ;;
  esac

  if default_strategy_exists "$flag"; then
    log "flag $flag: la estrategia 'default' ya existe"
  else
    code="$(curl -sS -m 10 -o "$body" -w '%{http_code}' -X POST \
      "$UNLEASH_API/admin/projects/default/features/$flag/environments/development/strategies" \
      -H "Authorization: $UNLEASH_ADMIN_TOKEN" \
      -H 'Content-Type: application/json' \
      -d '{"name":"default"}')"
    case "$code" in
      200 | 201) log "flag $flag: estrategia 'default' añadida" ;;
      *)
        cat "$body" >&2 2>/dev/null || true
        die "Unleash devolvió HTTP $code al añadir la estrategia de $flag"
        ;;
    esac
  fi

  if development_enabled "$flag"; then
    log "flag $flag ya está activa en development"
  else
    code="$(curl -sS -m 10 -o "$body" -w '%{http_code}' -X POST \
      "$UNLEASH_API/admin/projects/default/features/$flag/environments/development/on" \
      -H "Authorization: $UNLEASH_ADMIN_TOKEN" \
      -H 'Content-Type: application/json' \
      -d '{"enabled":true}')"
    case "$code" in
      200 | 201) log "flag $flag activada en development" ;;
      *)
        cat "$body" >&2 2>/dev/null || true
        die "Unleash devolvió HTTP $code al activar la flag $flag"
        ;;
    esac
    development_enabled "$flag" || die "la flag $flag sigue desactivada en development"
  fi
}

ensure_unleash_flags() {
  log "asegurando feature flags de Unleash (si no están, el browser worker rechaza toda plataforma)"
  local flag
  for flag in \
    platform.mock-a.enabled \
    platform.mock-b.enabled \
    platform.mock-c.enabled \
    negotiation.autonomous_send; do
    ensure_flag "$flag"
  done
}

# -----------------------------------------------------------------------------
# Arranque de procesos de host
# -----------------------------------------------------------------------------

STARTED_PIDS=()

start_service() {
  local name="$1" port="$2"
  shift 2

  if [ "$DRY_RUN" = 1 ]; then
    log "[dry-run] arrancaría $name en :$port"
    printf '[dry-run]   %s\n' "$*"
    return 0
  fi

  if [ -n "$(port_pid "$port")" ] && port_is_managed "$name" "$port"; then
    log "$name ya está escuchando en :$port (pid $(managed_pid "$name"))"
    return 0
  fi
  local pid
  pid="$(managed_pid "$name" || true)"
  if [ -n "$pid" ]; then
    if pid_looks_like_service "$name" "$pid"; then
      log "$name ya tiene un proceso vivo (pid $pid); espero a que escuche en :$port"
      return 0
    fi
    warn "el PID $pid guardado para $name no parece ese servicio; lo ignoro y arranco de nuevo"
    rm -f "$PID_DIR/$name.pid"
  fi

  mkdir -p "$PID_DIR"
  local logfile="$DEMO_DIR/$name.log"
  : >"$logfile"
  log "arrancando $name en :$port (log: $logfile)"
  # Children of this script, not a detached session: `setsid`/`nohup` are silently killed in some
  # sandboxes (the process never reaches its listen call), and a demo is meant to stop with Ctrl-C
  # anyway. The script traps INT/TERM and kills this group; `demo:app:stop` covers the other case.
  "$@" >>"$logfile" 2>&1 </dev/null &
  STARTED_PIDS+=("$!")
  local started=$!
  printf '%s\n' "$started" >"$PID_DIR/$name.pid"

  # `setsid` forks when the caller is a process-group leader, so `$!` can be an intermediate that exits
  # at once while the real service is still booting. Liveness is therefore "the port answers", not
  # "this PID is alive": a service that truly died shows up in the log and in this same timeout.
  local waited=0
  while [ "$waited" -lt 45 ]; do
    if [ -n "$(port_pid "$port")" ]; then
      return 0
    fi
    sleep 1
    waited=$((waited + 1))
  done
  # Nothing listens after 45 s: show what the service said and stop. `setsid` may fork, so the PID we
  # recorded is not a reliable liveness signal; the port is.
  tail_log "$name"
  rm -f "$PID_DIR/$name.pid"
  die "$name no escuchó en :$port en 45 s."
}

# -----------------------------------------------------------------------------
# Banner final
# -----------------------------------------------------------------------------

demo_password() {
  local realm="$ROOT_DIR/infra/keycloak/realm-apex.json" user="owner-a@apex.local"
  if command -v node >/dev/null 2>&1 && [ -f "$realm" ]; then
    node -e 'const fs=require("fs");const r=JSON.parse(fs.readFileSync(process.argv[1],"utf8"));const u=(r.users||[]).find(x=>x.username===process.argv[2]);const c=((u&&u.credentials)||[]).find(x=>x.type==="password");process.stdout.write(c?c.value:"")' \
      "$realm" "$user" 2>/dev/null || true
  fi
}

print_banner() {
  local password
  password="$(demo_password)"
  [ -n "$password" ] || password="(ver infra/keycloak/realm-apex.json)"
  cat <<EOF

────────────────────────────────────────────────────────────────────────────
 APEX-EFN — demo de la app completa
────────────────────────────────────────────────────────────────────────────
 Web .................... http://localhost:3000
 Orchestrator (API/docs)  http://127.0.0.1:8000/docs
 Mock marketplace ....... http://127.0.0.1:8002
 Browser worker ......... http://127.0.0.1:4010/internal/v1/health
 Keycloak ............... http://localhost:8080 (realm "apex")
 Modelo ................. ${LLM_MODEL:-stub local (Docker :8001)}

 Usuario demo ........... owner-a@apex.local  /  $password
 Tenant ................. tenant-a   (también existe tenant-b)

 DEMO_MODE=1: los tenants ya tienen config ADR-900 y un snapshot financiero
 ACTIVO SIN FIRMA para poder lanzar una misión sin passkey. Es solo para la
 demo: salta la firma que exigen los criterios 17/21.

 Logs ................... $DEMO_DIR/*.log
 Parar los procesos ..... pnpm demo:app:stop
 Parar también Docker ... pnpm dev:down
────────────────────────────────────────────────────────────────────────────
EOF
}

# -----------------------------------------------------------------------------
# Flujo principal
# -----------------------------------------------------------------------------

if [ "$MODE" = "stop" ]; then
  if [ "$DRY_RUN" = 0 ]; then
    mkdir -p "$PID_DIR"
  fi
  log "parando los procesos de host de la demo"
  stop_all
  exit 0
fi

log "raíz del repo: $ROOT_DIR"

# Optional real model. `DEEPSEEK_API_KEY` (or `LLM_GATEWAY_API_KEY`) in the environment or in the
# gitignored `.env.local` at the repo root switches every role from the stub to an OpenAI-compatible
# endpoint, and the mock marketplace's sellers to the same model, so both sides write real prose.
# The prices are still decided in code: the model only writes text.
if [ -f "$ROOT_DIR/.env.local" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$ROOT_DIR/.env.local"
  set +a
fi
LLM_API_KEY="${DEEPSEEK_API_KEY:-${LLM_GATEWAY_API_KEY:-}}"
if [ -n "$LLM_API_KEY" ]; then
  LLM_BASE_URL="${LLM_GATEWAY_URL:-https://api.deepseek.com/v1}"
  LLM_MODEL="${LLM_MODEL_OVERRIDE:-deepseek-chat}"
  log "modelo real: $LLM_MODEL en $LLM_BASE_URL (intérprete, negociador y vendedores)"
else
  LLM_BASE_URL="http://127.0.0.1:$LLM_STUB_PORT/v1"
  LLM_MODEL=""
  log "modelo: stub local en :$LLM_STUB_PORT (exporta DEEPSEEK_API_KEY para usar el modelo real)"
fi
require_cmd docker "Instala Docker Engine + el plugin 'docker compose'."
require_cmd pnpm "Instala pnpm >= 9 (corepack enable)."
require_cmd curl "Instala curl."
require_cmd uv "Instala uv (https://docs.astral.sh/uv/) para el orchestrator."
require_cmd node "Instala Node >= 22."

if [ "$DRY_RUN" = 0 ]; then
  docker info >/dev/null 2>&1 || die "el daemon de Docker no responde. Arráncalo y reintenta."
  [ -d "$ROOT_DIR/node_modules" ] ||
    die "faltan las dependencias de Node. Ejecuta 'pnpm install' una vez y vuelve a intentarlo."
  mkdir -p "$PID_DIR"
fi

assert_port_available orchestrator "$ORCHESTRATOR_PORT"
assert_port_available llm-stub "$LLM_STUB_PORT"
assert_port_available marketplace "$MARKETPLACE_PORT"
assert_port_available worker "$WORKER_PORT"
assert_port_available web "$WEB_PORT"

if [ "$RESET" = 1 ]; then
  warn "opción --reset: se BORRAN los volúmenes locales (Postgres, RustFS, Keycloak, Redis...)."
  warn "Se pierden los datos de demo actuales y se vuelven a migrar y sembrar."
  stop_all
  run_cmd pnpm dev:reset
fi

log "levantando la infraestructura base con Docker (sin borrar datos)"
if [ "$DRY_RUN" = 1 ]; then
  log "[dry-run] docker compose up -d --wait postgres redis keycloak vault rustfs unleash llm-stub"
  log "[dry-run] docker compose up -d vault-init rustfs-init"
else
  docker compose up -d --wait postgres redis keycloak vault rustfs unleash llm-stub ||
    die "'docker compose up --wait' falló. Revisa 'docker compose ps' y 'docker compose logs'."
  # Los one-shot (vault-init, rustfs-init) no tienen healthcheck: se lanzan aparte y no bloquean
  # el arranque de los demás, pero sí se espera a que terminen bien.
  log "lanzando los inicializadores one-shot (vault-init, rustfs-init)"
  docker compose up -d vault-init rustfs-init ||
    die "no se pudieron lanzar vault-init/rustfs-init."
  wait_one_shot vault-init
  wait_one_shot rustfs-init
fi

wait_postgres
wait_http "llm-stub" "http://127.0.0.1:$LLM_STUB_PORT/health" llm-stub
wait_http "Unleash" "http://127.0.0.1:4242/health" unleash
wait_http "Keycloak (realm apex)" "http://127.0.0.1:8080/realms/apex/.well-known/openid-configuration" ""
wait_http "Unleash (API de administración)" "$UNLEASH_API/admin/projects/default/features" unleash \
  -H "Authorization: $UNLEASH_ADMIN_TOKEN"

ensure_database
ensure_unleash_flags

# La web necesita su propio .env.local (Next.js no lee el .env de la raíz). No lo escribimos:
# puede que otro proceso lo esté configurando y no queremos pisarlo.
if [ ! -f "$ROOT_DIR/apps/web/.env.local" ]; then
  warn "falta apps/web/.env.local: la web arrancará, pero el login y el proxy al orchestrator pueden fallar."
  warn "Créalo una vez con los valores de desarrollo del repo: cp .env.example apps/web/.env.local"
  warn "(está en .gitignore; no lo commitees)."
fi

# Los cuatro procesos de host. Nota: los valores son placeholders de desarrollo.
if [ "$DRY_RUN" = 1 ]; then
  # Every step above printed its plan; stop here so a dry run never touches a process.
  log "[dry-run] fin del plan: no se arranca ningún proceso"
  exit 0
fi

# Sin `tsx watch`: el modo vigilancia necesita una TTY (renderiza una barra de estado y lee de stdin) y
# muere en silencio en cuanto la salida va a un log, que es justo lo que hace este script. Para una demo el
# recargado automático no aporta nada; si tocas el código, relanza.
if [ -n "$LLM_API_KEY" ]; then
  MARKETPLACE_SIM_ENV=(SIM_LLM_URL="$LLM_BASE_URL" SIM_LLM_MODEL="$LLM_MODEL" SIM_LLM_API_KEY="$LLM_API_KEY")
else
  MARKETPLACE_SIM_ENV=()
fi

start_service marketplace "$MARKETPLACE_PORT" \
  /usr/bin/env PORT="$MARKETPLACE_PORT" HOST=127.0.0.1 "${MARKETPLACE_SIM_ENV[@]}" \
  bash -c 'cd "$1" && exec ./node_modules/.bin/tsx src/index.ts' \
  _ "$ROOT_DIR/apps/mock-marketplace"

start_service worker "$WORKER_PORT" \
  /usr/bin/env \
  PORT="$WORKER_PORT" \
  REDIS_URL="redis://127.0.0.1:6379" \
  BROWSER_WORKER_TOKEN="$BROWSER_WORKER_TOKEN" \
  VAULT_ADDR="http://127.0.0.1:8200" \
  VAULT_TOKEN="apex-dev-root-token" \
  UNLEASH_URL="$UNLEASH_API" \
  UNLEASH_API_TOKEN="$UNLEASH_CLIENT_TOKEN" \
  MOCK_A_BASE_URL="http://127.0.0.1:$MARKETPLACE_PORT" \
  MOCK_B_BASE_URL="http://127.0.0.1:$MARKETPLACE_PORT" \
  MOCK_C_BASE_URL="http://127.0.0.1:$MARKETPLACE_PORT" \
  ARTIFACT_DIR="$DEMO_DIR/artifacts" \
  BROWSER_WORKER_REAL_BROWSER=0 \
  bash -c 'cd "$1" && exec ./node_modules/.bin/tsx src/index.ts' \
  _ "$ROOT_DIR/apps/browser-worker"

# NEGOTIATION_AUTONOMOUS_SEND: Phase 1 is semi-automatic by product design (every draft waits for a
# person). The demo lets the agent send so the chat flows while the audience watches.
start_service orchestrator "$ORCHESTRATOR_PORT" \
  /usr/bin/env \
  DATABASE_URL="$APP_DATABASE_URL" \
  MIGRATE_DATABASE_URL="$OWNER_DATABASE_URL" \
  REDIS_URL="redis://127.0.0.1:6379" \
  S3_ENDPOINT="http://127.0.0.1:9000" \
  S3_ACCESS_KEY="apex-dev" \
  S3_SECRET_KEY="apex-dev-secret" \
  BROWSER_WORKER_URL="http://127.0.0.1:$WORKER_PORT" \
  BROWSER_WORKER_TOKEN="$BROWSER_WORKER_TOKEN" \
  LLM_GATEWAY_URL="$LLM_BASE_URL" \
  LLM_GATEWAY_API_KEY="$LLM_API_KEY" \
  LLM_MODEL_OVERRIDE="$LLM_MODEL" \
  MISSION_AUTORUN=1 \
  APEX_AUTH_ISSUER="http://localhost:8080/realms/apex" \
  APEX_AUTH_AUDIENCE="apex-orchestrator" \
  APEX_AUTH_JWKS_URL="http://127.0.0.1:8080/realms/apex/protocol/openid-connect/certs" \
  APEX_ALLOW_TENANT_HEADER=true \
  APEX_DEV_ROLES="owner,admin,buyer,finance,viewer" \
  UNLEASH_URL="$UNLEASH_API" \
  UNLEASH_API_TOKEN="$UNLEASH_CLIENT_TOKEN" \
  OTEL_EXPORTER_OTLP_ENDPOINT="http://127.0.0.1:4318" \
  LOG_LEVEL=INFO \
  MOCK_MARKETPLACE_URL="http://127.0.0.1:$MARKETPLACE_PORT" \
  NEGOTIATION_STEP_DELAY_S=0.8 \
  NEGOTIATION_AUTONOMOUS_SEND=1 \
  DEMO_MODE=1 \
  bash -c 'cd "$1" && exec uv run uvicorn apex.main:app --host 127.0.0.1 --port "$2"' \
  _ "$ROOT_DIR/apps/orchestrator" "$ORCHESTRATOR_PORT"

start_service web "$WEB_PORT" \
  /usr/bin/env ORCHESTRATOR_URL="http://127.0.0.1:$ORCHESTRATOR_PORT" \
  pnpm --filter @apex/web dev

wait_http "mock-marketplace" "http://127.0.0.1:$MARKETPLACE_PORT/healthz" marketplace
wait_http "browser-worker" "http://127.0.0.1:$WORKER_PORT/internal/v1/health" worker \
  -H "Authorization: Bearer $BROWSER_WORKER_TOKEN"
wait_http "orchestrator" "http://127.0.0.1:$ORCHESTRATOR_PORT/health" orchestrator
wait_web

print_banner

# The demo runs in the foreground: this script owns the four processes. Ctrl-C (or SIGTERM) stops them.
cleanup() {
  trap - INT TERM EXIT
  log "parando los procesos de la demo"
  local pid
  for pid in "${STARTED_PIDS[@]:-}"; do
    [ -n "$pid" ] || continue
    kill -TERM "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}
trap cleanup INT TERM
trap cleanup EXIT

log "demo en marcha. Ctrl-C para parar los procesos (Docker se queda levantado)."
wait
