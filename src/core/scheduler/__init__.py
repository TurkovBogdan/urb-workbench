"""Public API of the core task scheduler."""

from __future__ import annotations

from src.core.config import Config
from src.core.scheduler.context import TaskContext
from src.core.scheduler.registry import (
    TaskEntry,
    TaskHandler,
    TaskRegistry,
    get_registry,
)
from src.core.scheduler.runner import run_entry
from src.core.scheduler.task_base import CoreTaskBase
from src.core.scheduler.ticker import Ticker


_TICKER: Ticker | None = None
# Override from the worker process: forces the ticker to start (bypassing worker_enabled) and
# sets the scope/knobs. Set by the entry point (src/app.py) BEFORE the lifespan.
_WORKER_OVERRIDE: dict | None = None


def configure_worker(
    *,
    modules: frozenset[str] | None,
    max_concurrent: int,
    tick: int,
) -> None:
    """Configure the process as a worker: forced ticker start + module scope.

    Called by the entry point of a pure worker process before the lifespan starts.
    After that ``start()`` brings up the ticker regardless of ``config.worker_enabled``.
    """
    global _WORKER_OVERRIDE
    _WORKER_OVERRIDE = {
        "modules": modules,
        "max_concurrent": max_concurrent,
        "tick": tick,
    }


def register(
    *,
    module: str,
    code: str,
    name: str,
    description: str,
    schedule: str | None,
    handler: TaskHandler,
    ttl: int,
    enabled: bool,
    user_request: bool = False,
    sort: int = 500,
) -> None:
    """Register a task. ``schedule`` is a standard 5-field cron; None → on request only."""
    get_registry().register(
        module=module,
        code=code,
        name=name,
        description=description,
        schedule=schedule,
        handler=handler,
        ttl=ttl,
        enabled=enabled,
        user_request=user_request,
        sort=sort,
    )


async def start(config: Config) -> None:
    """Start the ticker. Parameters come from the worker override (if set) or the config.

    Without an override the ticker starts only when ``config.worker_enabled`` (the embedded
    dev mode). The override (a pure worker process) forces the start and sets the scope.
    """
    global _TICKER
    if _TICKER is not None:
        return
    if _WORKER_OVERRIDE is not None:
        ov = _WORKER_OVERRIDE
        _TICKER = Ticker(
            tick_seconds=ov["tick"],
            max_concurrent_runs=ov["max_concurrent"],
            modules=ov["modules"],
        )
    elif config.worker_enabled:
        _TICKER = Ticker(
            tick_seconds=config.worker_tick_seconds,
            max_concurrent_runs=config.worker_max_concurrent_runs,
            modules=config.worker_modules_set,
        )
    else:
        return
    await _TICKER.start()


async def stop() -> None:
    global _TICKER, _WORKER_OVERRIDE
    _WORKER_OVERRIDE = None
    if _TICKER is None:
        return
    await _TICKER.stop()
    _TICKER = None


__all__ = [
    "CoreTaskBase",
    "TaskContext",
    "TaskEntry",
    "TaskHandler",
    "TaskRegistry",
    "Ticker",
    "configure_worker",
    "get_registry",
    "register",
    "run_entry",
    "start",
    "stop",
]
