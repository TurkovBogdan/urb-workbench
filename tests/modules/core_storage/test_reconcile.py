"""The reconciliation of the base with the disk — every discrepancy on a temp storage root.

Rows and bytes are made to disagree the way a crash leaves them: bytes deleted under a row, a row
deleted under its bytes, bytes overwritten. Ages are back-dated — a row's ``created_at``, a file's
``mtime`` — since the grace period is what keeps a registration midway out of the report.
"""

from __future__ import annotations

import os
import time
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import delete, update

from src.core.config import Config
from src.core.database import close_database, init_database, write_scope
from src.core.utils.date import utc_now
from src.modules.core_storage import layout as layout_module
from src.modules.core_storage.cli import (
    EXIT_CLEAN,
    EXIT_FOUND,
    EXIT_UNAVAILABLE,
    storage_check_command,
)
from src.modules.core_storage.crud import file as file_crud
from src.modules.core_storage.dto import Owner
from src.modules.core_storage.errors import FileNotFound
from src.modules.core_storage.models import CoreStorageFile, CoreStorageFileOwner
from src.modules.core_storage.module import CoreStorageModule
from src.modules.core_storage.services import files, ownership
from src.modules.core_storage.services import reconcile as reconcile_module
from src.modules.core_storage.services.cleanup import purge_expired
from src.modules.core_storage.services.reconcile import reconcile_storage, stored_name
from src.modules.core_storage.services.registration import file_register_bytes, file_register_path
from src.modules.core_storage.tasks.reconcile_task import ReconcileTask

from .conftest import STORES, mark_deleted_at

pytestmark = pytest.mark.db

OWNER = Owner("task", "T1")
LONG_AGO = timedelta(days=2)


async def settle(code: str) -> None:
    """Back-date the row past the grace period, as a file registered yesterday."""
    async with write_scope() as s:
        await s.execute(
            update(CoreStorageFile)
            .where(CoreStorageFile.code == code)
            .values(created_at=utc_now() - LONG_AGO)
        )


def age(path: Path) -> None:
    old = time.time() - LONG_AGO.total_seconds()
    os.utime(path, (old, old))


async def stored_and_settled(content: bytes, store: str = "public", owner: Owner = OWNER):
    stored = await file_register_bytes(content, store=store, owner=owner, filename="note.txt")
    await settle(stored.code)
    return stored


def bytes_without_a_row(root: Path, relative: str, content: bytes = b"left behind") -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    age(path)
    return path


async def drop_row(code: str) -> None:
    """The cleanup's half that commits before the bytes are unlinked."""
    async with write_scope() as s:
        await s.execute(delete(CoreStorageFileOwner).where(CoreStorageFileOwner.file_code == code))
        await s.execute(delete(CoreStorageFile).where(CoreStorageFile.code == code))


async def test_a_whole_storage_is_consistent(db):
    await stored_and_settled(b"one")
    await stored_and_settled(b"two", store="private")

    report = await reconcile_storage(fix=True)

    assert report.clean
    assert (report.rows, report.removed, report.missing, report.orphans) == (2, 0, [], [])


async def test_a_held_file_without_bytes_is_reported_and_kept(db):
    stored = await stored_and_settled(b"lost bytes")
    files.file_path(stored).unlink()

    report = await reconcile_storage(fix=True)

    assert report.missing == [stored.code]
    assert not report.clean
    assert (await files.file_get(stored.code)).code == stored.code
    assert [place.owner for place in await ownership.file_owners(stored.code)] == [OWNER]
    with pytest.raises(FileNotFound):
        await files.file_open(stored.code)


async def test_a_row_younger_than_the_term_is_not_looked_for(db):
    """Between its commit and its `replace` a registration has a row and no bytes yet."""
    stored = await file_register_bytes(b"in flight", store="public", owner=OWNER)
    files.file_path(stored).unlink()

    report = await reconcile_storage(fix=True)

    assert report.rows == 0
    assert report.missing == []


async def test_a_marked_file_without_bytes_is_left_to_the_cleanup(db):
    stored = await stored_and_settled(b"released and lost")
    await ownership.file_release(stored.code, OWNER)
    await mark_deleted_at(stored.code, utc_now() - LONG_AGO)
    files.file_path(stored).unlink()

    report = await reconcile_storage(fix=True)

    assert (report.missing, report.missing_marked) == ([], 1)
    assert report.clean
    assert (await purge_expired(timedelta(hours=1), 0)).purged == 1
    assert await file_crud.file_get(stored.code, include_deleted=True) is None


async def test_bytes_of_another_size_are_reported(db):
    stored = await stored_and_settled(b"the right bytes")
    path = files.file_path(stored)
    path.chmod(0o644)
    path.write_bytes(b"short")

    report = await reconcile_storage(fix=True)

    assert report.mismatched == [stored.code]
    assert path.read_bytes() == b"short"


async def test_bytes_of_the_same_size_differ_only_by_sha256(db):
    stored = await stored_and_settled(b"aaaaaaaa")
    path = files.file_path(stored)
    path.chmod(0o644)
    path.write_bytes(b"bbbbbbbb")

    by_size = await reconcile_storage(fix=False)
    by_hash = await reconcile_storage(fix=False, hash_bytes=True)

    assert by_size.mismatched == []
    assert by_hash.mismatched == [stored.code]
    assert by_hash.hashed


async def test_bytes_without_a_row_are_only_reported_without_fix(db):
    path = bytes_without_a_row(db.root, "public/AB/CD/ABCDEF0123.txt")

    report = await reconcile_storage(fix=False)

    assert report.orphans == [path]
    assert report.removed == 0
    assert path.exists()
    assert not report.clean


async def test_bytes_without_a_row_past_the_term_are_removed_with_their_folders(db):
    kept = await stored_and_settled(b"stays")
    orphan = bytes_without_a_row(db.root, "public/AB/CD/ABCDEF0123.txt")

    report = await reconcile_storage(fix=True)

    assert (report.orphans, report.removed) == ([orphan], 1)
    assert not orphan.exists()
    assert not (db.root / "public" / "AB").exists()
    assert files.file_path(kept).read_bytes() == b"stays"
    assert report.clean


async def test_bytes_the_cleanup_left_after_its_commit_are_removed(db):
    stored = await stored_and_settled(b"purge died midway")
    path = files.file_path(stored)
    age(path)
    await drop_row(stored.code)

    report = await reconcile_storage(fix=True)

    assert report.removed == 1
    assert not path.exists()


async def test_young_bytes_without_a_row_are_left_alone(db):
    path = db.root / "public" / "AB" / "CD" / "ABCDEF0123.txt"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"just placed")

    report = await reconcile_storage(fix=True)

    assert (report.young, report.orphans, report.removed) == (1, [], 0)
    assert path.exists()


async def test_bytes_under_another_extension_than_the_row_are_not_its_bytes(db):
    stored = await stored_and_settled(b"plain text")
    right = files.file_path(stored)
    wrong = right.with_name(f"{stored.code}.png")
    os.replace(right, wrong)
    age(wrong)

    report = await reconcile_storage(fix=True)

    assert report.missing == [stored.code]
    assert (report.orphans, report.removed) == ([wrong], 1)


async def test_a_name_that_is_no_file_s_is_reported_and_left(db):
    stranger = db.root / "public" / "AB" / "CD" / "notes.txt"
    stranger.parent.mkdir(parents=True)
    stranger.write_text("someone's")
    age(stranger)
    temporary = stranger.with_name(".ABCDEF0123.txt.0f0f0f0f.part")
    temporary.write_text("the cleanup's")
    age(temporary)

    report = await reconcile_storage(fix=True)

    assert report.strangers == [stranger]
    assert stranger.exists() and temporary.exists()
    assert report.orphans == []


async def test_a_store_taken_off_the_list_is_still_reconciled(db, monkeypatch):
    stored = await stored_and_settled(b"in a closed store", store="private")
    monkeypatch.setattr(layout_module.get_layout(), "stores", ("public",))
    orphan = bytes_without_a_row(db.root, "private/AB/CD/ABCDEF0123.txt")

    report = await reconcile_storage(fix=True)

    assert report.removed == 1 and not orphan.exists()
    assert files.file_path(stored).exists()


async def test_a_row_that_appears_before_the_removal_keeps_its_bytes(db, monkeypatch):
    """The removal takes the file's row first and reads it again: a row committed after the disk
    pass is seen there, and its bytes stay."""
    orphan = bytes_without_a_row(db.root, "public/AB/CD/ABCDEF0123.txt")
    real_find = reconcile_module._find_orphans

    async def a_row_arrives(layout, stores, report, *, written_by):
        await real_find(layout, stores, report, written_by=written_by)
        async with write_scope() as s:
            await file_crud.file_insert(
                code="ABCDEF0123", store="public", sha256="0" * 64, type="text",
                size=11, mime="text/plain", extension=".txt", session=s,
            )

    monkeypatch.setattr(reconcile_module, "_find_orphans", a_row_arrives)

    report = await reconcile_storage(fix=True)

    assert report.orphans == [orphan]
    assert report.removed == 0
    assert orphan.exists()


async def test_the_scheduled_run_removes_nothing_on_a_root_likely_shared(db, monkeypatch):
    orphan = bytes_without_a_row(db.root, "public/AB/CD/ABCDEF0123.txt")
    monkeypatch.setattr(layout_module.get_layout(), "root_shared", True)

    guarded = await reconcile_storage(fix=True, guarded=True)
    by_hand = await reconcile_storage(fix=True)

    assert guarded.removed == 0 and "another database" in guarded.refused
    assert by_hand.removed == 1 and not orphan.exists()


async def test_the_scheduled_run_removes_nothing_when_the_leftovers_are_too_many(db):
    """A copy of the base on the original's root: everything the original registered since looks
    like bytes without a row."""
    for index in range(11):
        bytes_without_a_row(db.root, f"public/AB/CD/ABCDEF{index:04d}.txt")

    guarded = await reconcile_storage(fix=True, guarded=True)

    assert guarded.removed == 0
    assert "more than a crash leaves" in guarded.refused
    assert len(list((db.root / "public" / "AB" / "CD").iterdir())) == 11


async def test_the_scheduled_run_removes_a_crash_s_few_leftovers(db):
    for index in range(10):
        bytes_without_a_row(db.root, f"public/AB/CD/ABCDEF{index:04d}.txt")

    guarded = await reconcile_storage(fix=True, guarded=True)

    assert (guarded.removed, guarded.refused) == (10, "")


@pytest.mark.parametrize(
    ("relative", "parsed"),
    [
        ("public/AB/CD/ABCDEF0123.png", ("ABCDEF0123", ".png")),
        ("public/AB/CD/ABCDEF0123", ("ABCDEF0123", "")),
        ("public/AB/CD/abcdef0123.png", None),
        ("public/AB/EF/ABCDEF0123.png", None),
        ("public/AB/CD/ABCDEF012.png", None),
        ("public/AB/CD/notes.txt", None),
    ],
)
def test_the_name_of_stored_bytes(relative: str, parsed):
    assert stored_name(Path("/root") / relative) == parsed


# ── the same content brought again ───────────────────────────────────────────

async def test_uploading_the_same_content_brings_lost_bytes_back(db):
    stored = await stored_and_settled(b"lost and found")
    files.file_path(stored).unlink()

    again = await file_register_bytes(b"lost and found", store="public", owner=Owner("task", "T2"))

    assert again.code == stored.code
    path = files.file_path(stored)
    assert path.read_bytes() == b"lost and found"
    assert oct(path.stat().st_mode & 0o777) == "0o444"
    with await files.file_open(stored.code) as handle:
        assert handle.read() == b"lost and found"
    assert (await reconcile_storage(fix=False)).clean


async def test_uploading_the_same_content_replaces_damaged_bytes(db):
    stored = await stored_and_settled(b"the whole content")
    path = files.file_path(stored)
    path.chmod(0o644)
    path.write_bytes(b"cut")

    await file_register_bytes(b"the whole content", store="public", owner=Owner("task", "T2"))

    assert path.read_bytes() == b"the whole content"


async def test_a_moved_source_heals_lost_bytes_and_is_taken(db, tmp_path: Path):
    stored = await stored_and_settled(b"from a download")
    files.file_path(stored).unlink()
    download = tmp_path / "download.bin"
    download.write_bytes(b"from a download")

    await file_register_path(download, store="public", owner=Owner("task", "T2"), move=True)

    assert files.file_path(stored).read_bytes() == b"from a download"
    assert not download.exists()


async def test_whole_bytes_are_not_touched_by_a_second_upload(db):
    stored = await stored_and_settled(b"already there")
    path = files.file_path(stored)
    inode = path.stat().st_ino

    await file_register_bytes(b"already there", store="public", owner=Owner("task", "T2"))

    assert path.stat().st_ino == inode


# ── the scheduled task ───────────────────────────────────────────────────────

class Context:
    def __init__(self) -> None:
        self.lines: list[tuple[str, str]] = []

    async def info(self, msg: str, *args) -> None:
        self.lines.append(("info", msg % args))

    async def warn(self, msg: str, *args) -> None:
        self.lines.append(("warn", msg % args))

    async def error(self, msg: str, *args) -> None:
        self.lines.append(("error", msg % args))


async def test_the_task_reports_into_its_run_and_removes_few_leftovers(db):
    lost = await stored_and_settled(b"held, bytes gone")
    files.file_path(lost).unlink()
    orphan = bytes_without_a_row(db.root, "public/AB/CD/ABCDEF0123.txt")
    ctx = Context()

    await ReconcileTask.handle(ctx)

    assert not orphan.exists()
    summary = next(text for level, text in ctx.lines if level == "info")
    assert "live without bytes 1" in summary and "removed 1" in summary
    assert ("error", f"file {lost.code} is held and its bytes are gone") in ctx.lines


def test_the_task_runs_hourly_apart_from_the_cleanup():
    assert ReconcileTask.SCHEDULE == "20 * * * *"
    assert (ReconcileTask.MODULE, ReconcileTask.CODE) == ("core_storage", "reconcile")


# ── app.py storage check ─────────────────────────────────────────────────────

@pytest.fixture
async def file_install(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Config:
    """A file base with one settled file and one leftover — the command opens its own engine."""
    config = Config(
        db_provider="sqlite",
        db_path=str(tmp_path / "install.sqlite3"),
        storage_path=str(tmp_path / "storage"),
    )
    layout = layout_module.StorageLayout(config.storage_root, tmp_path / "tmp", STORES)
    monkeypatch.setattr(layout_module, "_layout", layout)
    engine = await init_database(config)
    from src.core.database.runtime import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        await stored_and_settled(b"kept")
        bytes_without_a_row(config.storage_root, "public/AB/CD/ABCDEF0123.txt")
    finally:
        await close_database()
    return config


async def test_the_command_reports_without_fix_and_removes_with_it(file_install: Config, capsys):
    modules = [CoreStorageModule(stores=STORES)]
    leftover = file_install.storage_root / "public" / "AB" / "CD" / "ABCDEF0123.txt"

    assert await storage_check_command(modules, file_install, fix=False, hash_bytes=True) == EXIT_FOUND
    printed = capsys.readouterr().out
    assert "run with --fix to remove them" in printed
    assert str(leftover) in printed and leftover.exists()
    assert "sha256 compared:         yes" in printed

    assert await storage_check_command(modules, file_install, fix=True, hash_bytes=False) == EXIT_CLEAN
    assert "removed 1" in capsys.readouterr().out
    assert not leftover.exists()


async def test_the_command_without_the_module_or_a_base_cannot_run(tmp_path: Path, capsys):
    assert await storage_check_command([], Config(), fix=False, hash_bytes=False) == EXIT_UNAVAILABLE
    assert "not one of this application's modules" in capsys.readouterr().err

    empty = Config(db_provider="sqlite", db_path=str(tmp_path / "empty.sqlite3"),
                   storage_path=str(tmp_path / "storage"))
    modules = [CoreStorageModule(stores=STORES)]
    assert await storage_check_command(modules, empty, fix=False, hash_bytes=False) == EXIT_UNAVAILABLE
    assert "could not run" in capsys.readouterr().err
