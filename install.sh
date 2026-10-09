#!/usr/bin/env bash
# First run of an installation: check the tools, install the dependencies, start the application.
#
#   git clone https://github.com/TurkovBogdan/urb-workbench && cd urb-workbench
#   ./install.sh
#
# The script sets up the tree it lives in. Running it again is safe: dependencies are synced
# again and the application comes up. `.env` and the database schema are created by the first
# start itself (`src/app.py`), so there is no separate configuration step here.
set -euo pipefail
cd "$(dirname "$0")"

UV_INSTALLER_URL="https://astral.sh/uv/install.sh"
UV_PATH_SNIPPET="$HOME/.local/bin/env"

die() {
  echo "install.sh: $1" >&2
  exit 1
}

require_checkout() {
  [[ -f src/app.py ]] ||
    die "no src/app.py next to this script — run it from a cloned repository"
}

# The script does not install system packages under sudo: that is the machine owner's call, not the installer's.
require_git() {
  command -v git >/dev/null 2>&1 && return 0
  die "git is required — install it with your package manager (Debian/Ubuntu: sudo apt-get install -y git; macOS: brew install git)"
}

# Only ask a person at a terminal: in a pipeline (cron, CI) silence is not a "yes".
confirmed() {
  [[ -t 0 ]] || return 1
  local answer
  read -r -p "$1 [y/N] " answer
  [[ "$answer" == [yY] ]]
}

ensure_uv() {
  command -v uv >/dev/null 2>&1 && return 0
  echo "uv not found — it is the project manager, and it also downloads Python 3.12."
  echo "Official installer: curl -LsSf $UV_INSTALLER_URL | sh"
  confirmed "Install uv now?" ||
    die "the installation cannot proceed without uv — install it and run the script again"
  curl -LsSf "$UV_INSTALLER_URL" | sh
  # The installer puts the binary into ~/.local/bin, but this shell's PATH is already built —
  # without picking it up, the very next line would not find the uv it just installed.
  if [[ -f "$UV_PATH_SNIPPET" ]]; then
    # shellcheck source=/dev/null
    source "$UV_PATH_SNIPPET"
  fi
  command -v uv >/dev/null 2>&1 ||
    die "uv is installed but not on PATH — log in again and rerun the script"
}

# Printed BEFORE the start: after that the terminal is taken by the running application, and the
# hint would scroll off the screen along with the log.
announce_next_steps() {
  cat <<'EOF'

Dependencies are in place. The first start will create .env with the installation's secrets and set up an empty database.
The browser will open on the "Server" page — that is where the installation settings (port, database, mode) are edited.
Then, in the interface:

  "Integrations" — a search service key; one is enough, Tavily by default
  "MCP servers"  — a ready-made connection config for the MCP client

Stop: ./run.sh stop     Update: ./update.sh

EOF
}

require_checkout
require_git
ensure_uv
# --all-groups: the same set the update syncs, otherwise the very first `./update.sh` would
# rebuild the environment from scratch.
uv sync --all-groups
announce_next_steps
# The installation ends not on the home page but on the installation settings: the first thing a
# person decides after the first start is whether to keep the port, database and mode `.env` was written with.
RUN_OPEN_PATH=/settings/core exec ./run.sh
