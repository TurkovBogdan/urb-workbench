"""Reads for moving a task between installations — whole rows by code, deleted ones included.

The rest of the module hides a deleted row; an import must see it: a code in the bin is still a
taken code, and a task in the bin is what «update» brings back. Writes are not here — the import
writes its rows in one transaction of its own (``transfer/apply.py``).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from sqlalchemy import select

from src.core.database import session_scope
from src.modules.notes.models.note import Note
from src.modules.tasks.models.file import TasksFile
from src.modules.tasks.models.journal import TasksJournal
from src.modules.tasks.models.link import TasksLink
from src.modules.tasks.models.note import TasksNote
from src.modules.tasks.models.stage import TasksStage
from src.modules.tasks.models.task import TasksTask


def _codes(codes: Iterable[str]) -> list[str]:
    return sorted(set(codes))


async def rows_by_codes(model: Any, codes: Iterable[str], *, key: str = "code") -> dict[str, Any]:
    """``code → row`` for the codes taken in this base; a deleted row counts."""
    wanted = _codes(codes)
    if not wanted:
        return {}
    column = getattr(model, key)
    async with session_scope() as s:
        rows = (await s.execute(select(model).where(column.in_(wanted)))).scalars().all()
    return {getattr(row, key): row for row in rows}


async def links_of(task_codes: Iterable[str]) -> dict[str, TasksLink]:
    return await rows_by_codes(TasksLink, task_codes, key="task_code")


async def live_children(parent_code: str) -> list[TasksTask]:
    """The live subtasks of a task, top of their row first."""
    async with session_scope() as s:
        stmt = (
            select(TasksTask)
            .join(TasksLink, TasksLink.task_code == TasksTask.code)
            .where(TasksLink.parent_code == parent_code, TasksTask.deleted_at.is_(None))
            .order_by(TasksLink.sort.desc(), TasksTask.created_at)
        )
        return list((await s.execute(stmt)).scalars().all())


async def stages_of(task_codes: Iterable[str]) -> list[TasksStage]:
    wanted = _codes(task_codes)
    async with session_scope() as s:
        stmt = (
            select(TasksStage)
            .where(TasksStage.task_code.in_(wanted))
            .order_by(TasksStage.task_code, TasksStage.number)
        )
        return list((await s.execute(stmt)).scalars().all())


async def journal_of(task_codes: Iterable[str]) -> list[TasksJournal]:
    wanted = _codes(task_codes)
    async with session_scope() as s:
        stmt = (
            select(TasksJournal)
            .where(TasksJournal.task_code.in_(wanted))
            .order_by(TasksJournal.task_code, TasksJournal.created_at, TasksJournal.code)
        )
        return list((await s.execute(stmt)).scalars().all())


async def live_notes_of(task_codes: Iterable[str]) -> list[tuple[TasksNote, Note]]:
    """The live notes of the tasks with their documents, in each task's order."""
    wanted = _codes(task_codes)
    async with session_scope() as s:
        stmt = (
            select(TasksNote, Note)
            .join(Note, Note.code == TasksNote.note_code)
            .where(TasksNote.task_code.in_(wanted), Note.deleted_at.is_(None))
            .order_by(TasksNote.task_code, TasksNote.sort.desc(), TasksNote.created_at)
        )
        return [(link, note) for link, note in (await s.execute(stmt)).all()]


async def notes_by_codes(codes: Iterable[str]) -> dict[str, tuple[Note, TasksNote | None]]:
    """``note code → (document, its task link or None)`` for the codes taken here."""
    wanted = _codes(codes)
    if not wanted:
        return {}
    async with session_scope() as s:
        stmt = (
            select(Note, TasksNote)
            .outerjoin(TasksNote, TasksNote.note_code == Note.code)
            .where(Note.code.in_(wanted))
        )
        return {note.code: (note, link) for note, link in (await s.execute(stmt)).all()}


async def bindings_of(task_codes: Iterable[str]) -> dict[tuple[str, str], TasksFile]:
    """``(task code, file code) → binding`` of the tasks."""
    wanted = _codes(task_codes)
    if not wanted:
        return {}
    async with session_scope() as s:
        rows = (await s.execute(select(TasksFile).where(TasksFile.task_code.in_(wanted)))).scalars().all()
    return {(row.task_code, row.file_code): row for row in rows}


async def codes_in_use(model: Any, codes: Iterable[str]) -> set[str]:
    return set(await rows_by_codes(model, codes))


__all__ = [
    "bindings_of",
    "codes_in_use",
    "journal_of",
    "links_of",
    "live_children",
    "live_notes_of",
    "notes_by_codes",
    "rows_by_codes",
    "stages_of",
]
