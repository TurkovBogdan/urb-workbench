"""CRUD for ``TasksGroup`` — task groups within a workspace. Each function owns its session.

Workspace consistency is checked here, on write: a group is created only in a live workspace, and
a reference to a missing workspace is a ``ValueError`` with a clear message rather than an
``IntegrityError`` from the depths of the driver. The FK in the schema stays as a safety net for
writes that bypass the CRUD.
"""

from __future__ import annotations

from sqlalchemy import delete as sa_delete, func, select, update

from src.core.database import session_scope, write_scope
from src.core.utils.date import utc_now
from src.modules.core_changes import DELETED, UPDATED, mark_changes
from src.modules.tasks.codes import new_code
from src.modules.tasks.constants import (
    COLOR_MAX,
    GROUP_DESCRIPTION_MAX,
    ICON_MAX,
    SORT_DEFAULT,
    SORT_STEP,
    TITLE_MAX,
)
from src.modules.tasks.crud.task import release_group_tasks
from src.modules.tasks.models.group import TasksGroup
from src.modules.tasks.text import clip, fit
from src.modules.workspace.models.workspace import Workspace


async def _require_workspace(s, workspace_code: str) -> None:
    """A live workspace, or refuse: a reference to a deleted one is as wrong as to a missing one."""
    stmt = select(Workspace.code).where(
        Workspace.code == workspace_code, Workspace.deleted_at.is_(None)
    )
    if (await s.execute(stmt)).scalar_one_or_none() is None:
        raise ValueError(
            f"Workspace {workspace_code!r} does not exist (or is deleted) — "
            "a group always belongs to a live workspace."
        )


async def _sort_at_end(s, workspace_code: str) -> int:
    """A position below every live group in the workspace; in an empty one — ``SORT_DEFAULT``.

    Computed in the same transaction as the insert: the value has no time to drift from a
    concurrent write, and two equal ``sort`` values do not break the order anyway — the title
    tie-break separates them.
    """
    stmt = select(func.min(TasksGroup.sort)).where(
        TasksGroup.workspace_code == workspace_code, TasksGroup.deleted_at.is_(None)
    )
    lowest = (await s.execute(stmt)).scalar_one_or_none()
    return SORT_DEFAULT if lowest is None else lowest - SORT_STEP


async def group_create(
    *,
    workspace_code: str,
    title: str,
    description: str | None = None,
    color: str | None = None,
    icon: str | None = None,
    sort: int | None = None,
) -> TasksGroup:
    """Create a group; ``sort=None`` — at the end of the list, a number — at that exact position.

    The default is "at the end" rather than ``SORT_DEFAULT`` on purpose: a new group sharing its
    ``sort`` with half its siblings gets its position from the title tie-break, which is random
    from the creator's point of view. The UI sends a number itself and never takes this branch.
    """
    async with write_scope() as s:
        await _require_workspace(s, workspace_code)
        row = TasksGroup(
            code=new_code(),
            workspace_code=workspace_code,
            title=clip(title, TITLE_MAX),
            description=fit(description, GROUP_DESCRIPTION_MAX, "group description"),
            color=clip(color, COLOR_MAX),
            icon=clip(icon, ICON_MAX),
            sort=await _sort_at_end(s, workspace_code) if sort is None else sort,
        )
        s.add(row)
        await s.flush()
        await s.refresh(row)
    return row


async def group_find_by_title(workspace_code: str, title: str) -> TasksGroup | None:
    """The workspace's live group with this title, case-insensitive; otherwise ``None``.

    Not needed by the schema but by whoever creates a group blind: there is no unique index on
    the "workspace + title" pair, and without this check one layout ends up with both "Billing"
    and "billing". Case is ignored because telling them apart means arguing with a person who
    sees them as one word.

    **Case is folded in Python, not in SQL**, and that is not taste. SQLite's ``lower()`` folds
    ASCII only: a Cyrillic title stays as it was, and the query finds nothing. On PostgreSQL the
    same function does fold Cyrillic — so ``func.lower`` would give the providers DIFFERENT
    behaviour on Russian titles, and on the dev provider the check would simply never fire,
    silently. The price is reading the workspace's groups in full; there are only a handful, and
    the caller reads the same list on the next line.
    """
    wanted = title.strip().casefold()
    stmt = select(TasksGroup).where(
        TasksGroup.workspace_code == workspace_code, TasksGroup.deleted_at.is_(None)
    )
    async with session_scope() as s:
        rows = list((await s.execute(stmt)).scalars().all())
    return next((row for row in rows if row.title.strip().casefold() == wanted), None)


async def group_get(code: str, *, include_deleted: bool = False) -> TasksGroup | None:
    stmt = select(TasksGroup).where(TasksGroup.code == code)
    if not include_deleted:
        stmt = stmt.where(TasksGroup.deleted_at.is_(None))
    async with session_scope() as s:
        return (await s.execute(stmt)).scalar_one_or_none()


async def group_list_by_workspace(
    workspace_code: str, *, include_deleted: bool = False
) -> list[TasksGroup]:
    """The workspace's groups: higher ``sort`` on top, then by title (and by code, for stability)."""
    stmt = (
        select(TasksGroup)
        .where(TasksGroup.workspace_code == workspace_code)
        .order_by(TasksGroup.sort.desc(), TasksGroup.title.asc(), TasksGroup.code.asc())
    )
    if not include_deleted:
        stmt = stmt.where(TasksGroup.deleted_at.is_(None))
    async with session_scope() as s:
        return list((await s.execute(stmt)).scalars().all())


async def group_update(
    code: str,
    *,
    title: str | None = None,
    description: str | None = None,
    color: str | None = None,
    icon: str | None = None,
    sort: int | None = None,
) -> TasksGroup | None:
    """Update the given group fields (``None`` = leave as is; ``sort=0`` is a valid position).

    A group's workspace never changes: moving a group between workspaces means dragging all its
    tasks along, which is a different operation, and nobody asked for it.
    """
    async with write_scope() as s:
        row = await s.get(TasksGroup, code)
        if row is None or row.deleted_at is not None:
            return None
        if title is not None:
            row.title = clip(title, TITLE_MAX)
        if description is not None:
            row.description = fit(description, GROUP_DESCRIPTION_MAX, "group description")
        if color is not None:
            row.color = clip(color, COLOR_MAX)
        if icon is not None:
            row.icon = clip(icon, ICON_MAX)
        if sort is not None:
            row.sort = sort
        await s.flush()
        await s.refresh(row)
    return row


async def group_reorder(
    code: str, *, after: str | None = None, before: str | None = None
) -> TasksGroup | None:
    """Place a group right below (``after``) or right above (``before``) a sibling.

    The position is given by a sibling, not a number: ``sort`` is internal mechanics, and whoever
    moves the group has no way to aim at it. Exactly one of the two reference points is required.

    After the insert the list is **renumbered in full** — top to bottom in steps of
    ``SORT_STEP`` — and only rows whose value actually changed are written. A workspace has a
    handful of groups, so the cheap "split the gap in half" arithmetic does not pay off: it adds a
    second branch for when the gap runs out, and that branch sits untested until the day it
    breaks.

    ``None`` — the group is missing or deleted; a reference point from another workspace, deleted
    or missing — ``ValueError`` naming the reason.
    """
    if (after is None) == (before is None):
        raise ValueError(
            "Pass exactly one of after / before — a position needs one point of reference."
        )
    anchor_code = after or before
    async with write_scope() as s:
        row = await s.get(TasksGroup, code)
        if row is None or row.deleted_at is not None:
            return None
        if anchor_code == code:
            raise ValueError(
                f"Group {code!r} cannot be placed relative to itself — name another group."
            )
        anchor = await s.get(TasksGroup, anchor_code)
        if anchor is None or anchor.deleted_at is not None:
            raise ValueError(f"Group {anchor_code!r} does not exist (or is deleted).")
        if anchor.workspace_code != row.workspace_code:
            raise ValueError(
                f"Group {anchor_code!r} belongs to workspace {anchor.workspace_code!r}, but "
                f"{code!r} belongs to {row.workspace_code!r} — a layout never spans workspaces."
            )
        siblings = list(
            (
                await s.execute(
                    select(TasksGroup)
                    .where(
                        TasksGroup.workspace_code == row.workspace_code,
                        TasksGroup.deleted_at.is_(None),
                    )
                    .order_by(
                        TasksGroup.sort.desc(),
                        TasksGroup.title.asc(),
                        TasksGroup.code.asc(),
                    )
                )
            )
            .scalars()
            .all()
        )
        ordered = [item for item in siblings if item.code != code]
        at = next(i for i, item in enumerate(ordered) if item.code == anchor_code)
        ordered.insert(at + 1 if after else at, row)
        top = SORT_DEFAULT + (len(ordered) - 1) * SORT_STEP
        for position, item in enumerate(ordered):
            place = top - position * SORT_STEP
            if item.sort != place:
                item.sort = place
        await s.flush()
        await s.refresh(row)
    return row


async def group_delete(
    code: str, *, hard: bool = False, tasks: str | None = None, target: str | None = None
) -> bool:
    """Delete a group: soft (default) or hard. ``True`` — the row existed.

    The group's tasks outlive it either way. With ``hard=True`` the FK's ``SET NULL`` ungroups
    them. A soft delete first takes every task off the group in the same transaction — ``tasks``
    says how (``ungroup`` / ``move`` to ``target`` / ``delete``), and is required while the group
    holds live tasks (``task_crud.release_group_tasks``). Tasks used to keep the reference so a
    restore could bring the layout back, but nothing draws a deleted group, so they vanished from
    the list; a restore now brings back the group alone.
    """
    async with write_scope() as s:
        row = await s.get(TasksGroup, code)
        if row is None:
            return False
        # Bulk statements yield no objects — so we name the code to the change feed ourselves.
        if hard:
            await s.execute(sa_delete(TasksGroup).where(TasksGroup.code == code))
            mark_changes(s, "tasks.group", DELETED, [code])
        else:
            if row.deleted_at is None:
                await release_group_tasks(s, code, disposal=tasks, target=target)
            await s.execute(
                update(TasksGroup)
                .where(TasksGroup.code == code, TasksGroup.deleted_at.is_(None))
                .values(deleted_at=utc_now())
            )
            mark_changes(s, "tasks.group", UPDATED, [code])
    return True


async def group_restore(code: str) -> bool:
    """Clear the deletion mark. ``True`` — the group was deleted and is now restored."""
    async with write_scope() as s:
        row = await s.get(TasksGroup, code)
        if row is None or row.deleted_at is None:
            return False
        row.deleted_at = None
        await s.flush()
    return True


async def group_count_by_workspace_codes(
    workspace_codes: list[str], *, include_deleted: bool = False
) -> dict[str, int]:
    """``workspace_code → number of its groups`` in one ``GROUP BY`` — for the workspace list.

    Counted for the whole list at once: there are a dozen cards on screen, and a query per card
    would be an N+1 where a single grouping suffices. A workspace without groups is absent from
    the result — the caller fills in the zero, to tell "not counted" from "found nothing".
    """
    if not workspace_codes:
        return {}
    stmt = (
        select(TasksGroup.workspace_code, func.count())
        .where(TasksGroup.workspace_code.in_(workspace_codes))
        .group_by(TasksGroup.workspace_code)
    )
    if not include_deleted:
        stmt = stmt.where(TasksGroup.deleted_at.is_(None))
    async with session_scope() as s:
        return {code: count for code, count in (await s.execute(stmt)).all()}


__all__ = [
    "group_count_by_workspace_codes",
    "group_create",
    "group_delete",
    "group_find_by_title",
    "group_get",
    "group_list_by_workspace",
    "group_reorder",
    "group_restore",
    "group_update",
]
