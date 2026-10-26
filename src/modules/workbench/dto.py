"""DTOs of the agent surface — what the ``workbench`` MCP tools return, and nothing else does.

The web viewer's contracts stay with the modules that own the data (``workspace/dto.py``,
``tasks/dto.py``); these are the agent's. The boundary is total: the surfaces share no contracts
even where the field sets coincide — ``WorkspaceListRow`` and ``AgentWorkspaceRow`` describe the
same table row and have diverged on purpose. A shared contract drifts one way: a field added for a
table column silently starts costing the agent context in every session. The ``Agent`` prefix
stays on every class here: the names are what the tool schemas carry (``$defs``), and a client
caches them.

Agent classes have no docstring on purpose: pydantic puts it into the tool's JSON schema as the
description, and the agent pays for it on every connection. So the notes on agent contracts live
in comments ABOVE the class.

A code in the output carries a presentation prefix (``TASK@…``) through the code types of the
module that owns the entity — the type word belongs to the entity's owner, not to whoever
returns it.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from src.core.utils.date import DatetimeUTCStr
from src.modules.codex.dto import CodexCode
from src.modules.tasks.dto import FileCode, GroupCode, JournalCode, NoteCode, StageCode, TaskCode
from src.modules.workspace.dto import WorkspaceCode


def _absent(value: object) -> bool:
    return value is None


# ── workspace ─────────────────────────────────────────────────────────────────
# The workspace the call ran in — goes into every response about the work (``codex_index``,
# ``codex_get`` and ``codex_tree`` aside: they read what is mounted into the active one). Not a
# service field
# and not debugging: the agent has no other way to notice it is working in the wrong context — a
# list of someone else's tasks looks like a list of tasks, and an empty one like "no work". A
# named workspace turns this mistake from invisible into obvious from the first response, and it
# costs two fields.
class AgentScope(BaseModel):
    workspace: WorkspaceCode
    workspace_title: str


# A workspace through the agent's eyes: what it is called, what is inside and whether the agent
# works in it. Counters come as a flat dict (``{"groups": 2, "tasks": 12}``), not as a list of
# rows with label keys as in the interface: a label key is needed by whoever renders human text,
# while the agent needs a number next to a name. The key set depends on the application's
# composition — it is the same registry (``workspace/stats.py``), and it is not a fixed contract.
class AgentWorkspaceRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: WorkspaceCode
    title: str
    description: str = ""
    counters: dict[str, int] = {}
    active: bool = False


# The binding response: the same workspace plus what the agent does not know about its choice —
# how long it lasts and what makes it permanent.
class AgentWorkspaceBound(AgentWorkspaceRow):
    note: str


# ── group ─────────────────────────────────────────────────────────────────────
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


# A journal entry. There is no "open" flag — it is derived from an empty ``resolution`` on a kind
# that waits for one (a ``fact`` never does), and keeping a computable flag alongside would create
# a second source of truth for the same thing.
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


# ── file ──────────────────────────────────────────────────────────────────────
# A file as its holder lists it (task_get, codex_get): the code to use and what it is called and
# holds there — nothing else; file_get reads the rest when the work needs it.
class AgentFileRow(BaseModel):
    code: FileCode
    title: str = ""
    description: str = ""


# Where to send the bytes when the server cannot reach the file: a one-time address, when it
# closes, and the command that sends them. The PUT answers with ``AgentFileAttached``.
class AgentFileUpload(BaseModel):
    url: str
    path: str
    expires_at: DatetimeUTCStr
    command: str


# attach_file answers one of two ways, the other half left out: attached — the code, the insert for
# a text (``IMAGE@`` for a picture, ``FILE@`` otherwise), the title and description as stored; or
# not reachable from the server — ``upload``, and the same attached shape comes back from the PUT.
class AgentFileAttached(AgentScope):
    code: FileCode | None = Field(default=None, exclude_if=_absent)
    insert: str | None = Field(default=None, exclude_if=_absent)
    title: str | None = Field(default=None, exclude_if=_absent)
    description: str | None = Field(default=None, exclude_if=_absent)
    upload: AgentFileUpload | None = Field(default=None, exclude_if=_absent)


# One place here holding the file — the holder to name in delete(code, holder), and what the file
# is called and holds there.
class AgentFilePlace(BaseModel):
    holder: str
    title: str = ""
    description: str = ""


# file_get: what the file is and three ways to it — ``url`` downloads it, ``resource`` shows it to
# the model (a picture as a picture, text as text), ``path`` reads it where the server runs.
# ``name`` is the name it came under.
class AgentFile(AgentScope):
    code: FileCode
    insert: str
    name: str
    mime: str
    type: str
    size: int
    url: str
    download_url: str
    resource: str
    path: str
    places: list[AgentFilePlace] = []


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
    files: list[AgentFileRow] = []


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


# ── codex ─────────────────────────────────────────────────────────────────────
# Every ``path`` here is the full one from the canvas root with a leading slash (``/python``,
# ``/python/test``): one form in every answer, so a path read anywhere can be passed back as is.
# Every codex or note row opens with the same trio — ``code``, ``path``, ``segment`` (the row's own
# last path part; for a codex, its first): together they say where a record lives.
#
# A mounted codex as the index shows it: the line the agent decides by (``description`` — when to
# turn to it) and whether it may write there. The rules themselves are a separate read. No
# workspace fields: the index is always of the active one. ``records`` — the live notes of the
# codex at every depth, as codex_tree shows them; named neutrally because "notes" means several
# things here (task notes ``NOTE@``, codex notes), and the person speaks of documentation. Unlike
# ``children``, a zero stays: it says the codex is empty.
class AgentCodexRow(BaseModel):
    code: CodexCode
    path: str
    segment: str
    title: str
    description: str = ""
    records: int
    editable: bool


class AgentCodexIndex(BaseModel):
    codexes: list[AgentCodexRow] = []


# A codex's rules of keeping its notes — its own shape, not a row of the index: the rules are one
# field today and are meant to split into several (editing, base structure, what belongs there).
# The answer of ``codex_rules``, which stays off the server until then (``tools/codex.py``).
class AgentCodexRules(BaseModel):
    code: CodexCode
    path: str
    segment: str
    title: str
    rules: str = ""


# Always a list, also for one codex, in the order asked; no workspace fields, as in the index.
class AgentCodexRulesList(BaseModel):
    nodes: list[AgentCodexRules] = []


# A child is listed to be chosen, not read: no text, and ``children`` is how many it holds itself.
# Across the codex answers an empty ``children`` (list or count) is left out rather than sent as
# ``[]`` / ``0``: a leaf costs no tokens, and the docstrings say a missing key means "none".
class AgentCodexChild(BaseModel):
    code: CodexCode
    path: str
    segment: str
    title: str
    description: str = ""
    children: int = Field(default=0, exclude_if=lambda v: not v)


# A codex or a note, by code or path; a codex is the one with no ``parent_code`` and a one-segment
# path. ``body`` is the text — for a codex, its rules of working in its area.
# ``parent_code`` is the parent note, or the codex for a top-level note. No codex code and no write
# right: the codex is the first path segment, and the right is per codex — codex_index carries it.
class AgentCodexNode(BaseModel):
    code: CodexCode
    path: str
    segment: str
    parent_code: CodexCode | None = None
    title: str
    description: str = ""
    body: str = ""
    children: list[AgentCodexChild] = Field(default_factory=list, exclude_if=lambda v: not v)
    files: list[AgentFileRow] = Field(default_factory=list, exclude_if=lambda v: not v)


# Always a list, also for one node, in the order asked; no workspace fields, as in the index. A
# named list rather than ``-> list[...]``: MCP structured content must be an object, so the fork
# wraps a bare list as ``{"result": [...]}`` anyway.
class AgentCodexNodeList(BaseModel):
    nodes: list[AgentCodexNode] = []


# ``description`` only in the long form (``with_description=true``): ``None`` is left out, while
# an empty "when to read" in the long form still comes as ``""``.
class AgentCodexTreeNode(BaseModel):
    code: CodexCode
    path: str
    segment: str
    title: str
    description: str | None = Field(default=None, exclude_if=lambda v: v is None)
    children: list[AgentCodexTreeNode] = Field(default_factory=list, exclude_if=lambda v: not v)


# No workspace fields, as in the other codex reads.
class AgentCodexTree(BaseModel):
    root: str
    nodes: list[AgentCodexTreeNode] = []


class AgentCodexHit(BaseModel):
    code: CodexCode
    path: str
    segment: str
    title: str
    description: str = ""
    fragment: str = ""


class AgentCodexSearch(AgentScope):
    hits: list[AgentCodexHit] = []


# After a write: where the note now is — the path is what changes on a rename or a move.
class AgentCodexNoteWritten(AgentScope):
    code: CodexCode
    path: str
    segment: str


__all__ = [
    "AgentCodexChild",
    "AgentCodexHit",
    "AgentCodexIndex",
    "AgentCodexNode",
    "AgentCodexNodeList",
    "AgentCodexNoteWritten",
    "AgentCodexRow",
    "AgentCodexRules",
    "AgentCodexRulesList",
    "AgentCodexSearch",
    "AgentCodexTree",
    "AgentCodexTreeNode",
    "AgentContentAdded",
    "AgentContentReplaced",
    "AgentContentSectionSet",
    "AgentContentSet",
    "AgentFile",
    "AgentFileAttached",
    "AgentFilePlace",
    "AgentFileRow",
    "AgentFileUpload",
    "AgentGroupList",
    "AgentGroupRow",
    "AgentJournalCreated",
    "AgentJournalList",
    "AgentJournalRow",
    "AgentScope",
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
    "AgentWorkspaceBound",
    "AgentWorkspaceRow",
]
