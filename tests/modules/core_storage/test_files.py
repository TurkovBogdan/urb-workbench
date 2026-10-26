"""Getting a stored file, and the file manager's deletion."""

from __future__ import annotations

import pytest

from src.modules.core_storage.dto import Owner
from src.modules.core_storage.errors import FileNotFound
from src.modules.core_storage.services.files import (
    file_delete,
    file_get,
    file_get_many,
    file_open,
    file_path,
)
from src.modules.core_storage.services.ownership import file_owners
from src.modules.core_storage.services.registration import file_register_bytes

from .conftest import owners_of

pytestmark = pytest.mark.db

TASK = Owner("task", "7DB4F6E0DE")
NOTE = Owner("note", "BD98065ED2")


MALFORMED = ["FILE@3F9A0C21BE", "3F9A0C21B", "3F9A0C21BZ", ""]


@pytest.mark.parametrize("code", MALFORMED)
async def test_a_malformed_code_answers_as_a_code_nobody_registered(db, code):
    from src.modules.core_storage.services.ownership import file_attach, file_release

    stored = await file_register_bytes(b"x", store="public", owner=TASK)

    for refused in (
        file_get(code),
        file_open(code),
        file_delete(code),
        file_attach(code, NOTE),
        file_release(code, TASK),
    ):
        with pytest.raises(FileNotFound):
            await refused
    assert await file_owners(code) == []
    assert list(await file_get_many([code, stored.code])) == [stored.code]
    assert await owners_of(stored.code) == [TASK]


async def test_get_takes_a_code_in_any_case(db):
    stored = await file_register_bytes(b"x", store="public", owner=TASK)
    assert (await file_get(stored.code.lower())).code == stored.code


async def test_get_many_of_no_codes_asks_nothing(db):
    assert await file_get_many([]) == {}


async def test_get_many_skips_codes_without_a_file(db):
    stored = await file_register_bytes(b"x", store="public", owner=TASK)
    found = await file_get_many([stored.code, "ABCDEF0123"])
    assert list(found) == [stored.code]


async def test_open_reads_the_bytes(db):
    stored = await file_register_bytes(b"content", store="public", owner=TASK)
    handle = await file_open(stored.code)
    try:
        assert handle.read() == b"content"
    finally:
        handle.close()


async def test_open_without_bytes_on_disk_is_not_found(db):
    stored = await file_register_bytes(b"content", store="public", owner=TASK)
    file_path(stored).unlink()
    with pytest.raises(FileNotFound):
        await file_open(stored.code)


async def test_the_manager_deletes_the_file_and_all_its_owners_softly(db):
    stored = await file_register_bytes(b"x", store="public", owner=TASK)
    from src.modules.core_storage.services.ownership import file_attach

    await file_attach(stored.code, NOTE)

    await file_delete(stored.code)

    with pytest.raises(FileNotFound):
        await file_get(stored.code)
    with pytest.raises(FileNotFound):
        await file_open(stored.code)
    marked = await file_get(stored.code, include_deleted=True)
    assert marked.deleted_at is not None
    assert await file_owners(stored.code) == []
    assert await file_get_many([stored.code]) == {}
    assert list(await file_get_many([stored.code], include_deleted=True)) == [stored.code]
    handle = await file_open(stored.code, include_deleted=True)
    handle.close()
    assert file_path(marked).exists()


async def test_a_store_taken_off_the_list_stays_readable_and_closes_to_new_files(
    db, monkeypatch: pytest.MonkeyPatch
):
    from src.modules.core_storage import layout as layout_module
    from src.modules.core_storage.errors import UnknownStore

    stored = await file_register_bytes(b"kept", store="private", owner=TASK)
    monkeypatch.setattr(
        layout_module, "_layout", layout_module.StorageLayout(db.root, db.tmp, ["public"])
    )

    handle = await file_open(stored.code)
    try:
        assert handle.read() == b"kept"
    finally:
        handle.close()
    with pytest.raises(UnknownStore):
        await file_register_bytes(b"new", store="private", owner=TASK)


async def test_deleting_an_unknown_or_deleted_file_is_not_found(db):
    with pytest.raises(FileNotFound):
        await file_delete("ABCDEF0123")
    stored = await file_register_bytes(b"x", store="public", owner=TASK)
    await file_delete(stored.code)
    with pytest.raises(FileNotFound):
        await file_delete(stored.code)
