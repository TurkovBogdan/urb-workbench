"""Content fields of a task: the brief lists and the agent's work.

The brief — ``context``, ``constraints``, ``criteria`` — is the requester's statement of the work;
``plan``, ``progress`` and ``result`` are the agent's, in the order the work goes. ``title`` and
``description`` are not content: they are a line and a paragraph, set whole by ``task_update``.
"""

from __future__ import annotations

from src.modules.tasks.constants import (
    CONSTRAINTS_MAX,
    CONTEXT_MAX,
    CRITERIA_MAX,
    PLAN_MAX,
    PROGRESS_MAX,
    RESULT_MAX,
    TASK_CODE_PREFIX,
)
from src.modules.tasks.mcp.content.base import McpContentHandler
from src.modules.tasks.models.task import TasksTask


class McpTaskContentHandler(McpContentHandler):
    """A content field of a task — the row is the task itself."""

    prefix = TASK_CODE_PREFIX
    model = TasksTask


class McpTaskContextHandler(McpTaskContentHandler):
    field = "context"
    limit = CONTEXT_MAX
    what = "the context"
    overflow_hint = "Point at files and decisions instead of retelling them."


class McpTaskConstraintsHandler(McpTaskContentHandler):
    field = "constraints"
    limit = CONSTRAINTS_MAX
    what = "the constraints"
    overflow_hint = "One line per rule; the reasoning behind one belongs in the context."


class McpTaskCriteriaHandler(McpTaskContentHandler):
    field = "criteria"
    limit = CRITERIA_MAX
    what = "the criteria"
    overflow_hint = "Five criteria that matter beat twenty that do not — merge or drop some."


class McpTaskPlanHandler(McpTaskContentHandler):
    field = "plan"
    limit = PLAN_MAX
    what = "the plan"
    overflow_hint = (
        "The end of a plan is where the files are listed, so it is never trimmed. Shorten what "
        "is already there; detail that does not fit belongs in stages (an extended task) or in "
        "a subtask."
    )


class McpTaskProgressHandler(McpTaskContentHandler):
    field = "progress"
    limit = PROGRESS_MAX
    what = "the progress"
    overflow_hint = (
        "An entry is a line or two — what is done, what comes next; decisions and findings go to "
        "the journal with note_add. Condense the oldest entries."
    )


class McpTaskResultHandler(McpTaskContentHandler):
    field = "result"
    limit = RESULT_MAX
    what = "the result"
    overflow_hint = (
        "The result says what was done, what checked it and what is left unchecked — not the "
        "story of the work, which is in the progress."
    )


__all__ = [
    "McpTaskConstraintsHandler",
    "McpTaskContentHandler",
    "McpTaskContextHandler",
    "McpTaskCriteriaHandler",
    "McpTaskPlanHandler",
    "McpTaskProgressHandler",
    "McpTaskResultHandler",
]
