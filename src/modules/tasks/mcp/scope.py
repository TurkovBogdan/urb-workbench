"""The workspace fence: the session's active workspace and a check that a code points into it.

One rule for the whole surface: **the workspace is a hard boundary**. A code from another
workspace is not silently processed but refused, naming both workspaces. The reason is not
security — everyone here has the same access — but that a boundary error is otherwise
invisible: another workspace's task looks like a task, and another workspace's empty list looks
like "no work".

The fence does not guess the code's type: the caller names it with the same prefix it used to
strip the presentation form. Guessing from the prefix would break on a bare code, and we accept
a bare code on a par with ``TASK@…`` — it is the internal form, and forbidding it would mean
forbidding passing back what the module itself returned.

The owner is looked up through the CRUD of the neighbouring entities, not with a query of our
own: for ``STAGE@``/``JOURNAL@`` the workspace is reached via the task, and "what does it cost" is
not a concern here — the fence fires once per call, not once per output row.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from src.modules.tasks.codes import tagged
from src.modules.tasks.constants import (
    GROUP_CODE_PREFIX,
    JOURNAL_CODE_PREFIX,
    STAGE_CODE_PREFIX,
    TASK_CODE_PREFIX,
)
from src.modules.tasks.crud import group as group_crud
from src.modules.tasks.crud import journal as journal_crud
from src.modules.tasks.crud import stage as stage_crud
from src.modules.tasks.crud import task as task_crud
from src.modules.workspace.codes import tagged as workspace_tagged
from src.modules.workspace.constants import WORKSPACE_CODE_PREFIX
from src.modules.workspace.crud import workspace as workspace_crud
from src.modules.workspace.mcp import session
from src.modules.workspace.mcp.errors import workspace_mismatch
from src.modules.workspace.models.workspace import Workspace


async def _group_workspace(code: str) -> str | None:
    row = await group_crud.group_get(code, include_deleted=True)
    return row.workspace_code if row else None


async def _task_workspace(code: str) -> str | None:
    row = await task_crud.task_get(code, include_deleted=True)
    return row.workspace_code if row else None


async def _stage_workspace(code: str) -> str | None:
    row = await stage_crud.stage_get(code)
    return await _task_workspace(row.task_code) if row else None


async def _journal_workspace(code: str) -> str | None:
    row = await journal_crud.journal_get(code)
    return await _task_workspace(row.task_code) if row else None


async def _itself(code: str) -> str:
    """A workspace owns itself: its code is compared with the active one directly."""
    return code


_OWNER: dict[str, Callable[[str], Awaitable[str | None]]] = {
    WORKSPACE_CODE_PREFIX: _itself,
    GROUP_CODE_PREFIX: _group_workspace,
    TASK_CODE_PREFIX: _task_workspace,
    STAGE_CODE_PREFIX: _stage_workspace,
    JOURNAL_CODE_PREFIX: _journal_workspace,
}


async def workspace_of(prefix: str, bare: str) -> str | None:
    """The bare code of the workspace that owns the entity; ``None`` — there is no such entity.

    The fence leaves a missing row alone: the tool itself will say "not found", in its own
    wording — which is more precise than a generic one.
    """
    owner = _OWNER.get(prefix)
    if owner is None:
        raise ValueError(
            f"{prefix}@ is not an entity of this module — expected one of "
            f"{', '.join(sorted(_OWNER))}."
        )
    return await owner(bare)


async def require_active() -> Workspace:
    """The session's active workspace or a teaching refusal. Checks nothing beyond that."""
    return await session.require_active()


async def require_scope(prefix: str, bare: str) -> Workspace:
    """The active workspace + a check that the named entity lies in exactly that workspace.

    Returns the workspace rather than ``None``: the caller needs it on the very next line — to
    build the reply envelope — and a second query for what the fence has just read would be
    wasted.
    """
    active = await require_active()
    owner = await workspace_of(prefix, bare)
    if owner is not None and owner != active.code:
        holder = await workspace_crud.workspace_get(owner, include_deleted=True)
        raise workspace_mismatch(
            code=str(tagged(prefix, bare)),
            owner_code=str(workspace_tagged(WORKSPACE_CODE_PREFIX, owner)),
            owner_title=holder.title if holder else "unknown",
            active_code=str(workspace_tagged(WORKSPACE_CODE_PREFIX, active.code)),
            active_title=active.title,
        )
    return active


__all__ = ["require_active", "require_scope", "workspace_of"]
