"""Heartbeat: маркер живого планировщика."""

from __future__ import annotations

from src.core.scheduler import CoreTaskBase, TaskContext


class HeartbeatTask(CoreTaskBase):
    """Сам факт записи success в core_tasks — сигнал живости планировщика."""

    MODULE = "core"
    CODE = "heartbeat"
    NAME = "Heartbeat"
    # Английский запасной текст: интерфейс показывает перевод из словаря по (MODULE, CODE).
    DESCRIPTION = "A sign the scheduler is alive: records a successful run in core_tasks every minute."
    SCHEDULE = "* * * * *"
    TTL = 30

    @staticmethod
    async def handle(ctx: TaskContext) -> None:
        return None


__all__ = ["HeartbeatTask"]
