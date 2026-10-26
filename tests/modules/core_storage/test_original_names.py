"""The original name of a file: where it is kept and when it changes.

Every place keeps the name it brought the file under; ``original_filename + original_extension``
gives that name back exactly. A refused name is checked by the state after it — rows, the temp
folder, the caller's file — not by the text of the error.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import func, select

from src.core.database import session_scope
from src.modules.core_storage.constants import EXTENSION_MAX, ORIGINAL_FILENAME_MAX
from src.modules.core_storage.dto import Owner
from src.modules.core_storage.models import CoreStorageFile, CoreStorageFileOwner
from src.modules.core_storage.services import registration
from src.modules.core_storage.services.files import file_delete
from src.modules.core_storage.services.ownership import file_attach, file_owners, file_release
from src.modules.core_storage.services.registration import (
    file_register_bytes,
    file_register_path,
    file_register_stream,
)

from .conftest import names_of, temp_leftovers

pytestmark = pytest.mark.db

TASK = Owner("task", "7DB4F6E0DE", "context")
NOTE = Owner("note", "BD98065ED2")
STAGE = Owner("stage", "AAAAAAAAAA")
PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452") + b"\x00" * 64
LONGEST_SUFFIX = "." + "x" * (EXTENSION_MAX - 1)
TOO_LONG = "n" * (ORIGINAL_FILENAME_MAX + 1) + ".pdf"


async def _counts() -> tuple[int, int]:
    async with session_scope() as s:
        file_rows = (await s.execute(select(func.count()).select_from(CoreStorageFile))).scalar_one()
        owner_rows = (await s.execute(select(func.count()).select_from(CoreStorageFileOwner))).scalar_one()
    return file_rows, owner_rows


async def _stream(*parts: bytes):
    for part in parts:
        yield part


async def test_each_entry_keeps_the_name_it_was_given(db, tmp_path: Path):
    shot = tmp_path / "Shot.PNG"
    shot.write_bytes(PNG)
    download = tmp_path / "fetch-1a2b.part"
    download.write_bytes(b"downloaded")

    from_bytes = await file_register_bytes(b"%PDF", store="public", owner=TASK, filename="report.final.PDF")
    from_stream = await file_register_stream(_stream(b"# a", b"\n"), store="public", owner=TASK, filename="notes.MD")
    from_path = await file_register_path(shot, store="public", owner=TASK)
    renamed = await file_register_path(download, store="public", owner=TASK, filename="report.pdf", move=True)

    assert await names_of(from_bytes.code) == {TASK: ("report.final", ".PDF")}
    assert await names_of(from_stream.code) == {TASK: ("notes", ".MD")}
    assert await names_of(from_path.code) == {TASK: ("Shot", ".PNG")}
    assert await names_of(renamed.code) == {TASK: ("report", ".pdf")}


async def test_the_stored_extension_still_comes_from_the_type(db):
    """The original extension is kept as brought; the one on disk follows the found mime."""
    stored = await file_register_bytes(PNG, store="public", owner=TASK, filename="photo.JPEG")
    assert (stored.mime, stored.extension) == ("image/png", ".png")
    assert await names_of(stored.code) == {TASK: ("photo", ".JPEG")}


async def test_a_file_brought_without_a_name_keeps_empty_strings(db):
    stored = await file_register_bytes(b"anonymous", store="public", owner=TASK)
    assert await names_of(stored.code) == {TASK: ("", "")}


async def test_the_listing_carries_the_owner_its_name_and_its_dates(db):
    stored = await file_register_bytes(b"x", store="public", owner=TASK, filename="plan.md")
    await file_attach(stored.code, NOTE)
    await file_release(stored.code, NOTE)

    live = await file_owners(stored.code)
    assert [(p.owner, p.original_filename, p.original_extension, p.deleted_at) for p in live] == [
        (TASK, "plan", ".md", None)
    ]
    assert live[0].created_at is not None
    released = {p.owner: p for p in await file_owners(stored.code, include_deleted=True)}
    assert released[NOTE].deleted_at is not None


async def test_the_same_bytes_keep_each_owners_own_name(db):
    first = await file_register_bytes(b"same", store="public", owner=TASK, filename="a.txt")
    again = await file_register_bytes(b"same", store="public", owner=NOTE, filename="b.TXT")

    assert again.code == first.code
    assert await names_of(first.code) == {TASK: ("a", ".txt"), NOTE: ("b", ".TXT")}


async def test_registering_again_while_holding_the_file_keeps_the_name(db):
    """A consumer that refuses the second registration (the place holds the file already) must
    find the place as it was — a registration does not rename a live place."""
    stored = await file_register_bytes(b"same", store="public", owner=TASK, filename="a.txt")

    await file_register_bytes(b"same", store="public", owner=TASK)
    await file_register_bytes(b"same", store="public", owner=TASK, filename="c.md")

    assert await names_of(stored.code) == {TASK: ("a", ".txt")}


async def test_losing_the_race_to_a_place_that_holds_the_file_keeps_the_name(db, monkeypatch):
    """The path where a parallel registration of the same content won the key: the dedup lookup
    is made to miss once, so the insert finds the content taken and joins the winner."""
    stored = await file_register_bytes(b"same", store="public", owner=TASK, filename="a.txt")
    real_find = registration.file_crud.file_find_by_sha256
    misses = iter([None])

    async def miss_once(*args, **kwargs):
        try:
            return next(misses)
        except StopIteration:
            return await real_find(*args, **kwargs)

    monkeypatch.setattr(registration.file_crud, "file_find_by_sha256", miss_once)

    joined = await file_register_bytes(b"same", store="public", owner=TASK, filename="c.md")
    other = await file_register_bytes(b"same", store="public", owner=NOTE, filename="b.md")

    assert joined.code == other.code == stored.code
    assert await names_of(stored.code) == {TASK: ("a", ".txt"), NOTE: ("b", ".md")}


async def test_a_file_the_file_manager_deleted_comes_back_under_the_new_name(db):
    """The file manager's deletion releases every place; registering the bytes again revives the
    file and the place, and a revived place takes the name it was brought under now."""
    stored = await file_register_bytes(b"x", store="public", owner=TASK, filename="old.md")
    await file_delete(stored.code)

    again = await file_register_bytes(b"x", store="public", owner=TASK, filename="new.md")

    assert again.code == stored.code and again.deleted_at is None
    assert await names_of(stored.code) == {TASK: ("new", ".md")}


async def test_a_released_owner_registering_again_revives_its_row_with_the_new_name(db):
    stored = await file_register_bytes(b"x", store="public", owner=TASK, filename="old.md")
    await file_release(stored.code, TASK)

    await file_register_bytes(b"x", store="public", owner=TASK, filename="new.md")

    assert await names_of(stored.code) == {TASK: ("new", ".md")}


async def test_attach_writes_a_given_name_and_copies_the_files_name_otherwise(db):
    stored = await file_register_bytes(b"x", store="public", owner=TASK, filename="plan.md")

    await file_attach(stored.code, NOTE)
    await file_attach(stored.code, STAGE, filename="Other.TXT")

    assert await names_of(stored.code) == {
        TASK: ("plan", ".md"),
        NOTE: ("plan", ".md"),
        STAGE: ("Other", ".TXT"),
    }


async def test_attach_with_an_empty_name_keeps_no_name(db):
    stored = await file_register_bytes(b"x", store="public", owner=TASK, filename="plan.md")
    await file_attach(stored.code, NOTE, filename="")
    assert (await names_of(stored.code))[NOTE] == ("", "")


async def test_attach_copies_the_earliest_name_there_is_skipping_rows_without_one(db):
    stored = await file_register_bytes(b"x", store="public", owner=TASK)
    await file_attach(stored.code, NOTE, filename="named.pdf")

    await file_attach(stored.code, STAGE)

    assert (await names_of(stored.code))[STAGE] == ("named", ".pdf")


async def test_the_earliest_name_goes_by_time_and_within_one_second_by_the_owner(db):
    """``created_at`` keeps whole seconds, so two places taken in one second tie on it. The rule
    is then the owner triple in plain order (type, id, key) — fixed, not whichever row the
    database returns first. Time decides first: an owner that sorts last but came earlier wins."""
    from datetime import timedelta

    from src.core.utils.date import utc_now

    from .conftest import back_date_owner

    late_but_first = Owner("zz", "9")
    early_in_order = Owner("aa", "1")
    third = Owner("mm", "5")
    stored = await file_register_bytes(b"tie", store="public", owner=late_but_first, filename="z.txt")
    await file_attach(stored.code, early_in_order, filename="a.txt")
    now = utc_now()
    await back_date_owner(stored.code, late_but_first, now - timedelta(hours=1))
    await back_date_owner(stored.code, early_in_order, now)

    await file_attach(stored.code, Owner("new", "1"))

    assert (await names_of(stored.code))[Owner("new", "1")] == ("z", ".txt")

    await back_date_owner(stored.code, late_but_first, now)
    await file_attach(stored.code, third, filename="m.txt")
    await back_date_owner(stored.code, third, now)

    await file_attach(stored.code, Owner("new", "2"))

    assert (await names_of(stored.code))[Owner("new", "2")] == ("a", ".txt")


async def test_attach_copies_from_a_released_row_too(db):
    stored = await file_register_bytes(b"x", store="public", owner=TASK, filename="plan.md")
    await file_release(stored.code, TASK)

    await file_attach(stored.code, NOTE)

    assert await names_of(stored.code) == {NOTE: ("plan", ".md")}


async def test_attach_to_a_file_nobody_named_leaves_the_name_empty(db):
    stored = await file_register_bytes(b"x", store="public", owner=TASK)
    await file_attach(stored.code, NOTE)
    assert (await names_of(stored.code))[NOTE] == ("", "")


async def test_taking_a_place_again_keeps_the_name_unless_a_new_one_is_given(db):
    stored = await file_register_bytes(b"x", store="public", owner=TASK, filename="plan.md")
    await file_release(stored.code, TASK)

    await file_attach(stored.code, TASK)
    assert await names_of(stored.code) == {TASK: ("plan", ".md")}

    await file_release(stored.code, TASK)
    await file_attach(stored.code, TASK, filename="renamed.TXT")
    assert await names_of(stored.code) == {TASK: ("renamed", ".TXT")}

    await file_attach(stored.code, TASK, filename="live.csv")
    assert await names_of(stored.code) == {TASK: ("live", ".csv")}
    await file_attach(stored.code, TASK)
    assert await names_of(stored.code) == {TASK: ("live", ".csv")}


async def test_a_name_at_the_width_is_stored_whole(db):
    brought = "и" * ORIGINAL_FILENAME_MAX + LONGEST_SUFFIX
    stored = await file_register_bytes(b"wide", store="public", owner=TASK, filename=brought)
    assert await names_of(stored.code) == {TASK: ("и" * ORIGINAL_FILENAME_MAX, LONGEST_SUFFIX)}


@pytest.mark.parametrize("refused", [TOO_LONG, "снимок\x00.png", "a\nb.png"], ids=["too-long", "nul", "newline"])
@pytest.mark.parametrize("entry", ["bytes", "stream", "path", "path-move"])
async def test_a_name_the_storage_cannot_keep_is_refused_and_nothing_is_written(
    db, tmp_path: Path, entry: str, refused: str
):
    source = tmp_path / "download.bin"
    source.write_bytes(b"downloaded")

    with pytest.raises(ValueError):
        if entry == "bytes":
            await file_register_bytes(b"downloaded", store="public", owner=TASK, filename=refused)
        elif entry == "stream":
            await file_register_stream(_stream(b"downloaded"), store="public", owner=TASK, filename=refused)
        else:
            await file_register_path(
                source, store="public", owner=TASK, filename=refused, move=entry == "path-move"
            )

    assert await _counts() == (0, 0)
    assert temp_leftovers(db) == []
    assert list(db.store_dir("public").rglob("*.*")) == []
    assert source.read_bytes() == b"downloaded"


async def test_a_name_too_long_for_a_stored_file_adds_no_owner(db):
    """The refusal holds on the dedup path too, where the bytes are already there and only the
    owner row would be written."""
    stored = await file_register_bytes(b"downloaded", store="public", owner=TASK, filename="d.bin")

    with pytest.raises(ValueError):
        await file_register_bytes(b"downloaded", store="public", owner=NOTE, filename=TOO_LONG)

    assert await _counts() == (1, 1)
    assert await names_of(stored.code) == {TASK: ("d", ".bin")}


async def test_a_name_that_is_not_a_string_is_refused_before_the_bytes_are_taken(db):
    with pytest.raises(ValueError):
        await file_register_bytes(b"x", store="public", owner=TASK, filename=None)
    assert await _counts() == (0, 0)
    assert temp_leftovers(db) == []


async def test_attach_with_a_name_too_long_changes_nothing(db):
    stored = await file_register_bytes(b"x", store="public", owner=TASK, filename="plan.md")

    with pytest.raises(ValueError):
        await file_attach(stored.code, NOTE, filename=TOO_LONG)
    with pytest.raises(ValueError):
        await file_attach(stored.code, TASK, filename=TOO_LONG)
    with pytest.raises(ValueError):
        await file_attach(stored.code, NOTE, filename="plan\x00.md")

    assert await names_of(stored.code, include_deleted=True) == {TASK: ("plan", ".md")}
