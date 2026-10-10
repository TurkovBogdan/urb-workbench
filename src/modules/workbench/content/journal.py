"""Content field of a journal entry: its ``body``, the detail behind the one-line subject.

``title`` is set once by ``journal_add``; ``resolution`` is written by ``journal_resolve``
together with the closing, once, and is not content.
"""

from __future__ import annotations

from src.modules.tasks.models.journal import TasksJournal
from src.modules.tasks.rules import JOURNAL_BODY_LIMIT
from src.modules.workbench.content.task_owned import McpTaskOwnedContentHandler
from src.modules.workbench.entities.tasks import JournalFence


class McpJournalBodyHandler(JournalFence, McpTaskOwnedContentHandler):
    model = TasksJournal
    field = "body"
    limit = JOURNAL_BODY_LIMIT
    what = "the journal entry body"
    overflow_hint = "An entry is one point; a second point is a second entry."


__all__ = ["McpJournalBodyHandler"]
