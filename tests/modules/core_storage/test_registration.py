"""Taking a file in: the three inputs, dedup, ``move``, the ceiling, and what a refusal leaves.

A refusal is checked by the state after it — rows, bytes on disk, the caller's file, the temp
folder — not by its text alone.
"""

from __future__ import annotations

import stat
from pathlib import Path

import pytest
from sqlalchemy import func, select

from src.core.database import session_scope
from src.modules.core_storage import layout as layout_module
from src.modules.core_storage.dto import Owner
from src.modules.core_storage.errors import CodeCollision, FileTooLarge, SourceNotFound, UnknownStore
from src.modules.core_storage.models import CoreStorageFile, CoreStorageFileOwner
from src.modules.core_storage.services import files, ownership, registration
from src.modules.core_storage.services.registration import (
    file_register_bytes,
    file_register_path,
    file_register_spooled,
    file_register_stream,
    file_spool,
)

from .conftest import Settings, owners_of, temp_leftovers

pytestmark = pytest.mark.db

TASK = Owner("task", "7DB4F6E0DE", "context")
NOTE = Owner("note", "BD98065ED2")
PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452") + b"\x00" * 64


async def _counts() -> tuple[int, int]:
    async with session_scope() as s:
        file_rows = (await s.execute(select(func.count()).select_from(CoreStorageFile))).scalar_one()
        owner_rows = (await s.execute(select(func.count()).select_from(CoreStorageFileOwner))).scalar_one()
    return file_rows, owner_rows


async def _stream(*parts: bytes):
    for part in parts:
        yield part


async def test_bytes_land_in_the_store_read_only_with_their_owner(db):
    stored = await file_register_bytes(b"# plan\n", store="public", owner=TASK, filename="plan.md")

    path = files.file_path(stored)
    assert path.read_bytes() == b"# plan\n"
    assert stat.S_IMODE(path.stat().st_mode) == 0o444
    assert path.parent.parent.parent == db.store_dir("public")
    assert (stored.store, stored.mime, stored.extension, stored.type, stored.size) == (
        "public",
        "text/markdown",
        ".md",
        "text",
        7,
    )
    assert await owners_of(stored.code) == [TASK]
    assert temp_leftovers(db) == []


async def test_the_three_inputs_give_one_file(db, tmp_path: Path):
    source = tmp_path / "shot.png"
    source.write_bytes(PNG)

    from_bytes = await file_register_bytes(PNG, store="public", owner=TASK)
    from_stream = await file_register_stream(_stream(PNG[:10], PNG[10:]), store="public", owner=NOTE)
    from_path = await file_register_path(source, store="public", owner=Owner("stage", "AAAAAAAAAA"))

    assert from_bytes.code == from_stream.code == from_path.code
    assert from_bytes.type == "image"
    assert await _counts() == (1, 3)
    assert source.read_bytes() == PNG


async def test_a_long_stream_in_small_chunks_keeps_every_byte_and_its_signature(db):
    import hashlib

    data = PNG + bytes(range(256)) * 100
    chunks = [data[i : i + 1000] for i in range(0, len(data), 1000)]

    stored = await file_register_stream(_stream(*chunks), store="public", owner=TASK, filename="x.md")

    assert len(chunks) > 9  # the head (8192 bytes) fills up while chunks are still coming
    assert stored.type == "image" and stored.size == len(data)
    assert stored.sha256 == hashlib.sha256(data).hexdigest()
    assert files.file_path(stored).read_bytes() == data


async def test_the_same_bytes_in_another_store_are_a_second_file(db):
    first = await file_register_bytes(b"same", store="public", owner=TASK)
    second = await file_register_bytes(b"same", store="private", owner=TASK)
    assert first.code != second.code
    assert await _counts() == (2, 2)


async def test_the_same_owner_registering_again_adds_no_row(db):
    await file_register_bytes(b"same", store="public", owner=TASK)
    await file_register_bytes(b"same", store="public", owner=TASK)
    assert await _counts() == (1, 1)


async def test_registering_a_soft_deleted_file_revives_it(db):
    stored = await file_register_bytes(b"same", store="public", owner=TASK)
    await ownership.file_release(stored.code, TASK)
    assert (await files.file_get(stored.code, include_deleted=True)).deleted_at is not None

    again = await file_register_bytes(b"same", store="public", owner=NOTE)

    assert again.code == stored.code and again.deleted_at is None
    assert await owners_of(stored.code) == [NOTE]


async def test_move_hands_a_new_file_over_without_a_copy(db, tmp_path: Path):
    source = tmp_path / "download.bin"
    source.write_bytes(b"downloaded")

    stored = await file_register_path(source, store="private", owner=TASK, move=True)

    assert not source.exists()
    assert files.file_path(stored).read_bytes() == b"downloaded"


async def test_move_of_stored_content_deletes_the_source(db, tmp_path: Path):
    existing = await file_register_bytes(b"downloaded", store="private", owner=TASK)
    source = tmp_path / "download.bin"
    source.write_bytes(b"downloaded")

    stored = await file_register_path(source, store="private", owner=NOTE, move=True)

    assert stored.code == existing.code
    assert not source.exists()
    assert await _counts() == (1, 2)


async def test_a_path_without_move_stays_untouched(db, tmp_path: Path):
    source = tmp_path / "mine.txt"
    source.write_bytes(b"keep me")
    await file_register_path(source, store="public", owner=TASK)
    assert source.read_bytes() == b"keep me"


async def test_the_name_hint_of_a_path_defaults_to_its_file_name(db, tmp_path: Path):
    source = tmp_path / "readme.md"
    source.write_bytes(b"no signature")
    stored = await file_register_path(source, store="public", owner=TASK)
    assert stored.mime == "text/markdown"


async def test_a_missing_path_is_refused(db, tmp_path: Path):
    with pytest.raises(SourceNotFound):
        await file_register_path(tmp_path / "nowhere.bin", store="public", owner=TASK)
    assert await _counts() == (0, 0)


async def test_an_unknown_store_leaves_nothing_and_keeps_the_source(db, tmp_path: Path):
    source = tmp_path / "download.bin"
    source.write_bytes(b"downloaded")

    with pytest.raises(UnknownStore):
        await file_register_path(source, store="archive", owner=TASK, move=True)
    with pytest.raises(UnknownStore):
        await file_register_bytes(b"x", store="archive", owner=TASK)

    assert source.exists()
    assert await _counts() == (0, 0)


async def test_over_the_ceiling_nothing_is_stored(db, tmp_path: Path):
    from src.modules.core_storage import settings

    settings.set_current(Settings(max_file_size_mb=1))
    big = b"x" * (1024 * 1024 + 1)
    source = tmp_path / "big.bin"
    source.write_bytes(big)

    with pytest.raises(FileTooLarge):
        await file_register_bytes(big, store="public", owner=TASK)
    with pytest.raises(FileTooLarge):
        await file_register_stream(_stream(big[:10], big[10:]), store="public", owner=TASK)
    with pytest.raises(FileTooLarge):
        await file_register_path(source, store="public", owner=TASK, move=True)

    assert source.exists()
    assert await _counts() == (0, 0)
    assert temp_leftovers(db) == []
    assert list(db.store_dir("public").rglob("*.*")) == []


async def test_a_spooled_stream_moved_into_place_leaves_nothing_behind(db):
    async with file_spool(_stream(PNG[:8], PNG[8:])) as spooled:
        assert spooled.path.read_bytes() == PNG
        stored = await file_register_spooled(spooled, store="public", owner=TASK, filename="экран.png")

    assert stored.size == len(PNG)
    assert stored.type == "image"
    assert files.file_path(stored).read_bytes() == PNG
    assert temp_leftovers(db) == []


async def test_a_spooled_stream_is_registered_by_its_counts_without_reading_it_again(
    db, monkeypatch: pytest.MonkeyPatch
):
    async def no_second_read(path):
        raise AssertionError(f"{path} was read again")

    monkeypatch.setattr(registration, "_inspect", no_second_read)
    monkeypatch.setattr(registration, "_chunks_of_file", no_second_read)

    async with file_spool(_stream(b"counted ", b"once")) as spooled:
        stored = await file_register_spooled(spooled, store="public", owner=TASK, filename="c.txt")

    assert (stored.sha256, stored.size) == (spooled.sha256, len(b"counted once"))


async def test_the_counts_of_a_file_the_module_did_not_spool_are_not_taken(db, tmp_path: Path):
    """The counts are taken on trust, so a file outside the module's temporary folder — whatever
    counts it comes with — is refused, and stays where it was."""
    from src.modules.core_storage.dto import SpooledFile

    elsewhere = tmp_path / "elsewhere.part"
    elsewhere.write_bytes(b"real bytes")
    forged = SpooledFile(path=elsewhere, sha256="0" * 64, size=1, head=b"")

    with pytest.raises(SourceNotFound):
        await file_register_spooled(forged, store="public", owner=TASK)

    assert elsewhere.read_bytes() == b"real bytes"
    assert await _counts() == (0, 0)


async def test_a_spool_is_removed_on_any_way_out(db):
    with pytest.raises(RuntimeError):
        async with file_spool(_stream(b"abc")) as spooled:
            assert spooled.path.exists()
            raise RuntimeError("the consumer refused")

    assert temp_leftovers(db) == []


async def test_a_spool_over_the_ceiling_is_refused_with_nothing_behind(db):
    from src.modules.core_storage import settings

    settings.set_current(Settings(max_file_size_mb=1))
    big = b"x" * (1024 * 1024 + 1)

    with pytest.raises(FileTooLarge):
        async with file_spool(_stream(big[:10], big[10:])):
            raise AssertionError("an over-long stream yields no file")

    assert temp_leftovers(db) == []
    assert await _counts() == (0, 0)


async def test_a_taken_code_is_chosen_again(db, monkeypatch: pytest.MonkeyPatch):
    taken = await file_register_bytes(b"first", store="public", owner=TASK)
    codes = iter([taken.code, "ABCDEF0123"])
    monkeypatch.setattr(registration, "new_code", lambda: next(codes))

    stored = await file_register_bytes(b"second", store="public", owner=TASK)

    assert stored.code == "ABCDEF0123"
    assert await _counts() == (2, 2)


async def test_codes_taken_every_time_give_up(db, monkeypatch: pytest.MonkeyPatch):
    taken = await file_register_bytes(b"first", store="public", owner=TASK)
    monkeypatch.setattr(registration, "new_code", lambda: taken.code)

    with pytest.raises(CodeCollision):
        await file_register_bytes(b"second", store="public", owner=TASK)
    assert await _counts() == (1, 1)


async def test_a_failed_move_takes_the_row_back(db, monkeypatch: pytest.MonkeyPatch):
    def place(self, temp_file, target):
        raise OSError("disk full")

    monkeypatch.setattr(layout_module.StorageLayout, "place", place)

    with pytest.raises(OSError):
        await file_register_bytes(b"lost", store="public", owner=TASK)

    assert await _counts() == (0, 0)
    assert temp_leftovers(db) == []
