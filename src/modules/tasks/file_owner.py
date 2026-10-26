"""The task as an owner in ``core_storage`` — and releasing it once the task's files are let go.

A task holds its files as one owner, ``("TASK", <task code>, "")``: its notes and stages are places
inside the task, not owners the storage sees. One binding row in ``tasks_file`` stands for exactly
one live owner row in the storage.

The release runs after the transaction that removed the binding rows has committed, never inside
it: the storage opens a write transaction of its own, and a nested writer on SQLite waits on the
lock until the timeout. A failure between the two leaves an owner without a binding — the file then
outlives its task until a reconciliation finds it; the opposite order would leave a binding to a
file the cleanup is free to remove.

Imports nothing of this module but its constants, so the deletion functions in ``crud`` can call it.
"""

from __future__ import annotations

from collections.abc import Iterable
from contextlib import AbstractAsyncContextManager

from src.modules.core_storage.dto import Owner
from src.modules.core_storage.errors import FileNotFound
from src.modules.core_storage.services.holder_lock import holder_lock, holder_locks
from src.modules.core_storage.services.ownership import file_release, owner_release_everywhere
from src.modules.tasks.constants import TASK_CODE_PREFIX


def task_owner(task_code: str) -> Owner:
    return Owner(type=TASK_CODE_PREFIX, id=task_code)


def task_files_lock(task_code: str) -> AbstractAsyncContextManager[None]:
    """One file operation of the task at a time — attach, detach, retitle, a deletion taking its
    files (``core_storage.services.holder_lock``). Not reentrant: take it once, at the top."""
    return holder_lock(TASK_CODE_PREFIX, task_code)


def tasks_files_lock(task_codes: Iterable[str]) -> AbstractAsyncContextManager[None]:
    """``task_files_lock`` of a whole branch at once, in a fixed order."""
    return holder_locks(TASK_CODE_PREFIX, task_codes)


async def release_task_file(task_code: str, file_code: str) -> bool:
    """Release the task's hold on one file; ``False`` — it held none (nothing changed).

    A file already gone from the storage holds nobody, which is what releasing was for.
    """
    try:
        return await file_release(file_code, task_owner(task_code))
    except FileNotFound:
        return False


async def release_task_files(pairs: Iterable[tuple[str, str]]) -> None:
    """Release every ``(task_code, file_code)`` pair whose binding row is gone."""
    for task_code, file_code in pairs:
        await release_task_file(task_code, file_code)


async def release_tasks_everywhere(task_codes: Iterable[str]) -> None:
    """Release purged tasks from every file they held — bound or left over from a failed release."""
    for task_code in task_codes:
        await owner_release_everywhere(TASK_CODE_PREFIX, task_code)


__all__ = [
    "release_task_file",
    "release_task_files",
    "release_tasks_everywhere",
    "task_files_lock",
    "task_owner",
    "tasks_files_lock",
]
