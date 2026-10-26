"""The workspace fence: the session's active workspace and a check that a code points into it.

One rule for the whole surface: **the workspace is a hard boundary**. A code from another
workspace is not silently processed but refused, naming both workspaces. The reason is not
security — everyone here has the same access — but that a boundary error is otherwise
invisible: another workspace's task looks like a task, and another workspace's empty list looks
like "no work".

The fence does not guess the code's type: the caller names it with the same prefix it used to
strip the presentation form. Guessing from the prefix would break on a bare code, and we accept
a bare code on a par with ``TASK@…`` — it is the internal form, and forbidding it would mean
forbidding passing back what the surface itself returned.

Whether a code is visible is each type's own answer (``contracts.Fence``), registered here by
prefix. A tool that holds a handler of a shared method asks that handler instead
(``require_visible``) — the handler is a fence too.
"""

from __future__ import annotations

from src.modules.workbench import session
from src.modules.workbench.contracts import Fence, OwnedFence, by_prefix
from src.modules.workbench.entities.codex import CodexFence
from src.modules.workbench.entities.file import FileFence
from src.modules.workbench.entities.tasks import (
    GroupFence,
    JournalFence,
    NoteFence,
    StageFence,
    TaskFence,
)
from src.modules.workbench.entities.workspace import WorkspaceFence
from src.modules.workspace.models.workspace import Workspace

FENCES: dict[str, Fence] = by_prefix(
    WorkspaceFence(),
    GroupFence(),
    TaskFence(),
    StageFence(),
    JournalFence(),
    NoteFence(),
    CodexFence(),
    FileFence(),
)


def _fence(prefix: str) -> Fence:
    fence = FENCES.get(prefix)
    if fence is None:
        raise ValueError(
            f"{prefix}@ is not an entity of this module — expected one of "
            f"{', '.join(sorted(FENCES))}."
        )
    return fence


async def workspace_of(prefix: str, bare: str) -> str | None:
    """The bare code of the workspace that owns the entity; ``None`` — there is no such entity.

    Only for a type owned by one workspace (``OwnedFence``). The fence leaves a missing row
    alone: the tool itself will say "not found", in its own wording — which is more precise than
    a generic one.
    """
    fence = _fence(prefix)
    if not isinstance(fence, OwnedFence):
        raise ValueError(f"{prefix}@ is not owned by one workspace — ask its fence instead.")
    return await fence.owner(bare)


async def require_active() -> Workspace:
    """The session's active workspace or a teaching refusal. Checks nothing beyond that."""
    return await session.require_active()


async def require_visible(fence: Fence, bare: str) -> Workspace:
    """The active workspace + the handler's own answer that ``bare`` is visible in it.

    Returns the workspace rather than ``None``: the caller needs it on the very next line — to
    build the reply envelope — and a second query for what the fence has just read would be
    wasted.
    """
    active = await require_active()
    await fence.require_visible(bare, active)
    return active


async def require_scope(prefix: str, bare: str) -> Workspace:
    """The active workspace + a check that the named entity is visible in exactly that one."""
    active = await require_active()
    await _fence(prefix).require_visible(bare, active)
    return active


__all__ = ["FENCES", "require_active", "require_scope", "require_visible", "workspace_of"]
