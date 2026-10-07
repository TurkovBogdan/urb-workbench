"""Restarting the process to apply a new ``.env`` (Config is read at startup).

The method depends on the mode, otherwise we hit "port already in use":

- **hot-reload (dev):** uvicorn holds the listening socket through its reload supervisor.
  ``os.execv`` would bring up a second process on the same port → conflict. So we just
  "touch" a watched file in ``src/`` — the supervisor rebuilds the worker the normal way
  (re-import ``server.py`` → ``Config()`` re-reads ``.env``), and the port is not rebound.
- **no reload (prod/single process):** ``os.execv`` replaces the image with the same
  ``python src/app.py …`` — the port is released by the replaced process.

Scheduled with a short delay so the HTTP response gets out before the restart.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import TypedDict

from pydantic import ValidationError

from src.core.config import Config
from src.core.loggers import get_logger

_LOG = get_logger()

# The src/app.py entry point — it is under uvicorn's reload_dirs (--reload watches src/).
_WATCHED_ENTRY = Path(__file__).resolve().parents[2] / "app.py"


def _reexec() -> None:
    os.execv(sys.executable, [sys.executable, *sys.argv])


def _trigger_reload() -> None:
    # Bump the watched file's mtime → uvicorn --reload rebuilds the worker.
    _WATCHED_ENTRY.touch()


def schedule_restart(*, hot_reload: bool, delay: float = 0.5) -> None:
    """Schedule a restart in ``delay`` seconds (after the current response is sent)."""
    action = _trigger_reload if hot_reload else _reexec
    how = "uvicorn reload (touch src)" if hot_reload else "os.execv"
    _LOG.warning("core_setup: restart in %.1fs via %s — .env will be re-read", delay, how)
    asyncio.get_running_loop().call_later(delay, action)


class Move(TypedDict):
    host: str
    port: int
    from_host: str
    from_port: int


def predict_move(*, hot_reload: bool, bound_host: str, bound_port: int) -> Move | None:
    """Where the restarted process will listen, if not where it listens now; ``None`` — it stays.

    Call after ``.env`` is written. Under hot-reload the supervisor keeps its socket through the
    rebuild, so a new host/port in ``.env`` waits for a full restart. Otherwise ``os.execv``
    inherits this process's environment, and a fresh ``Config()`` reads exactly what the new image
    will: the environment first (``--host``/``--port`` included, see ``src/app.py``), then ``.env``.
    """
    if hot_reload:
        return None
    try:
        fresh = Config()
    except ValidationError:
        # The new image will not start with this config either; there is no address to follow.
        return None
    if (fresh.server_host, fresh.server_port) == (bound_host, bound_port):
        return None
    return Move(
        host=fresh.server_host,
        port=fresh.server_port,
        from_host=bound_host,
        from_port=bound_port,
    )


__all__ = ["Move", "predict_move", "schedule_restart"]
