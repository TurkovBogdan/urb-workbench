"""CRUD for ``CodexMount`` — which workspace sees which codex, in what order, and whether the agent
may write there. Only the person mounts; the agent reads the result as its canvas.

A mount of a soft-deleted codex stays in the table and is not part of the canvas: restoring the
codex puts it back in every workspace it was mounted into, with the same rights.
"""

from __future__ import annotations

from sqlalchemy import func, select

from src.core.database import session_scope, write_scope
from src.modules.codex.constants import SORT_DEFAULT, SORT_STEP
from src.modules.codex.models import Codex, CodexMount
from src.modules.workspace.models import Workspace


def _live_mounts(workspace_code: str):
    return (
        select(CodexMount, Codex)
        .join(Codex, Codex.code == CodexMount.codex_code)
        .where(CodexMount.workspace_code == workspace_code, Codex.deleted_at.is_(None))
        .order_by(CodexMount.sort.desc(), CodexMount.codex_code.asc())
    )


async def _bottom_sort(s, workspace_code: str) -> int:
    lowest = await s.scalar(
        select(func.min(CodexMount.sort)).where(CodexMount.workspace_code == workspace_code)
    )
    return SORT_DEFAULT if lowest is None else lowest - SORT_STEP


async def mount_add(
    codex_code: str, workspace_code: str, *, agent_can_edit: bool = True
) -> CodexMount:
    """Mount a live codex into a live workspace, at the bottom of its canvas."""
    async with write_scope() as s:
        codex = await s.get(Codex, codex_code)
        if codex is None or codex.deleted_at is not None:
            raise ValueError(f"CODEX@{codex_code} is not a live codex — nothing to mount.")
        workspace = await s.get(Workspace, workspace_code)
        if workspace is None or workspace.deleted_at is not None:
            raise ValueError(f"WORKSPACE@{workspace_code} is not a live workspace.")
        if await s.get(CodexMount, (codex_code, workspace_code)) is not None:
            raise ValueError(
                f"The codex {codex.title!r} is already mounted into {workspace.title!r}."
            )
        row = CodexMount(
            codex_code=codex_code,
            workspace_code=workspace_code,
            agent_can_edit=agent_can_edit,
            sort=await _bottom_sort(s, workspace_code),
        )
        s.add(row)
        await s.flush()
        await s.refresh(row)
    return row


async def mount_remove(codex_code: str, workspace_code: str) -> bool:
    """Unmount. ``True`` — the codex was mounted there."""
    async with write_scope() as s:
        row = await s.get(CodexMount, (codex_code, workspace_code))
        if row is None:
            return False
        await s.delete(row)
    return True


async def mount_set_agent_can_edit(
    codex_code: str, workspace_code: str, value: bool
) -> CodexMount | None:
    async with write_scope() as s:
        row = await s.get(CodexMount, (codex_code, workspace_code))
        if row is None:
            return None
        row.agent_can_edit = value
        await s.flush()
        await s.refresh(row)
    return row


async def mount_get(codex_code: str, workspace_code: str) -> CodexMount | None:
    """The mount through which a workspace sees a codex; ``None`` — not visible there.

    A deleted codex is not visible through its mount: this is the check both surfaces ask before
    showing or writing anything of a codex.
    """
    async with session_scope() as s:
        row = await s.execute(
            _live_mounts(workspace_code).where(CodexMount.codex_code == codex_code)
        )
        found = row.first()
    return found[0] if found else None


async def mount_list(workspace_code: str) -> list[tuple[CodexMount, Codex]]:
    """The canvas of a workspace: its live mounted codexes, top of the person's order first."""
    async with session_scope() as s:
        return [tuple(row) for row in (await s.execute(_live_mounts(workspace_code))).all()]


async def mount_reorder(
    codex_code: str, workspace_code: str, *, after_code: str | None
) -> list[CodexMount] | None:
    """Place a mount right after ``after_code`` in the canvas (``None`` — at the top) and renumber.

    The whole row is renumbered in ``SORT_STEP`` steps, as ``tasks`` does with siblings: an integer
    gap runs out after a dozen moves, an even row never does.
    """
    async with write_scope() as s:
        moved = await s.get(CodexMount, (codex_code, workspace_code))
        if moved is None:
            return None
        row = list(
            (
                await s.scalars(
                    select(CodexMount)
                    .where(CodexMount.workspace_code == workspace_code)
                    .order_by(CodexMount.sort.desc(), CodexMount.codex_code.asc())
                )
            ).all()
        )
        if after_code is not None and all(item.codex_code != after_code for item in row):
            raise ValueError(f"CODEX@{after_code} is not mounted into this workspace.")
        order = [item for item in row if item.codex_code != codex_code]
        at = (
            0
            if after_code is None
            else next(i for i, item in enumerate(order) if item.codex_code == after_code) + 1
        )
        order.insert(at, moved)
        top = len(order) * SORT_STEP
        for index, item in enumerate(order):
            item.sort = top - index * SORT_STEP
        await s.flush()
        for item in order:
            await s.refresh(item)
    return order


__all__ = [
    "mount_add",
    "mount_get",
    "mount_list",
    "mount_remove",
    "mount_reorder",
    "mount_set_agent_can_edit",
]
