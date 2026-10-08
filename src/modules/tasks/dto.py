"""DTOs of the ``tasks`` module — the contracts of both surfaces: the web viewer and the agent.

**The ``Agent`` prefix = the agent surface.** A class with this prefix is returned by MCP tools
(``mcp/``) and nothing else; everything else is a web-viewer contract. The boundary is total: the
surfaces share no contracts even where the field sets coincide. A shared contract drifts one way —
a field added for a table column silently starts costing the agent context in every session.

Agent classes have no docstring on purpose: pydantic puts it into the tool's JSON schema as the
description, and the agent pays for it on every connection. So the notes on agent contracts live
in comments ABOVE the class.

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
from src.modules.workspace.dto import AgentScope

# Presentation code type: bare hash inside, ``WORKSPACE@<hash>`` outside. The workspace prefix is
# taken from its module: should it rename its type word, the reference follows on its own.
WorkspaceCode = prefixed(WORKSPACE_CODE_PREFIX)
GroupCode = prefixed(GROUP_CODE_PREFIX)
TaskCode = prefixed(TASK_CODE_PREFIX)
StageCode = prefixed(STAGE_CODE_PREFIX)
JournalCode = prefixed(JOURNAL_CODE_PREFIX)
NoteCode = prefixed(NOTE_CODE_PREFIX)


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

    There is no separate "open" flag: it is derived from an empty ``resolution``, and keeping a
    computable flag alongside would create a second source of truth for the same thing.
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


# A group as the agent sees it: where to put a task and what is already there. No styling (color,
# icon) — the UI draws those, they would tell the agent nothing and cost two fields in every
# response row; the surfaces are separated and will share no contract even where the field sets
# coincide. ``description``, by contrast, is essential: it holds the group's boundaries, and by
# them the agent decides where a new task goes — by the title alone it errs more often.
class AgentGroupRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: GroupCode
    title: str
    description: str = ""
    task_count: int = 0


# Groups of the active workspace — together with which workspace it was (``AgentScope``).
# The same type answers layout edits too: after creating or reordering a group the agent needs
# not an echo of what it sent but the new state of the list — its edit shifted the counts and the
# order, and otherwise it would fetch them with a second call.
class AgentGroupList(AgentScope):
    groups: list[AgentGroupRow] = []


# The layout after moving a batch of tasks: the same groups plus how many rows landed. Task codes
# do not come back — the agent just sent them itself; the counts of both affected groups it does
# not know.
class AgentTasksRegrouped(AgentGroupList):
    moved: int = 0


# ── task ──────────────────────────────────────────────────────────────────────
# A scanning-layer row: what one picks the next thing to take on by. No brief and no plan here —
# those come from ``task_get``; pulling them for the whole list costs more than reading the list
# twice. ``description`` (the goal) stays: without it a row answers only "what is it called",
# while the decision is made on "what will become true".
class AgentTaskRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: TaskCode
    title: str
    description: str = ""
    status: str
    priority: str
    type: str
    group_code: GroupCode | None = None
    parent_code: TaskCode | None = None
    has_children: bool = False
    deadline_at: DatetimeUTCStr | None = None


# ``shown`` versus ``total`` — the output cap shown as a number, not as a default in the schema.
# The gap is visible at once, and the description says what to narrow; a ``limit`` argument would
# cost a field in every call for something one response line settles.
class AgentTaskList(AgentScope):
    tasks: list[AgentTaskRow] = []
    shown: int = 0
    total: int = 0


# A plan stage: a step with its own state and its own evidence.
class AgentStageRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: StageCode
    number: int
    status: str
    title: str
    description: str = ""
    body: str = ""
    evidence: str = ""


# A journal entry. There is no "open" flag — it is derived from an empty ``resolution``, and
# keeping a computable flag alongside would create a second source of truth for the same thing.
class AgentJournalRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: JournalCode
    type: str
    title: str
    body: str = ""
    resolution: str = ""
    stage_code: StageCode | None = None
    created_at: DatetimeUTCStr


# A task note as the task lists it: what it is and when it changed, never its text — the agent
# decides by the description whether to open it with task_note_get.
class AgentTaskNoteRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: NoteCode
    title: str
    description: str = ""
    updated_at: DatetimeUTCStr


# A task note whole: the document and the task it belongs to.
class AgentTaskNote(AgentScope):
    code: NoteCode
    task_code: TaskCode
    title: str
    description: str = ""
    body: str = ""
    updated_at: DatetimeUTCStr


# A task note after task_note_update: the scan layer, without the text the agent did not touch.
class AgentTaskNoteUpdated(AgentScope):
    code: NoteCode
    task_code: TaskCode
    title: str
    description: str = ""
    updated_at: DatetimeUTCStr


class AgentTaskNoteCreated(AgentScope):
    code: NoteCode


# The work screen: brief, plan, stages and whatever is still open.
#
# Closed journal entries are not here, only their count: they answer "how did we get here", which
# is asked separately and rarely. A long task's journal outgrows its brief, and shipping it on
# every read means paying for what is read once.
#
# The group and the parent travel as code AND title: the agent does not open the page, and a title
# cannot be got from a code — it would have to call two more tools for two lines of text.
class AgentTaskDetail(AgentScope):
    code: TaskCode
    title: str
    description: str = ""
    context: str = ""
    constraints: str = ""
    criteria: str = ""
    plan: str = ""
    progress: str = ""
    result: str = ""
    status: str
    priority: str
    type: str
    created_by: str
    group_code: GroupCode | None = None
    group_title: str = ""
    parent_code: TaskCode | None = None
    parent_title: str = ""
    deadline_at: DatetimeUTCStr | None = None
    started_at: DatetimeUTCStr | None = None
    completed_at: DatetimeUTCStr | None = None
    canceled_at: DatetimeUTCStr | None = None
    children: list[AgentTaskRow] = []
    stages: list[AgentStageRow] = []
    open_entries: list[AgentJournalRow] = []
    closed_entries: int = 0
    unfinished_stages: int = 0
    notes: list[AgentTaskNoteRow] = []


# A creation receipt: the code and the workspace, nothing more. The agent would pay for an echo of
# its own input on every created row, and it knows that input already.
class AgentTaskCreated(AgentScope):
    code: TaskCode


class AgentStageCreated(AgentScope):
    code: StageCode
    number: int


class AgentJournalCreated(AgentScope):
    code: JournalCode


# A status change response carries not only the new status but also what still hangs on the
# task: this is the one moment the agent thinks about it. ``blocking_entries`` are the open
# journal entries the executor settles (decision and remark); ``open_entries`` additionally counts
# findings, which the person triages. Neither refuses the hand-off — they are counted.
class AgentTaskStatus(AgentScope):
    code: TaskCode
    status: str
    open_entries: int = 0
    blocking_entries: int = 0
    unfinished_stages: int = 0


# A stage edit response carries the TASK status next to the stage status: starting a stage does
# not move the task, and without this line the mismatch is visible only to whoever watches for it.
class AgentStageChanged(AgentScope):
    stage: AgentStageRow
    task_code: TaskCode
    task_status: str


class AgentJournalList(AgentScope):
    entries: list[AgentJournalRow] = []


# ── content editor ────────────────────────────────────────────────────────────
# A content edit answers with what the agent does not know yet. The text it sent does not come
# back in any form: it has just written it, and an echo would cost on every edit. ``code`` and
# ``field`` name what was edited, so a log of answers reads on its own.
#
# ``content_set`` is a receipt: the field is exactly the sent text, there is no seam, and all
# there is to report is the new length (which also shows how much room is left below the cap — and
# the cap refuses, it does not truncate).
class AgentContentSet(BaseModel):
    code: str
    field: str
    length: int


# A seam is a window of the field on both sides of the edit with a placeholder in place of the
# text. It shows exactly what could not be foreseen: what the insertion butted against on the left
# and on the right.
class AgentContentAdded(BaseModel):
    code: str
    field: str
    edit: str


# ``replaced`` equals the length of ``edits``: seams come in document order, one per occurrence.
class AgentContentReplaced(BaseModel):
    code: str
    field: str
    replaced: int
    edits: list[str] = []


# For a section edit the unpredictable part is not the joint but the extent of the cut: the server
# computes the boundary from the heading level. So the response shows what was removed, its real
# length and the heading where the cut stopped. A section thought to be short that comes back long
# is a cut that went further than intended, and this is the only place to notice it: the removed
# text is not saved anywhere.
class AgentContentSectionSet(BaseModel):
    code: str
    field: str
    removed: str
    removed_length: int
    stopped_at: str | None = None


__all__ = [
    "AgentContentAdded",
    "AgentContentReplaced",
    "AgentContentSectionSet",
    "AgentContentSet",
    "AgentGroupList",
    "AgentGroupRow",
    "AgentJournalCreated",
    "AgentJournalList",
    "AgentJournalRow",
    "AgentStageChanged",
    "AgentStageCreated",
    "AgentStageRow",
    "AgentTaskCreated",
    "AgentTaskDetail",
    "AgentTaskList",
    "AgentTaskNote",
    "AgentTaskNoteCreated",
    "AgentTaskNoteRow",
    "AgentTaskNoteUpdated",
    "AgentTaskRow",
    "AgentTaskStatus",
    "AgentTasksRegrouped",
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
    "TaskListRow",
    "TaskNoteRow",
    "TaskRow",
    "WorkspaceCode",
]
