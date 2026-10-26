"""This module's part in a workspace's final deletion: let go of the files its tasks held.

The FK cascade from ``workspaces`` takes the tasks, and with them their ``tasks_file`` rows; the
storage owners ``("TASK", <task code>, "")`` live in another module's table and would stay live
for good. The hook (``workspace.purge``) reads the codes of every task of the workspace — the
soft-deleted ones too, the cascade takes them all — inside the deleting transaction, and after
the commit releases each task from every file it held.

The tasks' file locks are not taken: an attach to one of these tasks running meanwhile has its row
refused (the task is gone) and gives its owner back itself, and ``owner_release_everywhere``
releases every owner of a task, bound or not.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.tasks.file_owner import release_tasks_everywhere
from src.modules.tasks.models.task import TasksTask
from src.modules.workspace.purge import AfterPurge, WorkspacePurgeHook


async def collect_purged_tasks(session: AsyncSession, workspace_code: str) -> AfterPurge | None:
    in_workspace = select(TasksTask.code).where(TasksTask.workspace_code == workspace_code)
    codes = list(await session.scalars(in_workspace))
    if not codes:
        return None

    async def release() -> None:
        await release_tasks_everywhere(codes)

    return release


WORKSPACE_PURGE_HOOK = WorkspacePurgeHook(key="tasks", before_purge=collect_purged_tasks)


__all__ = ["WORKSPACE_PURGE_HOOK", "collect_purged_tasks"]
