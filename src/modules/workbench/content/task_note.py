"""Content field of a task note: its ``body``, the document itself.

The row is the ``notes`` module's, and so is the rule that a deleted note takes no edits
(``notes/rules.py``); the task it belongs to is found through ``tasks_note``.
``title`` and ``description`` are not content — ``task_note_update`` sets them whole.
"""

from __future__ import annotations

from src.modules.notes.models.note import Note
from src.modules.notes.rules import NOTE_BODY_LIMIT, note_accepts_edits
from src.modules.tasks.crud.note import task_note_owner
from src.modules.tasks.models.task import TasksTask
from src.modules.workbench.content.task_owned import McpTaskOwnedContentHandler
from src.modules.workbench.entities.tasks import NoteFence


class McpTaskNoteBodyHandler(NoteFence, McpTaskOwnedContentHandler):
    model = Note
    field = "body"
    limit = NOTE_BODY_LIMIT
    what = "the task note body"
    overflow_hint = "A document past this size is two documents: split it with task_note_add."

    async def owning_task(self, s, row, code: str) -> TasksTask:
        """A note is edited here only as a task note — one held by no task does not exist here."""
        task = await task_note_owner(s, row.code)
        if task is None:
            raise ValueError(f"{code} does not exist.")
        return task

    def check(self, row, task, code: str) -> None:
        super().check(row, task, code)
        if not note_accepts_edits(row):
            raise ValueError(f"{code} is deleted — a person restores it, then it can be edited.")


__all__ = ["McpTaskNoteBodyHandler"]
