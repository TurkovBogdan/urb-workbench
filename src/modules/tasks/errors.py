"""Module rule refusals that have a name.

A plain ``ValueError`` from CRUD travels out as text — enough while the reader is the agent: the
text is in English, names the cause, and the agent fixes the call itself. But two refusals are
read by a PERSON in the interface, and an English phrase from deep inside the data layer is out
of place there.

So they carry a code: CRUD raises ``TaskRuleError`` with the rule's name, the API puts that name
into the response's ``code`` field, and the interface shows its own wording in its own language.
The exception text stays as it was — it is needed in logs and in replies to the agent, which does
not read the code.

A new code is introduced together with the rule it names, and goes into the interface dictionary
(``tasks.error.*``). A code without a translation does not break display: the interface falls
back to the response text.
"""

from __future__ import annotations

STAGE_EVIDENCE_REQUIRED = "stage_evidence_required"
"""The stage cannot be closed: its evidence of completion is empty."""

JOURNAL_ALREADY_RESOLVED = "journal_already_resolved"
"""The journal entry is already resolved: a resolution is written once."""

# HTTP-layer refusals: a person reads these too. The interface looks code
# ``tasks.<entity>.<reason>`` up as ``tasks.error.<entity>.<reason>``; the response text is the
# English fallback.
GROUP_NOT_FOUND = "tasks.group.not_found"
GROUP_DELETED = "tasks.group.deleted"
GROUP_NOT_DELETED = "tasks.group.not_deleted"
GROUP_HAS_TASKS = "tasks.group.has_tasks"
"""The group still holds live tasks, and the deletion did not say what becomes of them."""
TASK_NOT_FOUND = "tasks.task.not_found"
TASK_DELETED = "tasks.task.deleted"
TASK_NOT_DELETED = "tasks.task.not_deleted"
STAGE_NOT_FOUND = "tasks.stage.not_found"
JOURNAL_NOT_FOUND = "tasks.journal.not_found"
NOTE_NOT_FOUND = "tasks.note.not_found"
FILE_NOT_FOUND = "tasks.file.not_found"
"""The file is not in this task."""
FILE_ALREADY_ATTACHED = "tasks.file.already_attached"
"""The file is in the task already — a file is in a task once."""
FILE_FOREIGN_PLACE = "tasks.file.foreign_place"
"""The note or the stage named as the file's place is not a live one of this task, or both are named."""
FILE_NOT_STORED = "tasks.file.not_stored"
"""No file under this code in the storage."""
FILE_FOREIGN_STORE = "tasks.file.foreign_store"
"""The stored file lies in a store other than the one task files are served from."""
FILE_CONTROL_CHARACTER = "tasks.file.control_character"
"""A file's title or description holds a control character (``params.field`` names which)."""


class TaskRuleError(ValueError):
    """A module rule refusal with a machine-readable name.

    It subclasses ``ValueError`` on purpose: all of CRUD already raises that, and the API
    handlers catch it with a single ``except`` — adding a code must not require a second branch
    in every endpoint.

    ``params`` — what a surface needs to word the refusal or act on it, as ``ApiError`` carries
    them: the file a task holds already, so the page can quote it instead of failing.
    """

    def __init__(self, code: str, message: str, *, params: dict[str, str | int] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.params = params or {}


__all__ = [
    "FILE_ALREADY_ATTACHED",
    "FILE_CONTROL_CHARACTER",
    "FILE_FOREIGN_PLACE",
    "FILE_FOREIGN_STORE",
    "FILE_NOT_FOUND",
    "FILE_NOT_STORED",
    "GROUP_DELETED",
    "GROUP_HAS_TASKS",
    "GROUP_NOT_DELETED",
    "GROUP_NOT_FOUND",
    "JOURNAL_ALREADY_RESOLVED",
    "JOURNAL_NOT_FOUND",
    "NOTE_NOT_FOUND",
    "STAGE_EVIDENCE_REQUIRED",
    "STAGE_NOT_FOUND",
    "TASK_DELETED",
    "TASK_NOT_DELETED",
    "TASK_NOT_FOUND",
    "TaskRuleError",
]
