"""Task notes in CRUD: a document of ``notes`` and its row in ``tasks_note``, written together.

Every refusal is checked by what is in both tables after it: a note created and then left without
its link is a document no task holds and nothing shows.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from src.core.database import session_scope
from src.modules.notes.crud import note as notes_crud
from src.modules.notes.models.note import Note
from src.modules.tasks.constants import SORT_DEFAULT, SORT_STEP, TYPE_SIMPLE
from src.modules.tasks.crud import note as note_crud
from src.modules.tasks.crud import task as task_crud
from src.modules.tasks.models.note import TasksNote

pytestmark = pytest.mark.db


async def _counts() -> tuple[int, int]:
    async with session_scope() as s:
        notes = (await s.execute(select(func.count()).select_from(Note))).scalar_one()
        links = (await s.execute(select(func.count()).select_from(TasksNote))).scalar_one()
    return notes, links


@pytest.fixture
async def task(workspace):
    return await task_crud.task_create(workspace_code=workspace.code, title="Тарифы", type=TYPE_SIMPLE)


async def test_a_simple_task_keeps_notes_too(task):
    note = await note_crud.task_note_add(
        task_code=task.code, title="Схема", description="Когда открывать", body="# Схема\n"
    )

    assert await note_crud.task_note_task(note.code) == task.code
    stored = await notes_crud.note_get(note.code)
    assert (stored.title, stored.description, stored.body) == ("Схема", "Когда открывать", "# Схема\n")


async def test_notes_list_top_to_bottom_in_the_order_they_were_added(task):
    first = await note_crud.task_note_add(task_code=task.code, title="Первый")
    second = await note_crud.task_note_add(task_code=task.code, title="Второй")

    listed = await note_crud.task_note_list(task.code)

    assert [note.code for note in listed] == [first.code, second.code]
    async with session_scope() as s:
        sorts = [(await s.get(TasksNote, code)).sort for code in (first.code, second.code)]
    assert sorts == [SORT_DEFAULT, SORT_DEFAULT - SORT_STEP]


async def test_the_list_hides_a_deleted_note_and_carries_no_body(task):
    kept = await note_crud.task_note_add(task_code=task.code, title="Остаётся", body="текст")
    gone = await note_crud.task_note_add(task_code=task.code, title="Уходит")
    await notes_crud.note_delete(gone.code)

    [listed] = await note_crud.task_note_list(task.code)

    assert listed.code == kept.code
    with pytest.raises(SQLAlchemyError, match="body"):
        listed.body


async def test_a_deleted_task_takes_no_new_note(task):
    await task_crud.task_delete(task.code)

    with pytest.raises(ValueError, match="does not exist \\(or is deleted\\)"):
        await note_crud.task_note_add(task_code=task.code, title="Схема")

    assert await _counts() == (0, 0)


async def test_a_refusal_after_the_document_was_written_leaves_neither_half(task, monkeypatch):
    """The document is flushed before its link: a failure between them must take the document
    back too, or it stays as a note no task holds."""

    async def broken(s, task_code):
        raise RuntimeError("link refused")

    monkeypatch.setattr(note_crud, "_sort_at_end", broken)

    with pytest.raises(RuntimeError, match="link refused"):
        await note_crud.task_note_add(task_code=task.code, title="Схема")

    assert await _counts() == (0, 0)


async def test_a_body_over_the_limit_writes_nothing(task):
    with pytest.raises(ValueError, match="limit is 65536"):
        await note_crud.task_note_add(task_code=task.code, title="Схема", body="ж" * 65537)

    assert await _counts() == (0, 0)


async def test_a_hard_deleted_task_takes_its_links_and_leaves_the_documents(task):
    note = await note_crud.task_note_add(task_code=task.code, title="Схема")

    await task_crud.task_delete(task.code, hard=True)

    assert await note_crud.task_note_task(note.code) is None
    assert await notes_crud.note_get(note.code) is not None


async def test_a_hard_deleted_document_takes_its_link(task):
    note = await note_crud.task_note_add(task_code=task.code, title="Схема")

    await notes_crud.note_delete(note.code, hard=True)

    assert await note_crud.task_note_task(note.code) is None
    assert await note_crud.task_note_list(task.code) == []
