"""The ``tasks`` codes in the lookup: ``TASK@``, ``TASKGROUP@``, ``STAGE@``, ``JOURNAL@``, ``NOTE@``.

Every handler reads its codes in one query and settles each one the same way, in this order:
no row — ``not_found``; outside the workspace filter — ``foreign_scope``; deleted — ``deleted``.
A deleted entity of another workspace is ``foreign_scope``: that it was deleted is not said there.

**Where the workspace and the deletion come from.** A group and a task carry both in their own
row. A stage and a journal entry reach them through their task — they are deleted physically, so
the only way one is "deleted" is through a deleted task. A ``NOTE@`` is a ``notes`` document, but
only this module knows who holds it (``tasks_note``): it is answered here, through the holding
task, and a document no task holds is ``not_found``.

**Pages.** A task has its own; a stage and a journal entry live on their task's page, a note on
its page inside the task's; a group is a row of the groups list.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy import Select, or_, select

from src.core.database import session_scope
from src.modules.core_lookup import Filters, Miss, Preview, PreviewResult
from src.modules.notes.models.note import Note
from src.modules.tasks.codes import tagged
from src.modules.tasks.constants import NOTE_CODE_PREFIX, TASK_CODE_PREFIX
from src.modules.tasks.models import TasksGroup, TasksJournal, TasksNote, TasksStage, TasksTask
from src.modules.workspace.lookup import workspace_filter

GROUPS_PAGE = "/tasks/groups"


def task_page(task_code: str) -> str:
    return f"/tasks/task/{tagged(TASK_CODE_PREFIX, task_code)}"


async def _settle(
    codes: list[str], stmt: Select, filters: Filters, preview: Callable[[Any], Preview]
) -> PreviewResult:
    """``stmt`` selects ``code``, ``workspace_code`` and ``deleted`` per row, plus what ``preview``
    reads."""
    async with session_scope() as s:
        rows = {row.code: row for row in await s.execute(stmt)}
    narrowed = workspace_filter(filters)
    result: dict[str, Preview | Miss] = {}
    for code in codes:
        row = rows.get(code)
        if row is None:
            result[code] = Miss.NOT_FOUND
        elif narrowed is not None and row.workspace_code != narrowed:
            result[code] = Miss.FOREIGN_SCOPE
        elif row.deleted:
            result[code] = Miss.DELETED
        else:
            result[code] = preview(row)
    return result


async def task_preview(codes: list[str], filters: Filters) -> PreviewResult:
    stmt = select(
        TasksTask.code,
        TasksTask.workspace_code,
        TasksTask.deleted_at.is_not(None).label("deleted"),
        TasksTask.title,
        TasksTask.description,
    ).where(TasksTask.code.in_(codes))
    return await _settle(
        codes, stmt, filters, lambda row: Preview(row.title, row.description, task_page(row.code))
    )


async def group_preview(codes: list[str], filters: Filters) -> PreviewResult:
    stmt = select(
        TasksGroup.code,
        TasksGroup.workspace_code,
        TasksGroup.deleted_at.is_not(None).label("deleted"),
        TasksGroup.title,
        TasksGroup.description,
    ).where(TasksGroup.code.in_(codes))
    return await _settle(
        codes, stmt, filters, lambda row: Preview(row.title, row.description, GROUPS_PAGE)
    )


async def stage_preview(codes: list[str], filters: Filters) -> PreviewResult:
    stmt = (
        select(
            TasksStage.code,
            TasksTask.workspace_code,
            TasksTask.deleted_at.is_not(None).label("deleted"),
            TasksStage.title,
            TasksStage.description,
            TasksStage.task_code,
        )
        .join(TasksTask, TasksTask.code == TasksStage.task_code)
        .where(TasksStage.code.in_(codes))
    )
    return await _settle(
        codes,
        stmt,
        filters,
        lambda row: Preview(row.title, row.description, task_page(row.task_code)),
    )


async def journal_preview(codes: list[str], filters: Filters) -> PreviewResult:
    """A journal entry has a title and a body, no description: the preview's description is empty."""
    stmt = (
        select(
            TasksJournal.code,
            TasksTask.workspace_code,
            TasksTask.deleted_at.is_not(None).label("deleted"),
            TasksJournal.title,
            TasksJournal.task_code,
        )
        .join(TasksTask, TasksTask.code == TasksJournal.task_code)
        .where(TasksJournal.code.in_(codes))
    )
    return await _settle(
        codes, stmt, filters, lambda row: Preview(row.title, "", task_page(row.task_code))
    )


async def note_preview(codes: list[str], filters: Filters) -> PreviewResult:
    stmt = (
        select(
            Note.code,
            TasksTask.workspace_code,
            or_(Note.deleted_at.is_not(None), TasksTask.deleted_at.is_not(None)).label("deleted"),
            Note.title,
            Note.description,
            TasksNote.task_code,
        )
        .join(TasksNote, TasksNote.note_code == Note.code)
        .join(TasksTask, TasksTask.code == TasksNote.task_code)
        .where(Note.code.in_(codes))
    )
    return await _settle(
        codes,
        stmt,
        filters,
        lambda row: Preview(
            row.title,
            row.description,
            f"{task_page(row.task_code)}/note/{tagged(NOTE_CODE_PREFIX, row.code)}",
        ),
    )


__all__ = [
    "GROUPS_PAGE",
    "group_preview",
    "journal_preview",
    "note_preview",
    "stage_preview",
    "task_page",
    "task_preview",
]
