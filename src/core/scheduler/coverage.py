"""Whether the scheduled tasks have anything to run them — asked once, at startup.

The scheduler is not a process of its own: a backend carries it (``--backend --worker``), or a
pure worker does (``--worker``). A backend started without one — an MCP client's shim with
``MCP_STDIO_START_WORKER=false``, a hand-run ``--backend`` — serves everything and runs nothing on a
schedule: the storage cleanup, the owners' reconciliations, every hourly job stays undone, and
nothing on screen says so. The installation's process registry knows whether a worker of this
checkout is alive (``process_registry``); without one, the startup log names the tasks left
unattended and how to run them.
"""

from __future__ import annotations

import os

from src.core import process_registry
from src.core.config import Config
from src.core.loggers import get_logger
from src.core.scheduler.registry import TaskEntry, TaskRegistry

_LOG = get_logger("tasks")

_WORKER_ROLES = frozenset({process_registry.ROLE_WORKER, process_registry.ROLE_BACKEND_WORKER})


def unattended_tasks(registry: TaskRegistry, *, ticking: bool, app_env: str) -> list[TaskEntry]:
    """The enabled scheduled tasks nothing runs: no ticker here and no live worker of this
    installation's ``app_env`` (a worker of another profile runs another database's tasks)."""
    scheduled = [entry for entry in registry.all() if entry.enabled and entry.schedule]
    if ticking or not scheduled or _worker_alive(app_env):
        return []
    return scheduled


def warn_if_unattended(config: Config, *, registry: TaskRegistry, ticking: bool) -> None:
    left = unattended_tasks(registry, ticking=ticking, app_env=config.app_env)
    if not left:
        return
    _LOG.warning(
        "scheduler: no worker runs in this installation — %d scheduled task(s) will not run: %s. "
        "Start the backend with --worker (WORKER_ENABLED=true), run a separate `src/app.py "
        "--worker`, or let the MCP shim start it (MCP_STDIO_START_WORKER=true)",
        len(left),
        ", ".join(f"{entry.module}.{entry.code}" for entry in left),
    )


def _worker_alive(app_env: str) -> bool:
    own = os.getpid()
    return any(
        record.pid != own
        and record.role in _WORKER_ROLES
        and record.app_env == app_env
        and process_registry.verify(record) is process_registry.RecordState.VERIFIED
        for record in process_registry.read_records()
    )


__all__ = ["unattended_tasks", "warn_if_unattended"]
