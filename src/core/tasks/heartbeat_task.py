"""Heartbeat: a marker that the scheduler is alive."""

from __future__ import annotations

from src.core.scheduler import CoreTaskBase, TaskContext


class HeartbeatTask(CoreTaskBase):
    """The mere fact of a success recorded in core_tasks signals the scheduler is alive."""

    MODULE = "core"
    CODE = "heartbeat"
    NAME = "Heartbeat"
    # English fallback text: the UI shows the dictionary translation keyed by (MODULE, CODE).
    DESCRIPTION = "A sign the scheduler is alive: records a successful run in core_tasks every minute."
    SCHEDULE = "* * * * *"
    TTL = 30

    @staticmethod
    async def handle(ctx: TaskContext) -> None:
        return None


__all__ = ["HeartbeatTask"]
