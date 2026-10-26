"""Who really holds each invariant of the tables. The service never tries to break them, so these
tests break them directly and name the constraint that answers — on the database the tests run."""

from __future__ import annotations

import pytest
from sqlalchemy import delete, insert, update
from sqlalchemy.exc import IntegrityError

from src.core.database import write_scope
from src.modules.core_storage.dto import Owner
from src.modules.core_storage.models import CoreStorageFile, CoreStorageFileOwner
from src.modules.core_storage.services.registration import file_register_bytes

pytestmark = pytest.mark.db

TASK = Owner("task", "7DB4F6E0DE")


async def test_a_file_with_an_owner_row_cannot_be_deleted__the_fk_restrict_holds(db):
    stored = await file_register_bytes(b"held", store="public", owner=TASK)
    with pytest.raises(IntegrityError):
        async with write_scope() as s:
            await s.execute(delete(CoreStorageFile).where(CoreStorageFile.code == stored.code))


async def test_a_file_without_owner_rows_can_be_deleted(db):
    """Positive control for the test above: the refusal comes from the owner row, not from
    deleting a file as such."""
    stored = await file_register_bytes(b"held", store="public", owner=TASK)
    async with write_scope() as s:
        await s.execute(delete(CoreStorageFileOwner).where(CoreStorageFileOwner.file_code == stored.code))
        await s.execute(delete(CoreStorageFile).where(CoreStorageFile.code == stored.code))


async def test_an_owner_of_a_missing_file_cannot_be_written__the_fk_holds(db):
    with pytest.raises(IntegrityError):
        async with write_scope() as s:
            await s.execute(
                insert(CoreStorageFileOwner).values(
                    file_code="ABCDEF0123", owner_type="task", owner_id="1", owner_key=""
                )
            )


async def test_the_same_bytes_twice_in_one_store__the_unique_key_holds(db):
    stored = await file_register_bytes(b"once", store="public", owner=TASK)
    with pytest.raises(IntegrityError):
        async with write_scope() as s:
            await s.execute(
                insert(CoreStorageFile).values(
                    code="ABCDEF0123",
                    store="public",
                    sha256=stored.sha256,
                    type="text",
                    size=4,
                    mime="text/plain",
                    extension=".txt",
                )
            )


async def test_a_category_outside_the_list__the_check_holds(db):
    stored = await file_register_bytes(b"typed", store="public", owner=TASK)
    with pytest.raises(IntegrityError):
        async with write_scope() as s:
            await s.execute(
                update(CoreStorageFile).where(CoreStorageFile.code == stored.code).values(type="audio")
            )
