"""The registry of content handlers: which field of which entity ``content_*`` edits, and how.

The key is the code prefix and the field name — the column the agent sees in the answers. A new
content field, or a new entity type with content, is a handler class and a line here; the tools
do not change.

A miss is a refusal that teaches. A field that exists but is not content (``title``,
``evidence``…) names the tool that does set it; an unknown field lists what this type has.
"""

from __future__ import annotations

from src.modules.tasks.codes import code_prefix
from src.modules.tasks.constants import JOURNAL_CODE_PREFIX, STAGE_CODE_PREFIX, TASK_CODE_PREFIX
from src.modules.tasks.mcp.content.base import McpContentHandler
from src.modules.tasks.mcp.content.journal import McpJournalBodyHandler
from src.modules.tasks.mcp.content.stage import McpStageBodyHandler
from src.modules.tasks.mcp.content.task import (
    McpTaskConstraintsHandler,
    McpTaskContextHandler,
    McpTaskCriteriaHandler,
    McpTaskPlanHandler,
    McpTaskProgressHandler,
    McpTaskResultHandler,
)

MCP_CONTENT_HANDLERS: dict[tuple[str, str], McpContentHandler] = {
    (handler.prefix, handler.field): handler
    for handler in (
        McpTaskContextHandler(),
        McpTaskConstraintsHandler(),
        McpTaskCriteriaHandler(),
        McpTaskPlanHandler(),
        McpTaskProgressHandler(),
        McpTaskResultHandler(),
        McpStageBodyHandler(),
        McpJournalBodyHandler(),
    )
}

# Fields that exist but are not content — and where they are set instead. The refusal names the
# tool: "not here" without "but there" leaves the agent to guess.
_SET_ELSEWHERE = {
    (TASK_CODE_PREFIX, "title"): "task_update",
    (TASK_CODE_PREFIX, "description"): "task_update",
    (STAGE_CODE_PREFIX, "title"): "stage_update",
    (STAGE_CODE_PREFIX, "description"): "stage_update",
    (STAGE_CODE_PREFIX, "evidence"): "stage_close, together with closing the stage",
    (JOURNAL_CODE_PREFIX, "title"): "journal_add, once — a changed point is a new entry",
    (JOURNAL_CODE_PREFIX, "resolution"): "journal_resolve, once, together with closing the entry",
}

_PREFIXES = tuple(dict.fromkeys(prefix for prefix, _ in MCP_CONTENT_HANDLERS))


def content_fields(prefix: str) -> list[str]:
    """The content fields of one entity type, in registry order."""
    return [field for (owner, field) in MCP_CONTENT_HANDLERS if owner == prefix]


def handler_for(code: str, field: str) -> McpContentHandler:
    """The handler of ``field`` on the entity ``code`` names, or a refusal saying what to pass."""
    prefix = code_prefix(code)
    if prefix not in _PREFIXES:
        raise ValueError(
            f"{code!r} has no content to edit — content_* works on "
            f"{' / '.join(f'{p}@' for p in _PREFIXES)} codes."
        )
    handler = MCP_CONTENT_HANDLERS.get((prefix, field))
    if handler is not None:
        return handler
    fields = ", ".join(content_fields(prefix))
    elsewhere = _SET_ELSEWHERE.get((prefix, field))
    if elsewhere is not None:
        raise ValueError(
            f"{field!r} of a {prefix}@ is not content — it is set with {elsewhere}. "
            f"Content fields of a {prefix}@: {fields}."
        )
    raise ValueError(f"A {prefix}@ has no content field {field!r}. Its content fields: {fields}.")


__all__ = ["MCP_CONTENT_HANDLERS", "content_fields", "handler_for"]
