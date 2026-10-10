"""Content field of a plan stage: its ``body``, the work of the step in full.

``title`` and ``description`` are set whole by ``stage_update``; ``evidence`` is written by
``stage_close`` together with the closing, and is not content.
"""

from __future__ import annotations

from src.modules.tasks.models.stage import TasksStage
from src.modules.tasks.rules import STAGE_BODY_LIMIT
from src.modules.workbench.content.task_owned import McpTaskOwnedContentHandler
from src.modules.workbench.entities.tasks import StageFence


class McpStageBodyHandler(StageFence, McpTaskOwnedContentHandler):
    model = TasksStage
    field = "body"
    limit = STAGE_BODY_LIMIT
    what = "the stage body"
    overflow_hint = "A step that does not fit is two steps — split it with stage_add."


__all__ = ["McpStageBodyHandler"]
