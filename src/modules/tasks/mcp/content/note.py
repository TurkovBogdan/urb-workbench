"""Content field of a journal entry: its ``body``, the detail behind the one-line subject.

``title`` is set once by ``note_add``; ``resolution`` is written by ``note_resolve`` together
with the closing, once, and is not content.
"""

from __future__ import annotations

from src.modules.tasks.constants import NOTE_BODY_MAX, NOTE_CODE_PREFIX
from src.modules.tasks.mcp.content.base import McpContentHandler
from src.modules.tasks.models.note import TasksNote


class McpNoteBodyHandler(McpContentHandler):
    prefix = NOTE_CODE_PREFIX
    model = TasksNote
    field = "body"
    limit = NOTE_BODY_MAX
    what = "the journal entry body"
    overflow_hint = "An entry is one point; a second point is a second entry."


__all__ = ["McpNoteBodyHandler"]
