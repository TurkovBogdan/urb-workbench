"""CRUD for ``TasksTask`` — tasks. Each function owns its session.

Three rules of this file, duplicated nowhere else:

1. **A task and its tree edge are born together.** ``task_create`` writes the ``tasks_link`` row
   in the same transaction: without an edge the task does not belong to the tree, and "task
   first, link later" would leave a window in which it is visible nowhere. Atomicity is not a
   convenience here: there is nothing to rebuild a lost edge from later — only the caller knew
   the parent.
2. **Workspace consistency is checked on write.** Parent and child live in one workspace, the
   group comes from the task's workspace. A violation is a ``ValueError`` with a clear message:
   the schema does not forbid such a link (the FK looks at ``code``, not at the pair), so only
   this layer can.
3. **Soft delete cascades.** Deleting a branch task by task makes no sense, so descendants get
   **the same timestamp** as the root of the deletion. Restore works off that same mark: exactly
   those whose ``deleted_at`` matches the parent's mark come back — a task deleted separately and
   earlier does not resurface with the restore.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import case, delete as sa_delete, func, or_, select, update

from src.core.database import session_scope, write_scope
from src.core.utils.date import utc_now
from src.modules.core_changes import DELETED, UPDATED, mark_changes
from src.modules.tasks.codes import new_code
from src.modules.tasks.constants import (
    ACTOR_KINDS,
    CONSTRAINTS_MAX,
    CONTEXT_MAX,
    CRITERIA_MAX,
    DESCRIPTION_MAX,
    GROUP_TASK_DISPOSALS,
    GROUP_TASKS_DELETE,
    GROUP_TASKS_MOVE,
    PLAN_MAX,
    PROGRESS_MAX,
    RESULT_MAX,
    STATUS_CANCELED,
    STATUS_DONE,
    STATUS_IN_PROGRESS,
    TASK_CREATED_BY_DEFAULT,
    TASK_PRIORITIES,
    TASK_PRIORITY_DEFAULT,
    TASK_PRIORITY_WEIGHTS,
    TASK_STATUS_DEFAULT,
    TASK_STATUSES,
    TASK_STATUSES_TERMINAL,
    TASK_TYPE_DEFAULT,
    TASK_TYPES,
    TITLE_MAX,
)
from src.modules.tasks.crud.link import (
    bottom_sort,
    link_move_in,
    link_reorder_in,
    require_open_parent,
    require_parent_group_alive,
    require_root_parent,
)
from src.modules.tasks.errors import GROUP_HAS_TASKS, TaskRuleError
from src.modules.tasks.models.group import TasksGroup
from src.modules.tasks.models.link import TasksLink
from src.modules.tasks.models.journal import TasksJournal
from src.modules.tasks.models.stage import TasksStage
from src.modules.tasks.models.task import TasksTask
from src.modules.tasks.text import clip, fit
from src.modules.workspace.models.workspace import Workspace

# Priority sorts by weight, not by word: the alphabet knows nothing about importance
# (``burning`` would land between ``agent`` and ``frozen`` for no reason at all). An unknown value
# sinks to the very bottom — CHECK will not let one in, but the expression must be total.
_PRIORITY_ORDER = case(
    TASK_PRIORITY_WEIGHTS,
    value=TasksTask.priority,
    else_=max(TASK_PRIORITY_WEIGHTS.values()) + 10,
)


class _Keep:
    """A "field not passed" marker for ``task_update``.

    Needed for dates only. For text, "not passed" is expressed as ``None`` (the column stores the
    empty string itself), for the group reference — as ``""`` (see ``task_update``), but a date has
    no spare value left: both "leave as is" and "clear the deadline" are the same ``None``. They
    have to be told apart by a separate object, otherwise there would be no way to remove a
    deadline once set, and editing the card could only ever add.
    """

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover — for debug output only
        return "KEEP"


KEEP = _Keep()

# The phase timestamp a status transition sets. Other statuses mark no phase: "in testing" and
# "in review" are still "work in progress", and its start needs no second record.
_STATUS_STAMPS = {
    STATUS_IN_PROGRESS: "started_at",
    STATUS_DONE: "completed_at",
    STATUS_CANCELED: "canceled_at",
}

# The closing marks: a task carries at most one of them — the one of its current terminal status.
_CLOSING_STAMPS = ("completed_at", "canceled_at")


def _stamp_phase(row: TasksTask, status: str) -> None:
    """Make the phase marks agree with ``status`` — on a move and at creation alike.

    The start is stamped once and kept: going from ``done`` back to work and back again must not
    rewrite the date work on the task began — that is a fact, not the current state. The closing
    marks follow the status instead: an open task carries neither, a closed one only its own —
    a task moved straight from ``done`` to ``canceled`` is canceled, and a completion date left on
    it would claim an end the work did not reach. A mark already there for the same status stays.
    """
    current = _STATUS_STAMPS.get(status)
    for closing_field in _CLOSING_STAMPS:
        if closing_field != current:
            setattr(row, closing_field, None)
    if current is not None and getattr(row, current) is None:
        setattr(row, current, utc_now())


def _checked(value: str, allowed: tuple[str, ...], field: str) -> str:
    """A value from the vocabulary, or a refusal listing the allowed ones.

    Duplicates the schema's ``CHECK`` on purpose: from the database the same violation would
    arrive as an ``IntegrityError`` naming the constraint — text for an engineer, not for the
    caller.
    """
    if value not in allowed:
        raise ValueError(
            f"Unknown {field} {value!r}. Allowed: {', '.join(allowed)}."
        )
    return value


def _hit(query: str, *fields: str | None) -> bool:
    """Case-insensitive substring — compared in Python, not in SQL.

    SQLite's ``lower()`` folds ASCII only: a capitalised Cyrillic query would not find the same
    word in lower case there, yet would on PostgreSQL — one and the same search would answer
    differently on the two providers, and they would diverge silently. The selection holds
    hundreds of rows, not hundreds of thousands, so the cost of filtering in the application is
    nothing next to that difference.
    """
    needle = query.lower()
    return any(field and needle in field.lower() for field in fields)


async def _require_workspace(s, workspace_code: str) -> None:
    stmt = select(Workspace.code).where(
        Workspace.code == workspace_code, Workspace.deleted_at.is_(None)
    )
    if (await s.execute(stmt)).scalar_one_or_none() is None:
        raise ValueError(
            f"Workspace {workspace_code!r} does not exist (or is deleted) — "
            "a task always belongs to a live workspace."
        )


async def _require_group_of(s, group_code: str, workspace_code: str) -> None:
    """The group exists and belongs to the same workspace as the task."""
    stmt = select(TasksGroup.workspace_code).where(
        TasksGroup.code == group_code, TasksGroup.deleted_at.is_(None)
    )
    owner = (await s.execute(stmt)).scalar_one_or_none()
    if owner is None:
        raise ValueError(f"Group {group_code!r} does not exist (or is deleted).")
    if owner != workspace_code:
        raise ValueError(
            f"Group {group_code!r} belongs to workspace {owner!r}, but the task belongs to "
            f"{workspace_code!r} — a group never spans workspaces."
        )


async def _require_parent_of(
    s, parent_code: str, workspace_code: str, child_status: str
) -> str | None:
    """The parent exists, lives in the same workspace as the child, is not closed while the child
    is open, and is not a subtask itself.

    Returns the parent's group: the child takes it along with its place in the tree.
    """
    stmt = select(TasksTask.workspace_code, TasksTask.group_code, TasksTask.status).where(
        TasksTask.code == parent_code, TasksTask.deleted_at.is_(None)
    )
    found = (await s.execute(stmt)).one_or_none()
    if found is None:
        raise ValueError(f"Parent task {parent_code!r} does not exist (or is deleted).")
    owner, parent_group, parent_status = found
    if owner != workspace_code:
        raise ValueError(
            f"Parent task {parent_code!r} belongs to workspace {owner!r}, but the child "
            f"belongs to {workspace_code!r} — a branch never spans workspaces."
        )
    require_open_parent(parent_code, parent_status, child_status)
    await require_parent_group_alive(s, parent_code, parent_group)
    await require_root_parent(s, parent_code)
    return parent_group


async def _require_parent_group(s, code: str, group_code: str | None) -> None:
    """Refuse if a subtask is assigned a group other than its parent's.

    Roots are unaffected. A subtask is allowed exactly one group — its parent's: that way it can be
    brought back there if it drifted from its parent before the rule existed.
    """
    link = await s.get(TasksLink, code)
    if link is None or link.parent_code is None:
        return
    parent = await s.get(TasksTask, link.parent_code)
    if parent is None or parent.group_code == group_code:
        return
    raise ValueError(
        f"Task {code!r} is a subtask of {link.parent_code!r}, and a subtask sits in its "
        f"parent's group. File {link.parent_code!r} instead — its subtasks follow it — or take "
        f"{code!r} out of the branch first."
    )


async def _carry_children(s, parent: TasksTask) -> None:
    """Subtasks follow their parent into its new group — deleted ones too.

    Deleted ones because a restore brings them back to their old place in the tree, and with a
    foreign group they would come back as a violation nobody committed.
    """
    children = list(
        (
            await s.execute(
                select(TasksLink.task_code).where(TasksLink.parent_code == parent.code)
            )
        )
        .scalars()
        .all()
    )
    if not children:
        return
    await s.execute(
        update(TasksTask)
        .where(TasksTask.code.in_(children))
        .values(group_code=parent.group_code, updated_at=utc_now())
    )
    mark_changes(s, "tasks.task", UPDATED, children)


async def _branch_stamp(s, branch: list[str]) -> datetime:
    """A deletion mark that nothing in this branch carries yet.

    The mark identifies a delete operation (restore uses it to pick "those that left together"),
    and its precision is one second: ``utc_now`` drops microseconds, and so does
    ``TIMESTAMP(precision=0)`` on PostgreSQL. Deleting a descendant on its own and, a moment later,
    the whole parent fits within one second, and two different operations would share one mark:
    restoring the parent would also bring back what the person had deliberately removed earlier.
    So on a collision the mark is shifted a second forward — then it no longer belongs to the
    other operation.
    """
    stmt = select(TasksTask.deleted_at).where(
        TasksTask.code.in_(branch), TasksTask.deleted_at.is_not(None)
    )
    taken = set((await s.execute(stmt)).scalars().all())
    stamp = utc_now()
    while stamp in taken:
        stamp += timedelta(seconds=1)
    return stamp


async def _descendant_codes(s, code: str) -> list[str]:
    """Codes of all the task's descendants — a breadth-first walk over the link table.

    Walked in Python rather than with a recursive CTE: one developer's task tree is measured in
    hundreds of rows, and the readability of the expression is worth more here than one
    round-trip. ``seen`` guards against a cycle that could have reached the database bypassing the
    CRUD: an endless loop in delete is worse than a crooked tree.
    """
    found: list[str] = []
    seen = {code}
    frontier = [code]
    while frontier:
        stmt = select(TasksLink.task_code).where(TasksLink.parent_code.in_(frontier))
        children = [c for c in (await s.execute(stmt)).scalars().all() if c not in seen]
        seen.update(children)
        found.extend(children)
        frontier = children
    return found


async def task_create(
    *,
    workspace_code: str,
    title: str,
    group_code: str | None = None,
    parent_code: str | None = None,
    description: str | None = None,
    context: str | None = None,
    constraints: str | None = None,
    criteria: str | None = None,
    plan: str | None = None,
    progress: str | None = None,
    result: str | None = None,
    type: str = TASK_TYPE_DEFAULT,
    status: str = TASK_STATUS_DEFAULT,
    priority: str = TASK_PRIORITY_DEFAULT,
    created_by: str = TASK_CREATED_BY_DEFAULT,
    deadline_at: datetime | None = None,
) -> TasksTask:
    """Create a task together with its tree edge.

    ``parent_code=None`` — a root of the workspace. The edge is always created at a position below
    the whole sibling row (``bottom_sort``): the arrangement at the top is handwork, and a fresh
    task must not jump over it. From there it is moved by dragging (``link_reorder``) or moved
    under another parent (``task_update(parent_code=…)``).

    A subtask takes its parent's group. An empty ``group_code`` means "not given", not "outside any
    group": that way a form that asks nothing about a subtask's group does not run into a refusal.
    """
    _checked(type, TASK_TYPES, "task type")
    _checked(status, TASK_STATUSES, "task status")
    _checked(priority, TASK_PRIORITIES, "task priority")
    _checked(created_by, ACTOR_KINDS, "actor kind")
    async with write_scope() as s:
        await _require_workspace(s, workspace_code)
        if group_code:
            await _require_group_of(s, group_code, workspace_code)
        if parent_code:
            parent_group = await _require_parent_of(s, parent_code, workspace_code, status)
            if group_code and group_code != parent_group:
                parent_filing = f"under {parent_group!r}" if parent_group else "in no group"
                raise ValueError(
                    f"A subtask sits in its parent's group, and {parent_code!r} is filed "
                    f"{parent_filing}, not under {group_code!r}. Leave the group out — the "
                    "subtask takes its parent's."
                )
            group_code = parent_group
        row = TasksTask(
            code=new_code(),
            workspace_code=workspace_code,
            group_code=group_code or None,
            type=type,
            status=status,
            priority=priority,
            title=clip(title, TITLE_MAX),
            description=clip(description, DESCRIPTION_MAX),
            context=clip(context, CONTEXT_MAX),
            constraints=clip(constraints, CONSTRAINTS_MAX),
            criteria=clip(criteria, CRITERIA_MAX),
            plan=fit(plan, PLAN_MAX, "task plan"),
            progress=fit(progress, PROGRESS_MAX, "task progress"),
            result=fit(result, RESULT_MAX, "task result"),
            deadline_at=deadline_at,
            created_by=created_by,
        )
        _stamp_phase(row, status)
        s.add(row)
        await s.flush()
        s.add(
            TasksLink(
                task_code=row.code,
                parent_code=parent_code or None,
                # Below the whole sibling row, not at a constant 500: a row reordered with the
                # mouse is renumbered from its length, and a constant value would wedge a fresh
                # task into its middle.
                sort=await bottom_sort(
                    s, parent_code or None, workspace_code, group_code or None
                ),
            )
        )
        await s.flush()
        await s.refresh(row)
    return row


async def task_get(code: str, *, include_deleted: bool = False) -> TasksTask | None:
    stmt = select(TasksTask).where(TasksTask.code == code)
    if not include_deleted:
        stmt = stmt.where(TasksTask.deleted_at.is_(None))
    async with session_scope() as s:
        return (await s.execute(stmt)).scalar_one_or_none()


async def task_list_by_workspace(
    workspace_code: str,
    *,
    status: str | None = None,
    statuses: tuple[str, ...] | None = None,
    query: str | None = None,
    group_code: str | None = None,
    include_deleted: bool = False,
) -> list[TasksTask]:
    """A flat list of the workspace's tasks in MANUAL order: higher ``sort`` on top.

    The person sets the order by dragging (``link_reorder``), and it is the only truth about what
    comes after what. The list used to be built by priority and creation time; that is
    incompatible with manual arrangement: a row moved with the mouse would snap back on the very
    next request. Priority remains a glyph on the row and a filter over it.

    The sort lives in ``tasks_link`` — its values are local to the children of one parent, and the
    combined list (roots mixed with branches) preserves the order within each branch: the UI lays
    the flat response out by parent anyway.

    ``group_code=""`` — only ungrouped tasks (the only way to ask about ``NULL``), a code — only
    that group, ``None`` — no group filter at all.

    ``status`` narrows to one value, ``statuses`` — to a set (that is how "everything unfinished" is
    expressed: listing five statuses is cheaper than adding negation to the schema). Both given —
    both apply, i.e. the intersection; there is no reason to call it that way, but nothing to
    forbid either.

    ``query`` searches for a case-insensitive substring in the title and goal. Bodies are not
    included: they are searched separately and on explicit request — ``task_search_codes``.
    """
    stmt = (
        select(TasksTask)
        .join(TasksLink, TasksLink.task_code == TasksTask.code)
        .where(TasksTask.workspace_code == workspace_code)
        .order_by(TasksLink.sort.desc(), TasksTask.created_at.asc(), TasksTask.code.asc())
    )
    if status is not None:
        stmt = stmt.where(TasksTask.status == _checked(status, TASK_STATUSES, "task status"))
    if statuses is not None:
        for value in statuses:
            _checked(value, TASK_STATUSES, "task status")
        stmt = stmt.where(TasksTask.status.in_(statuses))
    if group_code == "":
        stmt = stmt.where(TasksTask.group_code.is_(None))
    elif group_code is not None:
        stmt = stmt.where(TasksTask.group_code == group_code)
    if not include_deleted:
        stmt = stmt.where(TasksTask.deleted_at.is_(None))
    async with session_scope() as s:
        rows = list((await s.execute(stmt)).scalars().all())
    if not query:
        return rows
    return [row for row in rows if _hit(query, row.title, row.description)]


async def task_search_codes(
    workspace_code: str,
    query: str,
    *,
    in_brief: bool = False,
    in_plan: bool = False,
    in_journal: bool = False,
) -> list[str]:
    """Codes of the workspace's tasks whose BODIES match the query — in the named areas.

    Title and goal are left out on purpose: they are visible on the list row, and whoever searches
    them already has the list in hand. This is where one comes for what the row lacks — the
    brief, the plan with its stages, and the journal. No area is on by default: a search that
    quietly digs into eight-kilobyte bodies returns matches that do not tell you whether it is the
    right task.

    It returns CODES specifically, not rows: the caller holds the whole workspace list and
    intersects it with its own — it needs no second copy of the same cards. For the same reason
    deleted tasks are not filtered out: the intersection on the other side decides what to show.
    """
    if not query or not (in_brief or in_plan or in_journal):
        return []

    hits: set[str] = set()

    if in_brief or in_plan:
        columns = [TasksTask.code]
        if in_brief:
            columns += [TasksTask.context, TasksTask.constraints, TasksTask.criteria]
        if in_plan:
            columns += [TasksTask.plan, TasksTask.progress, TasksTask.result]
        stmt = select(*columns).where(TasksTask.workspace_code == workspace_code)
        async with session_scope() as s:
            for code, *texts in (await s.execute(stmt)).all():
                if _hit(query, *texts):
                    hits.add(code)

    # Stages and journal hang off the task and do not know their workspace — hence the join.
    if in_plan:
        stmt = (
            select(
                TasksStage.task_code,
                TasksStage.title,
                TasksStage.description,
                TasksStage.body,
                TasksStage.evidence,
            )
            .join(TasksTask, TasksTask.code == TasksStage.task_code)
            .where(TasksTask.workspace_code == workspace_code)
        )
        async with session_scope() as s:
            for task_code, *texts in (await s.execute(stmt)).all():
                if _hit(query, *texts):
                    hits.add(task_code)

    if in_journal:
        stmt = (
            select(TasksJournal.task_code, TasksJournal.title, TasksJournal.body, TasksJournal.resolution)
            .join(TasksTask, TasksTask.code == TasksJournal.task_code)
            .where(TasksTask.workspace_code == workspace_code)
        )
        async with session_scope() as s:
            for task_code, *texts in (await s.execute(stmt)).all():
                if _hit(query, *texts):
                    hits.add(task_code)

    return sorted(hits)


async def task_list_by_parent(
    parent_code: str | None,
    *,
    workspace_code: str | None = None,
    include_deleted: bool = False,
) -> list[TasksTask]:
    """A node's children in order (higher ``sort`` on top).

    ``parent_code=None`` — the roots; every workspace has its own, so with ``None`` it makes sense
    to pass ``workspace_code`` too, otherwise the roots of all workspaces come back at once.
    """
    stmt = (
        select(TasksTask)
        .join(TasksLink, TasksLink.task_code == TasksTask.code)
        .order_by(TasksLink.sort.desc(), TasksTask.code.asc())
    )
    if parent_code is None:
        stmt = stmt.where(TasksLink.parent_code.is_(None))
    else:
        stmt = stmt.where(TasksLink.parent_code == parent_code)
    if workspace_code is not None:
        stmt = stmt.where(TasksTask.workspace_code == workspace_code)
    if not include_deleted:
        stmt = stmt.where(TasksTask.deleted_at.is_(None))
    async with session_scope() as s:
        return list((await s.execute(stmt)).scalars().all())


async def _refile(s, row: TasksTask) -> None:
    """The task changed group — put it at the end of the new group's row.

    A root's sibling row is its group (``crud/link.py::_siblings``), so moving between groups is
    moving between rows: the old position number means nothing in the new row, and keeping it
    would stick the task into the middle of someone else's arrangement at random. At the end, not
    the start, for the same reason as a fresh task: the top of the row is handwork.

    A subtask is left alone: its row is set by its parent, and a group change does not affect its
    place in the tree.
    """
    link = await s.get(TasksLink, row.code)
    if link is None or link.parent_code is not None:
        return
    link.sort = await bottom_sort(
        s, None, row.workspace_code, row.group_code, moved_code=row.code
    )


async def _place_in_tree(
    s, row: TasksTask, *, parent_code: str | None, group_code: str | None
) -> None:
    """Parent, then group — inside the caller's transaction; ``None`` — leave as is.

    Group after parent: that way "move to the root and straight into another group" is a single
    motion, and a subtask's group is checked at its new place.
    """
    if group_code:
        await _require_group_of(s, group_code, row.workspace_code)
    if parent_code is not None:
        link = await s.get(TasksLink, row.code)
        if link is not None and (parent_code or None) != link.parent_code:
            await link_move_in(s, row, parent_code)
    if group_code is None or (group_code or None) == row.group_code:
        return
    if parent_code:
        raise ValueError(
            f"Moving {row.code!r} under {parent_code!r} gives it {parent_code!r}'s group — "
            "a subtask sits in its parent's group. Leave group_code out, or pass the parent's."
        )
    await _require_parent_group(s, row.code, group_code or None)
    row.group_code = group_code or None
    await _refile(s, row)
    await _carry_children(s, row)


async def task_reorder(
    code: str,
    *,
    after_code: str | None,
    parent_code: str | None = None,
    group_code: str | None = None,
) -> TasksTask | None:
    """A row drag: the new place in the tree and among its siblings — in one transaction.

    ``parent_code`` / ``group_code`` — as in ``task_update`` (``None`` — leave as is, ``""`` —
    clear), ``after_code`` — the sibling just above at the new place, ``None`` — to the start. A
    refused position rolls back the move too: otherwise the person would see an error while the
    task already sat in its new place. ``None`` in the result — no such task (or it is deleted).
    """
    async with write_scope() as s:
        row = await s.get(TasksTask, code)
        if row is None or row.deleted_at is not None:
            return None
        await _place_in_tree(s, row, parent_code=parent_code, group_code=group_code)
        await link_reorder_in(s, code, after_code=after_code)
        await s.flush()
        await s.refresh(row)
    return row


async def task_update(
    code: str,
    *,
    title: str | None = None,
    description: str | None = None,
    context: str | None = None,
    constraints: str | None = None,
    criteria: str | None = None,
    plan: str | None = None,
    progress: str | None = None,
    result: str | None = None,
    type: str | None = None,
    priority: str | None = None,
    group_code: str | None = None,
    parent_code: str | None = None,
    deadline_at: datetime | None | _Keep = KEEP,
) -> TasksTask | None:
    """Update the given task fields (``None`` = leave as is).

    ``group_code=""`` — ungroup (``NULL``): an empty string means "not set" in every text field of
    the module, and for a reference the only form of "not set" is ``NULL``.

    ``parent_code`` — move under this parent, ``""`` — move out to the root; the move rules are in
    ``crud/link.py::link_move_in``. The move and the card edit are one transaction: a refused move
    rolls the edit back too. The group is applied after the move, so "move to the root and straight
    into another group" is a single call, and a subtask's group can only be its parent's. When a
    root changes group, its subtasks follow.

    For dates "leave as is" is ``KEEP``, and ``None`` clears the date: a date is the only field
    with no "empty" value of its own besides ``None`` (see ``_Keep``).

    Status is absent here on purpose: ``task_update_status`` changes it, because the transition
    also sets the phase timestamp, and there is no reason to allow going around it.
    """
    if type is not None:
        _checked(type, TASK_TYPES, "task type")
    if priority is not None:
        _checked(priority, TASK_PRIORITIES, "task priority")
    async with write_scope() as s:
        row = await s.get(TasksTask, code)
        if row is None or row.deleted_at is not None:
            return None
        if title is not None:
            row.title = clip(title, TITLE_MAX)
        if description is not None:
            row.description = clip(description, DESCRIPTION_MAX)
        if context is not None:
            row.context = clip(context, CONTEXT_MAX)
        if constraints is not None:
            row.constraints = clip(constraints, CONSTRAINTS_MAX)
        if criteria is not None:
            row.criteria = clip(criteria, CRITERIA_MAX)
        if plan is not None:
            row.plan = fit(plan, PLAN_MAX, "task plan")
        if progress is not None:
            row.progress = fit(progress, PROGRESS_MAX, "task progress")
        if result is not None:
            row.result = fit(result, RESULT_MAX, "task result")
        if type is not None:
            row.type = type
        if priority is not None:
            row.priority = priority
        await _place_in_tree(s, row, parent_code=parent_code, group_code=group_code)
        if not isinstance(deadline_at, _Keep):
            row.deadline_at = deadline_at
        await s.flush()
        await s.refresh(row)
    return row


async def _require_no_open_subtasks(s, row: TasksTask, status: str) -> None:
    """Refuse to close a task while it has open live subtasks — they are named."""
    open_subtasks_query = (
        select(TasksTask.code, TasksTask.status)
        .join(TasksLink, TasksLink.task_code == TasksTask.code)
        .where(
            TasksLink.parent_code == row.code,
            TasksTask.deleted_at.is_(None),
            TasksTask.status.not_in(TASK_STATUSES_TERMINAL),
        )
    )
    open_subtasks = (await s.execute(open_subtasks_query)).all()
    if open_subtasks:
        named = ", ".join(f"{code!r} ({state})" for code, state in open_subtasks)
        raise ValueError(
            f"Task {row.code!r} cannot be {status!r} while its subtasks are open: {named}. "
            "Close or cancel them first, or take them out of this task."
        )


async def _require_open_parent_for_status(s, row: TasksTask, status: str) -> None:
    """Refuse to reopen a subtask of a closed task: the parent is reopened first."""
    link = await s.get(TasksLink, row.code)
    if link is None or link.parent_code is None:
        return
    parent = await s.get(TasksTask, link.parent_code)
    if parent is None or parent.status not in TASK_STATUSES_TERMINAL:
        return
    raise ValueError(
        f"Task {row.code!r} is a subtask of {link.parent_code!r}, which is {parent.status!r} — "
        f"a closed task holds no open parts, so {row.code!r} cannot go to {status!r}. Reopening "
        f"{link.parent_code!r} is the person's call; ask for it."
    )


async def task_update_status(code: str, status: str) -> TasksTask | None:
    """Change the status and stamp the phase: ``in_progress`` → ``started_at``, ``done`` →
    ``completed_at``, ``canceled`` → ``canceled_at`` — the rules are ``_stamp_phase``'s.

    A closed task holds no open parts — from both sides: a task with open live subtasks is not
    closed, and a subtask of a closed task is not reopened. What to do with the parent then is the
    person's call — reopen it or close the parts — hence a refusal here, not a cascade.
    """
    _checked(status, TASK_STATUSES, "task status")
    async with write_scope() as s:
        row = await s.get(TasksTask, code)
        if row is None or row.deleted_at is not None:
            return None
        if status in TASK_STATUSES_TERMINAL:
            await _require_no_open_subtasks(s, row, status)
        else:
            await _require_open_parent_for_status(s, row, status)
        row.status = status
        _stamp_phase(row, status)
        await s.flush()
        await s.refresh(row)
    return row


async def task_delete(code: str, *, hard: bool = False) -> bool:
    """Delete a task together with its branch. ``True`` — the task existed.

    The soft path (default) puts **one and the same** timestamp on the task and all its
    descendants — ``task_restore`` later works off it. Descendants deleted earlier keep their own
    mark and do not come back with the restore (how that holds at one-second time precision — see
    ``_branch_stamp``).

    ``hard=True`` physically removes the whole branch. Descendants have to be listed explicitly:
    the FK cascade would remove only the edges (``tasks_link``), and the descendant tasks
    themselves would stay in the database with no place in the tree at all — invisible to any
    walk.
    """
    async with write_scope() as s:
        row = await s.get(TasksTask, code)
        if row is None:
            return False
        branch = [code, *await _descendant_codes(s, code)]
        if hard:
            await s.execute(
                sa_delete(TasksLink).where(
                    or_(
                        TasksLink.task_code.in_(branch),
                        TasksLink.parent_code.in_(branch),
                    )
                )
            )
            await s.execute(sa_delete(TasksTask).where(TasksTask.code.in_(branch)))
            # Bulk statements yield no objects — so we name the branch to the change feed ourselves.
            mark_changes(s, "tasks.task", DELETED, branch)
            mark_changes(s, "tasks.link", DELETED, branch)
        else:
            stamp = await _branch_stamp(s, branch)
            await s.execute(
                update(TasksTask)
                .where(TasksTask.code.in_(branch), TasksTask.deleted_at.is_(None))
                .values(deleted_at=stamp)
            )
            # A soft delete is a row edit (the ``deleted_at`` mark), not a disappearance.
            mark_changes(s, "tasks.task", UPDATED, branch)
    return True


async def task_restore(code: str) -> bool:
    """Restore a task and the descendants that left with it. ``True`` — the task was deleted.

    "Left together" means ``deleted_at`` matches the task's own mark: a different mark belongs to
    a separate, earlier deletion, and nobody asked to resurrect that.
    """
    async with write_scope() as s:
        row = await s.get(TasksTask, code)
        if row is None or row.deleted_at is None:
            return False
        stamp = row.deleted_at
        branch = [code, *await _descendant_codes(s, code)]
        await s.execute(
            update(TasksTask)
            .where(TasksTask.code.in_(branch), TasksTask.deleted_at == stamp)
            .values(deleted_at=None)
        )
        mark_changes(s, "tasks.task", UPDATED, branch)
    return True


async def task_count_by_workspace_codes(
    workspace_codes: list[str], *, include_deleted: bool = False
) -> dict[str, int]:
    """``workspace_code → number of its tasks`` in one ``GROUP BY`` — for the workspace list.

    The counters for every card in the list come from one query, not a query per card: the whole
    list fits on screen, and an N+1 here would cost exactly as many lines of code as it saves. A
    workspace with no tasks is simply absent from the result — the caller fills in the zero.
    """
    if not workspace_codes:
        return {}
    stmt = (
        select(TasksTask.workspace_code, func.count())
        .where(TasksTask.workspace_code.in_(workspace_codes))
        .group_by(TasksTask.workspace_code)
    )
    if not include_deleted:
        stmt = stmt.where(TasksTask.deleted_at.is_(None))
    async with session_scope() as s:
        return {code: count for code, count in (await s.execute(stmt)).all()}


async def task_count_by_group_codes(
    group_codes: list[str], *, include_deleted: bool = False
) -> dict[str, int]:
    """``group_code → number of its tasks`` in one ``GROUP BY`` — for the group list.

    Same technique as the workspace counter: the group list fits on screen whole, and a query per
    card would be an N+1 where a single grouping suffices. A group with no tasks is absent from
    the result — the caller fills in the zero.
    """
    if not group_codes:
        return {}
    stmt = (
        select(TasksTask.group_code, func.count())
        .where(TasksTask.group_code.in_(group_codes))
        .group_by(TasksTask.group_code)
    )
    if not include_deleted:
        stmt = stmt.where(TasksTask.deleted_at.is_(None))
    async with session_scope() as s:
        return {code: count for code, count in (await s.execute(stmt)).all()}


async def task_workspace_by_codes(codes: list[str]) -> dict[str, str]:
    """``code → workspace_code`` for live tasks in one query; missing ones are absent.

    Needed by whoever checks the boundary for a BATCH of codes: the workspace fence
    (``mcp/scope.py``) reads one task at a time, and over a list that would become a query per
    item. A code absent from the result means both "no such task" and "deleted": for a check
    before a write there is no difference between them.
    """
    if not codes:
        return {}
    stmt = select(TasksTask.code, TasksTask.workspace_code).where(
        TasksTask.code.in_(codes), TasksTask.deleted_at.is_(None)
    )
    async with session_scope() as s:
        return {code: workspace for code, workspace in (await s.execute(stmt)).all()}


async def release_group_tasks(
    s, group_code: str, *, disposal: str | None, target: str | None = None
) -> int:
    """Take every task off ``group_code`` before the group is soft-deleted; return how many live.

    Runs inside the caller's transaction (``group_crud.group_delete``): the group's deletion and
    the fate of its tasks commit together or not at all. Afterwards no task — live or already in
    the trash — points at the group, because nothing draws a deleted group and its tasks would
    vanish from every list while still existing.

    ``disposal`` is one of ``GROUP_TASK_DISPOSALS`` and is required while the group holds live
    tasks; with none it may be ``None``, and the trashed ones just lose the group. ``delete`` puts
    the live tasks and their subtask branches in the trash under one mark, then ungroups them like
    the rest, so a task restored later lands in "No group" rather than in a group that is gone.
    """
    rows = list(
        (
            await s.execute(
                select(TasksTask)
                .where(TasksTask.group_code == group_code)
                .order_by(TasksTask.created_at, TasksTask.code)
            )
        )
        .scalars()
        .all()
    )
    live = [row for row in rows if row.deleted_at is None]
    if live and disposal not in GROUP_TASK_DISPOSALS:
        raise TaskRuleError(
            GROUP_HAS_TASKS,
            f"The group holds {len(live)} live task(s) — say what becomes of them: "
            f"{', '.join(GROUP_TASK_DISPOSALS)}.",
        )
    destination: str | None = None
    if live and disposal == GROUP_TASKS_MOVE:
        if not target or target == group_code:
            raise ValueError("Name another group of this workspace to move the tasks to.")
        await _require_group_of(s, target, live[0].workspace_code)
        destination = target
    if live and disposal == GROUP_TASKS_DELETE:
        branch: list[str] = []
        for row in live:
            branch += [row.code, *await _descendant_codes(s, row.code)]
        stamp = await _branch_stamp(s, branch)
        await s.execute(
            update(TasksTask)
            .where(TasksTask.code.in_(branch), TasksTask.deleted_at.is_(None))
            .values(deleted_at=stamp)
        )
        # Bulk statement — the change feed is told by hand, as in ``task_delete``.
        mark_changes(s, "tasks.task", UPDATED, branch)
    # Edited through the ORM so ``updated_at`` moves, and filed at the end of the new row like any
    # refile (``_refile``); subtasks are in the same group and follow their parents.
    for row in rows:
        row.group_code = destination
        await _refile(s, row)
    await s.flush()
    return len(live)


async def task_regroup(codes: list[str], group_code: str | None) -> int:
    """Refile a batch of tasks into a group (``None`` — ungroup); return how many landed.

    One transaction for the whole batch, and that is its reason to exist: the same work as three
    ``task_update`` calls can apply partially, and a partially refiled batch looks exactly like a
    refiled one.

    That is also why the checks run before the first write: a missing task, tasks from different
    workspaces, a group from elsewhere — each is a ``ValueError`` listing the offending codes, and
    not a single row is touched.

    A subtask's group is its parent's, so the subtasks of a refiled root follow it, and a subtask
    in the batch without its parent is refused (except one returning to its parent's group).

    Rows are edited through the ORM, not with a bulk ``UPDATE``: the ``onupdate`` of
    ``updated_at`` lives on the mapper, and bypassing it would leave yesterday's timestamp.
    """
    if not codes:
        raise ValueError("No task codes given — name at least one task to file.")
    async with write_scope() as s:
        rows = list(
            (
                await s.execute(
                    select(TasksTask).where(
                        TasksTask.code.in_(codes), TasksTask.deleted_at.is_(None)
                    )
                )
            )
            .scalars()
            .all()
        )
        missing = [code for code in codes if code not in {row.code for row in rows}]
        if missing:
            raise ValueError(
                f"No live task for {', '.join(repr(code) for code in missing)} — "
                "nothing was filed."
            )
        workspaces = {row.workspace_code for row in rows}
        if len(workspaces) > 1:
            raise ValueError(
                "These tasks live in different workspaces "
                f"({', '.join(sorted(repr(code) for code in workspaces))}) — "
                "a single call files work inside one."
            )
        if group_code:
            await _require_group_of(s, group_code, workspaces.pop())
        target = group_code or None
        parent_by_subtask = dict(
            (
                await s.execute(
                    select(TasksLink.task_code, TasksLink.parent_code).where(
                        TasksLink.task_code.in_(codes), TasksLink.parent_code.is_not(None)
                    )
                )
            ).all()
        )
        parent_groups = dict(
            (
                await s.execute(
                    select(TasksTask.code, TasksTask.group_code).where(
                        TasksTask.code.in_(set(parent_by_subtask.values()))
                    )
                )
            ).all()
        )
        # A subtask whose parent is in the same batch will follow it anyway — nothing to refuse.
        misfiled = [
            code
            for code, parent in parent_by_subtask.items()
            if parent not in codes and parent_groups.get(parent) != target
        ]
        if misfiled:
            named = ", ".join(
                f"{code!r} (a subtask of {parent_by_subtask[code]!r})" for code in misfiled
            )
            raise ValueError(
                f"{named} — a subtask sits in its parent's group. File the parents instead, "
                "their subtasks follow them. Nothing was filed."
            )
        # Refiled tasks go to the end of the new group's row — one by one, in the order listed:
        # a root's row is its group, and its old position in another group means nothing here.
        for row in rows:
            if target == row.group_code:
                continue
            row.group_code = target
            await _refile(s, row)
            await _carry_children(s, row)
        await s.flush()
    return len(rows)


__all__ = [
    "KEEP",
    "task_count_by_group_codes",
    "task_count_by_workspace_codes",
    "task_create",
    "task_delete",
    "task_get",
    "task_list_by_parent",
    "task_list_by_workspace",
    "release_group_tasks",
    "task_regroup",
    "task_reorder",
    "task_restore",
    "task_update",
    "task_update_status",
    "task_workspace_by_codes",
]
