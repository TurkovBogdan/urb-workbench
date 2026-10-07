"""The single entry point: launching a process (server/worker) and DB migrations.

Without a subcommand it LAUNCHES a process. The role is a composition of two surfaces
(precedence flag > env > default):

    uv run python src/app.py --backend --worker   — dev: web + jobs in one process
    uv run python src/app.py --backend             — prod-web: HTTP only
    uv run python src/app.py --worker              — prod-worker: background only
    uv run python src/app.py                       — role from env (SERVER_ENABLED/WORKER_ENABLED)
    uv run python src/app.py --mcp-stdio           — MCP stdio shim: the client spawns us,
                                                     the shim lazily brings up backend + browser
    uv run python src/app.py --mcp-stdio workbench — the same, with an explicit server: several
                                                     servers are mounted and guessing is impossible

The `migrate` subcommand — DB migrations as a separate run (without bringing up the server):

    uv run python src/app.py migrate            — dry-run check (alias for check); exit 1 on drift
    uv run python src/app.py migrate check
    uv run python src/app.py migrate upgrade    — apply core + modules up to head

The `backup` subcommand — a database copy (`src/core/backup.py`) before a migration: SQLite via
`VACUUM INTO` + `integrity_check`, PostgreSQL via `pg_dump --format=custom` verified with
`pg_restore --list`. Without an argument the path is chosen by provider:

    uv run python src/app.py backup            — next to the file DB / runtime/<profile>/backup
    uv run python src/app.py backup <path>     — an explicit file (never overwrites an existing one)

The `update` subcommand — updating the whole installation (wrapped by `./update.sh`): checks,
maintenance flag, stopping processes, fast-forward to origin/UPDATE_BRANCH, `uv sync`,
database copy, migrations, restart waiting for readiness. `--dry-run` prints the steps and the
stop plan without touching anything. Exit codes: 0 — updated/already current, 1 — preconditions
failed, 2 — another updater holds the flag, 3 — rolled back, 4 — a migration failed (the flag
is left up), 5 — the database copy failed (schema untouched), 6 — the rollback failed,
7 — could not stop the installation's processes, 8 — the backend did not come up after the update,
9 — the update failed unexpectedly (the traceback goes to the log, the flag stays as it was),
10 — found installation processes with no record of themselves (stop them with `--stop-unregistered`),
11 — unsupported platform (Windows): the manual procedure is printed.

The `stop` subcommand — stop this installation's processes (and only its own) by the same
registry records and through the same layer as the update: by group TERM → CONT → KILL with
proof of death; another user's and unregistered processes are a refusal, not a silent skip.
Stopping does not touch Vite — it is not an application process (`./run.sh stop` stops it).

    uv run python src/app.py stop                       — stop
    uv run python src/app.py stop --dry-run             — print the plan, touch nothing
    uv run python src/app.py stop --stop-unregistered   — also stop processes without a record

Exit codes: 0 — stopped (or there was nothing to stop), 7 — something survived the signals, a
process of another user, or a group shared with the stopper, 10 — found processes with no record
of themselves, 11 — unsupported platform (Windows).

A launched process (server/worker) records itself in the registry `runtime/processes/<pid>.json`
(`src/core/process_registry.py`) and drops the record on exit: the update stops the installation
by these records instead of recognising it by cwd and argv.

While a live updater holds the maintenance flag (`runtime/maintenance.json`), LAUNCHING a
process is refused with code 1 — otherwise the MCP shim would bring up a backend on a
half-rewritten tree. Subcommands are not gated: the update runs `backup` and `migrate upgrade`
precisely while the flag is up.

`--backend`/`--worker` (and `--no-backend`/`--no-worker`) override the env toggles
`SERVER_ENABLED`/`WORKER_ENABLED`. The flags are written to env BEFORE `Config()`, so
uvicorn's reload/processes subprocesses inherit them.

Surfaces:
- **SERVER** (`SERVER_ENABLED`) — the HTTP server (internal/external/webhook zones).
  Brought up via uvicorn on `SERVER_HOST:SERVER_PORT`. `SERVER_HOT_RELOAD=true`
  → one process watching `src/` (dev); otherwise `SERVER_PROCESSES` processes.
- **WORKER** (`WORKER_ENABLED`) — scheduler + job execution. When SERVER is
  off, the process is a pure worker: NO uvicorn and no port binding, the lifespan
  is driven directly; the scope is limited by `WORKER_MODULES`. With `SERVER_HOT_RELOAD`
  the pure worker runs under watch (`watchfiles`) — the same key as the server's:
  the worker subprocess restarts on edits to `src/`. The embedded worker (alongside
  SERVER) reloads together with uvicorn's reload.

When SERVER is on, the embedded ticker is brought up in the app's lifespan per
`WORKER_ENABLED` (that is how dev keeps both web and jobs). A pure worker (no SERVER)
forces the ticker via `scheduler.configure_worker`.

ONLY `migrate upgrade` applies migrations (and the installation update, which calls
it) — starting a process does not migrate a database that already has a schema: a lagging
chain brings the app up in degraded mode (`src/core/router/degraded.py`).
The exception is an empty database: a fresh install applies the chain itself. The frontend
static files are served by the same backend from `web/dist` (Vite in dev).
"""

import argparse
import asyncio
import atexit
import os
import signal
import sys
from pathlib import Path

# The entry point lives in src/ — the project root is the parent of src/.
sys.path.insert(0, str(Path(__file__).parents[1]))

# How long uvicorn waits for open connections on shutdown. A connection that never ends by itself
# (an MCP session, a change-feed socket of `core_changes`) would otherwise hang shutdown and
# hot-reload while it is open. A normal request finishes within two seconds; whatever is still
# open is cut, and the tab reconnects.
GRACEFUL_SHUTDOWN_SECONDS = 2


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="app",
        description="Launch a process (server/worker) or run DB migrations (migrate).",
    )
    # ── launch flags (top-level; apply when no subcommand is given) ───────────
    p.add_argument(
        "--backend",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="bring up the HTTP server; overrides SERVER_ENABLED (flag > env)",
    )
    p.add_argument(
        "--worker",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="bring up the scheduler + jobs; overrides WORKER_ENABLED (flag > env)",
    )
    p.add_argument(
        "--mcp-stdio",
        nargs="?",
        const="",
        default=None,
        metavar="CODE",
        help="MCP stdio shim role: the client spawns it over stdio, the shim lazily brings up "
        "backend + browser and bridges calls to its /mcp/<code> (see apps/app/mcp_stdio.py). "
        "CODE — which of the mounted servers to proxy (overrides MCP_STDIO_CODE); "
        "without a value the only mounted one is used",
    )
    p.add_argument(
        "--mcp-workspace",
        default=None,
        metavar="CODE",
        help="the workspace of THIS connection (WORKSPACE@… or a bare code); "
        "overrides MCP_WORKSPACE. A session default — the agent changes it, the config stays put",
    )
    p.add_argument(
        "--hot-reload",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="hot-reload the server/worker on edits to src/ (dev); overrides SERVER_HOT_RELOAD",
    )
    p.add_argument("--host", default=None, help="override SERVER_HOST")
    p.add_argument("--port", type=int, default=None, help="override SERVER_PORT")
    p.add_argument(
        "--processes",
        type=int,
        default=None,
        help="override SERVER_PROCESSES (ignored under hot-reload)",
    )
    p.add_argument(
        "--debug-delay",
        type=int,
        default=None,
        metavar="MS",
        help="DEBUG: delay (ms) on every internal API request; ← SERVER_DEBUG_DELAY_MS (0=off)",
    )
    p.add_argument(
        "--worker-module",
        action="append",
        default=None,
        metavar="NAME",
        help="worker scope: only this module's jobs (repeatable); ← WORKER_MODULES",
    )
    p.add_argument(
        "--worker-tick-seconds",
        type=int,
        default=None,
        help="override WORKER_TICK_SECONDS",
    )
    p.add_argument(
        "--worker-max-concurrent",
        type=int,
        default=None,
        help="override WORKER_MAX_CONCURRENT_RUNS",
    )

    # ── migrate subcommand ───────────────────────────────────────────────────
    sub = p.add_subparsers(dest="command")
    mig = sub.add_parser("migrate", help="DB migrations (check|upgrade)")
    mig.add_argument(
        "action",
        nargs="?",
        choices=("check", "upgrade"),
        default="check",
        help="check — dry-run check (default); upgrade — apply up to head",
    )

    # ── backup subcommand ────────────────────────────────────────────────────
    bak = sub.add_parser("backup", help="database copy before a migration (sqlite/postgres)")
    bak.add_argument(
        "target",
        nargs="?",
        default=None,
        metavar="PATH",
        help="where to put the copy; empty — next to the file database or runtime/<profile>/backup",
    )

    # ── update subcommand ────────────────────────────────────────────────────
    upd = sub.add_parser("update", help="update the installation to origin/UPDATE_BRANCH")
    upd.add_argument(
        "--dry-run",
        action="store_true",
        help="walk the sequence and print the steps (including the process stop plan), "
        "touching nothing: no signals, fetch/merge/sync, database copy or migrations",
    )
    upd.add_argument(
        "--stop-unregistered",
        action="store_true",
        help="also stop this checkout's processes that have no registry record (otherwise the "
        "update refuses with code 10); needed once — on the first update after the registry ships",
    )

    # ── stop subcommand ──────────────────────────────────────────────────────
    stp = sub.add_parser("stop", help="stop this install's processes by their registry records")
    stp.add_argument(
        "--dry-run",
        action="store_true",
        help="print the stop plan and exit without sending signals",
    )
    stp.add_argument(
        "--stop-unregistered",
        action="store_true",
        help="also stop this checkout's processes that have no registry record (otherwise refuse "
        "with code 10)",
    )
    return p.parse_args(argv)


def _apply_env_overrides(args: argparse.Namespace) -> None:
    """CLI > env: set env BEFORE Config()/importing the app.

    Both uvicorn's reload and processes subprocesses pick the values up (they inherit env).
    """
    if args.backend is not None:
        os.environ["SERVER_ENABLED"] = "true" if args.backend else "false"
    if args.worker is not None:
        os.environ["WORKER_ENABLED"] = "true" if args.worker else "false"
    if args.hot_reload is not None:
        os.environ["SERVER_HOT_RELOAD"] = "true" if args.hot_reload else "false"
    # In env, not only in `args`: the running app has to know the address it is bound to — the
    # settings page predicts from it where a restart will move the server (core_setup/restart.py).
    if args.host is not None:
        os.environ["SERVER_HOST"] = args.host
    if args.port is not None:
        os.environ["SERVER_PORT"] = str(args.port)
    if args.debug_delay is not None:
        os.environ["SERVER_DEBUG_DELAY_MS"] = str(args.debug_delay)
    if args.worker_module is not None:
        os.environ["WORKER_MODULES"] = ",".join(args.worker_module)
    if args.worker_tick_seconds is not None:
        os.environ["WORKER_TICK_SECONDS"] = str(args.worker_tick_seconds)
    if args.worker_max_concurrent is not None:
        os.environ["WORKER_MAX_CONCURRENT_RUNS"] = str(args.worker_max_concurrent)


def _run_server(config, args: argparse.Namespace) -> None:
    """Bring up the HTTP server via uvicorn. The embedded ticker starts in the lifespan per
    WORKER_ENABLED."""
    import uvicorn

    host = config.server_host
    port = config.server_port
    log_level = config.app_log_level.lower()
    if config.server_hot_reload:
        # --reload is incompatible with processes>1: the reload supervisor holds one process.
        uvicorn.run(
            "src.apps.app.server:app",
            host=host,
            port=port,
            reload=True,
            reload_dirs=[str(Path(__file__).parent)],
            log_level=log_level,
            timeout_graceful_shutdown=GRACEFUL_SHUTDOWN_SECONDS,
        )
        return
    uvicorn.run(
        "src.apps.app.server:app",
        host=host,
        port=port,
        workers=args.processes or config.server_processes,
        log_level=log_level,
        timeout_graceful_shutdown=GRACEFUL_SHUTDOWN_SECONDS,
    )


def _run_worker_hot_reload() -> None:
    """A pure worker under watch: restart the worker subprocess on edits to src/ (dev).

    The same `SERVER_HOT_RELOAD` key as the server's. A pure worker has no uvicorn
    (and hence no reload supervisor of its own), so we keep the watch ourselves via
    `watchfiles.run_process`: on a change in `src/` the subprocess restarts from scratch.
    The child is the same `src/app.py --worker --no-backend`, but with `--no-hot-reload`
    (otherwise watch-within-watch recursion); scope/knobs are inherited via env.
    """
    import shlex

    from watchfiles import run_process

    src_dir = str(Path(__file__).parent)
    cmd = shlex.join(
        [sys.executable, str(Path(__file__)), "--worker", "--no-backend", "--no-hot-reload"]
    )
    run_process(src_dir, target=cmd)


async def _run_worker(config) -> None:
    """A pure worker: the lifespan driven directly, no uvicorn/port. Waits for SIGTERM/SIGINT."""
    from src.apps.app.modules import build_modules
    from src.core import scheduler
    from src.core.app_factory import create_app

    # Force the ticker (bypassing SERVER) + set scope/knobs from config.
    scheduler.configure_worker(
        modules=config.worker_modules_set,
        max_concurrent=config.worker_max_concurrent_runs,
        tick=config.worker_tick_seconds,
    )
    app = create_app(modules=build_modules(), config=config)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # pragma: no cover — non-POSIX
            pass

    async with app.router.lifespan_context(app):
        await stop.wait()


def _run_the_role(config, args: argparse.Namespace) -> None:
    """The process's actual work: the HTTP server or a pure worker (under watch with hot-reload)."""
    if config.server_enabled:
        # The embedded worker (if WORKER_ENABLED) comes up in the app's lifespan.
        _run_server(config, args)
        return
    # A pure worker — no uvicorn and no port.
    if config.server_hot_reload:
        _run_worker_hot_reload()
        return
    asyncio.run(_run_worker(config))


def _run_recorded(config, args: argparse.Namespace) -> None:
    """Run the role while the process is recorded in the installation registry (`process_registry`).

    The record has to be dropped in two places: uvicorn returns from `run()` on SIGTERM and reaches
    `finally`, while a `SystemExit` from deep inside (e.g. a port already in use) leaves via
    `atexit`. Neither fires on SIGKILL or on `os.execv` — a record that outlived its process is
    recognised by the pid + start time pair and removed by the next `announce`.
    """
    from src.core import process_registry

    process_registry.announce(config)
    atexit.register(process_registry.withdraw)
    try:
        _run_the_role(config, args)
    finally:
        process_registry.withdraw()


# ── migrations (migrate subcommand) ─────────────────────────────────────────


def _print_migration_status(status) -> None:
    print(f"current heads: {', '.join(status.current_heads) or '(none — fresh DB)'}")
    print(f"target heads:  {', '.join(status.target_heads) or '(none)'}")
    if status.up_to_date:
        print("migrations: up to date — nothing to apply")
        return
    print(f"pending ({len(status.pending)}):")
    for rev in status.pending:
        print(f"  {rev.revision}  {rev.message}")
        print(f"      {rev.path}")


async def _run_migrate(action: str) -> int:
    """check — print the state (exit 1 on drift); upgrade — apply up to head."""
    from src.apps.app.modules import build_modules
    from src.core.config import Config
    from src.core.database import close_database, init_database
    from src.core.database.migrations import AlembicRunner

    runner = AlembicRunner(modules=build_modules())
    engine = await init_database(Config())
    try:
        status = await runner.status(engine)
        _print_migration_status(status)
        if action == "check":
            return 0 if status.up_to_date else 1
        if status.up_to_date:
            return 0
        await runner.upgrade_head(engine)
        print("migrations: applied — now at head")
    finally:
        await close_database()
    return 0


def _launches_a_process(args: argparse.Namespace) -> bool:
    """No subcommand means we are launching a process (`--mcp-stdio` included).

    Subcommands (`migrate`, `backup`, `update`, `stop`) are exempt from the gate on purpose: the
    updater itself runs `backup` and `migrate upgrade` with the flag up, and a failed migration
    does not lower the flag — gating subcommands would lock the update in from the inside and
    rule out a retry.
    """
    return args.command is None


def _maintenance_refusal() -> str | None:
    """The refusal text when a live updater holds the maintenance flag; otherwise None."""
    from src.core import maintenance

    held = maintenance.active()
    if held is None:
        return None
    return (
        f"the installation is being updated ({held.describe()}) — launching a process is refused.\n"
        f"wait for the update to finish; flag: {maintenance.flag_path()}"
    )


def main(argv: list[str] | None = None) -> int | None:
    args = _parse_args(argv)

    if args.command == "migrate":
        return asyncio.run(_run_migrate(args.action))

    if args.command == "backup":
        from src.core.backup import backup_command

        return backup_command(args.target)

    if args.command == "update":
        from src.core.update import update_command

        return update_command(dry_run=args.dry_run, stop_unregistered=args.stop_unregistered)

    if args.command == "stop":
        from src.core.update import stop_command

        return stop_command(dry_run=args.dry_run, stop_unregistered=args.stop_unregistered)

    if _launches_a_process(args):
        refusal = _maintenance_refusal()
        if refusal is not None:
            print(refusal, file=sys.stderr)
            return 1

    # ``is not None`` rather than truthiness: a bare ``--mcp-stdio`` yields an empty string (we
    # find the code ourselves), and a truthiness check would mistake it for no role at all.
    if args.mcp_stdio is not None:
        # The shim brings up the backend itself as a separate process — this process's role env
        # is left alone (it is neither server nor worker but a stdio bridge). That is also why the
        # shared ``_apply_env_overrides`` is not called here: of all the overrides exactly these
        # two make sense for the shim, and both are properties of the CONNECTION, not the install.
        if args.mcp_stdio:
            os.environ["MCP_STDIO_CODE"] = args.mcp_stdio
        if args.mcp_workspace is not None:
            os.environ["MCP_WORKSPACE"] = args.mcp_workspace
        from src.apps.app.mcp_stdio import run_mcp_stdio
        from src.core.config import Config

        run_mcp_stdio(Config())
        return None

    _apply_env_overrides(args)

    from src.core.config import Config
    from src.modules.core_setup.env_file import (
        ensure_generated,
        ensure_keys_present,
        env_path,
        seed_defaults_if_absent,
    )

    config = Config()
    if seed_defaults_if_absent(config):
        print(f"first run: created {env_path()} with default values")
    # Keys that appeared later than the file itself would otherwise never reach a live install:
    # they are visible neither in `.env` nor on the settings page, and there is nowhere to set them.
    for key in ensure_keys_present(config):
        print(f"added with its default value: {key} → {env_path()}")
    # Installation secrets are topped up into an existing .env too: the encryption key appeared
    # later than the file itself, and without this step it would exist on no live install.
    for key in ensure_generated(config):
        print(f"generated {key} → {env_path()}")
    if not config.server_enabled and not config.worker_enabled:
        # No surface at all is not an error but a valid no-op (e.g. a process
        # that was launched only for `migrate`). Clean exit (code 0).
        print(
            "neither SERVER nor WORKER is enabled — nothing to run (for migrations: "
            "`src/app.py migrate`). Exiting."
        )
        return None

    _run_recorded(config, args)
    return None


if __name__ == "__main__":
    raise SystemExit(main())
