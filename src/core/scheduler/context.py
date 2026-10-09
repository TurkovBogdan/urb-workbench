"""TaskContext — what a task handler sees."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.core.crud import tasks as crud_tasks
from src.core.crud import tasks_logs as crud_tasks_logs
from src.core.locks import CoreLock
from src.core.loggers import get_logger
from src.core.models.tasks import CoreTaskLogLevel

_SYS_LEVELS = {
    CoreTaskLogLevel.debug: "debug",
    CoreTaskLogLevel.info: "info",
    CoreTaskLogLevel.warn: "warning",
    CoreTaskLogLevel.error: "error",
}


@dataclass
class TaskContext:
    task_id: int
    module: str
    code: str
    lock: CoreLock  # task-level lock: key ``task:{module}:{code}``, owner=task_run:{id}

    @property
    def _file_log(self):
        """Tee logger: the shared ``tasks`` channel + the task's own ``tasks/<code>``."""
        return get_logger("tasks", f"tasks/{self.code}")

    async def set_payload(self, payload: dict[str, Any]) -> None:
        """Record the run's payload. DB errors are swallowed — they must not crash the handler."""
        try:
            await crud_tasks.update_payload(self.task_id, payload)
        except Exception:
            self._file_log.exception("failed to write payload for task %d", self.task_id)

    async def _write_log(self, level: CoreTaskLogLevel, msg: str) -> None:
        """One row in core_tasks_logs + a copy to the ``tasks`` and ``tasks/<code>`` file channels.

        Every call gets its own session with an immediate commit, so the log survives
        the task being dropped on TTL. A DB write error is swallowed.
        """
        log = self._file_log
        try:
            await crud_tasks_logs.create(
                task_id=self.task_id, level=level, message=msg
            )
        except Exception:
            log.exception("failed to write task log")
        sys_method = getattr(log, _SYS_LEVELS[level])
        sys_method("[%s.%s#%d] %s", self.module, self.code, self.task_id, msg)

    async def debug(self, msg: str, *args: Any) -> None:
        await self._write_log(CoreTaskLogLevel.debug, msg % args if args else msg)

    async def info(self, msg: str, *args: Any) -> None:
        await self._write_log(CoreTaskLogLevel.info, msg % args if args else msg)

    async def warn(self, msg: str, *args: Any) -> None:
        await self._write_log(CoreTaskLogLevel.warn, msg % args if args else msg)

    async def error(self, msg: str, *args: Any) -> None:
        await self._write_log(CoreTaskLogLevel.error, msg % args if args else msg)


__all__ = ["TaskContext"]
