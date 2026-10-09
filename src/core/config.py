"""Application config loaded from .env via pydantic-settings.

Naming: this layer is called ``Config`` (deploy-time, env-backed, read-only).
Runtime user-tunable parameters live in ``src.core.settings`` and the
``core_modules_settings`` table.
"""

from __future__ import annotations

import ssl
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.pool import StaticPool

from src.core.app_path import resolve_runtime_root


def _app_root() -> Path:
    """Application root: the folder next to the binary (frozen) or the project root."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def _env_file() -> Path:
    """`.env` next to the binary in frozen mode, otherwise in the project root."""
    return _app_root() / ".env"


class Config(BaseSettings):
    """Core application config. Modules register their own ``*Config`` separately."""

    model_config = SettingsConfigDict(
        env_file=_env_file(),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        # An empty value in .env/env (`SERVER_VITE_PORT=`) means "not set" → the default
        # applies. Otherwise "" breaks optional non-strings (`int | None`) on validation.
        env_ignore_empty=True,
    )

    # ── APP — process identity ─────────────────────────────────────────────
    # APP_ENV selects runtime/<env>/ (also read directly in app_path.py, before
    # Config) and carries the dev/test/prod axis. Behaviour does NOT branch on it —
    # it only picks the runtime directory (reload/CORS are explicit SERVER_* keys).
    app_env: str = "prod"
    app_log_level: str = "INFO"
    # A behaviour switch of its own, deliberately not derived from APP_ENV: a prod profile
    # can be debugged and a dev one shown clean. No CLI flag — a flag would beat the
    # value the settings page writes into .env.
    app_dev_mode: bool = False

    # ── SERVER — HTTP transport (shared by the internal/external/webhook zones) ─
    # SERVER_ENABLED — whether to bring up the HTTP server. OFF by default: a process
    # can run as "worker only" (lifespan alive, no HTTP routes mounted).
    # The --backend CLI flag overrides it (flag > env).
    server_enabled: bool = False
    server_host: str = "127.0.0.1"
    server_port: int = 13410
    # Hot reload on source changes (src/), one key for both surfaces:
    # SERVER → uvicorn --reload; a pure WORKER → watchfiles restarts the subprocess.
    # Dev only; INcompatible with server_processes>1 (the reload supervisor holds a
    # single process). The --hot-reload/--no-hot-reload CLI flag overrides it.
    server_hot_reload: bool = False
    # Number of uvicorn processes (NOT the background worker — this is HTTP, see
    # WORKER_*). 1 is a single process; >1 takes several cores (then migrations run
    # only via `src/app.py migrate`, and the scheduler in a worker process, see
    # WORKER_ENABLED). Ignored when server_hot_reload=true.
    server_processes: int = 1
    # Vite dev-server port: needed only for dev CORS (origins below). Empty = prod
    # (nginx serves the frontend, no CORS needed). web/vite.config.ts reads the same port.
    server_vite_port: int | None = None
    # DEBUG only: an artificial delay (ms) on EVERY internal-zone request — for
    # debugging the frontend (skeletons/loaders). 0 = off: the zone dependency is not
    # mounted at all (zero overhead). The --debug-delay CLI flag overrides it. Keep 0 in prod.
    server_debug_delay_ms: int = 0

    # ── MCP — modules exposed as MCP servers (the /mcp zone) ───────────────
    # Allowed Host headers for the mounted MCP servers (CSV): protection against
    # DNS rebinding at the ASGI layer (TrustedHostMiddleware). Empty = no check
    # (dev/localhost, or nginx filters Host by server_name). In prod behind nginx,
    # set the public host(s). The fastmcp fork has no bundled TransportSecuritySettings.
    mcp_allowed_hosts: str = ""

    @property
    def mcp_allowed_hosts_list(self) -> list[str]:
        """``mcp_allowed_hosts`` (CSV) → list; empty → ``[]`` (check disabled)."""
        return [h.strip() for h in self.mcp_allowed_hosts.split(",") if h.strip()]

    # Static bearer token for the MCP servers (interim auth until an auth module): the
    # module's resolver checks the presented token against this value. Empty = local
    # mode with no check (allow-all, dev/localhost). Set it non-empty in prod.
    mcp_token: str = ""

    # ── MCP stdio shim (the client spawns us as a command server) ──────────
    # The `--mcp-stdio` role: an MCP client launches the process over stdio, the shim
    # lazily brings up the backend and bridges calls to its /mcp/<code>. Nothing runs
    # at rest; the backend outlives the shim (stopped by hand). See apps/app/mcp_stdio.py.
    # Open the system browser on the home page when the backend was actually started.
    mcp_stdio_open_browser: bool = True
    # Whether to start the worker (scheduler) together with the backend. Research/search
    # are synchronous — not needed by default; enable it if background jobs appear.
    mcp_stdio_start_worker: bool = False
    # How many seconds to wait for the backend to become ready (/internal/health) after spawn.
    mcp_stdio_boot_timeout: int = 30
    # Code of the proxied MCP server. Empty → the only one the modules mount.
    mcp_stdio_code: str = ""
    # Workspace of THIS connection (``WORKSPACE@…`` or a bare code). The shim passes it
    # to the backend in a header, and the session starts already bound — so a project
    # with its own `.mcp.json` separates work from personal without a single call. The
    # agent may override the value for its session (`workspace_use`); the file stays as is.
    # Empty = the agent picks the workspace; until then the bound tools refuse.
    mcp_workspace: str = ""

    # ── UPDATE — updating the installation (`src/app.py update`) ───────────
    # The branch the installation updates to: the command does a strict fast-forward
    # to origin/<branch> and REFUSES if the checkout is on another branch — an update
    # never moves an installation onto another line of code. The remote is deliberately
    # not exposed in ENV: `.env` is written without escaping and without auth, and a
    # value like `--upload-pack=…` is arbitrary code execution.
    update_branch: str = "main"

    # ── SECRETS — master key for encrypting values in the DB ───────────────
    # The installation key (32 bytes, base64url) that wraps the keys of encrypted
    # records. It has NO consumer right now: the only one was core_connectors,
    # removed 2026-09-20. The key is still issued on first start
    # (core_setup/env_file.py) and waits for its next consumer — declaring it anew
    # costs more than keeping it. Empty is not a startup error but the
    # "encryption off" state. It lives in the environment, not in the DB: it is
    # what opens the DB. dev and stable have different keys; the ENV settings
    # page does NOT edit it.
    secrets_key: str = ""

    # ── DATABASE: provider ─────────────────────────────────────────────────
    # sqlite is the default: zero-install (no server, one file). postgres is the
    # option for production scale (pgvector), requires DB_HOST/DB_NAME/DB_USER/DB_PASSWORD.
    db_provider: Literal["postgres", "sqlite"] = "sqlite"
    # SQLite file (only when db_provider=sqlite). Empty → <runtime_root>/app.sqlite3.
    db_path: str = ""

    # ── DATABASE: postgres connection ──────────────────────────────────────
    # Required when db_provider=postgres; ignored with sqlite (see _validate_db).
    db_host: str = ""
    db_port: int = 5432
    db_name: str = ""
    db_user: str = ""
    db_password: str = ""
    db_echo: bool = False

    # TLS. ``db_ssl=True`` → strict verify-full against the CA from ``db_cert``
    # (encryption + chain verification + hostname match). ``db_cert`` is the
    # path to the CA file relative to the application root; required with ``db_ssl``.
    # ``db_client_cert``/``db_client_key`` — client certificate for mutual
    # TLS (a server with ``clientcert=verify-full``); set both or neither.
    db_ssl: bool = True
    db_cert: str | None = None
    db_client_cert: str | None = None
    db_client_key: str | None = None

    # Network timeouts and the connection pool (critical for a remote DB).
    db_connect_timeout: int = 10
    db_pool_size: int = 10
    db_max_overflow: int = 5
    db_pool_recycle: int = 1800
    db_pool_timeout: int = 30

    # Time ceiling for ONE query (asyncpg command_timeout). 0 = no limit.
    # Note: it also applies to migrations at startup — use a large value/0 if
    # there is heavy DDL. Protects the pool from "hung" connections on an unstable
    # remote link.
    db_command_timeout: int = 0
    # Liveness check of a connection before handing it out of the pool (+1 RTT per
    # checkout). Justified for background jobs against a remote DB; turn it off if RTT
    # is high and the link is stable (then db_pool_recycle + keepalive cover drops).
    db_pool_pre_ping: bool = True
    # TCP keepalive towards PG: keeps the NAT mapping alive and catches a dead
    # peer faster on a remote link. 0 = don't set (PG system default, ~2 h).
    db_tcp_keepalives_idle: int = 60

    # ── WORKER — background: scheduler + job execution ─────────────────────
    # WORKER_ENABLED — whether to run the ticker in this process. dev sets true (one
    # process holds web + jobs); prod web = false (background in a separate worker
    # process). The --worker CLI flag overrides it (flag > env).
    worker_enabled: bool = False
    # Worker scope: CSV of module names whose jobs this process runs; empty = all.
    worker_modules: str = ""
    # Scheduler engine knobs — shared by the embedded (dev) and the worker process.
    worker_tick_seconds: int = 5
    # Ceiling on concurrently running jobs (asyncio.Semaphore in Ticker).
    # Keep it in line with the DB pool: each job holds ≥1 connection, so a
    # value > (db_pool_size + db_max_overflow) will hit db_pool_timeout.
    worker_max_concurrent_runs: int = 10

    @property
    def worker_modules_set(self) -> frozenset[str] | None:
        """``worker_modules`` (CSV) → frozenset; empty → None (all modules)."""
        names = {n.strip() for n in self.worker_modules.split(",") if n.strip()}
        return frozenset(names) or None

    @property
    def cors_origins(self) -> list[str]:
        """Dev CORS origins for Vite. Empty if server_vite_port is not set (prod)."""
        if self.server_vite_port is None:
            return []
        return [
            f"http://localhost:{self.server_vite_port}",
            f"http://127.0.0.1:{self.server_vite_port}",
        ]

    @model_validator(mode="after")
    def _validate_db(self) -> "Config":
        if self.db_provider == "postgres":
            missing = [
                name.upper()
                for name in ("db_host", "db_name", "db_user", "db_password")
                if not getattr(self, name)
            ]
            if missing:
                raise ValueError(
                    f"DB_PROVIDER=postgres requires: {', '.join(missing)}"
                )
            if self.db_ssl and not self.db_cert:
                raise ValueError("DB_CERT required when DB_SSL is enabled")
        if bool(self.db_client_cert) != bool(self.db_client_key):
            raise ValueError("DB_CLIENT_CERT and DB_CLIENT_KEY must be set together")
        return self

    @property
    def sqlite_in_memory(self) -> bool:
        """SQLite entirely in RAM: ``DB_PROVIDER=sqlite`` + ``DB_PATH=:memory:``.

        The database lives within a single connection, hence StaticPool below
        (see ``engine_kwargs``). Used by tests instead of a physical Postgres.
        """
        return self.db_provider == "sqlite" and self.db_path == ":memory:"

    @property
    def sqlite_file(self) -> Path | None:
        """DB file when the provider is file SQLite; otherwise ``None`` (postgres, in-memory)."""
        if self.db_provider != "sqlite" or self.sqlite_in_memory:
            return None
        return self._sqlite_path()

    def _sqlite_path(self) -> Path:
        """SQLite DB file: ``db_path`` (if set) or ``<runtime_root>/app.sqlite3``."""
        if self.db_path:
            return self._resolve(self.db_path)
        return resolve_runtime_root() / "app.sqlite3"

    @property
    def database_url(self) -> str:
        if self.db_provider == "sqlite":
            if self.sqlite_in_memory:
                return "sqlite+aiosqlite://"
            return f"sqlite+aiosqlite:///{self._sqlite_path()}"
        return (
            f"postgresql+asyncpg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def engine_kwargs(self) -> dict[str, Any]:
        """``create_async_engine`` kwargs (pool + connect_args) for the current provider.

        SQLite has a single writer: the pool is not tuned, only a per-connection busy timeout.
        In-memory SQLite lives inside one connection — StaticPool keeps it the only
        one, shared by all of the engine's sessions (otherwise each new session would
        get its own empty DB).
        Postgres — the pool and (optionally) verify-full TLS from ``db_connect_args``.
        """
        if self.db_provider == "sqlite":
            connect_args: dict[str, Any] = {"timeout": self.db_connect_timeout}
            if self.sqlite_in_memory:
                connect_args["check_same_thread"] = False
                return {"connect_args": connect_args, "poolclass": StaticPool}
            return {"connect_args": connect_args}
        return {
            "pool_pre_ping": self.db_pool_pre_ping,
            "pool_size": self.db_pool_size,
            "max_overflow": self.db_max_overflow,
            "pool_recycle": self.db_pool_recycle,
            "pool_timeout": self.db_pool_timeout,
            "connect_args": self.db_connect_args,
        }

    @property
    def db_connect_args(self) -> dict[str, Any]:
        """asyncpg connect args for the engine: connect timeout and (optionally) verify-full TLS.

        With ``db_client_cert``/``db_client_key`` set, the context also carries the
        client certificate (mutual TLS).
        """
        # jit=off — PG JIT adds tens of ms to the short OLTP queries of syncs.
        server_settings: dict[str, str] = {"jit": "off"}
        if self.db_tcp_keepalives_idle:
            server_settings["tcp_keepalives_idle"] = str(self.db_tcp_keepalives_idle)
        args: dict[str, Any] = {
            "timeout": self.db_connect_timeout,
            "server_settings": server_settings,
        }
        if self.db_command_timeout:
            args["command_timeout"] = self.db_command_timeout
        if self.db_ssl:
            ctx = ssl.create_default_context(cafile=str(self._resolve(self.db_cert)))
            ctx.check_hostname = True
            ctx.verify_mode = ssl.CERT_REQUIRED
            if self.db_client_cert:
                ctx.load_cert_chain(
                    certfile=str(self._resolve(self.db_client_cert)),
                    keyfile=str(self._resolve(self.db_client_key)),
                )
            args["ssl"] = ctx
        return args

    @staticmethod
    def _resolve(path: str) -> Path:
        """File path: absolute as is, relative — from the application root."""
        p = Path(path)
        return p if p.is_absolute() else _app_root() / p


@lru_cache(maxsize=1)
def get_config() -> Config:
    """Cached instance. Used by apps/* and by tests via override."""
    return Config()


__all__ = ["Config", "get_config"]
