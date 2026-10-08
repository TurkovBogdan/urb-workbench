"""Constants of the ``tasks`` module — code length, prefixes, field sizes and value vocabularies.

The single source for three places that must agree: the ORM model (``String(n)`` +
``CheckConstraint``), the migration (``sa.CheckConstraint``) and truncation in CRUD
(``text.clip``). If they drifted apart, the mismatch would surface only on PostgreSQL: SQLite does
not check ``VARCHAR`` width at all.

The vocabularies (``TASK_STATUSES`` and its neighbours) are **tuples of strings, not a native DB
enum**. There is exactly one reason: migrations run on both SQLite (dev, zero-install) and
PostgreSQL, and ``CREATE TYPE`` does not exist on SQLite. A side benefit — a new status value is
added by editing the tuple and one ``CHECK``, with no ``ALTER TYPE`` and no table rebuild.

Text limits are uniform across the module: ``title`` and ``description`` are the lines a person
and an agent scan a list by, not prose (prose lives in ``body`` with no limit).
"""

from __future__ import annotations

# ── presentation code prefixes (the boundary, NOT storage — see tasks.codes) ──
# The DB holds a bare hex code; the type word is put on at output and stripped at input.
# There is no workspace prefix here: that entity belongs to the ``workspace`` module, and its type
# word is taken from there (``workspace.constants.WORKSPACE_CODE_PREFIX``). A local copy would
# drift from the original the very day the owner renames its word.
# A task group is ``TASKGROUP``, not a bare ``GROUP``: an agent connected to several MCP servers
# meets more than one kind of group, and a code that names its own system is refused as the wrong
# type instead of being looked up and reported "not found".
GROUP_CODE_PREFIX = "TASKGROUP"
TASK_CODE_PREFIX = "TASK"
STAGE_CODE_PREFIX = "STAGE"
NOTE_CODE_PREFIX = "NOTE"

# Retired type words still accepted on input, mapped to the current one. Codes already written into
# task bodies, journals and agents' notes keep resolving; output never uses them.
LEGACY_CODE_PREFIXES = {"GROUP": GROUP_CODE_PREFIX}

# Entity code length in hex characters. The agent retypes the code into every call and pays for it
# in tokens: 10 characters instead of 22 save ~6.8 tokens per reference. It cannot be shorter — at
# 8 characters a one-character typo hits a live row once in 3600, at 10 once in 733000.
# Matches ``workspace.constants.CODE_LEN``: the workspace code is stored in our columns, and
# different widths for one code are a future truncated reference.
CODE_LEN = 10

# ── text column sizes ──
# The triad is the same for every entity in the module: ``title`` is the name, ``description`` is
# what it is and why (by these two the agent decides whether to read on), ``body`` is the markdown
# body.
TITLE_MAX = 128
DESCRIPTION_MAX = 512
# A group's description is a one-line boundary under its name in every list card, not a goal: a
# paragraph there pushes the tasks below the fold. Refused over the limit rather than cut.
GROUP_DESCRIPTION_MAX = 128
# The body of a stage. A task has no ``body`` of its own: its text is the brief and the work fields
# below.
BODY_MAX = 8192
COLOR_MAX = 32
ICON_MAX = 64
# Task brief: details, boundaries and acceptance requirements. Constraints and criteria are lists —
# each criterion carries what proves it — and 1024 cut a real brief short (``tsm_008``).
CONTEXT_MAX = 4048
CONSTRAINTS_MAX = 2048
CRITERIA_MAX = 2048
# The agent's work on a task, three fields in the order the work goes: the plan written before the
# code changes, the progress diary kept along the way, the result written at hand-over. Each
# answers its own question — intent, course, outcome — and sections inside one field would blur
# them. ``PROGRESS_MAX`` is provisional: the live journal puts 90% of tasks under 8.7k of notes.
PLAN_MAX = 8192
PROGRESS_MAX = 16384
RESULT_MAX = 2048
# Pointer to the evidence that a stage is done. Tight on purpose: command output does not fit, and
# writing a story instead of a reference will not work.
EVIDENCE_MAX = 1024
# Journal: the subject of an entry and its resolution.
NOTE_BODY_MAX = 2048
RESOLUTION_MAX = 1024
# Width of columns holding a value from the vocabularies below (status/priority/type/actor). The
# longest value is ``in_progress`` (11), with room for a future word or two.
ENUM_VALUE_MAX = 16

# ── list positions ──
# Higher ``sort`` = higher up. A non-zero starting value, so the first row can be moved both up
# and down without renumbering its neighbours; a step of 5 leaves room for four insertions between
# any two neighbours without reordering the whole list.
SORT_DEFAULT = 500
SORT_STEP = 5

# ── statuses ──
# One vocabulary for the task and the plan stage: two value sets in one module would drift apart,
# and the reader would have to keep in mind which is which. Only the defaults differ.
STATUS_BACKLOG = "backlog"
STATUS_PLANNED = "planned"
STATUS_IN_PROGRESS = "in_progress"
STATUS_IN_TEST = "in_test"
STATUS_IN_REVIEW = "in_review"
STATUS_DONE = "done"
STATUS_CANCELED = "canceled"
TASK_STATUSES = (
    STATUS_BACKLOG,
    STATUS_PLANNED,
    STATUS_IN_PROGRESS,
    STATUS_IN_TEST,
    STATUS_IN_REVIEW,
    STATUS_DONE,
    STATUS_CANCELED,
)
TASK_STATUS_DEFAULT = STATUS_BACKLOG
# A stage is created already planned: it is part of the plan, not an idea for later, and its
# number sets its place in the queue.
STAGE_STATUS_DEFAULT = STATUS_PLANNED
# Terminal statuses: the work is over (succeeded or abandoned) and will not move back on its own.
# Needed wherever "active" is separated from history — for both the task and the stage.
TASK_STATUSES_TERMINAL = (STATUS_DONE, STATUS_CANCELED)

# ── task priorities ──
PRIORITY_BURNING = "burning"
PRIORITY_HIGH = "high"
PRIORITY_NORMAL = "normal"
PRIORITY_LOW = "low"
PRIORITY_FROZEN = "frozen"
TASK_PRIORITIES = (
    PRIORITY_BURNING,
    PRIORITY_HIGH,
    PRIORITY_NORMAL,
    PRIORITY_LOW,
    PRIORITY_FROZEN,
)
TASK_PRIORITY_DEFAULT = PRIORITY_NORMAL
# Sort weight: lower weight = more important (``ORDER BY weight ASC`` puts burning on top).
# Sorting by the word itself is impossible — the alphabet knows nothing about importance. A step of
# 10 leaves room for a new priority between any two neighbours.
TASK_PRIORITY_WEIGHTS = {
    PRIORITY_BURNING: 10,
    PRIORITY_HIGH: 20,
    PRIORITY_NORMAL: 30,
    PRIORITY_LOW: 40,
    PRIORITY_FROZEN: 50,
}

# ── task type ──
# Depth of tracking, not a place in the hierarchy: a task becomes a container by having children.
# Three levels, each adding exactly one way of tracking the work:
#
#   simple    — title, goal and context (what to know before starting). No constraints,
#               criteria, plan or journal; often a task for the person.
#   standard  — plus constraints and criteria (the full brief), a prose plan and a work journal.
#   extended  — plus STAGES: the work is split into steps, each with its own state and
#               evidence of completion.
#
# The line between standard and extended runs exactly along stages, not along "tracking density"
# in general: a prose plan answers "how will I do this", stages answer "where am I now and what
# proves what is done". The second question only makes sense for work lasting longer than one
# session, and forcing it on an ordinary task demands ceremony where a paragraph is enough.
TYPE_SIMPLE = "simple"
TYPE_STANDARD = "standard"
TYPE_EXTENDED = "extended"
TASK_TYPES = (TYPE_SIMPLE, TYPE_STANDARD, TYPE_EXTENDED)
TASK_TYPE_DEFAULT = TYPE_SIMPLE
# Types with a brief, a plan and a journal — everything except simple.
TASK_TYPES_WITH_PLAN = (TYPE_STANDARD, TYPE_EXTENDED)
# Types with stages — extended only. A separate tuple, not a slice of the previous one: these are
# two different rules, and gluing them together means one day shifting both while changing one.
TASK_TYPES_WITH_STAGES = (TYPE_EXTENDED,)

# ── what becomes of a group's tasks when the group is deleted ──
# A soft-deleted group must not keep tasks pointing at it: no screen draws a group that is gone,
# so its tasks vanished from the list while still existing. Deleting a group with live tasks
# therefore names one of these, and it is applied in the same transaction as the deletion.
#   ungroup — the tasks lose their group and land in "No group";
#   move    — the tasks go to another live group of the same workspace;
#   delete  — the live tasks go to the trash with their subtask branches.
GROUP_TASKS_UNGROUP = "ungroup"
GROUP_TASKS_MOVE = "move"
GROUP_TASKS_DELETE = "delete"
GROUP_TASK_DISPOSALS = (GROUP_TASKS_UNGROUP, GROUP_TASKS_MOVE, GROUP_TASKS_DELETE)

# ── journal entry type ──
# What the row describes. Ordered from frequent to rare: the agent picks the first value of an
# enumeration noticeably more often than the rest, so the frequent kind must come before the rare.
NOTE_DECISION = "decision"
NOTE_REMARK = "remark"
NOTE_FINDING = "finding"
NOTE_FACT = "fact"
NOTE_TYPES = (NOTE_DECISION, NOTE_REMARK, NOTE_FINDING, NOTE_FACT)
# Kinds that can be open at all. ``fact`` is closed the moment it is written — it awaits nothing.
NOTE_TYPES_OPENABLE = (NOTE_DECISION, NOTE_REMARK, NOTE_FINDING)
# Kinds whose being unresolved blocks hand-off. A decision without a resolution is an assumption,
# and whoever made it must lift it; a remark is a request from the brief's author, and the executor
# must address it. A finding is NOT included: it is about work outside this task, the person
# triages it in their own order, and if we counted it alongside, the very first finding would lock
# hand-off forever.
NOTE_TYPES_BLOCKING = (NOTE_DECISION, NOTE_REMARK)
# Kinds the agent creates. ``remark`` is the brief author's word, and the agent has no tool for it:
# both halves of an entry written by one hand turn the gate into self-assessment.
NOTE_TYPES_BY_AGENT = (NOTE_DECISION, NOTE_FINDING, NOTE_FACT)

# ── actor kind ──
# Who created the row. The same vocabulary as the task type's, but a different meaning (authorship,
# not addressee), hence a separate tuple: nothing stops them from drifting apart.
ACTOR_HUMAN = "human"
ACTOR_AGENT = "agent"
ACTOR_KINDS = (ACTOR_HUMAN, ACTOR_AGENT)
TASK_CREATED_BY_DEFAULT = ACTOR_HUMAN


def sql_in(values: tuple[str, ...]) -> str:
    """Tuple of values → string for ``col IN (...)`` in a ``CheckConstraint``."""
    return ", ".join(f"'{value}'" for value in values)


__all__ = [
    "ACTOR_AGENT",
    "ACTOR_HUMAN",
    "ACTOR_KINDS",
    "BODY_MAX",
    "CODE_LEN",
    "COLOR_MAX",
    "CONSTRAINTS_MAX",
    "CONTEXT_MAX",
    "CRITERIA_MAX",
    "DESCRIPTION_MAX",
    "ENUM_VALUE_MAX",
    "EVIDENCE_MAX",
    "GROUP_CODE_PREFIX",
    "GROUP_DESCRIPTION_MAX",
    "GROUP_TASKS_DELETE",
    "GROUP_TASKS_MOVE",
    "GROUP_TASKS_UNGROUP",
    "GROUP_TASK_DISPOSALS",
    "ICON_MAX",
    "NOTE_BODY_MAX",
    "NOTE_CODE_PREFIX",
    "NOTE_DECISION",
    "NOTE_FACT",
    "NOTE_FINDING",
    "NOTE_REMARK",
    "NOTE_TYPES",
    "NOTE_TYPES_BLOCKING",
    "NOTE_TYPES_BY_AGENT",
    "NOTE_TYPES_OPENABLE",
    "PLAN_MAX",
    "PRIORITY_BURNING",
    "PRIORITY_FROZEN",
    "PRIORITY_HIGH",
    "PRIORITY_LOW",
    "PRIORITY_NORMAL",
    "PROGRESS_MAX",
    "RESOLUTION_MAX",
    "RESULT_MAX",
    "SORT_DEFAULT",
    "SORT_STEP",
    "STAGE_CODE_PREFIX",
    "STAGE_STATUS_DEFAULT",
    "STATUS_BACKLOG",
    "STATUS_CANCELED",
    "STATUS_DONE",
    "STATUS_IN_PROGRESS",
    "STATUS_IN_REVIEW",
    "STATUS_IN_TEST",
    "STATUS_PLANNED",
    "TASK_CODE_PREFIX",
    "TASK_CREATED_BY_DEFAULT",
    "TASK_PRIORITIES",
    "TASK_PRIORITY_DEFAULT",
    "TASK_PRIORITY_WEIGHTS",
    "TASK_STATUSES",
    "TASK_STATUSES_TERMINAL",
    "TASK_STATUS_DEFAULT",
    "TASK_TYPES",
    "TASK_TYPES_WITH_PLAN",
    "TASK_TYPES_WITH_STAGES",
    "TASK_TYPE_DEFAULT",
    "TITLE_MAX",
    "TYPE_EXTENDED",
    "TYPE_SIMPLE",
    "TYPE_STANDARD",
    "sql_in",
]
