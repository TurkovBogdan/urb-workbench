"""Hourly reconciliation of the tasks' storage owners with their binding rows (``reconcile.py``).

The folder is ``scheduled/``, not ``tasks/`` as in ``core_storage``: inside the ``tasks`` module a
``tasks.tasks`` package would read as the module's own entity.

Hourly rather than daily: the backend runs only while it is in use, and a nightly run would not
happen on a machine that is off at night. The half hour keeps it apart from the storage's own
cleanup at the top of the hour.
"""

from __future__ import annotations

from src.core.scheduler import CoreTaskBase, TaskContext
from src.modules.tasks.reconcile import reconcile_task_owners


class FileOwnersTask(CoreTaskBase):
    MODULE = "tasks"
    CODE = "file_owners"
    NAME = "Task file owners"
    # English fallback text: the UI shows the dictionary translation keyed by (MODULE, CODE).
    DESCRIPTION = (
        "Hourly: releases the storage owners of task files that no binding row holds any more, "
        "and reports bindings whose file the storage counts no owner for."
    )
    SCHEDULE = "30 * * * *"
    TTL = 600

    @staticmethod
    async def handle(ctx: TaskContext) -> None:
        report = await reconcile_task_owners()
        await ctx.info("released %d", report.released)
        for task_code, file_code in report.unheld:
            await ctx.warn("task %s binds %s with no live owner", task_code, file_code)


__all__ = ["FileOwnersTask"]
