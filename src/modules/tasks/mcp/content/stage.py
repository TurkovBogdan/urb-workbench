"""Content field of a plan stage: its ``body``, the work of the step in full.

``title`` and ``description`` are set whole by ``stage_update``; ``evidence`` is written by
``stage_close`` together with the closing, and is not content.
"""

from __future__ import annotations

from src.modules.tasks.constants import BODY_MAX, STAGE_CODE_PREFIX
from src.modules.tasks.mcp.content.base import McpContentHandler
from src.modules.tasks.models.stage import TasksStage


class McpStageBodyHandler(McpContentHandler):
    prefix = STAGE_CODE_PREFIX
    model = TasksStage
    field = "body"
    limit = BODY_MAX
    what = "the stage body"
    overflow_hint = "A step that does not fit is two steps — split it with stage_add."


__all__ = ["McpStageBodyHandler"]
