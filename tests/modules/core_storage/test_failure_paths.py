"""Failure paths of registration: what each refusal and each crash leaves behind.

Every negative assertion carries a positive control — a check that the place looked at is the
place the code writes to — so an empty folder cannot pass for a clean one.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from src.core.database import session_scope
from src.modules.core_storage import layout as layout_module
from src.modules.core_storage import settings
from src.modules.core_storage.dto import Owner
from src.modules.core_storage.errors import FileNotFound, FileTooLarge
from src.modules.core_storage.mime import Detected
from src.modules.core_storage.models import CoreStorageFile, CoreStorageFileOwner
from src.modules.core_storage.services import files, ownership, registration
from src.modules.core_storage.services.registration import (
    file_register_bytes,
    file_register_path,
    file_register_stream,
)

from .conftest import Settings, names_of, temp_leftovers

pytestmark = pytest.mark.db

TASK = Owner("task", "7DB4F6E0DE")
NOTE = Owner("note", "BD98065ED2")
MB = 1024 * 1024


async def _counts() -> tuple[int, int]:
    async with session_scope() as s:
        file_rows = (await s.execute(select(func.count()).select_from(CoreStorageFile))).scalar_one()
        owner_rows = (await s.execute(select(func.count()).select_from(CoreStorageFileOwner))).scalar_one()
    return file_rows, owner_rows


def _bytes_on_disk(layout) -> list[Path]:
    return sorted(p for p in layout.root.rglob("*") if p.is_file())


async def test_the_stream_is_spooled_into_the_core_temp_folder(db):
    """Positive control for every ``temp_leftovers == []``: the spool really writes there."""
    seen: list[list[Path]] = []

    async def chunks():
        yield b"first"
        seen.append(temp_leftovers(db))
        yield b"second"

    await file_register_stream(chunks(), store="public", owner=TASK)

    assert len(seen[0]) == 1 and seen[0][0].name.endswith(".part")
    assert temp_leftovers(db) == []


async def test_a_stream_failing_midway_leaves_nothing(db):
    async def chunks():
        yield b"half"
        raise RuntimeError("connection reset")

    with pytest.raises(RuntimeError, match="connection reset"):
        await file_register_stream(chunks(), store="public", owner=TASK)

    assert await _counts() == (0, 0)
    assert temp_leftovers(db) == []
    assert _bytes_on_disk(db) == []


async def test_a_stream_yielding_text_is_refused_and_leaves_nothing(db):
    async def chunks():
        yield b"bytes"
        yield "text"

    with pytest.raises(TypeError):
        await file_register_stream(chunks(), store="public", owner=TASK)

    assert await _counts() == (0, 0)
    assert temp_leftovers(db) == []


@pytest.mark.parametrize("entry", ["bytes", "stream", "path", "path-move"])
async def test_a_file_exactly_at_the_ceiling_is_taken(db, tmp_path: Path, entry: str):
    settings.set_current(Settings(max_file_size_mb=1))
    data = b"a" * MB
    source = tmp_path / "at-ceiling.bin"
    source.write_bytes(data)

    if entry == "bytes":
        stored = await file_register_bytes(data, store="public", owner=TASK)
    elif entry == "stream":
        stored = await file_register_stream(_one(data), store="public", owner=TASK)
    elif entry == "path":
        stored = await file_register_path(source, store="public", owner=TASK)
    else:
        stored = await file_register_path(source, store="public", owner=TASK, move=True)

    assert stored.size == MB
    assert files.file_path(stored).stat().st_size == MB


async def _one(data: bytes):
    yield data


async def test_one_byte_over_the_ceiling_names_both_numbers(db):
    settings.set_current(Settings(max_file_size_mb=1))
    with pytest.raises(FileTooLarge) as refused:
        await file_register_bytes(b"a" * (MB + 1), store="public", owner=TASK)
    assert (refused.value.limit, refused.value.size) == (MB, MB + 1)
    assert await _counts() == (0, 0)


async def test_an_empty_file_is_a_file(db):
    stored = await file_register_bytes(b"", store="public", owner=TASK, filename="empty.md")
    assert (stored.size, stored.mime) == (0, "text/markdown")
    assert files.file_path(stored).read_bytes() == b""


async def test_a_prefixed_code_is_not_a_storage_code(db):
    """Pinned: the module takes bare codes; a presentation prefix belongs to the consumer."""
    stored = await file_register_bytes(b"x", store="public", owner=TASK)
    with pytest.raises(FileNotFound):
        await files.file_get(f"FILE@{stored.code}")
    assert (await files.file_get(stored.code)).code == stored.code


async def test_losing_the_race_for_the_content_joins_the_winner(db, monkeypatch: pytest.MonkeyPatch):
    """The dedup lookup and the insert are not atomic: a parallel registration can store the
    same bytes in between. Simulated by a lookup that misses a row that is already there."""
    winner = await file_register_bytes(b"contested", store="public", owner=TASK, filename="plan.md")

    async def missed(store, sha256, owner, name):
        return None

    monkeypatch.setattr(registration, "_take_existing", missed)

    joined = await file_register_bytes(b"contested", store="public", owner=NOTE, filename="Copy.MD")

    assert joined.code == winner.code
    assert await _counts() == (1, 2)
    assert await names_of(winner.code) == {TASK: ("plan", ".md"), NOTE: ("Copy", ".MD")}
    assert len(_bytes_on_disk(db)) == 1
    assert temp_leftovers(db) == []


async def test_losing_the_race_revives_a_marked_winner(db, monkeypatch: pytest.MonkeyPatch):
    winner = await file_register_bytes(b"contested", store="public", owner=TASK)
    await ownership.file_release(winner.code, TASK)

    async def missed(store, sha256, owner, name):
        return None

    monkeypatch.setattr(registration, "_take_existing", missed)

    joined = await file_register_bytes(b"contested", store="public", owner=NOTE)

    assert joined.code == winner.code and joined.deleted_at is None


async def test_a_refusal_other_than_a_taken_code_goes_out_as_is(db, monkeypatch: pytest.MonkeyPatch):
    """The ``IntegrityError`` branch retries only a taken code; a broken row — here a category
    the CHECK refuses — must not spin the retry loop and must leave nothing behind."""
    monkeypatch.setattr(
        registration, "detect", lambda head, filename: Detected("text/plain", ".txt", "bogus")
    )
    attempts: list[str] = []
    real_new_code = registration.new_code

    def counted() -> str:
        code = real_new_code()
        attempts.append(code)
        return code

    monkeypatch.setattr(registration, "new_code", counted)

    with pytest.raises(IntegrityError):
        await file_register_bytes(b"broken", store="public", owner=TASK)

    assert len(attempts) == 1
    assert await _counts() == (0, 0)
    assert temp_leftovers(db) == []


async def test_a_code_taken_by_a_soft_deleted_file_is_chosen_again(db, monkeypatch: pytest.MonkeyPatch):
    marked = await file_register_bytes(b"marked", store="public", owner=TASK)
    await ownership.file_release(marked.code, TASK)
    codes = iter([marked.code, "ABCDEF0123"])
    monkeypatch.setattr(registration, "new_code", lambda: next(codes))

    stored = await file_register_bytes(b"fresh", store="public", owner=TASK)

    assert stored.code == "ABCDEF0123"


async def test_a_move_failing_outside_os_errors_still_takes_the_row_back(db, monkeypatch: pytest.MonkeyPatch):
    def place(self, temp_file, target):
        raise RuntimeError("not an OS error")

    monkeypatch.setattr(layout_module.StorageLayout, "place", place)

    with pytest.raises(RuntimeError, match="not an OS error"):
        await file_register_bytes(b"lost", store="public", owner=TASK)

    assert await _counts() == (0, 0)
    assert temp_leftovers(db) == []


async def test_move_hands_the_file_over_even_when_the_database_fails(db, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Pinned: with ``move=True`` the module owns the file from the moment the checks before
    ``_register`` pass, so a failure inside it removes the handed-over file too."""
    source = tmp_path / "download.bin"
    source.write_bytes(b"downloaded")

    async def boom(*args, **kwargs):
        raise RuntimeError("database is gone")

    monkeypatch.setattr(registration, "_take_existing", boom)

    with pytest.raises(RuntimeError):
        await file_register_path(source, store="public", owner=TASK, move=True)

    assert not source.exists()


async def test_a_refusal_before_the_hand_over_keeps_the_moved_file(db, tmp_path: Path):
    settings.set_current(Settings(max_file_size_mb=1))
    source = tmp_path / "big.bin"
    source.write_bytes(b"a" * (MB + 1))

    with pytest.raises(FileTooLarge):
        await file_register_path(source, store="public", owner=TASK, move=True)

    assert source.stat().st_size == MB + 1
