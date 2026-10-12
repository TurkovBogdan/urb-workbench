"""Content of what a task holds — the task itself, its stages, its journal entries, its notes.

They share one rule, and it is the ``tasks`` module's (``tasks/rules.py``): a deleted task is
closed for edits, and so is everything hanging off it. A handler here finds the owning task in the
edit's own transaction and asks that rule; the refusal it gives the agent is this surface's
wording (``entities/tasks.py::deleted_task_refusal``).
"""

from __future__ import annotations

from typing import ClassVar

from src.modules.tasks.models.task import TasksTask
from src.modules.tasks.rules import task_accepts_edits
from src.modules.workbench.content.base import McpContentHandler
from src.modules.workbench.entities.tasks import deleted_task_refusal


class McpTaskOwnedContentHandler(McpContentHandler):
    """A content field on a row that belongs to a task — ``model`` is the row's table."""

    model: ClassVar[type]

    async def load(self, s, bare: str):
        return await s.get(self.model, bare)

    def task_code_of(self, row) -> str:
        """The task the row belongs to: a stage and a journal entry carry it in ``task_code``."""
        return row.task_code

    async def owning_task(self, s, row, code: str) -> TasksTask:
        """The task row the edited row belongs to, read in the edit's own transaction."""
        return await s.get(TasksTask, self.task_code_of(row))

    async def check_row(self, s, row, code: str) -> None:
        task = row if isinstance(row, TasksTask) else await self.owning_task(s, row, code)
        self.check(row, task, code)

    def check(self, row, task: TasksTask, code: str) -> None:
        """May the field be edited now. A deleted task is the person's to restore, not to edit."""
        if not task_accepts_edits(task):
            raise ValueError(deleted_task_refusal(task.code))


__all__ = ["McpTaskOwnedContentHandler"]
