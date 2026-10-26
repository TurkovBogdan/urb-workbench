"""core/backup: the copy the update refuses to migrate without — the database of both providers
and the stored files beside it.

SQLite is exercised against real files (`VACUUM INTO`, `integrity_check`, a WAL sidecar that a
plain `cp` would miss), the storage snapshot against a real tree in a temp folder. PostgreSQL is
exercised against stand-in `pg_dump`/`pg_restore` scripts on `PATH`: this machine has no
`postgresql-client`, and what has to be proven here is the argument construction, the password
handling, the verification and the refusals — not that libpq speaks TCP. A real dump and restore
against a real server is `tests/modules/core_storage/test_backup_restore_postgres.py` (`heavy`).
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import signal
import sqlite3
import sys
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from src.core import backup as backup_module
from src.core.backup import (
    MANIFEST_NAME,
    POSTGRES_CLIENT_PACKAGE,
    STORAGE_DIR_NAME,
    BackupRefused,
    back_up,
    backup_command,
    default_target,
    dump_postgres,
    first_ctrl_c_only,
    remove_tree,
)
from src.core.backup_inventory import INVENTORY_NAME
from src.core.config import Config

REVISIONS = ("com_004", "rem_005")


def sqlite_config(path: Path, storage: Path | None = None) -> Config:
    root = storage if storage is not None else path.parent / "storage"
    return Config(db_provider="sqlite", db_path=str(path), storage_path=str(root))


def postgres_config(**over) -> Config:
    settings = dict(
        db_provider="postgres",
        db_host="127.0.0.1",
        db_port=1,
        db_name="research",
        db_user="urb",
        db_password="s3cret",
        db_ssl=False,
    )
    return Config(**{**settings, **over})


def stored(root: Path, relative: str, content: bytes) -> Path:
    """A stored file as the storage leaves it: read-only, under its code folders."""
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    path.chmod(0o444)
    return path


def make_database(path: Path, *, rows: int = 3) -> Path:
    connection = sqlite3.connect(path)
    with connection:
        connection.execute("CREATE TABLE alembic_version (version_num TEXT)")
        connection.executemany(
            "INSERT INTO alembic_version VALUES (?)", [(revision,) for revision in REVISIONS]
        )
        connection.execute("CREATE TABLE note (code TEXT PRIMARY KEY)")
        connection.executemany(
            "INSERT INTO note VALUES (?)", [(f"NOTE_{index}",) for index in range(rows)]
        )
    connection.close()
    return path


def rows_in(path: Path, table: str) -> int:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    finally:
        connection.close()


# ── sqlite ───────────────────────────────────────────────────────────────────

@pytest.mark.pure
def test_sqlite_copy_carries_the_data_and_verifies_itself(tmp_path: Path):
    source = make_database(tmp_path / "app.sqlite3")

    copy = back_up(sqlite_config(source), tmp_path / "copy")

    assert copy.target.is_dir()
    assert copy.database == tmp_path / "copy" / "app.sqlite3"
    assert rows_in(copy.database, "note") == 3
    assert copy.revisions == REVISIONS
    assert copy.verification == "integrity_check: ok"
    assert copy.diagnostics == ("foreign_key_check: no violations",)


@pytest.mark.pure
def test_sqlite_copy_includes_what_is_still_in_the_wal_sidecar(tmp_path: Path):
    """The reason this is not `cp`: in WAL mode committed rows live beside the main file until a
    checkpoint, so copying the file alone silently loses them."""
    source = make_database(tmp_path / "app.sqlite3")
    writer = sqlite3.connect(source)
    writer.execute("PRAGMA journal_mode=WAL")
    with writer:
        writer.execute("INSERT INTO note VALUES ('NOTE_in_wal')")
    try:
        assert (source.parent / f"{source.name}-wal").exists()

        copy = back_up(sqlite_config(source), tmp_path / "copy")
    finally:
        writer.close()

    assert rows_in(copy.database, "note") == 4


@pytest.mark.pure
def test_sqlite_default_target_lands_next_to_the_base(tmp_path: Path):
    source = make_database(tmp_path / "app.sqlite3")

    copy = back_up(sqlite_config(source))

    assert copy.target.parent == tmp_path / "backup"
    assert copy.target.name.startswith("app.sqlite3.")
    assert copy.target.is_dir()
    assert default_target(sqlite_config(source)).parent == tmp_path / "backup"


@pytest.mark.pure
def test_refuses_to_overwrite_an_existing_file(tmp_path: Path):
    source = make_database(tmp_path / "app.sqlite3")
    occupied = tmp_path / "copy"
    occupied.write_text("do not lose me")

    with pytest.raises(BackupRefused) as refusal:
        back_up(sqlite_config(source), occupied)

    assert occupied.read_text() == "do not lose me"
    assert "already exists" in str(refusal.value)


@pytest.mark.pure
def test_refuses_a_missing_database(tmp_path: Path):
    with pytest.raises(BackupRefused) as refusal:
        back_up(sqlite_config(tmp_path / "nothing.sqlite3"), tmp_path / "copy")

    assert "not found" in str(refusal.value)
    assert not (tmp_path / "copy").exists()


@pytest.mark.pure
def test_refuses_an_in_memory_base(tmp_path: Path):
    with pytest.raises(BackupRefused) as refusal:
        back_up(sqlite_config(Path(":memory:"), tmp_path / "storage"), tmp_path / "copy")

    assert ":memory:" in str(refusal.value)
    assert not (tmp_path / "copy").exists()


# ── stored files ─────────────────────────────────────────────────────────────

@pytest.mark.pure
def test_the_stored_files_are_kept_beside_the_database_as_links(tmp_path: Path):
    """A link is a snapshot because stored bytes never change in place — and a second copy of the
    same files costs no space."""
    source = make_database(tmp_path / "app.sqlite3")
    root = tmp_path / "storage"
    first = stored(root, "public/AB/CD/ABCDEF0123.png", b"png bytes")
    stored(root, "private/12/34/1234567890", b"secret")

    copy = back_up(sqlite_config(source, root), tmp_path / "copy")

    kept = copy.target / STORAGE_DIR_NAME / "public/AB/CD/ABCDEF0123.png"
    assert kept.read_bytes() == b"png bytes"
    assert kept.stat().st_ino == first.stat().st_ino
    assert (copy.target / STORAGE_DIR_NAME / "private/12/34/1234567890").read_bytes() == b"secret"
    assert (copy.storage.files, copy.storage.linked, copy.storage.copied) == (2, 2, 0)
    assert copy.storage.size == len(b"png bytes") + len(b"secret")


@pytest.mark.pure
def test_a_file_the_cleanup_removes_later_stays_in_the_copy(tmp_path: Path):
    source = make_database(tmp_path / "app.sqlite3")
    root = tmp_path / "storage"
    original = stored(root, "public/AB/CD/ABCDEF0123.txt", b"kept")

    copy = back_up(sqlite_config(source, root), tmp_path / "copy")
    original.unlink()

    assert (copy.target / STORAGE_DIR_NAME / "public/AB/CD/ABCDEF0123.txt").read_bytes() == b"kept"


@pytest.mark.pure
def test_half_written_temporaries_are_not_in_the_copy(tmp_path: Path):
    source = make_database(tmp_path / "app.sqlite3")
    root = tmp_path / "storage"
    stored(root, "public/AB/CD/ABCDEF0123.txt", b"whole")
    stored(root, "public/AB/CD/.ABCDEF0124.txt.0f0f0f0f.part", b"half")

    copy = back_up(sqlite_config(source, root), tmp_path / "copy")

    folder = copy.target / STORAGE_DIR_NAME / "public/AB/CD"
    assert sorted(path.name for path in folder.iterdir()) == ["ABCDEF0123.txt"]
    assert copy.storage.files == 1


@pytest.mark.pure
def test_where_no_link_can_be_made_the_file_is_copied(tmp_path: Path, monkeypatch):
    """A copy on another disk: `link` answers EXDEV, and the bytes travel as a copy."""
    source = make_database(tmp_path / "app.sqlite3")
    root = tmp_path / "storage"
    original = stored(root, "public/AB/CD/ABCDEF0123.txt", b"across disks")

    def no_links(source, target):
        raise OSError(errno.EXDEV, "Invalid cross-device link")

    monkeypatch.setattr(backup_module.os, "link", no_links)

    copy = back_up(sqlite_config(source, root), tmp_path / "copy")

    kept = copy.target / STORAGE_DIR_NAME / "public/AB/CD/ABCDEF0123.txt"
    assert kept.read_bytes() == b"across disks"
    assert kept.stat().st_ino != original.stat().st_ino
    assert (copy.storage.linked, copy.storage.copied) == (0, 1)


@pytest.mark.pure
def test_a_file_that_vanishes_midway_is_not_counted(tmp_path: Path, monkeypatch):
    source = make_database(tmp_path / "app.sqlite3")
    root = tmp_path / "storage"
    stored(root, "public/AB/CD/ABCDEF0123.txt", b"stays")
    stored(root, "public/AB/CD/ABCDEF0124.txt", b"purged meanwhile")
    real_link = os.link

    def cleanup_wins(source, target):
        if str(source).endswith("ABCDEF0124.txt"):
            raise FileNotFoundError(errno.ENOENT, "No such file or directory", str(source))
        real_link(source, target)

    monkeypatch.setattr(backup_module.os, "link", cleanup_wins)

    copy = back_up(sqlite_config(source, root), tmp_path / "copy")

    assert copy.storage.files == 1
    assert not (copy.target / STORAGE_DIR_NAME / "public/AB/CD/ABCDEF0124.txt").exists()


@pytest.mark.pure
def test_a_symbolic_link_is_not_followed_out_of_the_tree(tmp_path: Path):
    source = make_database(tmp_path / "app.sqlite3")
    root = tmp_path / "storage"
    stored(root, "public/AB/CD/ABCDEF0123.txt", b"inside")
    outside = tmp_path / "outside.txt"
    outside.write_text("not ours")
    (root / "public" / "pointer").symlink_to(outside)

    copy = back_up(sqlite_config(source, root), tmp_path / "copy")

    assert not (copy.target / STORAGE_DIR_NAME / "public" / "pointer").exists()
    assert copy.storage.skipped == 1
    assert "1 symbolic link(s) left out" in copy.describe()


@pytest.mark.pure
def test_no_storage_root_means_no_files_to_keep(tmp_path: Path):
    source = make_database(tmp_path / "app.sqlite3")

    copy = back_up(sqlite_config(source, tmp_path / "never-made"), tmp_path / "copy")

    assert copy.storage is None
    assert not (copy.target / STORAGE_DIR_NAME).exists()
    assert not (copy.target / INVENTORY_NAME).exists()
    assert json.loads((copy.target / MANIFEST_NAME).read_text())["storage"] is None
    assert "does not exist — no stored files to keep" in copy.describe()


@pytest.mark.pure
def test_the_manifest_describes_the_copy_and_is_written_last(tmp_path: Path, monkeypatch):
    source = make_database(tmp_path / "app.sqlite3")
    root = tmp_path / "storage"
    stored(root, "public/AB/CD/ABCDEF0123.txt", b"12345")
    seen_at_snapshot: list[bool] = []
    seen_at_inventory: list[bool] = []
    real_snapshot = backup_module.snapshot_tree
    real_inventory = backup_module.write_inventory

    def watching(source_root, target):
        seen_at_snapshot.append((target.parent / MANIFEST_NAME).exists())
        return real_snapshot(source_root, target)

    def watching_inventory(directory, files):
        seen_at_inventory.append((directory / MANIFEST_NAME).exists())
        return real_inventory(directory, files)

    monkeypatch.setattr(backup_module, "snapshot_tree", watching)
    monkeypatch.setattr(backup_module, "write_inventory", watching_inventory)

    copy = back_up(sqlite_config(source, root), tmp_path / "copy")

    manifest = json.loads((copy.target / MANIFEST_NAME).read_text())
    inventory = (copy.target / INVENTORY_NAME).read_bytes()
    assert seen_at_snapshot == [False]
    assert seen_at_inventory == [False]
    assert manifest["format"] == 1
    assert manifest["provider"] == "sqlite"
    assert manifest["database"] == "app.sqlite3"
    assert manifest["revisions"] == list(REVISIONS)
    assert manifest["storage"] == {
        "source": str(root),
        "files": 1,
        "bytes": 5,
        "inventory": INVENTORY_NAME,
        "inventory_sha256": hashlib.sha256(inventory).hexdigest(),
    }
    assert json.loads(inventory) == {"public/AB/CD/ABCDEF0123.txt": 5}
    assert manifest["made_by"] == "manual"


@pytest.mark.pure
def test_the_inventory_lists_exactly_what_the_snapshot_took(tmp_path: Path, monkeypatch):
    """A temporary, a symbolic link and a file the cleanup removed midway are not in the copy, so
    they are not in its inventory either — or a whole copy would fail its own check."""
    source = make_database(tmp_path / "app.sqlite3")
    root = tmp_path / "storage"
    stored(root, "public/AB/CD/ABCDEF0123.txt", b"kept")
    stored(root, "private/12/34/1234567890", b"also kept")
    stored(root, "public/AB/CD/.ABCDEF0124.txt.0f0f0f0f.part", b"half")
    stored(root, "public/AB/CD/ABCDEF0125.txt", b"purged meanwhile")
    (root / "public" / "pointer").symlink_to(tmp_path / "app.sqlite3")
    real_link = os.link

    def cleanup_wins(origin, target):
        if str(origin).endswith("ABCDEF0125.txt"):
            raise FileNotFoundError(errno.ENOENT, "No such file or directory", str(origin))
        real_link(origin, target)

    monkeypatch.setattr(backup_module.os, "link", cleanup_wins)

    copy = back_up(sqlite_config(source, root), tmp_path / "copy")

    assert json.loads((copy.target / INVENTORY_NAME).read_text()) == {
        "private/12/34/1234567890": len(b"also kept"),
        "public/AB/CD/ABCDEF0123.txt": len(b"kept"),
    }


@pytest.mark.pure
def test_the_manifest_says_the_update_took_its_copy(tmp_path: Path):
    """Only the update's own copies are ever pruned; the field is what tells them apart."""
    source = make_database(tmp_path / "app.sqlite3")

    copy = back_up(sqlite_config(source), tmp_path / "copy", made_by="update")

    assert json.loads((copy.target / MANIFEST_NAME).read_text())["made_by"] == "update"
    assert "(made by update)" in copy.describe()


@pytest.mark.pure
def test_an_unknown_author_is_refused_before_anything_is_written(tmp_path: Path):
    source = make_database(tmp_path / "app.sqlite3")

    with pytest.raises(BackupRefused):
        back_up(sqlite_config(source), tmp_path / "copy", made_by="cron")

    assert not (tmp_path / "copy").exists()


@pytest.mark.pure
def test_the_database_is_copied_before_the_files(tmp_path: Path, monkeypatch):
    """The order the consistency argument rests on (module docstring of `src/core/backup.py`)."""
    source = make_database(tmp_path / "app.sqlite3")
    root = tmp_path / "storage"
    stored(root, "public/AB/CD/ABCDEF0123.txt", b"x")
    order: list[str] = []
    real_sqlite, real_snapshot = backup_module._back_up_sqlite, backup_module.snapshot_tree
    monkeypatch.setattr(
        backup_module,
        "_back_up_sqlite",
        lambda config, target: order.append("database") or real_sqlite(config, target),
    )
    monkeypatch.setattr(
        backup_module,
        "snapshot_tree",
        lambda source_root, target: order.append("files") or real_snapshot(source_root, target),
    )

    back_up(sqlite_config(source, root), tmp_path / "copy")

    assert order == ["database", "files"]


@pytest.mark.pure
def test_a_failed_snapshot_leaves_no_half_copy_behind(tmp_path: Path, monkeypatch):
    source = make_database(tmp_path / "app.sqlite3")
    root = tmp_path / "storage"
    stored(root, "public/AB/CD/ABCDEF0123.txt", b"x")

    def disk_full(source_root, target):
        target.mkdir()
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(backup_module, "snapshot_tree", disk_full)

    with pytest.raises(BackupRefused) as refusal:
        back_up(sqlite_config(source, root), tmp_path / "copy")

    assert "No space left on device" in str(refusal.value)
    assert not (tmp_path / "copy").exists()
    assert (root / "public/AB/CD/ABCDEF0123.txt").read_bytes() == b"x"


@pytest.mark.pure
@pytest.mark.skipif(os.geteuid() == 0, reason="root reads a folder whatever its mode")
def test_a_folder_that_cannot_be_read_refuses_the_copy(tmp_path: Path):
    """Skipping it would leave its files out of the copy and out of its inventory alike — a copy
    that passes every check while missing them."""
    source = make_database(tmp_path / "app.sqlite3")
    root = tmp_path / "storage"
    stored(root, "public/AB/CD/ABCDEF0123.txt", b"x")
    stored(root, "private/12/34/1234567890", b"hidden")
    locked = root / "private" / "12"
    locked.chmod(0o000)
    try:
        with pytest.raises(BackupRefused) as refusal:
            back_up(sqlite_config(source, root), tmp_path / "copy")
    finally:
        locked.chmod(0o755)

    assert "could not be copied" in str(refusal.value)
    assert not (tmp_path / "copy").exists()


@pytest.mark.pure
def test_a_file_purged_while_it_is_copied_across_disks_leaves_nothing_behind(
    tmp_path: Path, monkeypatch
):
    """The original vanishes after its bytes were copied: the copy keeps neither the bytes nor an
    inventory entry, so it still matches its inventory."""
    source = make_database(tmp_path / "app.sqlite3")
    root = tmp_path / "storage"
    stored(root, "public/AB/CD/ABCDEF0123.txt", b"stays")
    doomed = stored(root, "public/AB/CD/ABCDEF0124.txt", b"purged mid-copy")
    real_copy = backup_module.shutil.copy2

    def no_links(origin, target):
        raise OSError(errno.EXDEV, "Invalid cross-device link")

    def purged_after_copying(origin, target):
        real_copy(origin, target)
        if Path(origin) == doomed:
            doomed.unlink()

    monkeypatch.setattr(backup_module.os, "link", no_links)
    monkeypatch.setattr(backup_module.shutil, "copy2", purged_after_copying)

    copy = back_up(sqlite_config(source, root), tmp_path / "copy")

    folder = copy.target / STORAGE_DIR_NAME / "public/AB/CD"
    assert sorted(path.name for path in folder.iterdir()) == ["ABCDEF0123.txt"]
    assert json.loads((copy.target / INVENTORY_NAME).read_text()) == {
        "public/AB/CD/ABCDEF0123.txt": len(b"stays")
    }


@pytest.mark.pure
def test_refuses_a_copy_inside_the_storage_root_it_copies(tmp_path: Path):
    """The walk would descend into the copy it is writing."""
    source = make_database(tmp_path / "app.sqlite3")
    root = tmp_path / "storage"
    stored(root, "public/AB/CD/ABCDEF0123.txt", b"x")

    with pytest.raises(BackupRefused) as refusal:
        back_up(sqlite_config(source, root), root / "backup" / "copy")

    assert "inside the storage root" in str(refusal.value)
    assert not (root / "backup").exists()


@pytest.mark.pure
def test_the_command_reports_a_refusal_on_stderr_and_exits_nonzero(capsys):
    """The suite itself runs on `DB_PATH=:memory:` — a refusal is exactly the right answer."""
    assert backup_command() == 1
    assert "error:" in capsys.readouterr().err


@pytest.mark.pure
def test_the_command_prints_where_the_copy_went(tmp_path: Path, capsys, monkeypatch):
    source = make_database(tmp_path / "app.sqlite3")
    monkeypatch.setenv("DB_PROVIDER", "sqlite")
    monkeypatch.setenv("DB_PATH", str(source))
    monkeypatch.setenv("STORAGE_PATH", str(tmp_path / "storage"))
    stored(tmp_path / "storage", "public/AB/CD/ABCDEF0123.txt", b"x")

    assert backup_command(str(tmp_path / "copy")) == 0
    printed = capsys.readouterr().out
    assert str(tmp_path / "copy") in printed
    assert "integrity_check: ok" in printed
    assert ", ".join(REVISIONS) in printed
    assert "1 file(s)" in printed


# ── refusals and interruptions leave nothing behind ─────────────────────────

@pytest.fixture
def nested(tmp_path: Path) -> Iterator[Callable[[Path], Path]]:
    """Makes a chain of one-letter folders under a root, deeper than `shutil.rmtree` recurses
    and every path still well under PATH_MAX; answers the deepest folder. Built a level at a
    time — `mkdir(parents=True)` recurses as well. The test's folder goes afterwards: pytest
    clears its old temp folders with `shutil.rmtree`, which would choke on the chain."""

    def make(root: Path) -> Path:
        folder = root
        folder.mkdir(parents=True, exist_ok=True)
        for _ in range(sys.getrecursionlimit() + 200):
            folder = folder / "d"
            folder.mkdir()
        return folder

    yield make
    remove_tree(tmp_path, ignore_errors=True)


@contextmanager
def deadline(seconds: int = 5) -> Iterator[None]:
    """Fails the test instead of hanging it: reading a FIFO waits for a writer forever."""

    def expired(signum, frame):
        raise TimeoutError(f"still waiting after {seconds} s")

    previous = signal.signal(signal.SIGALRM, expired)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


@pytest.mark.pure
def test_a_refused_copy_leaves_no_folder_it_made(tmp_path: Path):
    config = sqlite_config(tmp_path / "install" / "app.sqlite3")

    with pytest.raises(BackupRefused, match="database file not found"):
        back_up(config, tmp_path / "copies" / "of today" / "copy")
    with pytest.raises(BackupRefused, match="database file not found"):
        back_up(config)

    assert list(tmp_path.iterdir()) == []


@pytest.mark.pure
def test_a_base_that_is_no_database_is_refused_not_crashed_on(tmp_path: Path):
    source = tmp_path / "app.sqlite3"
    source.write_bytes(b"not a database at all, just bytes " * 200)

    with pytest.raises(BackupRefused) as refusal:
        back_up(sqlite_config(source), tmp_path / "copy")

    assert "file is not a database" in str(refusal.value)
    assert not (tmp_path / "copy").exists()


@pytest.mark.pure
def test_a_manifest_the_disk_has_no_room_for_is_a_refusal(tmp_path: Path, monkeypatch):
    source = make_database(tmp_path / "app.sqlite3")
    stored(tmp_path / "storage", "public/AB/CD/ABCDEF0123.txt", b"x")

    def disk_full(directory, files):
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(backup_module, "write_inventory", disk_full)

    with pytest.raises(BackupRefused) as refusal:
        back_up(sqlite_config(source), tmp_path / "copy")

    assert "No space left on device" in str(refusal.value)
    assert not (tmp_path / "copy").exists()


@pytest.mark.pure
def test_a_failed_copy_of_a_tree_nested_past_the_recursion_limit_goes_whole(
    tmp_path: Path, monkeypatch, nested
):
    source = make_database(tmp_path / "app.sqlite3")
    root = tmp_path / "storage"
    (nested(root / "public") / "DEEP.txt").write_bytes(b"deep")

    def disk_full(directory, files):
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(backup_module, "write_inventory", disk_full)

    with pytest.raises(BackupRefused):
        back_up(sqlite_config(source, root), tmp_path / "copy")

    assert not (tmp_path / "copy").exists()


@pytest.mark.pure
def test_ctrl_c_while_copying_leaves_nothing_and_exits_1(tmp_path: Path, monkeypatch, capsys):
    source = make_database(tmp_path / "app.sqlite3")
    monkeypatch.setenv("DB_PROVIDER", "sqlite")
    monkeypatch.setenv("DB_PATH", str(source))
    monkeypatch.setenv("STORAGE_PATH", str(tmp_path / "storage"))
    stored(tmp_path / "storage", "public/AB/CD/ABCDEF0123.txt", b"x")
    real_snapshot = backup_module.snapshot_tree

    def interrupted(source_root, target):
        real_snapshot(source_root, target)
        raise KeyboardInterrupt

    monkeypatch.setattr(backup_module, "snapshot_tree", interrupted)

    assert backup_command(str(tmp_path / "copies" / "copy")) == 1

    assert "interrupted" in capsys.readouterr().err
    assert not (tmp_path / "copies").exists()


@pytest.mark.pure
@pytest.mark.skipif(
    threading.current_thread() is not threading.main_thread(),
    reason="signal handlers belong to the main thread",
)
def test_a_command_hears_the_first_ctrl_c_and_ignores_the_rest():
    """After the first press the command cleans up and reports; a second must not cut that short,
    nor its exit after it. A press that got through is caught here rather than left to stop the
    whole test run, and the handler of the run is put back by hand."""
    handler_before = signal.getsignal(signal.SIGINT)
    got_through: list[int] = []
    try:
        with first_ctrl_c_only():
            with pytest.raises(KeyboardInterrupt):
                signal.raise_signal(signal.SIGINT)
            for press in range(3):
                try:
                    signal.raise_signal(signal.SIGINT)
                except KeyboardInterrupt:
                    got_through.append(press)
        handler_after = signal.getsignal(signal.SIGINT)
    finally:
        signal.signal(signal.SIGINT, handler_before)

    assert got_through == []
    assert handler_after is signal.SIG_IGN


@pytest.mark.pure
def test_a_command_never_pressed_gets_its_handler_back():
    handler_before = signal.getsignal(signal.SIGINT)

    with first_ctrl_c_only():
        pass

    assert signal.getsignal(signal.SIGINT) is handler_before


# ── postgres ─────────────────────────────────────────────────────────────────

def fake_tool(directory: Path, name: str, body: str) -> None:
    script = directory / name
    script.write_text(f"#!{sys.executable}\nimport json, os, sys\n{body}")
    script.chmod(0o755)


def pg_client(
    tmp_path: Path,
    monkeypatch,
    *,
    dump_succeeds=True,
    listing_succeeds=True,
    unreadable_marked: str | None = None,
) -> Path:
    """A `pg_dump`/`pg_restore` pair on PATH that records how it was called.
    ``unreadable_marked`` — `pg_restore --list` fails only on an archive whose path holds it."""
    binaries = tmp_path / "bin"
    binaries.mkdir()
    record = tmp_path / "calls.json"
    dump_body = (
        f"record = {str(record)!r}\n"
        "argv = sys.argv[1:]\n"
        "json.dump({'argv': argv, 'password': os.environ.get('PGPASSWORD')}, open(record, 'w'))\n"
        + (
            "target = argv[argv.index('--file') + 1]\n"
            "open(target, 'w').write('PGDMP fake archive')\n"
            if dump_succeeds
            else "sys.stderr.write('connection refused')\nsys.exit(1)\n"
        )
    )
    unreadable = "sys.stderr.write('input file appears to be a text format dump')\nsys.exit(1)\n"
    listing_body = (
        "print(';     Archive created at 2026-09-12')\n"
        "print('215; 1259 16384 TABLE public research urb')\n"
        "print('216; 1259 16385 TABLE public note urb')\n"
        if listing_succeeds
        else unreadable
    )
    if unreadable_marked is not None:
        listing_body = (
            f"if {unreadable_marked!r} in sys.argv[-1]:\n"
            + "".join(f"    {line}\n" for line in unreadable.splitlines())
            + listing_body
        )
    fake_tool(binaries, "pg_dump", dump_body)
    fake_tool(binaries, "pg_restore", listing_body)
    monkeypatch.setenv("PATH", f"{binaries}:{Path(sys.executable).parent}")
    return record


@pytest.mark.pure
def test_postgres_dump_is_custom_format_and_verified_by_pg_restore(tmp_path: Path, monkeypatch):
    record = pg_client(tmp_path, monkeypatch)
    target = tmp_path / "copy"

    copy = back_up(postgres_config(storage_path=str(tmp_path / "storage")), target)

    called = json.loads(record.read_text())
    assert "--format=custom" in called["argv"]
    assert called["argv"][called["argv"].index("--file") + 1] == str(target / "research.dump")
    assert copy.database == target / "research.dump"
    assert json.loads((target / MANIFEST_NAME).read_text())["provider"] == "postgres"
    assert called["argv"][:8] == [
        "--host", "127.0.0.1", "--port", "1", "--username", "urb", "--dbname", "research",
    ]
    assert copy.verification == "pg_restore --list: ok, 2 object(s) in the archive"
    assert copy.source == "urb@127.0.0.1:1/research"


@pytest.mark.pure
def test_postgres_password_travels_in_the_environment_not_in_argv(tmp_path: Path, monkeypatch):
    record = pg_client(tmp_path, monkeypatch)

    back_up(postgres_config(storage_path=str(tmp_path / "storage")), tmp_path / "copy")

    called = json.loads(record.read_text())
    assert called["password"] == "s3cret"
    assert not any("s3cret" in argument for argument in called["argv"])


@pytest.mark.pure
def test_postgres_revisions_degrade_to_nothing_when_the_base_is_unreachable(
    tmp_path: Path, monkeypatch
):
    """Diagnostics never decide: a base that will not tell its heads is still worth copying."""
    pg_client(tmp_path, monkeypatch)

    copy = back_up(postgres_config(storage_path=str(tmp_path / "storage")), tmp_path / "copy")

    assert copy.revisions == ()
    assert "(none read)" in copy.describe()


@pytest.mark.pure
def test_a_failed_dump_leaves_no_half_archive_behind(tmp_path: Path, monkeypatch):
    pg_client(tmp_path, monkeypatch, dump_succeeds=False)
    target = tmp_path / "copy"

    with pytest.raises(BackupRefused) as refusal:
        back_up(postgres_config(storage_path=str(tmp_path / "storage")), target)

    assert target.exists() is False
    assert "pg_dump failed" in str(refusal.value)


@pytest.mark.pure
def test_an_archive_pg_restore_cannot_read_is_not_a_backup(tmp_path: Path, monkeypatch):
    pg_client(tmp_path, monkeypatch, listing_succeeds=False)

    with pytest.raises(BackupRefused) as refusal:
        back_up(postgres_config(storage_path=str(tmp_path / "storage")), tmp_path / "copy")

    assert f"pg_restore cannot read {tmp_path / 'copy' / 'research.dump'}" in str(refusal.value)
    assert not (tmp_path / "copy").exists()


@pytest.mark.pure
def test_a_dump_pg_restore_cannot_read_is_removed_and_named(tmp_path: Path, monkeypatch):
    """`restore` dumps the current base aside through the same call, outside any copy directory:
    a dump left there would outlive a refusal that says nothing was changed."""
    pg_client(tmp_path, monkeypatch, listing_succeeds=False)
    target = tmp_path / "research.before-restore.20261025-120000.dump"

    with pytest.raises(BackupRefused) as refusal:
        dump_postgres(postgres_config(), target)

    assert f"pg_restore cannot read {target}" in str(refusal.value)
    assert not target.exists()


@pytest.mark.pure
def test_missing_client_binaries_are_a_refusal_not_a_skipped_copy(tmp_path: Path, monkeypatch):
    """The one thing that must never happen: an update migrating because the copy was «optional»."""
    empty = tmp_path / "bin"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))

    with pytest.raises(BackupRefused) as refusal:
        back_up(postgres_config(storage_path=str(tmp_path / "storage")), tmp_path / "copy")

    assert "pg_dump" in str(refusal.value)
    assert POSTGRES_CLIENT_PACKAGE in str(refusal.value)


@pytest.mark.pure
def test_postgres_default_target_sits_under_the_runtime_root():
    target = default_target(postgres_config())

    assert target.parent.name == "backup"
    assert target.name.startswith("research.")
    assert not target.name.endswith(".dump")
