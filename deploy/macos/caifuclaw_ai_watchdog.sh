#!/usr/bin/env bash

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ROOT="${CAIFUCLAW_AI_ROOT:-${CAIFUCLAW_ERP_ROOT:-$DEFAULT_ROOT}}"
export PYTHONPATH="${ROOT}${PYTHONPATH:+:${PYTHONPATH}}"

INTERVAL="${CAIFUCLAW_AI_WATCHDOG_INTERVAL:-${CAIFUCLAW_ERP_WATCHDOG_INTERVAL:-30}}"
HEALTH_TIMEOUT_SECONDS="${CAIFUCLAW_AI_HEALTH_TIMEOUT_SECONDS:-${CAIFUCLAW_ERP_HEALTH_TIMEOUT_SECONDS:-60}}"
HEALTH_RETRY_ATTEMPTS="${CAIFUCLAW_AI_HEALTH_RETRY_ATTEMPTS:-${CAIFUCLAW_ERP_HEALTH_RETRY_ATTEMPTS:-3}}"
HEALTH_RETRY_DELAY_SECONDS="${CAIFUCLAW_AI_HEALTH_RETRY_DELAY_SECONDS:-${CAIFUCLAW_ERP_HEALTH_RETRY_DELAY_SECONDS:-2}}"
ONCE=0
RESTART=0
STOP_ONLY=0

while [ "$#" -gt 0 ]; do
  case "$1" in
    --once)
      ONCE=1
      ;;
    --restart)
      RESTART=1
      ;;
    --stop)
      STOP_ONLY=1
      ;;
    --interval)
      shift
      INTERVAL="${1:-$INTERVAL}"
      ;;
    --health-timeout)
      shift
      HEALTH_TIMEOUT_SECONDS="${1:-$HEALTH_TIMEOUT_SECONDS}"
      ;;
    --health-retries)
      shift
      HEALTH_RETRY_ATTEMPTS="${1:-$HEALTH_RETRY_ATTEMPTS}"
      ;;
    --health-retry-delay)
      shift
      HEALTH_RETRY_DELAY_SECONDS="${1:-$HEALTH_RETRY_DELAY_SECONDS}"
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
  shift
done

PYTHON="${CAIFUCLAW_AI_PYTHON:-${CAIFUCLAW_ERP_PYTHON:-}}"
if [ -z "$PYTHON" ]; then
  if [ -x "${ROOT}/.venv312/bin/python" ]; then
    PYTHON="${ROOT}/.venv312/bin/python"
  elif [ -x "${ROOT}/.venv/bin/python" ]; then
    PYTHON="${ROOT}/.venv/bin/python"
  else
    PYTHON="$(command -v python3 || true)"
  fi
fi

NPM="${CAIFUCLAW_AI_NPM:-${CAIFUCLAW_ERP_NPM:-$(command -v npm || true)}}"
CURL="${CAIFUCLAW_AI_CURL:-${CAIFUCLAW_ERP_CURL:-$(command -v curl || true)}}"
WATCHDOG_LOG_DIR="${ROOT}/logs/watchdog"
WATCHDOG_LOG="${WATCHDOG_LOG_DIR}/watchdog.log"
SERVICES="connector-runtime-api caifuclaw-business-api"
LEGACY_SERVICES="caifuclaw-business-frontend"

mkdir -p "$WATCHDOG_LOG_DIR"

log() {
  printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" | tee -a "$WATCHDOG_LOG"
}

contains() {
  case "$1" in
    *"$2"*) return 0 ;;
    *) return 1 ;;
  esac
}

require_command() {
  local path="$1"
  local label="$2"
  if [ -z "$path" ] || [ ! -x "$path" ]; then
    log "Missing executable for ${label}: ${path:-not found}"
    exit 1
  fi
}

service_port() {
  case "$1" in
    connector-runtime-api) echo "8100" ;;
    caifuclaw-business-api) echo "9999" ;;
    caifuclaw-business-frontend) echo "5173" ;;
    *) return 1 ;;
  esac
}

service_health_url() {
  case "$1" in
    connector-runtime-api) echo "http://127.0.0.1:8100/health" ;;
    caifuclaw-business-api) echo "http://127.0.0.1:9999/health" ;;
    caifuclaw-business-frontend) echo "http://127.0.0.1:5173" ;;
    *) return 1 ;;
  esac
}

service_pid_file() {
  case "$1" in
    connector-runtime-api) echo "${ROOT}/run_logs/connector_runtime_api.pid" ;;
    caifuclaw-business-api) echo "${ROOT}/run_logs/caifuclaw_business_api.pid" ;;
    caifuclaw-business-frontend) echo "${ROOT}/run_logs/caifuclaw_business_frontend.pid" ;;
    *) return 1 ;;
  esac
}

health_ok() {
  "$CURL" -fsS --max-time 5 "$1" >/dev/null 2>&1
}

health_ok_after_retries() {
  local name="$1"
  local url="$2"
  local attempt=1

  while [ "$attempt" -le "$HEALTH_RETRY_ATTEMPTS" ]; do
    if health_ok "$url"; then
      if [ "$attempt" -gt 1 ]; then
        log "Recovered ${name} health after retry ${attempt}/${HEALTH_RETRY_ATTEMPTS}: ${url}"
      fi
      return 0
    fi
    if [ "$attempt" -lt "$HEALTH_RETRY_ATTEMPTS" ]; then
      sleep "$HEALTH_RETRY_DELAY_SECONDS"
    fi
    attempt=$((attempt + 1))
  done

  return 1
}

port_pids() {
  lsof -nP -tiTCP:"$1" -sTCP:LISTEN 2>/dev/null || true
}

pid_command() {
  ps -p "$1" -o command= 2>/dev/null || true
}

pid_is_running() {
  kill -0 "$1" 2>/dev/null
}

command_matches_service() {
  local name="$1"
  local command_line="$2"

  case "$name" in
    connector-runtime-api)
      contains "$command_line" "uvicorn app.main:app" && contains "$command_line" "--port 8100"
      ;;
    caifuclaw-business-api)
      contains "$command_line" "uvicorn app.main:app" && contains "$command_line" "--port 9999"
      ;;
    caifuclaw-business-frontend)
      contains "$command_line" "vite" && contains "$command_line" "--port 5173"
      ;;
    *)
      return 1
      ;;
  esac
}

pid_file_service_pid() {
  local name="$1"
  local pid_file
  local pid
  local command_line
  pid_file="$(service_pid_file "$name")"

  if [ ! -f "$pid_file" ]; then
    return 1
  fi

  pid="$(cat "$pid_file" 2>/dev/null || true)"
  if [ -z "$pid" ] || ! pid_is_running "$pid"; then
    return 1
  fi

  command_line="$(pid_command "$pid")"
  if command_matches_service "$name" "$command_line"; then
    echo "$pid"
    return 0
  fi

  return 1
}

port_service_pid() {
  local name="$1"
  local port="$2"
  local pid
  local command_line

  for pid in $(port_pids "$port"); do
    command_line="$(pid_command "$pid")"
    if command_matches_service "$name" "$command_line"; then
      echo "$pid"
      return 0
    fi
  done

  return 1
}

stop_recorded_service_pid() {
  local name="$1"
  local pid="$2"
  local command_line

  if [ -z "$pid" ] || ! pid_is_running "$pid"; then
    return 0
  fi

  command_line="$(pid_command "$pid")"
  if ! command_matches_service "$name" "$command_line"; then
    return 0
  fi

  log "Stopping recorded ${name} startup, pid=${pid}"
  kill "$pid" 2>/dev/null || true
  sleep 2
  if pid_is_running "$pid"; then
    log "Force stopping recorded ${name} startup, pid=${pid}"
    kill -9 "$pid" 2>/dev/null || true
  fi
}

stop_service() {
  local name="$1"
  local port
  local pid
  local command_line
  port="$(service_port "$name")"

  for pid in $(port_pids "$port"); do
    command_line="$(pid_command "$pid")"
    if command_matches_service "$name" "$command_line"; then
      log "Stopping ${name} on port ${port}, pid=${pid}"
      kill "$pid" 2>/dev/null || true
    else
      log "Skip unknown listener on port ${port}, pid=${pid}, command=${command_line}"
    fi
  done

  sleep 2

  for pid in $(port_pids "$port"); do
    command_line="$(pid_command "$pid")"
    if command_matches_service "$name" "$command_line"; then
      log "Force stopping ${name} on port ${port}, pid=${pid}"
      kill -9 "$pid" 2>/dev/null || true
    fi
  done
}

start_detached() {
  local name="$1"
  local cwd="$2"
  local stdout_log="$3"
  local stderr_log="$4"
  local pid_file="$5"
  shift 5

  mkdir -p "$(dirname "$stdout_log")" "$(dirname "$stderr_log")" "$(dirname "$pid_file")"

  if [ ! -d "$cwd" ]; then
    log "Missing working directory for ${name}: ${cwd}"
    return 1
  fi

  (
    cd "$cwd" || exit 1
    nohup "$@" >>"$stdout_log" 2>>"$stderr_log" </dev/null &
    echo $! >"$pid_file"
  )

  log "Started ${name}, pid=$(cat "$pid_file" 2>/dev/null || echo unknown)"
}

latest_source_mtime() {
  local frontend_root="${ROOT}/caifuclaw_business_app/frontend"
  find \
    "${frontend_root}/src" \
    "${frontend_root}/public" \
    "${frontend_root}/index.html" \
    "${frontend_root}/package.json" \
    "${frontend_root}/package-lock.json" \
    "${frontend_root}/vite.config.ts" \
    "${frontend_root}/tsconfig.json" \
    "${frontend_root}/tsconfig.node.json" \
    -type f -print0 2>/dev/null | xargs -0 stat -f '%m' 2>/dev/null | sort -nr | head -1
}

missing_business_frontend_assets() {
  local frontend_root="${ROOT}/caifuclaw_business_app/frontend"
  "$PYTHON" - "$frontend_root" <<'PY'
import re
import sys
from pathlib import Path

frontend_root = Path(sys.argv[1])
dist_root = frontend_root / "dist"
index_path = dist_root / "index.html"

if not index_path.is_file():
    print("/index.html")
    sys.exit(1)

html = index_path.read_text(encoding="utf-8", errors="ignore")
missing = []
for asset in sorted(set(re.findall(r'["\'](/assets/[^"\']+)["\']', html))):
    asset_path = dist_root / asset.split("?", 1)[0].lstrip("/")
    if not asset_path.is_file():
        missing.append(asset)

if missing:
    print(" ".join(missing))
    sys.exit(1)
PY
}

build_business_frontend_dist_if_stale() {
  local frontend_root="${ROOT}/caifuclaw_business_app/frontend"
  local dist_index="${frontend_root}/dist/index.html"
  local source_mtime
  local dist_mtime=0
  local missing_assets=""

  [ -f "${frontend_root}/package.json" ] || { log "Missing caifuclaw frontend package.json"; return 1; }

  source_mtime="$(latest_source_mtime)"
  if [ -z "$source_mtime" ]; then
    log "Unable to determine caifuclaw frontend source mtime"
    return 1
  fi

  if [ -f "$dist_index" ]; then
    dist_mtime="$(stat -f '%m' "$dist_index" 2>/dev/null || echo 0)"
  fi

  if ! missing_assets="$(missing_business_frontend_assets)"; then
    log "Business frontend dist is missing referenced assets: ${missing_assets}"
  elif [ "$dist_mtime" -ge "$source_mtime" ]; then
    log "Business frontend dist is current for port 9999"
    return 0
  fi

  log "Business frontend dist is stale; rebuilding static files for port 9999"
  (
    cd "$frontend_root" || exit 1
    "$NPM" run build -- --outDir dist --emptyOutDir
  )
}

start_service() {
  local name="$1"

  case "$name" in
    connector-runtime-api)
      [ -f "${ROOT}/connector_runtime/app/main.py" ] || { log "Missing connector runtime app"; return 1; }
      start_detached "$name" "${ROOT}/connector_runtime" \
        "${ROOT}/connector_runtime/logs/connector_runtime_api.current.out.log" \
        "${ROOT}/connector_runtime/logs/connector_runtime_api.current.err.log" \
        "${ROOT}/run_logs/connector_runtime_api.pid" \
        "$PYTHON" -m uvicorn app.main:app --host 0.0.0.0 --port 8100
      ;;
    caifuclaw-business-api)
      [ -f "${ROOT}/caifuclaw_business_app/app/main.py" ] || { log "Missing CaifuClaw AI application"; return 1; }
      start_detached "$name" "${ROOT}/caifuclaw_business_app" \
        "${ROOT}/caifuclaw_business_app/logs/caifuclaw_business_api.current.out.log" \
        "${ROOT}/caifuclaw_business_app/logs/caifuclaw_business_api.current.err.log" \
        "${ROOT}/run_logs/caifuclaw_business_api.pid" \
        "$PYTHON" -m uvicorn app.main:app --host 0.0.0.0 --port 9999
      ;;
    *)
      log "Unknown service: ${name}"
      return 1
      ;;
  esac
}

wait_for_service() {
  local name="$1"
  local url
  local deadline
  url="$(service_health_url "$name")"
  deadline=$((SECONDS + HEALTH_TIMEOUT_SECONDS))

  while [ "$SECONDS" -lt "$deadline" ]; do
    if health_ok "$url"; then
      log "Healthy ${name}: ${url}"
      return 0
    fi
    sleep 2
  done

  log "Health check failed for ${name}: ${url}"
  return 1
}

port_has_unknown_listener() {
  local name="$1"
  local port="$2"
  local pid
  local command_line

  for pid in $(port_pids "$port"); do
    command_line="$(pid_command "$pid")"
    if ! command_matches_service "$name" "$command_line"; then
      log "Port ${port} is busy with unknown process, pid=${pid}, command=${command_line}"
      return 0
    fi
  done

  return 1
}

check_service() {
  local name="$1"
  local port
  local url
  local pid
  port="$(service_port "$name")"
  url="$(service_health_url "$name")"

  if [ "$name" = "caifuclaw-business-api" ]; then
    build_business_frontend_dist_if_stale || return 1
  fi

  if health_ok_after_retries "$name" "$url"; then
    return 0
  fi

  log "Unhealthy ${name}: ${url}"

  pid="$(pid_file_service_pid "$name" || true)"
  if [ -z "$pid" ]; then
    pid="$(port_service_pid "$name" "$port" || true)"
  fi
  if [ -n "$pid" ]; then
    log "Waiting for existing ${name} listener/startup, pid=${pid}"
    if wait_for_service "$name"; then
      return 0
    fi
    log "Existing ${name} did not become healthy in time, pid=${pid}"
    stop_recorded_service_pid "$name" "$pid"
  fi

  if [ -n "$(port_pids "$port")" ]; then
    if port_has_unknown_listener "$name" "$port"; then
      log "Skip restarting ${name}; port ${port} is not owned by CaifuClaw AI"
      return 1
    fi
    stop_service "$name"
  fi

  start_service "$name" && wait_for_service "$name"
}

run_cycle() {
  local name
  for name in $SERVICES; do
    check_service "$name" || true
  done
}

stop_legacy_services() {
  local name
  for name in $LEGACY_SERVICES; do
    stop_service "$name"
  done
}

require_command "$PYTHON" "python"
require_command "$NPM" "npm"
require_command "$CURL" "curl"
mkdir -p "${ROOT}/run_logs"

log "CaifuClaw AI watchdog starting, root=${ROOT}, interval=${INTERVAL}s, python=${PYTHON}"
log "Business frontend is served by caifuclaw-business-api on port 9999"

if [ "$RESTART" -eq 1 ]; then
  for service in $SERVICES; do
    stop_service "$service"
  done
fi
stop_legacy_services

if [ "$STOP_ONLY" -eq 1 ]; then
  log "Stop requested; exiting after stopping services"
  exit 0
fi

while true; do
  run_cycle
  if [ "$ONCE" -eq 1 ]; then
    log "One-shot check complete"
    exit 0
  fi
  sleep "$INTERVAL"
done
