"""The notes service — what a consumer gets from each operation, and what a refusal leaves behind.

A refusal is checked by the state after it, not by its text alone: a write that validated half
of its values and touched the row before the second failed would refuse and still have written.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from src.core.database import session_scope
from src.modules.notes.constants import BODY_MAX, CODE_LEN, DESCRIPTION_MAX, TITLE_MAX
from src.modules.notes.crud import note as note_crud
from src.modules.notes.models.note import Note

pytestmark = pytest.mark.db


async def _count() -> int:
    async with session_scope() as s:
        return (await s.execute(select(func.count()).select_from(Note))).scalar_one()


# ── create ────────────────────────────────────────────────────────────────────


async def test_create_stores_the_document_under_an_upper_case_code(db):
    row = await note_crud.note_create(
        title="  Схема журнала  ", description="Когда открывать", body="# Таблицы\n"
    )

    stored = await note_crud.note_get(row.code)
    assert len(row.code) == CODE_LEN and row.code == row.code.upper()
    assert (stored.title, stored.description, stored.body) == (
        "Схема журнала",
        "Когда открывать",
        "# Таблицы\n",
    )
    assert stored.deleted_at is None


async def test_create_takes_each_field_up_to_its_limit(db):
    row = await note_crud.note_create(
        title="т" * TITLE_MAX, description="о" * DESCRIPTION_MAX, body="ж" * BODY_MAX
    )

    stored = await note_crud.note_get(row.code)
    assert (len(stored.title), len(stored.description), len(stored.body)) == (
        TITLE_MAX,
        DESCRIPTION_MAX,
        BODY_MAX,
    )


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"title": "т" * (TITLE_MAX + 1)}, f"limit is {TITLE_MAX}"),
        ({"title": "Т", "description": "о" * (DESCRIPTION_MAX + 1)}, f"limit is {DESCRIPTION_MAX}"),
        ({"title": "Т", "body": "ж" * (BODY_MAX + 1)}, f"limit is {BODY_MAX}"),
        ({"title": "   "}, "title is empty"),
    ],
    ids=["title", "description", "body", "blank-title"],
)
async def test_create_refuses_and_writes_nothing(db, fields, message):
    with pytest.raises(ValueError, match=message):
        await note_crud.note_create(**fields)

    assert await _count() == 0


# ── get ───────────────────────────────────────────────────────────────────────


async def test_get_hides_a_deleted_note_unless_asked(db):
    row = await note_crud.note_create(title="Удалённый")
    await note_crud.note_delete(row.code)

    assert await note_crud.note_get(row.code) is None
    assert (await note_crud.note_get(row.code, include_deleted=True)).code == row.code


async def test_get_many_keeps_the_callers_order_and_skips_what_is_not_there(db):
    first = await note_crud.note_create(title="Первый")
    second = await note_crud.note_create(title="Второй")
    gone = await note_crud.note_create(title="Удалённый")
    await note_crud.note_delete(gone.code)

    rows = await note_crud.note_get_many(
        [second.code, "0000000000", first.code, gone.code, second.code]
    )

    assert [row.title for row in rows] == ["Второй", "Первый"]
    listed = await note_crud.note_get_many([gone.code], include_deleted=True)
    assert [row.code for row in listed] == [gone.code]


async def test_get_many_leaves_the_body_unloaded(db):
    row = await note_crud.note_create(title="Длинный", body="ж" * 1000)

    [listed] = await note_crud.note_get_many([row.code])

    assert listed.title == "Длинный"
    with pytest.raises(SQLAlchemyError, match="body"):
        listed.body


async def test_get_many_of_nothing_is_empty(db):
    assert await note_crud.note_get_many([]) == []


# ── update ────────────────────────────────────────────────────────────────────


async def test_update_changes_only_what_is_passed(db):
    row = await note_crud.note_create(title="Схема", description="Когда", body="старый")

    await note_crud.note_update(row.code, body="новый")
    await note_crud.note_update(row.code, description="")

    stored = await note_crud.note_get(row.code)
    assert (stored.title, stored.description, stored.body) == ("Схема", "", "новый")
    assert stored.updated_at >= row.updated_at


async def test_update_refusing_one_field_changes_none(db):
    row = await note_crud.note_create(title="Схема", body="старый")

    with pytest.raises(ValueError, match=f"limit is {BODY_MAX}"):
        await note_crud.note_update(row.code, title="Новое имя", body="ж" * (BODY_MAX + 1))

    stored = await note_crud.note_get(row.code)
    assert (stored.title, stored.body) == ("Схема", "старый")


async def test_a_deleted_note_is_not_updated(db):
    row = await note_crud.note_create(title="Схема")
    await note_crud.note_delete(row.code)

    assert await note_crud.note_update(row.code, title="Новое") is None
    assert (await note_crud.note_get(row.code, include_deleted=True)).title == "Схема"


async def test_update_of_a_missing_note_is_none(db):
    assert await note_crud.note_update("0000000000", title="Новое") is None


# ── delete and restore ────────────────────────────────────────────────────────


async def test_soft_delete_keeps_the_row_and_its_first_mark(db, monkeypatch):
    row = await note_crud.note_create(title="Схема")

    assert await note_crud.note_delete(row.code) is True
    marked = (await note_crud.note_get(row.code, include_deleted=True)).deleted_at
    # Timestamps are whole seconds: without a later clock the second mark would equal the first
    # and a re-marking delete would pass unseen.
    monkeypatch.setattr(note_crud, "utc_now", lambda: marked + timedelta(days=1))
    assert await note_crud.note_delete(row.code) is True

    assert marked is not None
    assert (await note_crud.note_get(row.code, include_deleted=True)).deleted_at == marked
    assert await _count() == 1


@pytest.mark.parametrize("soft_first", [False, True], ids=["live", "already-soft"])
async def test_hard_delete_removes_the_row(db, soft_first):
    row = await note_crud.note_create(title="Схема")
    kept = await note_crud.note_create(title="Соседний")
    if soft_first:
        await note_crud.note_delete(row.code)

    assert await note_crud.note_delete(row.code, hard=True) is True

    assert await note_crud.note_get(row.code, include_deleted=True) is None
    assert await note_crud.note_get(kept.code) is not None


async def test_delete_of_a_missing_note_is_false(db):
    assert await note_crud.note_delete("0000000000") is False
    assert await note_crud.note_delete("0000000000", hard=True) is False


async def test_restore_brings_a_deleted_note_back_whole(db):
    row = await note_crud.note_create(title="Схема", body="текст")
    await note_crud.note_delete(row.code)

    assert await note_crud.note_restore(row.code) is True

    stored = await note_crud.note_get(row.code)
    assert (stored.title, stored.body, stored.deleted_at) == ("Схема", "текст", None)


async def test_restore_of_a_live_or_missing_note_is_false(db):
    row = await note_crud.note_create(title="Схема")

    assert await note_crud.note_restore(row.code) is False
    assert await note_crud.note_restore("0000000000") is False
