"""Content field of a journal entry: its ``body``, the detail behind the one-line subject.

``title`` is set once by ``journal_add``; ``resolution`` is written by ``journal_resolve``
together with the closing, once, and is not content.
"""

from __future__ import annotations

from src.modules.tasks.constants import JOURNAL_BODY_MAX, JOURNAL_CODE_PREFIX
from src.modules.tasks.mcp.content.base import McpContentHandler
from src.modules.tasks.models.journal import TasksJournal


class McpJournalBodyHandler(McpContentHandler):
    prefix = JOURNAL_CODE_PREFIX
    model = TasksJournal
    field = "body"
    limit = JOURNAL_BODY_MAX
    what = "the journal entry body"
    overflow_hint = "An entry is one point; a second point is a second entry."


__all__ = ["McpJournalBodyHandler"]
