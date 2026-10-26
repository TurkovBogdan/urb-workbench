"""DTOs of the ``tasks`` module — the web viewer's contracts.

The agent's contracts are not here: they belong to the agent surface, the ``workbench`` module
(``workbench/dto.py``). The code types below (``TaskCode``…) are shared with it — the type word
belongs to the entity's owner. The two surfaces share no contracts beyond that, even where the
field sets coincide: a shared contract drifts one way — a field added for a table column silently
starts costing the agent context in every session.

A code in the output carries a presentation prefix (``WORKSPACE@…``) — that is the job of
``prefixed`` from ``tasks.codes``: the serializer puts the type word on only in JSON, the internal
``model_dump()`` stays bare. On input a code is accepted in both forms — ``bare_code`` strips the
prefix at the endpoint boundary, not here: a DTO describes the response, parsing an address is the
route's job.

Dates are emitted via the core ``DatetimeUTCStr`` (SQL format without ``T``) — exactly what the
frontend parser ``web/src/shared/utils/date.ts`` (Luxon ``fromSQL``) expects. It does not parse
ISO with ``T``, and the date on a card would silently turn "invalid".

There is no workspace card here: it lives in the ``workspace`` module alongside the entity itself.
Only a REFERENCE to it goes out from here — ``workspace_code`` with a prefix built from another
module's constant: the type word belongs to the entity's owner, not to whoever references it.

A task's place in the tree travels **in the same row** as its fields (``parent_code`` / ``sort``),
even though in the DB they sit in a separate table (``tasks_link``). The split is needed for
writing (moving a branch does not rewrite the card), not for reading: the list needs both halves
at once anyway, and would have made a second request for the edges regardless.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from src.core.utils.date import DatetimeUTCStr
from src.modules.tasks.codes import prefixed
from src.modules.tasks.constants import (
    FILE_CODE_PREFIX,
    GROUP_CODE_PREFIX,
    JOURNAL_CODE_PREFIX,
    NOTE_CODE_PREFIX,
    SORT_DEFAULT,
    STAGE_CODE_PREFIX,
    TASK_CODE_PREFIX,
    TASK_PRIORITY_DEFAULT,
    TASK_STATUS_DEFAULT,
    TASK_TYPE_DEFAULT,
)
from src.modules.workspace.constants import WORKSPACE_CODE_PREFIX

# Presentation code type: bare hash inside, ``WORKSPACE@<hash>`` outside. The workspace prefix is
# taken from its module: should it rename its type word, the reference follows on its own.
WorkspaceCode = prefixed(WORKSPACE_CODE_PREFIX)
GroupCode = prefixed(GROUP_CODE_PREFIX)
TaskCode = prefixed(TASK_CODE_PREFIX)
StageCode = prefixed(STAGE_CODE_PREFIX)
JournalCode = prefixed(JOURNAL_CODE_PREFIX)
NoteCode = prefixed(NOTE_CODE_PREFIX)
FileCode = prefixed(FILE_CODE_PREFIX)


class GroupRow(BaseModel):
    """A task group — a section header in the task list and a card in its own section."""

    model_config = ConfigDict(from_attributes=True)

    code: GroupCode
    workspace_code: WorkspaceCode
    title: str
    description: str = ""
    color: str = ""
    icon: str = ""
    sort: int = SORT_DEFAULT
    created_at: DatetimeUTCStr
    updated_at: DatetimeUTCStr
    deleted_at: DatetimeUTCStr | None = None


class GroupListRow(GroupRow):
    """A group list row: the card plus a count of the live tasks inside.

    The count is here for the same reason as on the workspace: a group exists to hold something,
    and "delete" without a number would be asking to confirm the unknown.
    """

    task_count: int = 0


class TaskRow(BaseModel):
    """The task's own fields — everything in ``tasks`` except the brief and the work text.

    The long text is left out on purpose: the list shows not a single line of it, yet it outweighs
    the rest of the card combined. Only the detail (``TaskDetail``) returns it.

    Phase timestamps (``started_at`` / ``completed_at`` / ``canceled_at``) travel in the list too:
    it is the only way to tell "done yesterday" from "done in March" without opening the task.
    """

    model_config = ConfigDict(from_attributes=True)

    code: TaskCode
    workspace_code: WorkspaceCode
    group_code: GroupCode | None = None
    type: str = TASK_TYPE_DEFAULT
    status: str = TASK_STATUS_DEFAULT
    priority: str = TASK_PRIORITY_DEFAULT
    title: str
    description: str = ""
    created_by: str
    deadline_at: DatetimeUTCStr | None = None
    started_at: DatetimeUTCStr | None = None
    completed_at: DatetimeUTCStr | None = None
    canceled_at: DatetimeUTCStr | None = None
    created_at: DatetimeUTCStr
    updated_at: DatetimeUTCStr
    deleted_at: DatetimeUTCStr | None = None


class TaskListRow(TaskRow):
    """A list row: the task card plus its place in the tree and a flag for a branch beneath it.

    ``has_children`` is a flag, not a count: the list uses it to draw a "there is more inside"
    mark, there is nowhere to show the exact number, and counting it per row would mean paying for
    something invisible. The list itself is flat: the detail unfolds the tree.
    """

    parent_code: TaskCode | None = None
    sort: int = SORT_DEFAULT
    has_children: bool = False


class StageRow(BaseModel):
    """A plan stage — a row of the canvas and a card in the task detail."""

    model_config = ConfigDict(from_attributes=True)

    code: StageCode
    task_code: TaskCode
    number: int
    status: str
    title: str
    description: str = ""
    body: str = ""
    evidence: str = ""
    started_at: DatetimeUTCStr | None = None
    finished_at: DatetimeUTCStr | None = None
    created_at: DatetimeUTCStr
    updated_at: DatetimeUTCStr


class JournalRow(BaseModel):
    """A journal entry: the subject (``title`` + ``body``) and the resolution.

    There is no separate "open" flag: it is derived from an empty ``resolution`` on a kind that
    waits for one (a ``fact`` never does), and keeping a computable flag alongside would create a
    second source of truth for the same thing.
    """

    model_config = ConfigDict(from_attributes=True)

    code: JournalCode
    task_code: TaskCode
    stage_code: StageCode | None = None
    type: str
    title: str
    body: str = ""
    resolution: str = ""
    created_at: DatetimeUTCStr


class TaskNoteRow(BaseModel):
    """A task note in the task's list: the document's scan layer, without its text.

    The text is read and saved on the document's own route (``/internal/notes/{code}``): a task
    with three 64K documents would otherwise carry them on every open of its page.
    """

    model_config = ConfigDict(from_attributes=True)

    code: NoteCode
    title: str
    description: str = ""
    created_at: DatetimeUTCStr
    updated_at: DatetimeUTCStr


class TaskNoteDetail(TaskNoteRow):
    """A task note whole — its page: the text, and the task it belongs to."""

    task_code: TaskCode
    body: str = ""


class TaskFileRow(BaseModel):
    """A file in the task's list: the binding, and what the storage knows of the file.

    ``title`` empty — the file is shown under the name it came in with,
    ``original_filename + original_extension``. ``note_code`` / ``stage_code`` — where in the task
    it was attached; both empty — the task as a whole. The list holds the files of the task's
    notes and stages too: a file is in the task once.
    """

    code: FileCode
    task_code: TaskCode
    note_code: NoteCode | None = None
    stage_code: StageCode | None = None
    title: str = ""
    description: str = ""
    original_filename: str = ""
    original_extension: str = ""
    mime: str
    type: str
    size: int
    sort: int = SORT_DEFAULT
    created_at: DatetimeUTCStr
    updated_at: DatetimeUTCStr


class TaskDetail(TaskListRow):
    """The whole task: brief, plan, tree neighbours, group, stages, journal and notes.

    Children are the same list rows (with their own edges and branch flag), so a child's card on
    the detail and a card in the list are one and the same object: their markup has nowhere to
    diverge.

    The group and the parent travel as rows, not just codes, although the codes are in the
    response too. The reason is practical: the page shows them by NAME ("Billing", "Invoices"),
    and a name cannot be got from a code — the client would have to make two extra requests on
    every task open for two lines of text. The codes stay anyway: editing and moving work by them.

    Stages and the journal travel here as well: the task detail is the work screen, and the client
    would make a second request for the plan regardless. A simple task has both lists empty —
    there is simply no one to create them.
    """

    context: str = ""
    constraints: str = ""
    criteria: str = ""
    plan: str = ""
    progress: str = ""
    result: str = ""
    group: GroupRow | None = None
    parent: TaskListRow | None = None
    children: list[TaskListRow] = []
    stages: list[StageRow] = []
    journal: list[JournalRow] = []
    notes: list[TaskNoteRow] = []


__all__ = [
    "FileCode",
    "GroupCode",
    "GroupListRow",
    "GroupRow",
    "JournalCode",
    "JournalRow",
    "NoteCode",
    "StageCode",
    "StageRow",
    "TaskCode",
    "TaskDetail",
    "TaskFileRow",
    "TaskListRow",
    "TaskNoteDetail",
    "TaskNoteRow",
    "TaskRow",
    "WorkspaceCode",
]
