"""CRUD for ``CodexMount`` — a codex's entry in a workspace: whether it is switched on there, its
place in the workspace's order, and whether the agent may write. Only the person mounts; the agent
reads the switched-on ones as its canvas.

**The order is the workspace's, over every codex.** The person arranges all codexes in a workspace,
the ones in use and the ones set aside, and switching one on or off must not move it: so switching
off keeps the row (``enabled = false``) with its place, and switching on again finds it there. A
codex never placed in the workspace has no row; it stands after the placed ones, by title, and
gets a row the first time it is switched on or moved.

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
    """The canvas: switched-on rows of live codexes, in the workspace's order."""
    return (
        select(CodexMount, Codex)
        .join(Codex, Codex.code == CodexMount.codex_code)
        .where(
            CodexMount.workspace_code == workspace_code,
            CodexMount.enabled.is_(True),
            Codex.deleted_at.is_(None),
        )
        .order_by(CodexMount.sort.desc(), CodexMount.codex_code.asc())
    )


async def _bottom_sort(s, workspace_code: str) -> int:
    lowest = await s.scalar(
        select(func.min(CodexMount.sort)).where(CodexMount.workspace_code == workspace_code)
    )
    return SORT_DEFAULT if lowest is None else lowest - SORT_STEP


async def _ordered(
    s, workspace_code: str, *, include_deleted: bool = False
) -> list[tuple[Codex, CodexMount | None]]:
    """Every codex in the workspace's order: placed ones by their row, then the never-placed."""
    codex_stmt = select(Codex)
    if not include_deleted:
        codex_stmt = codex_stmt.where(Codex.deleted_at.is_(None))
    codexes = {codex.code: codex for codex in (await s.scalars(codex_stmt)).all()}
    rows = (
        await s.scalars(
            select(CodexMount)
            .where(CodexMount.workspace_code == workspace_code)
            .order_by(CodexMount.sort.desc(), CodexMount.codex_code.asc())
        )
    ).all()
    placed = [(codexes[row.codex_code], row) for row in rows if row.codex_code in codexes]
    seen = {row.codex_code for row in rows}
    rest = sorted(
        (codex for code, codex in codexes.items() if code not in seen),
        key=lambda codex: (codex.title.casefold(), codex.code),
    )
    return [*placed, *((codex, None) for codex in rest)]


async def mount_add(
    codex_code: str, workspace_code: str, *, agent_can_edit: bool = True
) -> CodexMount:
    """Switch a live codex on in a live workspace — where it stood, or at the bottom if it never
    stood there."""
    async with write_scope() as s:
        codex = await s.get(Codex, codex_code)
        if codex is None or codex.deleted_at is not None:
            raise ValueError(f"CODEX@{codex_code} is not a live codex — nothing to mount.")
        workspace = await s.get(Workspace, workspace_code)
        if workspace is None or workspace.deleted_at is not None:
            raise ValueError(f"WORKSPACE@{workspace_code} is not a live workspace.")
        row = await s.get(CodexMount, (codex_code, workspace_code))
        if row is not None and row.enabled:
            raise ValueError(
                f"The codex {codex.title!r} is already mounted into {workspace.title!r}."
            )
        if row is None:
            row = CodexMount(
                codex_code=codex_code,
                workspace_code=workspace_code,
                agent_can_edit=agent_can_edit,
                sort=await _bottom_sort(s, workspace_code),
            )
            s.add(row)
        row.enabled = True
        await s.flush()
        await s.refresh(row)
    return row


async def mount_remove(codex_code: str, workspace_code: str) -> bool:
    """Switch off, keeping the place and dropping the agent's right to write — switching back on
    does not hand it back. ``True`` — the codex was switched on there."""
    async with write_scope() as s:
        row = await s.get(CodexMount, (codex_code, workspace_code))
        if row is None or not row.enabled:
            return False
        row.enabled = False
        row.agent_can_edit = False
    return True


async def mount_set_agent_can_edit(
    codex_code: str, workspace_code: str, value: bool
) -> CodexMount | None:
    """The agent's right — on a switched-on codex only; ``None`` — not mounted there."""
    async with write_scope() as s:
        row = await s.get(CodexMount, (codex_code, workspace_code))
        if row is None or not row.enabled:
            return None
        row.agent_can_edit = value
        await s.flush()
        await s.refresh(row)
    return row


async def mount_get(codex_code: str, workspace_code: str) -> CodexMount | None:
    """The mount through which a workspace sees a codex; ``None`` — not visible there.

    A switched-off or deleted codex is not visible: this is the check both surfaces ask before
    showing or writing anything of a codex.
    """
    async with session_scope() as s:
        row = await s.execute(
            _live_mounts(workspace_code).where(CodexMount.codex_code == codex_code)
        )
        found = row.first()
    return found[0] if found else None


async def mount_list(workspace_code: str) -> list[tuple[CodexMount, Codex]]:
    """The canvas of a workspace: its switched-on live codexes, in the workspace's order."""
    async with session_scope() as s:
        return [tuple(row) for row in (await s.execute(_live_mounts(workspace_code))).all()]


async def workspace_codexes(
    workspace_code: str, *, include_deleted: bool = False
) -> list[tuple[Codex, CodexMount | None]]:
    """Every codex as this workspace orders it, with its row — switched on or off — or ``None``
    when it was never placed here."""
    async with session_scope() as s:
        return await _ordered(s, workspace_code, include_deleted=include_deleted)


async def mount_counts() -> dict[str, int]:
    """How many live workspaces each codex is switched on in."""
    async with session_scope() as s:
        rows = await s.execute(
            select(CodexMount.codex_code, func.count())
            .join(Workspace, Workspace.code == CodexMount.workspace_code)
            .where(Workspace.deleted_at.is_(None), CodexMount.enabled.is_(True))
            .group_by(CodexMount.codex_code)
        )
        return {code: count for code, count in rows.all()}


async def mount_reorder(
    codex_code: str, workspace_code: str, *, after_code: str | None
) -> list[tuple[Codex, CodexMount | None]] | None:
    """Place a codex right after ``after_code`` in the workspace's order (``None`` — at the top),
    switched on or not, and renumber the whole order.

    Every codex the order reaches gets a row (switched off if it had none) — a place is a row. The
    row is renumbered in ``SORT_STEP`` steps, as ``tasks`` does with siblings: an integer gap runs
    out after a dozen moves, an even row never does. ``None`` — no such live codex.
    """
    async with write_scope() as s:
        if (await s.get(Workspace, workspace_code)) is None:
            return None
        order = await _ordered(s, workspace_code, include_deleted=True)
        moved = next((entry for entry in order if entry[0].code == codex_code), None)
        if moved is None or moved[0].deleted_at is not None:
            return None
        if after_code is not None and all(codex.code != after_code for codex, _ in order):
            raise ValueError(f"CODEX@{after_code} is not a codex of this workspace's order.")
        order = [entry for entry in order if entry[0].code != codex_code]
        at = (
            0
            if after_code is None
            else next(i for i, (codex, _) in enumerate(order) if codex.code == after_code) + 1
        )
        order.insert(at, moved)
        top = len(order) * SORT_STEP
        placed: list[tuple[Codex, CodexMount | None]] = []
        for index, (codex, row) in enumerate(order):
            if row is None:
                row = CodexMount(codex_code=codex.code, workspace_code=workspace_code, enabled=False)
                s.add(row)
            row.sort = top - index * SORT_STEP
            placed.append((codex, row))
        await s.flush()
    return await workspace_codexes(workspace_code)


__all__ = [
    "mount_add",
    "mount_counts",
    "mount_get",
    "mount_list",
    "mount_remove",
    "mount_reorder",
    "mount_set_agent_can_edit",
    "workspace_codexes",
]
