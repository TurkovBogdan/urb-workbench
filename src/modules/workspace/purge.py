"""Hooks "before final deletion" — how the modules above let go of what the FK cascade takes.

``workspace_delete(hard=True)`` removes the workspace row, and the database cascade removes the
rows of the modules above that point at it. A database cascade cannot do what lies outside the
database: a module whose rows hold something elsewhere — a storage owner of a file — is never told
its rows are gone. So it registers a hook here, as it registers a card counter (``stats.py``).

A hook runs in two steps, and the split is the point:

1. ``before_purge(session, workspace_code)`` runs inside the deleting transaction, before the
   workspace row goes — the rows the cascade is about to take are still there to be read. It only
   reads, and returns what to do once the deletion has committed (or ``None`` — nothing).
2. That step runs after the commit. Calls that open a write transaction of their own — the file
   storage does — must not run inside ours: a nested writer on SQLite waits on the lock until the
   timeout. A failing step is logged and the rest still run; the deletion stays done.

The registry is process-global and keyed, like the counters': a repeated application build
overwrites the entry by key.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.loggers import get_logger

AfterPurge = Callable[[], Awaitable[None]]
BeforePurge = Callable[[AsyncSession, str], Awaitable[AfterPurge | None]]

_LOG = get_logger("workspace")


@dataclass(frozen=True)
class WorkspacePurgeHook:
    """A module's part in a workspace's final deletion."""

    key: str
    """Who registered it — unique across the app; hooks run in key order."""

    before_purge: BeforePurge = field(compare=False)
    """``(session, workspace code) -> step after the commit``, read-only inside the deletion."""


_REGISTRY: dict[str, WorkspacePurgeHook] = {}


def register_purge_hook(hook: WorkspacePurgeHook) -> None:
    """Declare a hook (registering a key again replaces it)."""
    _REGISTRY[hook.key] = hook


def registered_purge_hooks() -> list[WorkspacePurgeHook]:
    return sorted(_REGISTRY.values(), key=lambda hook: hook.key)


def reset_purge_hooks() -> None:
    """Clear the registry — for tests that need a deletion without other modules' hooks."""
    _REGISTRY.clear()


async def collect_before_purge(
    session: AsyncSession, workspace_code: str
) -> list[tuple[str, AfterPurge]]:
    """Every hook's step after the commit, collected inside the deleting transaction."""
    steps: list[tuple[str, AfterPurge]] = []
    for hook in registered_purge_hooks():
        step = await hook.before_purge(session, workspace_code)
        if step is not None:
            steps.append((hook.key, step))
    return steps


async def run_after_purge(workspace_code: str, steps: list[tuple[str, AfterPurge]]) -> None:
    """Run the collected steps one by one; a failure is logged and does not stop the others."""
    for key, step in steps:
        try:
            await step()
        except Exception:
            _LOG.exception(
                "workspace: the %s step after purging %s failed — a reconciliation picks it up",
                key,
                workspace_code,
            )


__all__ = [
    "AfterPurge",
    "BeforePurge",
    "WorkspacePurgeHook",
    "collect_before_purge",
    "register_purge_hook",
    "registered_purge_hooks",
    "reset_purge_hooks",
    "run_after_purge",
]
