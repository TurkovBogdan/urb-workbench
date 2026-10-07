"""MCP stdio shim: the client spawns us as a ``command`` server, we bring up the backend.

The "nothing runs at rest" model: the MCP client launches this process over stdio
(the ``command`` transport) instead of connecting to an HTTP port. On start the shim:

1. Checks whether the backend is up (HTTP ``/internal/health``). If not, spawns
   ``src/app.py --backend`` in a separate session (``start_new_session`` — the process
   outlives the shim: the MCP session ends, the server stays; it is stopped
   by hand) and waits for readiness. Readiness is ``status="ok"`` in the body, not the 200
   itself: a backend with a lagging schema answers 200 and ``degraded``, and the shim refuses,
   naming the unapplied revisions. Under the update flag it does not spawn at all.
   The spawn and the readiness poll are shared with the updater (``core/backend_launch.py``).
2. Opens the system browser on the SPA home page — only when the backend was actually
   brought up (if the server was already alive, the page is already open; no spamming
   a second tab).
3. Acts as a stdio ↔ HTTP-MCP backend bridge (``fastmcp`` proxy): calls go to
   ``/mcp/<code>`` on the live server and come back to the client. Every such call carries
   a header with THIS connection's identifier — the backend uses it to tell one agent
   session from another and keeps the active workspace keyed by it
   (``core/mcp_headers``).

stdout is reserved for the MCP protocol — diagnostics go to a log channel (a file, not a
stream), and the backend subprocess's stdio is detached into its own log file, not the client
pipe.

``fastmcp`` (+13 MB) is imported lazily in ``_build_proxy`` — importing this module itself
does not pull in the fork (like the rest of the MCP infra).
"""

from __future__ import annotations

import sys
import webbrowser
from pathlib import Path
from uuid import uuid4

from src.core import maintenance
from src.core.backend_launch import (
    base_url,
    probe_health,
    spawn_backend,
    wait_until_ready,
)
from src.core.config import Config
from src.core.loggers import get_logger
from src.core.mcp_headers import MCP_SESSION_HEADER, MCP_WORKSPACE_HEADER

_LOG = get_logger("mcp")


def _use_file_only_logging(config: Config) -> None:
    """The shim logs to a file only: stdout carries the MCP protocol, echoing there breaks JSONRPC.

    ``CoreLogger`` mirrors to stdout by default; here we install a factory with
    ``stdout=False`` before the first log line (the ``get_logger`` proxy resolves to it)."""
    from src.core.app_path import AppPath, ensure_dirs
    from src.core.loggers import set_logger_factory
    from src.core.loggers.core_logger import CoreLogger

    paths = AppPath.from_root()
    ensure_dirs(paths)
    set_logger_factory(
        lambda channel: CoreLogger(
            logs_dir=paths.logs,
            file_name=channel,
            level=config.app_log_level,
            stdout=False,
        )
    )


def _resolve_code(config: Config) -> str:
    """Code of the mounted MCP server: from the setting, or the only one among the modules."""
    if config.mcp_stdio_code:
        return config.mcp_stdio_code
    from src.apps.app.modules import build_modules

    codes = [code for module in build_modules() for code in module.mcp_servers]
    if len(codes) == 1:
        return codes[0]
    raise RuntimeError(
        f"mcp-stdio: expected exactly one MCP server (found {len(codes)}: {codes}); "
        "set MCP_STDIO_CODE"
    )


def _backend_log_path(config: Config) -> Path:
    from src.core.app_path import AppPath, ensure_dirs

    paths = AppPath.from_root()
    ensure_dirs(paths)
    return paths.logs / "mcp_stdio_backend.log"


def _spawn_backend(config: Config) -> None:
    """Bring up the backend in its own session; its stdio is detached from the MCP client pipe."""
    command = spawn_backend(
        (sys.executable,),
        with_worker=config.mcp_stdio_start_worker,
        log_path=_backend_log_path(config),
    )
    _LOG.info("mcp-stdio: spawned backend %s → %s", " ".join(command), _backend_log_path(config))


def _open_home(config: Config) -> None:
    if config.mcp_stdio_open_browser:
        webbrowser.open(base_url(config) + "/")


def _refuse_during_update() -> None:
    """With the flag up we do not spawn the backend: the updater is rewriting the tree under us.

    `app.py::main` gates the shim's start too, but the flag can go up between that check and
    this one — the race is closed here.
    """
    held = maintenance.active()
    if held is None:
        return
    raise RuntimeError(
        f"mcp-stdio: the installation is being updated ({held.describe()}) — not starting the "
        "backend; reconnect once the update has finished"
    )


def _ensure_backend(config: Config) -> None:
    """Backend ready → nothing. Degraded → refuse with the reason. Otherwise spawn and wait."""
    _refuse_during_update()
    health = probe_health(config)
    if health is not None:
        if health.is_ready:
            _LOG.info("mcp-stdio: backend already up at %s", base_url(config))
            return
        raise RuntimeError(
            f"mcp-stdio: backend at {base_url(config)} is not ready — {health.describe()}"
        )
    _spawn_backend(config)
    booted = wait_until_ready(config, timeout=config.mcp_stdio_boot_timeout)
    if booted is None:
        raise RuntimeError(
            f"mcp-stdio: backend did not come up within {config.mcp_stdio_boot_timeout}s "
            f"(see {_backend_log_path(config)})"
        )
    if not booted.is_ready:
        raise RuntimeError(f"mcp-stdio: backend came up but is not ready — {booted.describe()}")
    _open_home(config)


def _session_headers(config: Config) -> dict[str, str]:
    """How the shim introduces itself to the backend: who calls, and in which default workspace.

    The identifier is born here and lives exactly as long as the connection: the shim is one
    process per MCP client. The backend keeps no sessions at all (the servers are mounted
    ``stateless_http``) and serves every connection at once, so the only way it can tell a call
    from this conversation from one in the next is this key — and it keeps the active workspace
    keyed by it too.

    The workspace from the config travels alongside in a separate header and stays the default:
    the meaning and cost of both are in ``core/mcp_headers``.
    """
    headers = {MCP_SESSION_HEADER: str(uuid4())}
    if config.mcp_workspace:
        headers[MCP_WORKSPACE_HEADER] = config.mcp_workspace
    return headers


def _build_proxy(config: Config, code: str):
    from fastmcp.client.transports import StreamableHttpTransport
    from fastmcp.server import create_proxy

    url = f"{base_url(config)}/mcp/{code}"
    # Transport headers are added to EVERY request to the backend, not just the first one —
    # that is what keeps the session binding: the bridge has no separate "login".
    transport = StreamableHttpTransport(
        url, headers=_session_headers(config), auth=config.mcp_token or None
    )
    return create_proxy(transport, name=code)


def run_mcp_stdio(config: Config) -> None:
    """Bring up the backend (if needed) and run the stdio bridge to its MCP server."""
    _use_file_only_logging(config)
    code = _resolve_code(config)
    _ensure_backend(config)
    proxy = _build_proxy(config, code)
    proxy.run(show_banner=False)


__all__ = ["run_mcp_stdio"]
