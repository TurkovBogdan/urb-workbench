"""Content field of a task note: its ``body``, the document itself.

The row is the ``notes`` module's; the task it belongs to is found through ``tasks_note``.
``title`` and ``description`` are not content — ``task_note_update`` sets them whole.
"""

from __future__ import annotations

from sqlalchemy import select

from src.modules.notes.constants import BODY_MAX
from src.modules.notes.models.note import Note
from src.modules.tasks.constants import NOTE_CODE_PREFIX
from src.modules.tasks.mcp.content.base import McpContentHandler
from src.modules.tasks.models.note import TasksNote
from src.modules.tasks.models.task import TasksTask


class McpTaskNoteBodyHandler(McpContentHandler):
    prefix = NOTE_CODE_PREFIX
    model = Note
    field = "body"
    limit = BODY_MAX
    what = "the task note body"
    overflow_hint = "A document past this size is two documents: split it with task_note_add."

    async def owning_task(self, s, row, code: str) -> TasksTask:
        """A note is edited here only as a task note — one held by no task does not exist here."""
        stmt = select(TasksTask).join(TasksNote, TasksNote.task_code == TasksTask.code).where(
            TasksNote.note_code == row.code
        )
        task = (await s.execute(stmt)).scalar_one_or_none()
        if task is None:
            raise ValueError(f"{code} does not exist.")
        return task

    def check(self, row, task, code: str) -> None:
        super().check(row, task, code)
        if row.deleted_at is not None:
            raise ValueError(f"{code} is deleted — a person restores it, then it can be edited.")


__all__ = ["McpTaskNoteBodyHandler"]
