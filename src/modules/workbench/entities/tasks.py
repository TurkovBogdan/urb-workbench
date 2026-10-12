"""The ``tasks`` types on the agent surface: ``TASKGROUP@``, ``TASK@``, ``STAGE@``, ``JOURNAL@``,
``NOTE@`` (a task note — a document of the ``notes`` module held by a task).

**Fences.** A group and a task carry their workspace in their own row; a stage, a journal entry
and a task note reach it through their task. The owner is looked up through the CRUD of the
entities, not with a query of our own: a fence fires once per call, not once per output row.

**What may be written** is the ``tasks`` module's rule (``tasks/rules.py``): a deleted task is
closed for edits, and so is everything hanging off it. The wording the agent reads is this
surface's — it names what to do instead (say so, do not make a replacement).
"""

from __future__ import annotations

from src.modules.notes.crud import note as notes_crud
from src.modules.tasks.codes import tagged
from src.modules.tasks.constants import (
    GROUP_CODE_PREFIX,
    JOURNAL_CODE_PREFIX,
    NOTE_CODE_PREFIX,
    STAGE_CODE_PREFIX,
    TASK_CODE_PREFIX,
)
from src.modules.tasks.crud import group as group_crud
from src.modules.tasks.crud import journal as journal_crud
from src.modules.tasks.crud import note as note_crud
from src.modules.tasks.crud import stage as stage_crud
from src.modules.tasks.crud import task as task_crud
from src.modules.tasks.rules import task_accepts_edits
from src.modules.workbench.contracts import Deletable, Openable, OwnedFence


def deleted_task_refusal(task_code: str) -> str:
    """One wording for every write that reaches a deleted task — its fields, stages, entries, notes."""
    return (
        f"{tagged(TASK_CODE_PREFIX, task_code)} is deleted — editing it is closed until a person "
        "restores it. Say so rather than creating a replacement."
    )


async def require_live_task(task_code: str) -> None:
    """A write to anything a task holds is a write to the task: a deleted one refuses it."""
    task = await task_crud.task_get(task_code, include_deleted=True)
    if task is None or not task_accepts_edits(task):
        raise ValueError(deleted_task_refusal(task_code))


# ── fences ────────────────────────────────────────────────────────────────────
class GroupFence(OwnedFence):
    prefix = GROUP_CODE_PREFIX

    async def owner(self, bare: str) -> str | None:
        row = await group_crud.group_get(bare, include_deleted=True)
        return row.workspace_code if row else None


class TaskFence(OwnedFence):
    prefix = TASK_CODE_PREFIX

    async def owner(self, bare: str) -> str | None:
        row = await task_crud.task_get(bare, include_deleted=True)
        return row.workspace_code if row else None


class StageFence(OwnedFence):
    prefix = STAGE_CODE_PREFIX

    async def owner(self, bare: str) -> str | None:
        row = await stage_crud.stage_get(bare)
        return await TaskFence().owner(row.task_code) if row else None


class JournalFence(OwnedFence):
    prefix = JOURNAL_CODE_PREFIX

    async def owner(self, bare: str) -> str | None:
        row = await journal_crud.journal_get(bare)
        return await TaskFence().owner(row.task_code) if row else None


class NoteFence(OwnedFence):
    prefix = NOTE_CODE_PREFIX

    async def owner(self, bare: str) -> str | None:
        """A task note's workspace is its task's. A ``NOTE@`` that is an old journal code is
        refused here, with the code it has now — every tool taking a ``NOTE@`` passes this fence
        first."""
        task_code = await note_crud.task_note_task(bare)
        if task_code is not None:
            return await TaskFence().owner(task_code)
        refusal = await journal_crud.retired_note_refusal(bare)
        if refusal is not None:
            raise ValueError(refusal)
        return None


# ── delete ────────────────────────────────────────────────────────────────────
class TaskDeletion(TaskFence, Deletable):
    async def delete(self, bare: str) -> bool:
        """The task and its whole branch, to the bin — a person can bring it back."""
        return await task_crud.task_delete(bare)


class StageDeletion(StageFence, Deletable):
    async def delete(self, bare: str) -> bool:
        """Removed outright: a step decided against is closed as canceled, which keeps why."""
        return await stage_crud.stage_delete(bare)


class NoteDeletion(NoteFence, Deletable):
    async def delete(self, bare: str) -> bool:
        """The note, to the bin; one held by no task is not a task note — from here it does not
        exist."""
        task_code = await note_crud.task_note_task(bare)
        if task_code is None:
            return False
        await require_live_task(task_code)
        return await notes_crud.note_delete(bare)


# ── pages ─────────────────────────────────────────────────────────────────────
async def _owning_task(prefix: str, bare: str) -> str:
    """The task that owns a stage or a journal entry."""
    if prefix == STAGE_CODE_PREFIX:
        row = await stage_crud.stage_get(bare)
    else:
        row = await journal_crud.journal_get(bare)
    if row is None:
        raise ValueError(f"{tagged(prefix, bare)} does not exist.")
    return row.task_code


def _task_page(task_code: str) -> str:
    return f"/tasks/task/{tagged(TASK_CODE_PREFIX, task_code)}"


class GroupPage(GroupFence, Openable):
    async def page(self, bare: str) -> str:
        """A group has no card page of its own: it lives as a row in the groups list."""
        return "/tasks/groups"


class TaskPage(TaskFence, Openable):
    async def page(self, bare: str) -> str:
        return _task_page(bare)


class StagePage(StageFence, Openable):
    async def page(self, bare: str) -> str:
        """A stage lives on its task's page and has none of its own."""
        return _task_page(await _owning_task(self.prefix, bare))


class JournalPage(JournalFence, Openable):
    async def page(self, bare: str) -> str:
        """A journal entry lives on its task's page and has none of its own."""
        return _task_page(await _owning_task(self.prefix, bare))


class NotePage(NoteFence, Openable):
    async def page(self, bare: str) -> str:
        """The page of a note — decided by what the note belongs to.

        A note of the ``notes`` module does not know its owner; each owner holds its own link.
        Today that is a task, and the note opens inside the task's page. A deleted note has no
        page to show — its owner's page lists it no more.
        """
        code = tagged(NOTE_CODE_PREFIX, bare)
        if await notes_crud.note_get(bare) is None:
            raise ValueError(f"{code} does not exist (or is deleted) — there is no page to show.")
        task = await note_crud.task_note_task(bare)
        if task is not None:
            return f"{_task_page(task)}/note/{code}"
        # Held by no owner this server knows: for the agent it does not exist, as for the other tools.
        raise ValueError(f"{code} does not exist (or is deleted) — there is no page to show.")


__all__ = [
    "GroupFence",
    "GroupPage",
    "JournalFence",
    "JournalPage",
    "NoteDeletion",
    "NoteFence",
    "NotePage",
    "StageDeletion",
    "StageFence",
    "StagePage",
    "TaskDeletion",
    "TaskFence",
    "TaskPage",
    "deleted_task_refusal",
    "require_live_task",
]
