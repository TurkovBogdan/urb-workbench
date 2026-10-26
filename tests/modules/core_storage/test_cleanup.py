"""The cleanup: files marked longer than the term go with their bytes; a held file stays."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

from src.core.utils.date import utc_now
from src.modules.core_storage.dto import Owner
from src.modules.core_storage.errors import FileNotFound
from src.modules.core_storage.services.cleanup import PurgeReport, purge_expired
from src.modules.core_storage.services.files import file_delete, file_get, file_path
from src.modules.core_storage.services.ownership import file_attach, file_owners, file_release
from src.modules.core_storage.services.registration import file_register_bytes

from .conftest import mark_deleted_at

pytestmark = pytest.mark.db

TASK = Owner("task", "7DB4F6E0DE")
NOTE = Owner("note", "BD98065ED2")
TERM = timedelta(hours=48)


async def _released(content: bytes, *, hours_ago: int):
    stored = await file_register_bytes(content, store="public", owner=TASK)
    await file_release(stored.code, TASK)
    await mark_deleted_at(stored.code, utc_now() - timedelta(hours=hours_ago))
    return stored


async def test_a_file_past_the_term_goes_with_its_bytes(db):
    stored = await _released(b"old", hours_ago=49)

    report = await purge_expired(TERM, 0)

    assert report == PurgeReport(purged=1, kept=0, bytes_failed=0)
    with pytest.raises(FileNotFound):
        await file_get(stored.code, include_deleted=True)
    assert await file_owners(stored.code, include_deleted=True) == []
    assert not file_path(stored).exists()


async def test_the_folders_emptied_by_a_purge_go_and_the_store_stays(db):
    stored = await _released(b"old", hours_ago=49)
    path = file_path(stored)
    assert path.parent.parent.parent == db.store_dir("public")

    await purge_expired(TERM, 0)

    assert not path.parent.exists() and not path.parent.parent.exists()
    assert db.store_dir("public").is_dir()


async def test_a_folder_still_holding_a_file_stays(db, monkeypatch: pytest.MonkeyPatch):
    from src.modules.core_storage.services import registration

    codes = iter(["AB12000001", "AB12000002"])
    monkeypatch.setattr(registration, "new_code", lambda: next(codes))
    gone = await _released(b"old", hours_ago=49)
    kept = await file_register_bytes(b"kept", store="public", owner=NOTE)
    assert file_path(gone).parent == file_path(kept).parent

    await purge_expired(TERM, 0)

    assert not file_path(gone).exists()
    assert file_path(kept).read_bytes() == b"kept"


async def test_a_file_within_the_term_waits(db):
    stored = await _released(b"recent", hours_ago=1)
    assert await purge_expired(TERM, 0) == PurgeReport(purged=0, kept=0, bytes_failed=0)
    assert file_path(stored).exists()


async def test_a_live_owner_keeps_a_marked_file_and_clears_the_mark(db):
    stored = await file_register_bytes(b"held", store="public", owner=TASK)
    await file_delete(stored.code)
    await file_attach(stored.code, NOTE)
    await mark_deleted_at(stored.code, utc_now() - timedelta(hours=49))

    report = await purge_expired(TERM, 0)

    assert report == PurgeReport(purged=0, kept=1, bytes_failed=0)
    assert (await file_get(stored.code)).deleted_at is None
    assert file_path(stored).exists()


async def test_the_limit_bounds_one_run_and_zero_means_all(db):
    for index in range(3):
        await _released(f"old {index}".encode(), hours_ago=49 + index)

    assert (await purge_expired(TERM, 2)).purged == 2
    assert (await purge_expired(TERM, 0)).purged == 1


async def test_bytes_already_gone_do_not_fail_the_run(db):
    stored = await _released(b"old", hours_ago=49)
    file_path(stored).unlink()
    assert await purge_expired(TERM, 0) == PurgeReport(purged=1, kept=0, bytes_failed=0)


async def test_bytes_that_cannot_be_removed_are_counted_and_the_row_still_goes(
    db, monkeypatch: pytest.MonkeyPatch
):
    stuck = await _released(b"stuck", hours_ago=49)
    free = await _released(b"free", hours_ago=50)
    stuck_path = file_path(stuck)
    real_unlink = Path.unlink

    def unlink(self, missing_ok=False):
        if self == stuck_path:
            raise PermissionError("read-only mount")
        real_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", unlink)

    report = await purge_expired(TERM, 0)

    assert report == PurgeReport(purged=2, kept=0, bytes_failed=1)
    assert stuck_path.exists() and not file_path(free).exists()
    with pytest.raises(FileNotFound):
        await file_get(stuck.code, include_deleted=True)


async def test_a_mark_cleared_after_the_selection_keeps_the_file(db, monkeypatch: pytest.MonkeyPatch):
    """The candidates are selected before each file's own transaction; a file taken back in
    between is found live inside it and kept."""
    from src.modules.core_storage.crud import file as file_crud
    from src.modules.core_storage.services import cleanup

    stored = await _released(b"taken back", hours_ago=49)
    candidates = await file_crud.file_expired(utc_now() - TERM, 0)
    await file_attach(stored.code, NOTE)

    async def stale_selection(before, limit):
        return candidates

    monkeypatch.setattr(cleanup.file_crud, "file_expired", stale_selection)

    assert await purge_expired(TERM, 0) == PurgeReport(purged=0, kept=1, bytes_failed=0)
    assert file_path(stored).exists()


async def test_files_of_a_store_off_the_list_are_still_cleaned(db, monkeypatch: pytest.MonkeyPatch):
    from src.modules.core_storage import layout as layout_module

    stored = await file_register_bytes(b"private", store="private", owner=TASK)
    await file_release(stored.code, TASK)
    await mark_deleted_at(stored.code, utc_now() - timedelta(hours=49))
    monkeypatch.setattr(
        layout_module, "_layout", layout_module.StorageLayout(db.root, db.tmp, ["public"])
    )

    assert (await purge_expired(TERM, 0)).purged == 1
    assert not file_path(stored).exists()


class _Context:
    def __init__(self) -> None:
        self.lines: list[str] = []

    async def info(self, message: str, *args) -> None:
        self.lines.append(message % args)


async def test_the_task_runs_the_cleanup_with_the_settings_and_reports_it(db):
    from src.modules.core_storage import settings
    from src.modules.core_storage.tasks.cleanup_task import CleanupTask

    from .conftest import Settings

    for index in range(3):
        await _released(f"old {index}".encode(), hours_ago=3)
    settings.set_current(Settings(cleanup_after_hours=2, cleanup_limit=2))
    stale = _aged(db.temp_file(), hours=2)
    context = _Context()

    await CleanupTask.handle(context)

    assert context.lines == [
        "purged 2, kept 0, bytes left on disk 0, temporary files removed 1"
    ]
    assert not stale.exists()


# ── temporary files ───────────────────────────────────────────────────────────


def _aged(path: Path, *, hours: float) -> Path:
    """A file at ``path`` last written ``hours`` ago."""
    import os
    import time

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"part")
    then = time.time() - hours * 3600
    os.utime(path, (then, then))
    return path


async def test_temporary_files_a_dead_process_left_go_and_fresh_ones_stay(
    db, monkeypatch: pytest.MonkeyPatch
):
    """A spool in ``tmp`` and a cross-device copy next to its target, untouched past the term, are
    leftovers; a fresh one is an upload in flight, and a file of someone else's stays whatever
    its age."""
    from src.modules.core_storage.services import cleanup
    from src.modules.core_storage.services.cleanup import purge_temporaries

    monkeypatch.setattr(cleanup, "_temporaries", set())
    spool = _aged(db.temp_file(), hours=2)
    copy = _aged(db.store_dir("public") / "AB" / "12" / ".AB12000001.png.0f0f0f0f.part", hours=2)
    in_flight = _aged(db.temp_file(), hours=0.1)
    foreign = _aged(db.tmp / "another-module.part", hours=5)
    stored = _aged(db.store_dir("public") / "AB" / "12" / "AB12000002.png", hours=5)

    removed = await purge_temporaries(timedelta(hours=1))

    assert removed == 2
    assert not spool.exists() and not copy.exists()
    assert in_flight.exists() and foreign.exists() and stored.exists()


async def test_a_consumer_names_its_own_temporary_files_for_the_cleanup(
    db, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    from src.modules.core_storage.services import cleanup
    from src.modules.core_storage.services.cleanup import purge_temporaries, register_temporaries

    monkeypatch.setattr(cleanup, "_temporaries", set())
    uploads = tmp_path / "uploads"
    register_temporaries(uploads, "upload-")
    left = _aged(uploads / "upload-1a2b.part", hours=3)
    unnamed = _aged(uploads / "other-1a2b.part", hours=3)

    assert await purge_temporaries(timedelta(hours=1)) == 1
    assert not left.exists() and unnamed.exists()
    with pytest.raises(ValueError):
        register_temporaries(uploads, "")
