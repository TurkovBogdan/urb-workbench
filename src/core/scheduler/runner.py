"""A single task run. Entry point for the ticker and (in the future) the CLI."""

from __future__ import annotations

import asyncio
import traceback
from contextlib import suppress

from src.core.crud import tasks as crud_tasks
from src.core.crud import tasks_logs as crud_tasks_logs
from src.core.locks import CoreLock, release_for_owners
from src.core.loggers import get_logger
from src.core.models.tasks import CoreTaskLogLevel
from src.core.scheduler.context import TaskContext
from src.core.scheduler.registry import TaskEntry


async def run_entry(entry: TaskEntry) -> None:
    """A single task run. Multi-instance safe: create_running is atomic."""
    log = get_logger("tasks", f"tasks/{entry.code}")
    task_id = await crud_tasks.create_running(module=entry.module, code=entry.code)
    if task_id is None:
        return

    owner = f"task_run:{task_id}"
    lock = await CoreLock.acquire(
        f"task:{entry.module}:{entry.code}", entry.ttl, owner=owner
    )
    if lock is None:
        # The partial index let us through, but another process still holds the task lock.
        # Roll back the running record through finalize_error and leave.
        await crud_tasks.finalize_error(task_id, text="task lock busy")
        return

    ctx = TaskContext(
        task_id=task_id,
        module=entry.module,
        code=entry.code,
        lock=lock,
    )

    hb = asyncio.create_task(_heartbeat_loop(task_id, entry.code, interval=30))
    try:
        await asyncio.wait_for(entry.handler(ctx), timeout=entry.ttl)
        await crud_tasks.finalize_success(task_id)
    except asyncio.TimeoutError:
        log.error(
            "[%s.%s#%d] timeout: %ds",
            entry.module, entry.code, task_id, entry.ttl,
        )
        await crud_tasks.finalize_error(task_id, text=f"timeout: {entry.ttl}s")
    except Exception as e:
        tb = traceback.format_exc()
        log.error(
            "[%s.%s#%d] crashed: %s\n%s",
            entry.module, entry.code, task_id, e, tb,
        )
        try:
            await crud_tasks_logs.create(
                task_id=task_id, level=CoreTaskLogLevel.error, message=tb,
            )
        except Exception:
            log.exception("failed to write task traceback log")
        await crud_tasks.finalize_error(task_id, text=str(e))
    finally:
        hb.cancel()
        with suppress(asyncio.CancelledError):
            await hb
        # Release the task lock and any sub-locks the handler took with ``owner=ctx.lock.owner``.
        try:
            await release_for_owners([owner])
        except Exception:
            log.exception(
                "failed to auto-release locks for task %d", task_id
            )


async def _heartbeat_loop(task_id: int, code: str, *, interval: int) -> None:
    log = get_logger("tasks", f"tasks/{code}")
    while True:
        await asyncio.sleep(interval)
        try:
            await crud_tasks.update_heartbeat(task_id)
        except Exception:
            log.exception("heartbeat update failed for task %d", task_id)


__all__ = ["run_entry"]
