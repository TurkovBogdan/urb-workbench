"""CRUD for ``Workspace`` — workspaces. Each function owns its own session.

Reads accept ``include_deleted`` and by default hide logically deleted rows: for the rest of the
code "deleted" means "does not exist".

``workspace_delete`` is soft by default — and that is not a formality: the modules above refer to
a workspace with ``ON DELETE CASCADE``, so ``hard=True`` physically takes away all of their
contents belonging to this workspace, with no chance of recovery. The module does not know who
exactly refers to it, and must not: the cascade is declared on the child side.
"""

from __future__ import annotations

from sqlalchemy import delete as sa_delete, func, select, update

from src.core.database import session_scope, write_scope
from src.core.utils.date import utc_now
from src.modules.workspace.codes import new_code
from src.modules.workspace.constants import (
    COLOR_MAX,
    DESCRIPTION_MAX,
    ICON_MAX,
    SORT_DEFAULT,
    SORT_STEP,
    TITLE_MAX,
)
from src.modules.workspace.models.workspace import Workspace
from src.modules.workspace.text import clip, fit


async def _sort_at_end(s) -> int:
    """A position below every live workspace; with none — ``SORT_DEFAULT``.

    Computed in the same transaction as the insert, as for a task group: the value has no time to
    drift from a concurrent write, and two equal ``sort`` values do not break the order anyway —
    the title tie-break separates them.
    """
    stmt = select(func.min(Workspace.sort)).where(Workspace.deleted_at.is_(None))
    lowest = (await s.execute(stmt)).scalar_one_or_none()
    return SORT_DEFAULT if lowest is None else lowest - SORT_STEP


async def workspace_create(
    *,
    title: str,
    description: str | None = None,
    color: str | None = None,
    icon: str | None = None,
    sort: int | None = None,
) -> Workspace:
    """Create a workspace; ``sort=None`` — at the end of the list, a number — at that position.

    "At the end" rather than ``SORT_DEFAULT`` for the same reason as a task group: a new row
    sharing its ``sort`` with the others would get its place from the title, not from when it
    was added.
    """
    async with write_scope() as s:
        row = Workspace(
            code=new_code(),
            title=clip(title, TITLE_MAX),
            description=fit(description, DESCRIPTION_MAX, "workspace description"),
            color=clip(color, COLOR_MAX),
            icon=clip(icon, ICON_MAX),
            sort=await _sort_at_end(s) if sort is None else sort,
        )
        s.add(row)
        await s.flush()
        await s.refresh(row)
    return row


async def workspace_get(
    code: str, *, include_deleted: bool = False
) -> Workspace | None:
    stmt = select(Workspace).where(Workspace.code == code)
    if not include_deleted:
        stmt = stmt.where(Workspace.deleted_at.is_(None))
    async with session_scope() as s:
        return (await s.execute(stmt)).scalar_one_or_none()


async def workspace_list(*, include_deleted: bool = False) -> list[Workspace]:
    """All workspaces: higher ``sort`` on top, then by title (and by code, for stability)."""
    stmt = select(Workspace).order_by(
        Workspace.sort.desc(), Workspace.title.asc(), Workspace.code.asc()
    )
    if not include_deleted:
        stmt = stmt.where(Workspace.deleted_at.is_(None))
    async with session_scope() as s:
        return list((await s.execute(stmt)).scalars().all())


async def workspace_update(
    code: str,
    *,
    title: str | None = None,
    description: str | None = None,
    color: str | None = None,
    icon: str | None = None,
    sort: int | None = None,
) -> Workspace | None:
    """Update the given fields (``None`` = leave alone, ``""`` = clear; ``sort=0`` is a position).

    A deleted workspace is not editable: ``workspace_restore`` first.
    """
    async with write_scope() as s:
        row = await s.get(Workspace, code)
        if row is None or row.deleted_at is not None:
            return None
        if title is not None:
            row.title = clip(title, TITLE_MAX)
        if description is not None:
            row.description = fit(description, DESCRIPTION_MAX, "workspace description")
        if color is not None:
            row.color = clip(color, COLOR_MAX)
        if icon is not None:
            row.icon = clip(icon, ICON_MAX)
        if sort is not None:
            row.sort = sort
        await s.flush()
        await s.refresh(row)
    return row


async def workspace_reorder(
    code: str, *, after: str | None = None, before: str | None = None
) -> Workspace | None:
    """Place a workspace right below (``after``) or right above (``before``) another one.

    The same contract as ``tasks.crud.group.group_reorder``: the position is named by a
    neighbour, not a number — whoever drags a row with the mouse sees which rows it landed
    between, never its ``sort``. Exactly one reference point is required. After the insert the
    live list is renumbered in full, top to bottom in steps of ``SORT_STEP``, and only rows whose
    value changed are written: there are a handful of workspaces, and "split the gap in half"
    would only add a branch for when the gap runs out.

    ``None`` — the workspace is missing or deleted; a reference point that is itself, deleted or
    missing — ``ValueError`` naming the reason.
    """
    if (after is None) == (before is None):
        raise ValueError(
            "Pass exactly one of after / before — a position needs one point of reference."
        )
    anchor_code = after or before
    async with write_scope() as s:
        row = await s.get(Workspace, code)
        if row is None or row.deleted_at is not None:
            return None
        if anchor_code == code:
            raise ValueError(
                f"Workspace {code!r} cannot be placed relative to itself — name another one."
            )
        anchor = await s.get(Workspace, anchor_code)
        if anchor is None or anchor.deleted_at is not None:
            raise ValueError(f"Workspace {anchor_code!r} does not exist (or is deleted).")
        siblings = list(
            (
                await s.execute(
                    select(Workspace)
                    .where(Workspace.deleted_at.is_(None))
                    .order_by(
                        Workspace.sort.desc(), Workspace.title.asc(), Workspace.code.asc()
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
            if item.sort == place:
                continue
            # A Core UPDATE that writes ``updated_at`` back as itself: the column's ``onupdate``
            # would otherwise stamp every renumbered row, and the list shows that date as "last
            # change" — one drag would claim eight workspaces were edited just now.
            await s.execute(
                update(Workspace)
                .where(Workspace.code == item.code)
                .values(sort=place, updated_at=Workspace.updated_at)
                .execution_options(synchronize_session=False)
            )
        await s.refresh(row)
    return row


async def workspace_delete(code: str, *, hard: bool = False) -> bool:
    """Delete a workspace: softly (the default) or physically. ``True`` — the row existed.

    ``hard=True`` takes away, by FK cascade, everything the modules above kept in this workspace
    — no timestamp remains afterwards, there is nothing to restore.
    """
    async with write_scope() as s:
        row = await s.get(Workspace, code)
        if row is None:
            return False
        if hard:
            await s.execute(
                sa_delete(Workspace).where(Workspace.code == code)
            )
        else:
            await s.execute(
                update(Workspace)
                .where(Workspace.code == code, Workspace.deleted_at.is_(None))
                .values(deleted_at=utc_now())
            )
    return True


async def workspace_restore(code: str) -> bool:
    """Clear the deletion mark. ``True`` — the workspace was deleted and has been brought back."""
    async with write_scope() as s:
        row = await s.get(Workspace, code)
        if row is None or row.deleted_at is None:
            return False
        row.deleted_at = None
        await s.flush()
    return True


__all__ = [
    "workspace_create",
    "workspace_delete",
    "workspace_get",
    "workspace_list",
    "workspace_reorder",
    "workspace_restore",
    "workspace_update",
]
