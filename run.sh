#!/usr/bin/env bash
# Project launcher: no arguments — run on the built frontend, dev (Vite + backend hot reload),
# build-prod (build the frontend), stop (shut down), test (pytest).
# Ports and the DB provider come from .env (SERVER_PORT, SERVER_VITE_PORT, DB_PROVIDER).
set -euo pipefail
cd "$(dirname "$0")"

if command -v pnpm >/dev/null 2>&1; then
  PNPM=(pnpm)
else
  PNPM=(corepack pnpm)
fi

usage() {
  cat <<'EOF'
run.sh — project launcher

  ./run.sh             backend (--backend --worker) + opens the web interface in the browser;
                       the frontend is served prebuilt from web/dist, no hot reload
  ./run.sh dev         front (Vite HMR) + backend (--backend --worker --hot-reload)
  ./run.sh build-prod  build the frontend in production mode into web/dist (needs Node.js 20+ and pnpm)
  ./run.sh stop        stop the installation by its process registry (src/app.py stop, arguments
                       pass through) plus Vite on SERVER_VITE_PORT from .env
  ./run.sh test        uv run pytest — arguments pass through (./run.sh test --core)
  ./run.sh help        this help

Building the frontend is a separate command: web/dist is in the repository and an installation
needs only `git pull`, so starting builds nothing (`./run.sh prod` = run without building).
The backend address comes from .env (SERVER_HOST/SERVER_PORT); Vite prints its own on startup.
EOF
}

# Address and readiness come from the application itself, via the same functions the MCP shim
# uses: every installation has its own port, and a browser opened before the first response shows
# a connection error. A backend answering with the stub page (schema behind) is opened too — the
# stub is the answer. The page is set from outside (RUN_OPEN_PATH): the installer wants "Server",
# not the home page.
open_page_when_serving() {
  uv run python - "${RUN_OPEN_PATH:-/}" <<'PY'
import sys
import webbrowser

sys.path.insert(0, ".")

from src.core.backend_launch import base_url, wait_until_ready
from src.core.config import Config

BOOT_TIMEOUT_SECONDS = 120

page = sys.argv[1]
config = Config()
address = base_url(config)
if wait_until_ready(config, timeout=BOOT_TIMEOUT_SECONDS) is None:
    print(f"run.sh: {address} did not respond within {BOOT_TIMEOUT_SECONDS} s — not opening the browser")
else:
    webbrowser.open(address + page)
PY
}

cmd="${1:-run}"
shift 2>/dev/null || true

case "$cmd" in
  run | prod)
    open_page_when_serving &
    opener_pid=$!
    trap 'kill "$opener_pid" 2>/dev/null || true' EXIT INT TERM
    # `--no-hot-reload` explicitly: the dev `.env` sets SERVER_HOT_RELOAD=true, and without the flag
    # this command would silently start the file watcher instead of the promised run on the built frontend.
    uv run python src/app.py --backend --worker --no-hot-reload
    ;;
  dev)
    "${PNPM[@]}" --dir web dev &
    vite_pid=$!
    trap 'kill "$vite_pid" 2>/dev/null || true' EXIT INT TERM
    uv run python src/app.py --backend --worker --hot-reload
    ;;
  build-prod)
    "${PNPM[@]}" --dir web build
    ;;
  stop)
    # backend/worker — by the installation's process registry (`runtime/processes/`): exactly this
    # checkout is stopped, as a group and with proof of death. Matching by process name was wrong
    # in principle here: an `app.py` pattern also catches a neighbouring installation, the MCP shims
    # and the agent's session. Arguments pass through: ./run.sh stop --dry-run, ./run.sh stop --stop-unregistered.
    stop_code=0
    uv run python src/app.py stop "$@" || stop_code=$?
    # Vite keeps no record of itself — it is not an application process, so it alone is left to
    # the port from .env. The port is never guessed: a deployed installation has no Vite at all, and
    # a guessed number may belong to someone else's process. A dry run leaves it alone too — "show the plan" stops nothing.
    vite_port=$(grep -E '^SERVER_VITE_PORT=' .env 2>/dev/null | cut -d= -f2 | tr -d '[:space:]' || true)
    if [[ -z "$vite_port" ]]; then
      echo "SERVER_VITE_PORT is not set in .env — not looking for Vite"
    elif [[ " $* " == *" --dry-run "* ]]; then
      echo "vite on :$vite_port left alone (--dry-run)"
    else
      fuser -k -TERM "$vite_port/tcp" 2>/dev/null && echo "stopped vite on :$vite_port" || true
    fi
    exit "$stop_code"
    ;;
  test)
    uv run pytest "$@"
    ;;
  help | -h | --help)
    usage
    ;;
  *)
    echo "unknown command: $cmd" >&2
    usage
    exit 1
    ;;
esac
