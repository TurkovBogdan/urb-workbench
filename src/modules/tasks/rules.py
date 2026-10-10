"""What a task's long texts may hold, and when they may be edited at all — one answer for every
surface.

The rules belong to the data, not to whoever writes it: the person in the browser (``api.py``)
and the agent (the ``workbench`` module) reach the same rows, and a rule kept inside one surface
is a rule the other one does not have. So the decision lives here; the wording of a refusal does
not — the HTTP API answers with a code the interface translates, the agent surface with a phrase
that names the tool to call instead, and both are said where they are read.

- **A deleted task is closed for edits** until a person restores it — its fields, and everything
  hanging off it (stages, journal entries, notes).
- **The type decides which fields a task has.** A ``simple`` task is a title, a goal and the
  context; the rest of the brief and the executor's work exist from ``standard`` up. Its page
  shows nothing else, so text written there would be seen by nobody.
- **The long texts have caps,** and each cap is the column's own width (``constants.py``).
"""

from __future__ import annotations

from src.modules.tasks.constants import (
    BODY_MAX,
    CONSTRAINTS_MAX,
    CONTEXT_MAX,
    CRITERIA_MAX,
    JOURNAL_BODY_MAX,
    PLAN_MAX,
    PROGRESS_MAX,
    RESULT_MAX,
    TASK_TYPES_WITH_PLAN,
)
from src.modules.tasks.models.task import TasksTask

# The long markdown fields of a task, in the order the work goes: the brief, then the executor's
# work. ``title`` and ``description`` are a line and a paragraph, not content.
TASK_CONTENT_LIMITS: dict[str, int] = {
    "context": CONTEXT_MAX,
    "constraints": CONSTRAINTS_MAX,
    "criteria": CRITERIA_MAX,
    "plan": PLAN_MAX,
    "progress": PROGRESS_MAX,
    "result": RESULT_MAX,
}

# The one content field every type has — the rest are the ``standard`` brief and work.
TASK_FIELDS_OF_EVERY_TYPE = ("context",)

STAGE_BODY_LIMIT = BODY_MAX
JOURNAL_BODY_LIMIT = JOURNAL_BODY_MAX


def task_accepts_edits(task: TasksTask) -> bool:
    """A task in the bin takes no edits — restoring it is the person's, and comes first."""
    return task.deleted_at is None


def task_type_has_field(task_type: str, field: str) -> bool:
    """Whether a task of ``task_type`` has the content field ``field`` at all."""
    return field in TASK_FIELDS_OF_EVERY_TYPE or task_type in TASK_TYPES_WITH_PLAN


__all__ = [
    "JOURNAL_BODY_LIMIT",
    "STAGE_BODY_LIMIT",
    "TASK_CONTENT_LIMITS",
    "TASK_FIELDS_OF_EVERY_TYPE",
    "task_accepts_edits",
    "task_type_has_field",
]
