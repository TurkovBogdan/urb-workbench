#!/usr/bin/env bash
# Updates the installation: fast-forward to origin/UPDATE_BRANCH, uv sync, database copy,
# migrations, restart. All the logic is in `src/app.py update` (see its docstring and exit codes).
#
#   ./update.sh            # update
#   ./update.sh --dry-run  # print the steps and the process-stop plan without touching anything
#
# `exec` is mandatory: it replaces the shell BEFORE git rewrites this file underneath it
# (bash reads a script as it executes). So is `cd`: `src/app.py` is relative, and
# `uv run` looks for the project from the current directory.
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)" || exit 1
exec uv run python src/app.py update "$@"
