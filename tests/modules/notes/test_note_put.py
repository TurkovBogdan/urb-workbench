"""``note_put``: a note written under the code it already has, in the consumer's transaction."""

from __future__ import annotations

from datetime import datetime

import pytest

from src.core.database import write_scope
from src.modules.notes.constants import BODY_MAX
from src.modules.notes.crud.note import note_create, note_delete, note_get, note_put

pytestmark = pytest.mark.db


async def test_a_new_note_takes_the_given_code_and_date(db):
    async with write_scope() as s:
        await note_put("ABCDEF0123", title="Схема", description="когда", body="текст",
                       created_at=datetime(2026, 1, 2, 3, 4, 5), session=s)

    row = await note_get("ABCDEF0123")
    assert (row.title, row.description, row.body) == ("Схема", "когда", "текст")
    assert row.created_at == datetime(2026, 1, 2, 3, 4, 5)


async def test_an_existing_note_is_overwritten_and_revived(db):
    note = await note_create(title="Было", body="старое")
    await note_delete(note.code)

    async with write_scope() as s:
        await note_put(note.code, title="Стало", body="новое", session=s)

    row = await note_get(note.code)
    assert row is not None and row.deleted_at is None
    assert (row.title, row.body) == ("Стало", "новое")


async def test_over_a_limit_nothing_is_written(db):
    with pytest.raises(ValueError):
        async with write_scope() as s:
            await note_put("ABCDEF0124", title="x", body="я" * (BODY_MAX + 1), session=s)

    assert await note_get("ABCDEF0124", include_deleted=True) is None
