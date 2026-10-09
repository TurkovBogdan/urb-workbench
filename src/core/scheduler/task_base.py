"""Base class of a scheduler task.

The lightweight variant: only declarative fields + a shared ``register()``. The run
logic lives in the subclass's ``handle(ctx)``.
"""

from __future__ import annotations

from src.core.loggers import get_logger
from src.core.loggers.logger_protocol import CoreLoggerProtocol
from src.core.scheduler.context import TaskContext
from src.core.scheduler.registry import get_registry


class CoreTaskBase:
    """Declarative base of a scheduler task.

    A subclass sets the class attributes and implements ``handle``. ``register()``
    assembles the registration from those attributes — no copy-pasted
    ``scheduler.register(...)`` calls.
    """

    MODULE: str
    CODE: str
    NAME: str
    DESCRIPTION: str
    SCHEDULE: str | None  # 5-field cron; None → automatic runs disabled
    TTL: int              # seconds; both the handler timeout and the task lock TTL
    ENABLED: bool = True
    USER_REQUEST: bool = False
    SORT: int = 500    # display order in the UI; does not affect execution

    @classmethod
    def logger(cls) -> CoreLoggerProtocol:
        """The task's tee logger: the shared ``tasks`` channel + its own ``tasks/<CODE>``.

        The same one the runner and TaskContext use — lines from the handler and
        from inner layers (importers, services) land in one and the same file
        ``logs/tasks/<CODE>.log``. Unlike ``ctx.info/warn`` it does not write to the
        DB (``core_tasks_logs``) — this is "technical" logging.
        """
        return get_logger("tasks", f"tasks/{cls.CODE}")

    @classmethod
    def register(cls) -> None:
        get_registry().register(
            module=cls.MODULE,
            code=cls.CODE,
            name=cls.NAME,
            description=cls.DESCRIPTION,
            schedule=cls.SCHEDULE,
            handler=cls.handle,
            ttl=cls.TTL,
            enabled=cls.ENABLED,
            user_request=cls.USER_REQUEST,
            sort=cls.SORT,
        )

    @staticmethod
    async def handle(ctx: TaskContext) -> None:
        raise NotImplementedError


__all__ = ["CoreTaskBase"]
