"""core/restore: a copy goes back whole — the database and the stored files together — and what
stood there is moved aside, never deleted.

Real files in a temp folder: a SQLite base with a WAL sidecar, a storage tree of read-only files.
The two things that touch the live machine are replaced: the maintenance flag lives in the temp
folder, and the stop plan is a stand-in — the real one would see this checkout's own backend.
PostgreSQL against a real server is `tests/modules/core_storage/test_backup_restore_postgres.py`
(`heavy`).
"""

from __future__ import annotations

import errno
import json
import os
import signal
import sqlite3
import threading
from pathlib import Path
from types import SimpleNamespace

import asyncpg
import pytest

from src.core import maintenance
from src.core import restore as restore_module
from src.core.backup import MANIFEST_NAME, BackupRefused, back_up
from src.core.backup_inventory import INVENTORY_NAME
from src.core.config import Config
from src.core.restore import (
    EXIT_NOT_WHOLE,
    EXIT_REFUSED,
    EXIT_RESTORED,
    EXIT_WHOLE,
    RestoreBroken,
    RestoreRefused,
    restore,
    restore_command,
    verify_command,
    verify_copy,
)
from tests.core.test_backup import deadline, nested, pg_client, postgres_config

pytestmark = pytest.mark.pure

STAMP = "20261025-120000"


@pytest.fixture(autouse=True)
def stopped_install(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """The install is down, and the flag is this test's own; the list records the flag's reasons."""
    monkeypatch.setattr(maintenance, "project_root", lambda: tmp_path / "checkout")
    monkeypatch.setattr(restore_module, "plan_live_stop", lambda: running(False))
    raised: list[str] = []
    real_begin = maintenance.begin

    def begin(reason: str):
        raised.append(reason)
        return real_begin(reason)

    monkeypatch.setattr(maintenance, "begin", begin)
    return raised


def running(alive: bool) -> SimpleNamespace:
    return SimpleNamespace(
        is_empty=not alive,
        foreign=(),
        strays=(),
        describe=lambda: "stopping the install:\n  pid 4242 [backend+worker]" if alive else "",
    )


def install(tmp_path: Path) -> Config:
    return Config(
        db_provider="sqlite",
        db_path=str(tmp_path / "install" / "app.sqlite3"),
        storage_path=str(tmp_path / "install" / "storage"),
    )


def make_base(path: Path, notes: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE IF NOT EXISTS note (code TEXT PRIMARY KEY)")
        connection.executemany("INSERT INTO note VALUES (?)", [(note,) for note in notes])
    connection.close()


def notes_in(path: Path) -> list[str]:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return sorted(row[0] for row in connection.execute("SELECT code FROM note"))
    finally:
        connection.close()


def put(root: Path, relative: str, content: bytes) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    path.chmod(0o444)
    return path


def tree(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def take_copy(tmp_path: Path) -> Path:
    config = install(tmp_path)
    make_base(config.sqlite_file, ["NOTE_A", "NOTE_B"])
    put(config.storage_root, "public/AB/CD/ABCDEF0123.png", b"picture")
    put(config.storage_root, "private/12/34/1234567890.txt", b"secret")
    return back_up(config, tmp_path / "copies" / "copy").target


def test_a_wiped_install_gets_its_base_and_its_files_back(tmp_path: Path):
    copy = take_copy(tmp_path)
    config = install(tmp_path)
    expected_files = tree(config.storage_root)
    config.sqlite_file.unlink()
    for path in config.storage_root.rglob("*"):
        if path.is_file():
            path.unlink()

    report = restore(config, copy, stamp=STAMP)

    assert notes_in(config.sqlite_file) == ["NOTE_A", "NOTE_B"]
    assert tree(config.storage_root) == expected_files
    assert report.files.files == 2


def test_what_stood_there_is_moved_aside_with_its_journal(tmp_path: Path):
    copy = take_copy(tmp_path)
    config = install(tmp_path)
    put(config.storage_root, "public/EE/FF/EEFF000000.txt", b"made after the copy")
    writer = sqlite3.connect(config.sqlite_file)
    writer.execute("PRAGMA journal_mode=WAL")
    with writer:
        writer.execute("INSERT INTO note VALUES ('NOTE_LATER')")
    writer.close()
    # A sidecar left by a crash: SQLite would replay it over whatever base lies under its name.
    (config.sqlite_file.parent / "app.sqlite3-wal").write_bytes(b"journal of the old base")

    report = restore(config, copy, stamp=STAMP)

    aside_base = config.sqlite_file.with_name(f"app.sqlite3.before-restore.{STAMP}")
    aside_root = config.storage_root.with_name(f"storage.before-restore.{STAMP}")
    assert notes_in(config.sqlite_file) == ["NOTE_A", "NOTE_B"]
    assert not (config.sqlite_file.parent / "app.sqlite3-wal").exists()
    assert (aside_base.parent / f"{aside_base.name}-wal").read_bytes() == b"journal of the old base"
    assert "public/EE/FF/EEFF000000.txt" not in tree(config.storage_root)
    assert tree(aside_root)["public/EE/FF/EEFF000000.txt"] == b"made after the copy"
    assert str(aside_base) in report.aside and str(aside_root) in report.aside


def test_the_copy_stays_whole_after_the_restored_install_works(tmp_path: Path):
    """The files come back as links to the copy and the base as a copy of it: a cleanup removing a
    file and a writer changing the base touch the install, not the copy — restoring it again gives
    the same state again."""
    copy = take_copy(tmp_path)
    config = install(tmp_path)

    restore(config, copy, stamp=STAMP)
    (config.storage_root / "public/AB/CD/ABCDEF0123.png").unlink()
    make_base(config.sqlite_file, ["NOTE_WRITTEN_AFTER"])
    restore(config, copy, stamp="20261025-130000")

    assert notes_in(config.sqlite_file) == ["NOTE_A", "NOTE_B"]
    assert tree(config.storage_root)["public/AB/CD/ABCDEF0123.png"] == b"picture"


def test_refuses_while_the_install_runs_and_changes_nothing(tmp_path: Path, monkeypatch):
    copy = take_copy(tmp_path)
    config = install(tmp_path)
    make_base(config.sqlite_file, ["NOTE_LIVE"])
    monkeypatch.setattr(restore_module, "plan_live_stop", lambda: running(True))

    with pytest.raises(RestoreRefused) as refusal:
        restore(config, copy, stamp=STAMP)

    assert "src/app.py stop" in str(refusal.value)
    assert "pid 4242" in str(refusal.value)
    assert sorted(notes_in(config.sqlite_file)) == ["NOTE_A", "NOTE_B", "NOTE_LIVE"]
    assert sorted(path.name for path in config.sqlite_file.parent.iterdir()) == [
        "app.sqlite3",
        "storage",
    ]
    assert maintenance.read() is None


def test_raises_the_maintenance_flag_and_lowers_it(tmp_path: Path, stopped_install):
    copy = take_copy(tmp_path)

    restore(install(tmp_path), copy, stamp=STAMP)

    assert stopped_install == [f"restore {copy}"]
    assert maintenance.read() is None


def test_refuses_while_another_holds_the_flag(tmp_path: Path, monkeypatch):
    copy = take_copy(tmp_path)

    def held(reason: str):
        raise maintenance.MaintenanceHeld("maintenance flag held by pid 1 (update main)")

    monkeypatch.setattr(maintenance, "begin", held)

    with pytest.raises(RestoreRefused) as refusal:
        restore(install(tmp_path), copy, stamp=STAMP)

    assert "under maintenance" in str(refusal.value)


def test_a_directory_without_a_manifest_is_not_a_copy(tmp_path: Path):
    """`backup` writes the manifest last: a copy cut short looks exactly like this."""
    copy = take_copy(tmp_path)
    (copy / MANIFEST_NAME).unlink()

    with pytest.raises(RestoreRefused) as refusal:
        restore(install(tmp_path), copy, stamp=STAMP)

    assert "no backup.json" in str(refusal.value)


def test_refuses_a_copy_of_the_other_provider(tmp_path: Path):
    copy = take_copy(tmp_path)
    manifest = json.loads((copy / MANIFEST_NAME).read_text())
    (copy / MANIFEST_NAME).write_text(json.dumps({**manifest, "provider": "postgres"}))

    with pytest.raises(RestoreRefused) as refusal:
        restore(install(tmp_path), copy, stamp=STAMP)

    assert "postgres base" in str(refusal.value)


def test_a_damaged_database_copy_is_refused_before_anything_moves(tmp_path: Path):
    copy = take_copy(tmp_path)
    config = install(tmp_path)
    database = copy / "app.sqlite3"
    database.chmod(0o644)
    database.write_bytes(b"not a database at all, just bytes " * 200)

    with pytest.raises(RestoreRefused):
        restore(config, copy, stamp=STAMP)

    assert notes_in(config.sqlite_file) == ["NOTE_A", "NOTE_B"]
    assert not list(config.sqlite_file.parent.glob("*.restoring.*"))


def test_a_swap_that_fails_is_undone(tmp_path: Path, monkeypatch):
    copy = take_copy(tmp_path)
    config = install(tmp_path)
    make_base(config.sqlite_file, ["NOTE_LIVE"])
    put(config.storage_root, "public/EE/FF/EEFF000000.txt", b"live file")
    before_files = tree(config.storage_root)
    real_rename = os.rename

    def refuse_the_base(source, target):
        if Path(source).name.startswith("app.sqlite3.restoring."):
            raise PermissionError(13, "Permission denied", str(target))
        real_rename(source, target)

    monkeypatch.setattr(restore_module.os, "rename", refuse_the_base)

    with pytest.raises(RestoreRefused) as refusal:
        restore(config, copy, stamp=STAMP)

    assert "was undone" in str(refusal.value)
    assert "NOTE_LIVE" in notes_in(config.sqlite_file)
    assert tree(config.storage_root) == before_files
    assert sorted(path.name for path in config.sqlite_file.parent.iterdir()) == [
        "app.sqlite3",
        "storage",
    ]


def test_the_command_reports_and_exits(tmp_path: Path, monkeypatch, capsys):
    copy = take_copy(tmp_path)
    config = install(tmp_path)
    monkeypatch.setenv("DB_PROVIDER", "sqlite")
    monkeypatch.setenv("DB_PATH", str(config.sqlite_file))
    monkeypatch.setenv("STORAGE_PATH", str(config.storage_root))

    assert restore_command(str(copy)) == EXIT_RESTORED
    printed = capsys.readouterr().out
    assert f"restored:  {copy}" in printed
    assert "2 file(s)" in printed

    assert restore_command(str(tmp_path / "nothing-here")) == EXIT_REFUSED
    assert "nothing was changed" in capsys.readouterr().err


# ── the stored files against the copy's inventory ───────────────────────────

COPIED_FILE = "storage/public/AB/CD/ABCDEF0123.png"


def live_install(tmp_path: Path) -> Config:
    """An install with a copy taken, then written to — a refusal must leave it exactly so."""
    config = install(tmp_path)
    make_base(config.sqlite_file, ["NOTE_LIVE"])
    put(config.storage_root, "public/EE/FF/EEFF000000.txt", b"made after the copy")
    return config


def state_of(config: Config) -> tuple:
    return (
        notes_in(config.sqlite_file),
        tree(config.storage_root),
        sorted(path.name for path in config.sqlite_file.parent.iterdir()),
    )


def replace_in_copy(copy: Path, relative: str, content: bytes) -> None:
    """The copy's file is a link to the live one: writing through it would change both, so the
    damage is a new file under the old name — what a disk or a hand would leave."""
    path = copy / relative
    path.unlink()
    path.write_bytes(content)


def as_taken_before_the_inventory(copy: Path) -> None:
    manifest = json.loads((copy / MANIFEST_NAME).read_text())
    del manifest["storage"]["inventory"], manifest["storage"]["inventory_sha256"]
    (copy / MANIFEST_NAME).write_text(json.dumps(manifest))
    (copy / INVENTORY_NAME).unlink()


def refused_restore(config: Config, copy: Path) -> str:
    before = state_of(config)
    with pytest.raises(RestoreRefused) as refusal:
        restore(config, copy, stamp=STAMP)
    assert state_of(config) == before
    assert maintenance.read() is None
    return str(refusal.value)


def test_a_copy_that_lost_a_file_is_refused_and_nothing_changes(tmp_path: Path):
    copy = take_copy(tmp_path)
    config = live_install(tmp_path)
    (copy / COPIED_FILE).unlink()

    refusal = refused_restore(config, copy)

    assert "missing: 1" in refusal
    assert "public/AB/CD/ABCDEF0123.png (7 bytes)" in refusal
    assert f"backup --verify {copy}" in refusal


def test_a_copy_whose_file_lost_its_tail_is_refused(tmp_path: Path):
    copy = take_copy(tmp_path)
    config = live_install(tmp_path)
    replace_in_copy(copy, COPIED_FILE, b"pic")

    refusal = refused_restore(config, copy)

    assert "size not as recorded: 1" in refusal
    assert "public/AB/CD/ABCDEF0123.png (recorded 7 bytes, found 3)" in refusal


def test_a_file_written_into_the_copy_is_refused_by_name(tmp_path: Path):
    copy = take_copy(tmp_path)
    config = live_install(tmp_path)
    put(copy / "storage", "public/99/99/9999999999.bin", b"not of this copy")

    refusal = refused_restore(config, copy)

    assert "not in the inventory: 1" in refusal
    assert "public/99/99/9999999999.bin" in refusal


def test_a_file_lost_while_the_tree_is_prepared_is_caught_too(tmp_path: Path, monkeypatch):
    """The check runs on the prepared tree — what would be swapped in — not on the copy before."""
    copy = take_copy(tmp_path)
    config = live_install(tmp_path)
    real_snapshot = restore_module.snapshot_tree

    def losing_one(source, target):
        snapshot = real_snapshot(source, target)
        del snapshot.entries["private/12/34/1234567890.txt"]
        return snapshot

    monkeypatch.setattr(restore_module, "snapshot_tree", losing_one)

    refusal = refused_restore(config, copy)

    assert "private/12/34/1234567890.txt" in refusal


def test_an_inventory_changed_after_the_copy_is_not_trusted(tmp_path: Path):
    copy = take_copy(tmp_path)
    config = live_install(tmp_path)
    (copy / COPIED_FILE).unlink()
    inventory = json.loads((copy / INVENTORY_NAME).read_text())
    del inventory["public/AB/CD/ABCDEF0123.png"]
    (copy / INVENTORY_NAME).write_text(json.dumps(inventory))

    refusal = refused_restore(config, copy)

    assert "sha256 differs" in refusal


def test_a_copy_whose_inventory_is_gone_is_refused(tmp_path: Path):
    copy = take_copy(tmp_path)
    config = live_install(tmp_path)
    (copy / INVENTORY_NAME).unlink()

    refusal = refused_restore(config, copy)

    assert "inventory of the stored files is missing" in refusal


def test_a_copy_taken_before_the_inventory_restores_against_its_totals(tmp_path: Path):
    copy = take_copy(tmp_path)
    config = live_install(tmp_path)
    as_taken_before_the_inventory(copy)

    report = restore(config, copy, stamp=STAMP)

    assert notes_in(config.sqlite_file) == ["NOTE_A", "NOTE_B"]
    assert "the totals its manifest records (2 file(s), 13 byte(s))" in report.describe()


def test_a_copy_taken_before_the_inventory_that_lost_a_file_is_refused(tmp_path: Path):
    copy = take_copy(tmp_path)
    config = live_install(tmp_path)
    as_taken_before_the_inventory(copy)
    (copy / COPIED_FILE).unlink()

    refusal = refused_restore(config, copy)

    assert "the tree holds 1 file(s), 6 byte(s)" in refusal
    assert "the manifest records 2 file(s), 13 byte(s)" in refusal
    assert "cannot be named" in refusal


def test_a_whole_copy_reports_how_its_files_were_checked(tmp_path: Path):
    copy = take_copy(tmp_path)

    report = restore(install(tmp_path), copy, stamp=STAMP)

    assert "checked:   every file as its inventory records (2 file(s))" in report.describe()


def test_the_command_refuses_a_damaged_copy_with_exit_1(tmp_path: Path, monkeypatch, capsys):
    copy = take_copy(tmp_path)
    config = live_install(tmp_path)
    monkeypatch.setenv("DB_PROVIDER", "sqlite")
    monkeypatch.setenv("DB_PATH", str(config.sqlite_file))
    monkeypatch.setenv("STORAGE_PATH", str(config.storage_root))
    (copy / COPIED_FILE).unlink()
    before = state_of(config)

    assert restore_command(str(copy)) == EXIT_REFUSED

    printed = capsys.readouterr().err
    assert "public/AB/CD/ABCDEF0123.png" in printed and "nothing was changed" in printed
    assert state_of(config) == before


# ── backup --verify ──────────────────────────────────────────────────────────


def test_verify_finds_a_whole_copy_whole_and_touches_nothing(
    tmp_path: Path, stopped_install, monkeypatch
):
    copy = take_copy(tmp_path)
    monkeypatch.setattr(restore_module, "plan_live_stop", lambda: running(True))
    before = tree(copy)

    report = verify_copy(install(tmp_path), copy)

    assert report.whole
    assert "integrity_check: ok" in report.database
    assert report.storage == "2 file(s), 13 byte(s) in storage/"
    assert "checked:   every file as its inventory records (2 file(s))" in report.describe()
    assert report.describe().endswith("whole")
    assert tree(copy) == before
    assert stopped_install == []


def test_verify_names_every_damage_it_finds(tmp_path: Path):
    copy = take_copy(tmp_path)
    (copy / COPIED_FILE).unlink()
    replace_in_copy(copy, "storage/private/12/34/1234567890.txt", b"secret but longer")
    put(copy / "storage", "public/99/99/9999999999.bin", b"stray")
    database = copy / "app.sqlite3"
    database.chmod(0o644)
    database.write_bytes(b"not a database at all, just bytes " * 200)
    before = tree(copy)

    report = verify_copy(install(tmp_path), copy)

    assert tree(copy) == before
    assert not report.whole
    described = report.describe()
    assert "not whole — restore refuses this copy:" in described
    assert "not a readable SQLite database" in described
    assert "missing: 1" in described
    assert "private/12/34/1234567890.txt (recorded 6 bytes, found 17)" in described
    assert "public/99/99/9999999999.bin (5 bytes)" in described


def test_verify_checks_an_old_copy_by_its_totals(tmp_path: Path):
    copy = take_copy(tmp_path)
    as_taken_before_the_inventory(copy)

    assert verify_copy(install(tmp_path), copy).whole
    (copy / COPIED_FILE).unlink()
    assert not verify_copy(install(tmp_path), copy).whole


def test_verify_notes_a_copy_of_the_other_provider_without_failing_it(tmp_path: Path):
    copy = take_copy(tmp_path)

    report = verify_copy(install(tmp_path).model_copy(update={"db_provider": "postgres"}), copy)

    assert report.whole
    assert "restore here refuses it" in report.describe()


def test_the_verify_command_exits_by_what_it_found(tmp_path: Path, capsys):
    copy = take_copy(tmp_path)

    assert verify_command(str(copy)) == EXIT_WHOLE
    assert capsys.readouterr().out.rstrip().endswith("whole")

    (copy / COPIED_FILE).unlink()
    assert verify_command(str(copy)) == EXIT_NOT_WHOLE
    assert "public/AB/CD/ABCDEF0123.png" in capsys.readouterr().out

    (copy / MANIFEST_NAME).unlink()
    assert verify_command(str(copy)) == EXIT_NOT_WHOLE
    assert "no backup.json" in capsys.readouterr().err


def test_a_name_that_is_no_utf8_is_reported_not_crashed_on(tmp_path: Path, capsys):
    copy = take_copy(tmp_path)
    (copy / "storage" / os.fsdecode(b"stray-\xff.bin")).write_bytes(b"?")

    assert verify_command(str(copy)) == EXIT_NOT_WHOLE

    assert "stray-\\udcff.bin" in capsys.readouterr().out


def test_a_manifest_nested_past_the_parser_is_refused_not_crashed_on(tmp_path: Path):
    copy = take_copy(tmp_path)
    (copy / MANIFEST_NAME).write_text("[" * 100_000)

    with pytest.raises(RestoreRefused, match="cannot be read"):
        verify_copy(install(tmp_path), copy)


# ── refusals while preparing leave nothing behind ────────────────────────────


def test_a_copy_without_stored_files_restores_an_empty_root(tmp_path: Path):
    config = install(tmp_path)
    make_base(config.sqlite_file, ["NOTE_A"])
    copy = back_up(config, tmp_path / "copies" / "copy").target
    put(config.storage_root, "public/EE/FF/EEFF000000.txt", b"made after the copy")

    report = restore(config, copy, stamp=STAMP)

    assert tree(config.storage_root) == {}
    assert "checked:   no stored files in the copy" in report.describe()


def test_a_base_copy_cut_short_by_a_full_disk_leaves_no_staged_base(tmp_path: Path, monkeypatch):
    copy = take_copy(tmp_path)
    config = live_install(tmp_path)

    def disk_full(source, target):
        Path(target).write_bytes(b"half a base")
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(restore_module.shutil, "copyfile", disk_full)

    refusal = refused_restore(config, copy)

    assert "No space left on device" in refusal


def test_postgres_is_not_dumped_aside_for_a_copy_that_lost_a_file(tmp_path: Path, monkeypatch):
    """The check comes before the dump of the current base: a refusal leaves no dump behind and
    never reaches the schema."""
    record = pg_client(tmp_path, monkeypatch)
    config = postgres_config(storage_path=str(tmp_path / "install" / "storage"))
    put(config.storage_root, "public/AB/CD/ABCDEF0123.png", b"picture")
    copy = back_up(config, tmp_path / "copies" / "copy").target
    record.unlink()
    monkeypatch.setattr(restore_module, "resolve_runtime_root", lambda: tmp_path / "runtime")
    (copy / COPIED_FILE).unlink()
    before = tree(config.storage_root)

    with pytest.raises(RestoreRefused) as refusal:
        restore(config, copy, stamp=STAMP)

    assert "public/AB/CD/ABCDEF0123.png" in str(refusal.value)
    assert not record.exists()
    assert not (tmp_path / "runtime").exists()
    assert tree(config.storage_root) == before
    assert sorted(path.name for path in config.storage_root.parent.iterdir()) == ["storage"]


# ── a refusal removes what this run made, and only that ──────────────────────


def test_a_restoring_folder_that_was_there_before_stays_untouched(tmp_path: Path):
    """Not this run's: an earlier restore cut short left it, or a hand put it there."""
    copy = take_copy(tmp_path)
    config = live_install(tmp_path)
    foreign = config.storage_root.with_name(f"storage.restoring.{STAMP}")
    put(foreign, "someone/else.txt", b"not this run's")

    refusal = refused_restore(config, copy)

    assert str(foreign) in refusal
    assert tree(foreign) == {"someone/else.txt": b"not this run's"}


def test_a_base_moved_aside_in_the_same_second_is_not_overwritten(tmp_path: Path):
    """Two restores within one second share the stamp: the second would rename the base over the
    one the first moved aside."""
    copy = take_copy(tmp_path)
    config = live_install(tmp_path)
    earlier = config.sqlite_file.with_name(f"app.sqlite3.before-restore.{STAMP}")
    make_base(earlier, ["NOTE_KEPT_BY_THE_EARLIER_RESTORE"])

    refusal = refused_restore(config, copy)

    assert str(earlier) in refusal
    assert notes_in(earlier) == ["NOTE_KEPT_BY_THE_EARLIER_RESTORE"]


def moved_install(tmp_path: Path) -> Config:
    """An install whose base and storage folders do not exist yet."""
    return Config(
        db_provider="sqlite",
        db_path=str(tmp_path / "moved" / "base" / "app.sqlite3"),
        storage_path=str(tmp_path / "moved" / "files" / "storage"),
    )


def test_a_refused_restore_removes_the_folders_it_made(tmp_path: Path):
    copy = take_copy(tmp_path)
    (copy / COPIED_FILE).unlink()

    with pytest.raises(RestoreRefused, match="missing: 1"):
        restore(moved_install(tmp_path), copy, stamp=STAMP)

    assert not (tmp_path / "moved").exists()


def test_an_undone_swap_removes_the_folders_it_made(tmp_path: Path, monkeypatch):
    copy = take_copy(tmp_path)
    real_rename = os.rename

    def refuse_the_base(source, target):
        if Path(source).name.startswith("app.sqlite3.restoring."):
            raise PermissionError(13, "Permission denied", str(target))
        real_rename(source, target)

    monkeypatch.setattr(restore_module.os, "rename", refuse_the_base)

    with pytest.raises(RestoreRefused, match="was undone"):
        restore(moved_install(tmp_path), copy, stamp=STAMP)

    assert not (tmp_path / "moved").exists()


def test_a_refusal_removes_a_prepared_tree_nested_past_the_recursion_limit(
    tmp_path: Path, nested
):
    config = install(tmp_path)
    make_base(config.sqlite_file, ["NOTE_A"])
    put(config.storage_root, "public/AB/CD/ABCDEF0123.png", b"picture")
    (nested(config.storage_root / "deep") / "DEEP.txt").write_bytes(b"deep")
    copy = back_up(config, tmp_path / "copies" / "copy").target
    (copy / COPIED_FILE).unlink()

    with pytest.raises(RestoreRefused, match="missing: 1"):
        restore(config, copy, stamp=STAMP)

    assert sorted(path.name for path in config.sqlite_file.parent.iterdir()) == [
        "app.sqlite3",
        "storage",
    ]


# ── PostgreSQL: the dump of the current base aside ───────────────────────────


def postgres_install(tmp_path: Path, monkeypatch, **client) -> tuple[Config, Path]:
    """An install on the stand-in client with one stored file, and a whole copy of it. The base
    sits on port 1, where nothing answers, unless a test stands one in (`answering_base`)."""
    pg_client(tmp_path, monkeypatch, **client)
    config = postgres_config(storage_path=str(tmp_path / "install" / "storage"))
    put(config.storage_root, "public/AB/CD/ABCDEF0123.png", b"picture")
    copy = back_up(config, tmp_path / "copies" / "copy").target
    monkeypatch.setattr(restore_module, "resolve_runtime_root", lambda: tmp_path / "runtime")
    return config, copy


def dump_aside(tmp_path: Path) -> Path:
    return tmp_path / "runtime" / "backup" / f"research.before-restore.{STAMP}.dump"


def answering_base(monkeypatch, answer: BaseException | None) -> list[str]:
    """The base the schema is emptied in; ``answer`` — what running the reset raises. The list
    records the statements it was sent."""
    sent: list[str] = []

    class Connection:
        async def execute(self, statement: str) -> None:
            sent.append(statement)
            if answer is not None:
                raise answer

        async def close(self) -> None:
            return None

    async def connect(config: Config) -> Connection:
        return Connection()

    monkeypatch.setattr(restore_module, "connect_postgres", connect)
    return sent


def assert_untouched(config: Config, tmp_path: Path, files: dict[str, bytes]) -> None:
    assert tree(config.storage_root) == files
    assert sorted(path.name for path in config.storage_root.parent.iterdir()) == ["storage"]
    assert not (tmp_path / "runtime").exists()
    assert maintenance.read() is None


def test_a_dump_aside_pg_restore_cannot_read_is_removed_and_named(tmp_path: Path, monkeypatch):
    config, copy = postgres_install(tmp_path, monkeypatch, unreadable_marked="before-restore")
    before = tree(config.storage_root)

    with pytest.raises(RestoreRefused) as refusal:
        restore(config, copy, stamp=STAMP)

    assert f"pg_restore cannot read {dump_aside(tmp_path)}" in str(refusal.value)
    assert "cannot read the copy" not in str(refusal.value)
    assert_untouched(config, tmp_path, before)


def test_a_swap_undone_on_postgres_removes_the_dump_aside(tmp_path: Path, monkeypatch):
    config, copy = postgres_install(tmp_path, monkeypatch)
    before = tree(config.storage_root)
    real_rename = os.rename

    def refuse_the_tree(source, target):
        if Path(source).name.startswith("storage.restoring."):
            raise PermissionError(13, "Permission denied", str(target))
        real_rename(source, target)

    monkeypatch.setattr(restore_module.os, "rename", refuse_the_tree)

    with pytest.raises(RestoreRefused, match="was undone"):
        restore(config, copy, stamp=STAMP)

    assert_untouched(config, tmp_path, before)


def test_a_base_that_cannot_be_reached_for_the_reset_keeps_nothing_aside(
    tmp_path: Path, monkeypatch
):
    """Nothing answers on port 1: no statement reached the base, so the dump is a duplicate."""
    config, copy = postgres_install(tmp_path, monkeypatch)
    before = tree(config.storage_root)

    with pytest.raises(RestoreRefused, match="could not be emptied"):
        restore(config, copy, stamp=STAMP)

    assert_untouched(config, tmp_path, before)


def test_a_reset_the_server_refuses_keeps_nothing_aside(tmp_path: Path, monkeypatch):
    """The reset is one transaction: an error the server answers with means it rolled back."""
    config, copy = postgres_install(tmp_path, monkeypatch)
    before = tree(config.storage_root)
    sent = answering_base(
        monkeypatch, asyncpg.exceptions.InsufficientPrivilegeError("must be owner of schema public")
    )

    with pytest.raises(RestoreRefused, match="must be owner of schema public"):
        restore(config, copy, stamp=STAMP)

    assert sent == [restore_module._RESET_SCHEMA]
    assert_untouched(config, tmp_path, before)


@pytest.mark.parametrize(
    "answer",
    [
        asyncpg.exceptions.ConnectionDoesNotExistError(
            "connection was closed in the middle of operation"
        ),
        KeyboardInterrupt(),
    ],
    ids=["connection lost", "ctrl-c"],
)
def test_a_reset_left_without_an_answer_keeps_the_dump_and_names_it(
    tmp_path: Path, monkeypatch, answer: BaseException
):
    """Whether the schema was emptied cannot be told: the files go back, the dump stays — the one
    way back if it was — and the command does not claim that nothing changed."""
    config, copy = postgres_install(tmp_path, monkeypatch)
    before = tree(config.storage_root)
    answering_base(monkeypatch, answer)

    with pytest.raises(RestoreBroken) as broken:
        restore(config, copy, stamp=STAMP)

    assert str(dump_aside(tmp_path)) in str(broken.value)
    assert "pg_restore --clean" in str(broken.value)
    assert dump_aside(tmp_path).is_file()
    assert tree(config.storage_root) == before
    assert sorted(path.name for path in config.storage_root.parent.iterdir()) == ["storage"]
    assert maintenance.read() is None


@pytest.mark.parametrize(
    "failure",
    [BackupRefused("`pg_restore` could not run: [Errno 26] Text file busy"), KeyboardInterrupt()],
    ids=["cannot run", "ctrl-c"],
)
def test_pg_restore_stopped_after_the_reset_names_the_way_back(
    tmp_path: Path, monkeypatch, failure: BaseException
):
    config, copy = postgres_install(tmp_path, monkeypatch)
    answering_base(monkeypatch, None)
    real_run = restore_module.run_tool

    def restoring_fails(argv, environment):
        if "--single-transaction" in argv:
            raise failure
        return real_run(argv, environment)

    monkeypatch.setattr(restore_module, "run_tool", restoring_fails)

    with pytest.raises(RestoreBroken) as broken:
        restore(config, copy, stamp=STAMP)

    assert str(dump_aside(tmp_path)) in str(broken.value)
    assert "pg_restore --clean" in str(broken.value)
    assert dump_aside(tmp_path).is_file()
    assert maintenance.read() is None
    # Both halves of the way back: the base in the dump, the files moved aside.
    aside_root = config.storage_root.with_name(f"storage.before-restore.{STAMP}")
    assert str(aside_root) in str(broken.value)
    assert aside_root.is_dir()


@pytest.mark.parametrize(
    "where", ["connecting", "looking for pg_restore"], ids=["connecting", "before the reset"]
)
def test_ctrl_c_before_the_reset_reaches_the_base_is_a_refusal(
    tmp_path: Path, monkeypatch, where: str
):
    """Nothing was sent to the base: the renames go back, the dump goes, exit 1 — not the unsure
    exit 2 of a reset that got no answer."""
    config, copy = postgres_install(tmp_path, monkeypatch)
    before = tree(config.storage_root)

    def interrupted(*args):
        raise KeyboardInterrupt

    if where == "connecting":
        monkeypatch.setattr(restore_module, "connect_postgres", interrupted)
    else:
        monkeypatch.setattr(restore_module, "require_tool", interrupted)

    with pytest.raises(RestoreRefused, match="interrupted"):
        restore(config, copy, stamp=STAMP)

    assert_untouched(config, tmp_path, before)


def test_a_copy_inside_the_storage_root_is_refused_before_anything_moves(tmp_path: Path):
    """The swap would move the copy aside together with the root it lies in."""
    config = install(tmp_path)
    make_base(config.sqlite_file, ["NOTE_A"])
    put(config.storage_root, "public/AB/CD/ABCDEF0123.png", b"picture")
    copy = back_up(config, tmp_path / "copies" / "copy").target
    inside = config.storage_root / "kept-here"
    copy.rename(inside)
    before = state_of(config)

    with pytest.raises(RestoreRefused, match="inside the storage root"):
        restore(config, inside, stamp=STAMP)

    assert state_of(config) == before


def test_a_flag_that_cannot_be_raised_is_a_refusal(tmp_path: Path, monkeypatch, capsys):
    copy = take_copy(tmp_path)
    config = command_install(tmp_path, monkeypatch)
    before = state_of(config)

    def read_only_runtime(reason: str):
        raise PermissionError(13, "Permission denied", "runtime/maintenance.json")

    monkeypatch.setattr(maintenance, "begin", read_only_runtime)

    assert restore_command(str(copy)) == EXIT_REFUSED

    assert "the maintenance flag cannot be raised" in capsys.readouterr().err
    assert state_of(config) == before


def test_a_copy_whose_path_holds_uri_characters_is_checked_as_itself(tmp_path: Path):
    """`#` and `?` would cut a raw SQLite URI short: the check would read another file — or
    create an empty one where the cut fell — and call a damaged base whole."""
    config = install(tmp_path)
    make_base(config.sqlite_file, ["NOTE_A"])
    copy = back_up(config, tmp_path / "copies" / "c#1?x").target
    database = copy / "app.sqlite3"
    database.chmod(0o644)
    database.write_bytes(b"not a database at all, just bytes " * 200)

    report = verify_copy(config, copy)

    assert not report.whole
    assert "not a readable SQLite database" in report.describe()
    assert sorted(path.name for path in copy.parent.iterdir()) == ["c#1?x"]


# ── Ctrl-C ───────────────────────────────────────────────────────────────────


def interrupt_while(where: str, monkeypatch) -> None:
    if where == "checking the copy":
        def interrupted_check(path):
            raise KeyboardInterrupt

        monkeypatch.setattr(restore_module, "check_sqlite_file", interrupted_check)
    elif where == "preparing the files":
        real_snapshot = restore_module.snapshot_tree

        def interrupted_snapshot(source, target):
            real_snapshot(source, target)
            raise KeyboardInterrupt

        monkeypatch.setattr(restore_module, "snapshot_tree", interrupted_snapshot)
    elif where == "copying the base":
        def interrupted_copy(source, target):
            Path(target).write_bytes(b"half a base")
            raise KeyboardInterrupt

        monkeypatch.setattr(restore_module.shutil, "copyfile", interrupted_copy)
    else:
        real_rename = os.rename

        def interrupted_rename(source, target):
            if Path(source).name.startswith("app.sqlite3.restoring."):
                raise KeyboardInterrupt
            real_rename(source, target)

        monkeypatch.setattr(restore_module.os, "rename", interrupted_rename)


def command_install(tmp_path: Path, monkeypatch) -> Config:
    config = live_install(tmp_path)
    monkeypatch.setenv("DB_PROVIDER", "sqlite")
    monkeypatch.setenv("DB_PATH", str(config.sqlite_file))
    monkeypatch.setenv("STORAGE_PATH", str(config.storage_root))
    return config


@pytest.mark.parametrize(
    "where", ["checking the copy", "preparing the files", "copying the base", "swapping"]
)
def test_ctrl_c_leaves_the_install_as_it_was_and_exits_1(
    tmp_path: Path, monkeypatch, capsys, where: str
):
    copy = take_copy(tmp_path)
    config = command_install(tmp_path, monkeypatch)
    before = state_of(config)
    interrupt_while(where, monkeypatch)

    assert restore_command(str(copy)) == EXIT_REFUSED

    printed = capsys.readouterr().err
    assert "interrupted" in printed and "nothing was changed" in printed
    assert state_of(config) == before
    assert maintenance.read() is None


@pytest.mark.skipif(
    threading.current_thread() is not threading.main_thread(),
    reason="signal handlers belong to the main thread",
)
def test_a_second_ctrl_c_does_not_cut_the_cleanup_short(tmp_path: Path, monkeypatch, capsys):
    """Removing a prepared tree of many files takes a while, and an impatient second Ctrl-C would
    leave half of it: the cleanup runs with SIGINT ignored, and the handler comes back after."""
    copy = take_copy(tmp_path)
    config = command_install(tmp_path, monkeypatch)
    before = state_of(config)
    interrupt_while("preparing the files", monkeypatch)
    handler_before = signal.getsignal(signal.SIGINT)
    seen: list[object] = []
    real_rmtree = restore_module.shutil.rmtree

    def watching(path, *args, **kwargs):
        seen.append(signal.getsignal(signal.SIGINT))
        return real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(restore_module.shutil, "rmtree", watching)

    assert restore_command(str(copy)) == EXIT_REFUSED

    assert seen == [signal.SIG_IGN]
    assert signal.getsignal(signal.SIGINT) is handler_before
    assert state_of(config) == before


def test_ctrl_c_while_verifying_exits_1(tmp_path: Path, monkeypatch, capsys):
    copy = take_copy(tmp_path)

    def interrupted(root):
        raise KeyboardInterrupt

    monkeypatch.setattr(restore_module, "scan_tree", interrupted)

    assert verify_command(str(copy)) == EXIT_NOT_WHOLE
    assert "interrupted" in capsys.readouterr().err


# ── a manifest that is no file ───────────────────────────────────────────────


@pytest.mark.skipif(
    threading.current_thread() is not threading.main_thread(),
    reason="signal handlers belong to the main thread",
)
@pytest.mark.parametrize("name", [MANIFEST_NAME, INVENTORY_NAME])
def test_a_manifest_that_is_no_regular_file_is_refused_not_waited_on(tmp_path: Path, name: str):
    copy = take_copy(tmp_path)
    (copy / name).unlink()
    os.mkfifo(copy / name)

    with deadline(), pytest.raises(RestoreRefused, match="not a regular file"):
        verify_copy(install(tmp_path), copy)
