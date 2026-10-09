"""CRUD for ``TasksNote`` — task notes: documents of the ``notes`` module that belong to a task.

The document is the ``notes`` module's: its fields, limits and soft delete live there, and this
layer reaches them through that module's service. What is the task's lives here: which task a
note belongs to and where it stands among the task's notes.

A note is created together with its row here, in one transaction (``note_create(session=…)``):
a refused link would otherwise leave a document behind that no task holds. A task of any type
keeps notes — a plan is a ``standard`` thing, a schema next to a short job is not.
"""

from __future__ import annotations

from sqlalchemy import func, select

from src.core.database import session_scope, write_scope
from src.modules.notes.crud import note as notes_crud
from src.modules.notes.models.note import Note
from src.modules.tasks.codes import tagged
from src.modules.tasks.constants import NOTE_CODE_PREFIX, SORT_DEFAULT, SORT_STEP, TASK_CODE_PREFIX
from src.modules.tasks.models.note import TasksNote
from src.modules.tasks.models.task import TasksTask


async def _sort_at_end(s, task_code: str) -> int:
    """A position below every note of the task; the first one gets ``SORT_DEFAULT``."""
    stmt = select(func.min(TasksNote.sort)).where(TasksNote.task_code == task_code)
    lowest = (await s.execute(stmt)).scalar_one_or_none()
    return SORT_DEFAULT if lowest is None else lowest - SORT_STEP


async def task_note_add(
    *, task_code: str, title: str, description: str | None = None, body: str | None = None
) -> Note:
    """Create a note of a live task, at the end of its notes. A refusal writes neither half."""
    async with write_scope() as s:
        task = await s.get(TasksTask, task_code)
        if task is None or task.deleted_at is not None:
            raise ValueError(
                f"Task {tagged(TASK_CODE_PREFIX, task_code)} does not exist (or is deleted) — a "
                "task note always belongs to a live task."
            )
        note = await notes_crud.note_create(
            title=title, description=description, body=body, session=s
        )
        sort = await _sort_at_end(s, task_code)
        s.add(TasksNote(note_code=note.code, task_code=task_code, sort=sort))
        await s.flush()
    return note


async def task_note_list(task_code: str) -> list[Note]:
    """The task's live notes, top to bottom, without ``body`` — the list a task shows."""
    stmt = (
        select(TasksNote.note_code)
        .where(TasksNote.task_code == task_code)
        .order_by(TasksNote.sort.desc(), TasksNote.created_at.asc(), TasksNote.note_code.asc())
    )
    async with session_scope() as s:
        codes = list((await s.execute(stmt)).scalars().all())
    return await notes_crud.note_get_many(codes)


async def task_note_task(note_code: str) -> str | None:
    """The task a note belongs to; ``None`` — the note is no task's."""
    async with session_scope() as s:
        row = await s.get(TasksNote, note_code)
    return row.task_code if row else None


async def task_note_reorder(task_code: str, codes: list[str]) -> None:
    """Put the named notes of a task in this order, top to bottom.

    The order comes whole, as the person sees it after a drag: the cards are a grid, and naming a
    position by one neighbour does not say where a card in the next row went. Notes left out —
    deleted ones the page does not show — keep their place below. A code that is not this task's
    is refused, and nothing moves.
    """
    wanted = list(dict.fromkeys(codes))
    async with write_scope() as s:
        stmt = select(TasksNote).where(TasksNote.task_code == task_code)
        links = {row.note_code: row for row in (await s.execute(stmt)).scalars().all()}
        foreign = [code for code in wanted if code not in links]
        if foreign:
            raise ValueError(
                f"Not notes of {tagged(TASK_CODE_PREFIX, task_code)}: "
                f"{', '.join(tagged(NOTE_CODE_PREFIX, code) or '' for code in foreign)}."
            )
        top = SORT_DEFAULT + (len(wanted) - 1) * SORT_STEP
        for position, code in enumerate(wanted):
            links[code].sort = top - position * SORT_STEP
        rest = [row for code, row in links.items() if code not in wanted]
        for position, row in enumerate(sorted(rest, key=lambda row: -row.sort), start=len(wanted)):
            row.sort = top - position * SORT_STEP


__all__ = ["task_note_add", "task_note_list", "task_note_reorder", "task_note_task"]
