"""The reconciliation of the tasks' storage owners with their binding rows.

One ``tasks_file`` row stands for one live owner ``("TASK", <task code>, "")``. Every deletion
removes the rows in its transaction and releases the owners after the commit; a failure between
the two — a crash, a refused write — leaves a live owner with no row, and the file would outlive
its task for good. The reconciliation finds those owners and releases them.

- **An owner with no row** is released under the task's file lock, after the row is looked for
  again inside it: an attach that has taken its owner and not yet written its row holds that lock,
  so it is waited for, not mistaken for an orphan. The lock is this process's; an attach in
  another one (a separate ``--worker``, several server processes) is told apart by age instead:
  only owners taken longer than ``FILE_OWNER_GRACE`` ago are candidates — a revived owner counts
  from its revival. A soft-deleted task keeps its rows, and with them its owners.
- **A row with no live owner** whose file is live is reported, not repaired: the cause is not
  known here, and taking the owner again could bring back a file someone meant to let go. A row
  whose file the file manager deleted is the designed state — the binding waits for the file to
  come back — and is not reported.

Only owners of type ``TASK`` are this module's; the codex reconciles its own.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.core.loggers import get_logger
from src.core.utils.date import utc_now
from src.modules.core_storage.errors import FileNotFound
from src.modules.core_storage.services.files import file_get_many
from src.modules.core_storage.services.ownership import file_release, held_by_type
from src.modules.tasks.constants import FILE_OWNER_GRACE, TASK_CODE_PREFIX
from src.modules.tasks.crud import file as file_crud
from src.modules.tasks.file_owner import task_files_lock

_LOG = get_logger("tasks")


@dataclass(frozen=True)
class OwnerReconcileReport:
    released: int
    """Live owners with no binding row, released."""

    unheld: list[tuple[str, str]]
    """``(task_code, file_code)`` of rows whose file is live and whose owner is not — reported."""


async def reconcile_task_owners() -> OwnerReconcileReport:
    settled = utc_now() - FILE_OWNER_GRACE
    bound = await file_crud.task_file_pairs()
    released = 0
    for place in await held_by_type(TASK_CODE_PREFIX, taken_before=settled):
        task_code = place.owner.id
        if (task_code, place.file_code) in bound:
            continue
        async with task_files_lock(task_code):
            if await file_crud.task_file_get(task_code, place.file_code) is not None:
                continue
            try:
                if not await file_release(place.file_code, place.owner):
                    continue
            except FileNotFound:
                continue
        released += 1
        _LOG.info("tasks: released %s of task %s — no binding row held it", place.file_code, task_code)
    return OwnerReconcileReport(released=released, unheld=await _unheld())


async def _unheld() -> list[tuple[str, str]]:
    held = {(place.owner.id, place.file_code) for place in await held_by_type(TASK_CODE_PREFIX)}
    missing = sorted(pair for pair in await file_crud.task_file_pairs() if pair not in held)
    live = await file_get_many([file_code for _, file_code in missing])
    unheld = [pair for pair in missing if pair[1] in live]
    for task_code, file_code in unheld:
        _LOG.warning(
            "tasks: task %s binds %s and the storage counts no owner for it — left as is",
            task_code,
            file_code,
        )
    return unheld


__all__ = ["OwnerReconcileReport", "reconcile_task_owners"]
