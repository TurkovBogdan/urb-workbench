"""CRUD for ``TasksLink`` — the edges of the task tree. Each function owns its session.

A link row is created by ``task_create`` (together with the task) and deleted by the FK cascade —
which is why there is neither ``link_create`` nor ``link_delete`` here: an edge does not live apart
from its task. What remains are operations on the shape of the tree — moving a branch and placing
it among its siblings.

An edge has no soft delete: it is the task that gets "deleted", and its edge simply follows along
(which is why ``include_deleted`` is not a parameter here — there is nothing to filter).
"""

from __future__ import annotations

from sqlalchemy import func, select

from src.core.database import session_scope, write_scope
from src.modules.tasks.constants import SORT_DEFAULT, SORT_STEP, TASK_STATUSES_TERMINAL
from src.modules.tasks.models.group import TasksGroup
from src.modules.tasks.models.link import TasksLink
from src.modules.tasks.models.task import TasksTask


async def _workspace_of(s, task_code: str) -> str | None:
    """The task's workspace (``None`` — no such task)."""
    stmt = select(TasksTask.workspace_code).where(TasksTask.code == task_code)
    return (await s.execute(stmt)).scalar_one_or_none()


async def _group_of(s, task_code: str) -> str | None:
    """The task's group; ``None`` — the task is ungrouped (or missing — call it after the check)."""
    stmt = select(TasksTask.group_code).where(TasksTask.code == task_code)
    return (await s.execute(stmt)).scalar_one_or_none()


def _siblings(stmt, parent_code: str | None, workspace_code: str, group_code: str | None):
    """Narrow a query to the SIBLING ROW — the only place this rule is written down.

    A subtask's siblings are the children of the same parent, and the group plays no part: the
    parent sets the place in the tree, and the subtask's own group does not affect it (list
    sections show only roots).

    A ROOT has no parent, so its group serves as its row: on screen tasks are laid out in cards by
    group, the person reorders a row inside their card — and the row must match what they are
    moving. While the row was shared across the workspace, a drop at the top of a card meant "to
    the start of the whole workspace": it looked right inside the group, but in the database the
    task leapt over neighbouring groups. "Ungrouped" is a row like any other
    (``group_code IS NULL``), not the absence of one.

    The workspace stays in the condition even with a group: ungrouped tasks share no group code,
    and without it other workspaces' tasks would join the row.
    """
    stmt = stmt.where(TasksTask.workspace_code == workspace_code)
    if parent_code is not None:
        return stmt.where(TasksLink.parent_code == parent_code)
    stmt = stmt.where(TasksLink.parent_code.is_(None))
    if group_code is None:
        return stmt.where(TasksTask.group_code.is_(None))
    return stmt.where(TasksTask.group_code == group_code)


async def _next_sort(
    s,
    parent_code: str | None,
    workspace_code: str,
    group_code: str | None,
    *,
    moved_code: str,
) -> int:
    """End of the sibling row: ``max(sort) + SORT_STEP``; in an empty row — ``SORT_DEFAULT``.

    The moving task itself is excluded from the row — otherwise a reorder within the same list
    would keep shifting it relative to its own former position.
    """
    stmt = _siblings(
        select(func.max(TasksLink.sort))
        .join(TasksTask, TasksTask.code == TasksLink.task_code)
        .where(TasksLink.task_code != moved_code),
        parent_code,
        workspace_code,
        group_code,
    )
    top = (await s.execute(stmt)).scalar_one_or_none()
    return SORT_DEFAULT if top is None else top + SORT_STEP


async def bottom_sort(
    s,
    parent_code: str | None,
    workspace_code: str,
    group_code: str | None = None,
    *,
    moved_code: str | None = None,
) -> int:
    """A position below the whole row: ``min(sort) - SORT_STEP``; in an empty row — ``SORT_DEFAULT``.

    This is where a FRESH task lands (``task_create``), and one that changed group: in the new row
    it has no earned place, and assigning it someone else's by its old number would drop it into
    the middle at random. The value is computed, not a constant: a row once reordered with the
    mouse is renumbered in ``SORT_STEP`` steps from its length, and a task with a constant
    ``SORT_DEFAULT`` would wedge into its middle — the higher, the shorter the row.

    Bottom, not top: the arrangement at the top is handwork, and a fresh row must not jump over it
    just because it is fresh.

    ``moved_code`` excludes the moving task itself from the row — its former number has nothing to
    do with the new row, and once inside ``min`` it would drag the result along with it.
    """
    stmt = _siblings(
        select(func.min(TasksLink.sort)).join(
            TasksTask, TasksTask.code == TasksLink.task_code
        ),
        parent_code,
        workspace_code,
        group_code,
    )
    if moved_code is not None:
        stmt = stmt.where(TasksLink.task_code != moved_code)
    bottom = (await s.execute(stmt)).scalar_one_or_none()
    return SORT_DEFAULT if bottom is None else bottom - SORT_STEP


async def link_get(task_code: str) -> TasksLink | None:
    """The task's edge — its place in the tree (parent, group, position)."""
    async with session_scope() as s:
        return await s.get(TasksLink, task_code)


async def link_list_by_parent(parent_code: str | None) -> list[TasksLink]:
    """Edges of a node's children, in order; ``parent_code=None`` — the roots (of all workspaces)."""
    stmt = select(TasksLink).order_by(TasksLink.sort.desc(), TasksLink.task_code.asc())
    if parent_code is None:
        stmt = stmt.where(TasksLink.parent_code.is_(None))
    else:
        stmt = stmt.where(TasksLink.parent_code == parent_code)
    async with session_scope() as s:
        return list((await s.execute(stmt)).scalars().all())


async def link_map_by_task_codes(task_codes: list[str]) -> dict[str, TasksLink]:
    """``task_code → its edge`` in one query for the whole list.

    The place in the tree lives in a separate table, but the reader (a list row) needs it on the
    same row as the task's fields: without this map every card would fetch its edge in a separate
    query — exactly the N+1 that the workspace counters already avoid by grouping.
    """
    if not task_codes:
        return {}
    stmt = select(TasksLink).where(TasksLink.task_code.in_(task_codes))
    async with session_scope() as s:
        return {link.task_code: link for link in (await s.execute(stmt)).scalars().all()}


async def link_child_count_by_parent_codes(
    parent_codes: list[str], *, include_deleted: bool = False
) -> dict[str, int]:
    """``parent_code → number of its children`` in one ``GROUP BY``; childless nodes are absent.

    Counts live children, which is why the link table is joined with tasks: an edge carries no
    deletion mark at all (the task does), and without the join "there is more inside" would count
    a branch lying entirely in the bin.
    """
    if not parent_codes:
        return {}
    stmt = (
        select(TasksLink.parent_code, func.count())
        .join(TasksTask, TasksTask.code == TasksLink.task_code)
        .where(TasksLink.parent_code.in_(parent_codes))
        .group_by(TasksLink.parent_code)
    )
    if not include_deleted:
        stmt = stmt.where(TasksTask.deleted_at.is_(None))
    async with session_scope() as s:
        return {code: count for code, count in (await s.execute(stmt)).all()}


async def require_root_parent(s, parent_code: str) -> None:
    """Refuse if the named parent is itself a subtask: the tree here is one level deep.

    The schema does not forbid a second level — an edge may point at any task — so only this
    layer holds the line, on every path that sets a parent: creation and move.
    """
    parent_link = await s.get(TasksLink, parent_code)
    if parent_link is not None and parent_link.parent_code is not None:
        raise ValueError(
            f"Task {parent_code!r} is itself a subtask of {parent_link.parent_code!r}, and the "
            "tree is one level deep — a subtask has no subtasks of its own. Put the task under "
            f"{parent_link.parent_code!r} instead, next to {parent_code!r}."
        )


async def require_parent_group_alive(s, parent_code: str, group_code: str | None) -> None:
    """Refuse if the parent's group is deleted: the subtask would inherit it and leave the list.

    The screen lays tasks out by live groups, and a subtask carrying a deleted group's code shows
    up nowhere, even though it is alive and counted.
    """
    if group_code is None:
        return
    group = await s.get(TasksGroup, group_code)
    if group is None or group.deleted_at is not None:
        raise ValueError(
            f"Parent task {parent_code!r} is filed under group {group_code!r}, which does not "
            "exist (or is deleted) — a subtask takes its parent's group and would vanish from "
            f"the list. Refile {parent_code!r} into a live group first."
        )


def require_open_parent(parent_code: str, parent_status: str, child_status: str) -> None:
    """Refuse if an open task is being put under a closed one.

    Accepted or canceled work gets no new parts: an open subtask under it is work nobody will see
    in the queue. A closed one is fine, though: filing already-done work under an epic is tidying
    up history, not new work.
    """
    if parent_status in TASK_STATUSES_TERMINAL and child_status not in TASK_STATUSES_TERMINAL:
        raise ValueError(
            f"Parent task {parent_code!r} is {parent_status!r} — accepted or called-off work "
            f"takes no new open parts, and this one is {child_status!r}. Pick a live parent, or "
            "ask the person to reopen that one. Only a closed task may go under a closed one."
        )


async def _require_parent_for(s, task: TasksTask, parent_code: str) -> TasksTask:
    """A parent the task may be put under, or a refusal naming the reason."""
    if parent_code == task.code:
        raise ValueError(f"Task {task.code!r} cannot be its own parent.")
    parent = await s.get(TasksTask, parent_code)
    if parent is None or parent.deleted_at is not None:
        raise ValueError(f"Parent task {parent_code!r} does not exist (or is deleted).")
    if parent.workspace_code != task.workspace_code:
        raise ValueError(
            f"Parent task {parent_code!r} belongs to workspace {parent.workspace_code!r}, but "
            f"the task belongs to {task.workspace_code!r} — a branch never spans workspaces."
        )
    require_open_parent(parent_code, parent.status, task.status)
    await require_parent_group_alive(s, parent_code, parent.group_code)
    await require_root_parent(s, parent_code)
    # Subtasks in the bin count too: a restore puts them back in their old place in the tree, and
    # under the moved task they would become a second level nobody built.
    children_query = (
        select(TasksLink.task_code, TasksTask.deleted_at.is_not(None))
        .join(TasksTask, TasksTask.code == TasksLink.task_code)
        .where(TasksLink.parent_code == task.code)
    )
    children = (await s.execute(children_query)).all()
    if children:
        named = ", ".join(
            f"{code!r} (in the bin)" if binned else repr(code) for code, binned in children
        )
        bin_hint = (
            " A subtask in the bin has to be restored or purged first — that is the person's."
            if any(binned for _, binned in children)
            else ""
        )
        raise ValueError(
            f"Task {task.code!r} has subtasks of its own ({named}), and the tree is one level "
            "deep — it cannot become a subtask. Move its subtasks out first (to the root or "
            f"under another task), then move this one.{bin_hint}"
        )
    return parent


async def link_move_in(
    s, task: TasksTask, parent_code: str | None, *, sort: int | None = None
) -> TasksLink:
    """Move a task inside the caller's transaction: ``parent_code`` — under it, ``""``/``None`` — to
    the root. ``sort=None`` — below the whole new row, the way a task refiled to another group lands.

    It has no session of its own on purpose: ``task_update`` moves a task and edits its card in a
    single call, and a refused move must roll the edit back with it — otherwise the agent would
    read the error as "nothing happened" while the title has already been rewritten.

    A subtask takes its parent's group: the group says what the work is about, and a part of the
    work is about the same thing as the whole. A task moved out to the root keeps its group — the
    group of its former parent.
    """
    link = await s.get(TasksLink, task.code)
    parent = await _require_parent_for(s, task, parent_code) if parent_code else None
    group_code = parent.group_code if parent else task.group_code
    place = (
        sort
        if sort is not None
        else await bottom_sort(
            s, parent_code or None, task.workspace_code, group_code, moved_code=task.code
        )
    )
    link.parent_code = parent_code or None
    link.sort = place
    task.group_code = group_code
    return link


async def link_move(
    task_code: str,
    *,
    parent_code: str | None = None,
    sort: int | None = None,
) -> TasksLink | None:
    """Move a task under another parent (``None`` — make it a root). Returns ``None`` — no such task.

    The move rules live in ``link_move_in``. Only the default position is set here: the top of the
    new row, ``max(sort) + SORT_STEP``.

    The position can be given explicitly — then move and placement happen in one motion rather
    than a move followed by an edit: in between, the task would briefly show up at the end of
    someone else's row, and the person would see an intermediate state they never asked for.
    """
    async with write_scope() as s:
        task = await s.get(TasksTask, task_code)
        if task is None or await s.get(TasksLink, task_code) is None:
            return None
        place = (
            sort
            if sort is not None
            else await _next_sort(
                s,
                parent_code or None,
                task.workspace_code,
                task.group_code,
                moved_code=task_code,
            )
        )
        link = await link_move_in(s, task, parent_code, sort=place)
        await s.flush()
        await s.refresh(link)
    return link


async def link_reorder(task_code: str, *, after_code: str | None) -> list[TasksLink] | None:
    """Place a task right after ``after_code`` among its siblings and renumber the whole row.

    ``after_code=None`` — to the start of the row (dragged above the first row). ``None`` in the
    result — no such task; ``ValueError`` — the named sibling is from another row, i.e. the drag
    target was chosen wrong.

    **Why all siblings are renumbered, not just the moved row.** The row defines the order as a
    whole, and keeping it on "somewhere midway between neighbours" means sooner or later hitting a
    spot with no midpoint left: ``sort`` is an integer, and after a dozen reorders there is nothing
    to insert between two adjacent numbers. Renumbering the row in ``SORT_STEP`` steps keeps the
    gaps even at all times, and costs one ``UPDATE`` per row — no parent has rows thousands long.

    Who the siblings are is ``_siblings``: for a subtask, its parent's children; for a root, the
    tasks of its group.

    The pre-reorder order is the same one the list shows (``sort`` descending, then by code): when
    moving a row, the person moves it relative to THE row on their screen.
    """
    async with write_scope() as s:
        order = await link_reorder_in(s, task_code, after_code=after_code)
        if order is None:
            return None
        await s.flush()
        for item in order:
            await s.refresh(item)
    return order


async def link_reorder_in(
    s, task_code: str, *, after_code: str | None
) -> list[TasksLink] | None:
    """``link_reorder`` inside the caller's transaction — for a drag that also moves the task.

    The row is read from the same session and must see the move already made in it: the siblings
    are the row the task was dropped into, not the one it was taken from. The factory's sessions
    do not flush on their own (``autoflush=False``), so the move is flushed explicitly before the
    row is read.
    """
    await s.flush()
    link = await s.get(TasksLink, task_code)
    if link is None:
        return None
    workspace_code = await _workspace_of(s, task_code)

    stmt = _siblings(
        select(TasksLink)
        .join(TasksTask, TasksTask.code == TasksLink.task_code)
        .order_by(TasksLink.sort.desc(), TasksLink.task_code.asc()),
        link.parent_code,
        workspace_code,
        await _group_of(s, task_code),
    )
    row = list((await s.execute(stmt)).scalars().all())

    if after_code is not None and all(item.task_code != after_code for item in row):
        raise ValueError(
            f"Task {after_code!r} is not a sibling of {task_code!r} — a task can only be "
            "placed among the tasks it shares a parent with (a top-level task — among the "
            "tasks of its group)."
        )

    order = [item for item in row if item.task_code != task_code]
    at = (
        0
        if after_code is None
        else next(i for i, item in enumerate(order) if item.task_code == after_code) + 1
    )
    order.insert(at, link)

    # Number top to bottom: the first row gets the largest ``sort``. The floor is ``SORT_STEP``,
    # so the row never hits zero and there is always room for a future row at the very bottom.
    top = len(order) * SORT_STEP
    for index, item in enumerate(order):
        item.sort = top - index * SORT_STEP
    return order


__all__ = [
    "link_child_count_by_parent_codes",
    "link_get",
    "link_list_by_parent",
    "link_map_by_task_codes",
    "link_move",
    "link_move_in",
    "link_reorder",
    "link_reorder_in",
    "require_open_parent",
    "require_parent_group_alive",
    "require_root_parent",
]
