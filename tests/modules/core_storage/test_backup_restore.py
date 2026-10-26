"""The storage through `app.py backup` and `app.py restore`: a restored install has no file row
without its bytes.

Real folders and a file SQLite base: files registered through the services, the copy taken by
`src/core/backup.py`, the install wiped, the copy restored by `src/core/restore.py` — then every
row is read back against its bytes on disk, sha256 included. The stop plan and the maintenance
flag are kept off the live machine, as in `tests/core/test_restore.py`.
"""

from __future__ import annotations

import asyncio
import hashlib
import shutil
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from src.core import backup as backup_module
from src.core import maintenance
from src.core import restore as restore_module
from src.core.backup import STORAGE_DIR_NAME, back_up
from src.core.config import Config
from src.core.database import close_database, init_database, session_scope
from src.core.restore import RestoreRefused, restore, verify_copy
from src.core.utils.date import utc_now
from src.modules.core_storage import layout as layout_module
from src.modules.core_storage.dto import Owner
from src.modules.core_storage.layout import StorageLayout
from src.modules.core_storage.models import CoreStorageFile
from src.modules.core_storage.services import files, ownership
from src.modules.core_storage.services.cleanup import purge_expired
from src.modules.core_storage.services.registration import file_register_bytes

from .conftest import STORES, mark_deleted_at

pytestmark = pytest.mark.db


@pytest.fixture
def install(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Config:
    config = Config(
        db_provider="sqlite",
        db_path=str(tmp_path / "install" / "app.sqlite3"),
        storage_path=str(tmp_path / "install" / "storage"),
    )
    layout = StorageLayout(config.storage_root, tmp_path / "install" / "tmp", STORES)
    layout.ensure_dirs()
    monkeypatch.setattr(layout_module, "_layout", layout)
    monkeypatch.setattr(maintenance, "project_root", lambda: tmp_path / "checkout")
    monkeypatch.setattr(
        restore_module,
        "plan_live_stop",
        lambda: SimpleNamespace(is_empty=True, foreign=(), strays=(), describe=lambda: ""),
    )
    return config


async def open_base(config: Config) -> None:
    engine = await init_database(config)
    from src.core.database.runtime import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def rows() -> list[CoreStorageFile]:
    async with session_scope() as s:
        return list((await s.execute(select(CoreStorageFile))).scalars())


def bytes_of(row: CoreStorageFile) -> bytes | None:
    path = layout_module.get_layout().file_path(row.store, row.code, row.extension)
    return path.read_bytes() if path.is_file() else None


def wipe(config: Config) -> None:
    for sidecar in ("", "-wal", "-shm"):
        Path(f"{config.sqlite_file}{sidecar}").unlink(missing_ok=True)
    shutil.rmtree(config.storage_root)


async def test_after_restore_every_row_has_its_bytes(install: Config, tmp_path: Path):
    await open_base(install)
    try:
        picture = await file_register_bytes(
            b"\x89PNG\r\n\x1a\n" + b"p" * 4000, store="public", owner=Owner("task", "T1")
        )
        shared = await file_register_bytes(b"one content", store="public", owner=Owner("task", "T2"))
        await ownership.file_attach(shared.code, Owner("note", "N1"))
        await file_register_bytes(b"private bytes", store="private", owner=Owner("task", "T3"))
        released = await file_register_bytes(b"let go", store="public", owner=Owner("task", "T4"))
        await ownership.file_release(released.code, Owner("task", "T4"))

        copy = await asyncio.to_thread(back_up, install, tmp_path / "copy")
        expected = {row.code: (row.sha256, row.size, row.deleted_at is None) for row in await rows()}
    finally:
        await close_database()

    wipe(install)
    await asyncio.to_thread(restore, install, copy.target)

    await open_base(install)
    try:
        restored = await rows()
        assert {row.code: (row.sha256, row.size, row.deleted_at is None) for row in restored} == expected
        for row in restored:
            content = bytes_of(row)
            assert content is not None, f"row {row.code} has no bytes"
            assert hashlib.sha256(content).hexdigest() == row.sha256
            assert len(content) == row.size
        with await files.file_open(picture.code) as handle:
            assert handle.read().startswith(b"\x89PNG")
    finally:
        await close_database()


async def test_a_live_install_copied_between_two_writes_keeps_every_live_row_whole(
    install: Config, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """The order of the copy, checked against the writers it races: between the database copy
    and the snapshot of the files a new file is registered and a released one is purged. The copy
    then holds bytes no row of it points at — harmless — and a marked row whose bytes are gone,
    which the copy's own cleanup removes. Every live row has its bytes."""
    await open_base(install)
    loop = asyncio.get_running_loop()
    try:
        await file_register_bytes(b"held all along", store="public", owner=Owner("task", "T1"))
        doomed = await file_register_bytes(b"purged between", store="public", owner=Owner("task", "T2"))
        await ownership.file_release(doomed.code, Owner("task", "T2"))
        await mark_deleted_at(doomed.code, utc_now() - timedelta(days=30))
        late: list[str] = []

        async def write_between() -> None:
            between = await file_register_bytes(
                b"registered between", store="public", owner=Owner("task", "T3")
            )
            late.append(between.code)
            assert (await purge_expired(timedelta(hours=1), 0)).purged == 1

        real_snapshot = backup_module.snapshot_tree

        def snapshot_after_the_writes(source, target):
            asyncio.run_coroutine_threadsafe(write_between(), loop).result()
            return real_snapshot(source, target)

        monkeypatch.setattr(backup_module, "snapshot_tree", snapshot_after_the_writes)
        copy = await asyncio.to_thread(back_up, install, tmp_path / "copy")
    finally:
        await close_database()

    wipe(install)
    await asyncio.to_thread(restore, install, copy.target)

    await open_base(install)
    try:
        restored = {row.code: row for row in await rows()}
        assert late[0] not in restored
        assert any(path.name.startswith(late[0]) for path in (install.storage_root).rglob("*"))
        assert restored[doomed.code].deleted_at is not None
        assert bytes_of(restored[doomed.code]) is None
        for row in restored.values():
            if row.deleted_at is None:
                assert hashlib.sha256(bytes_of(row) or b"").hexdigest() == row.sha256
        assert (await purge_expired(timedelta(hours=1), 0)).purged == 1
        assert doomed.code not in {row.code for row in await rows()}
    finally:
        await close_database()


async def test_a_copy_that_lost_a_stored_file_is_not_restored(install: Config, tmp_path: Path):
    """The bytes of a registered file deleted from the copy by hand: restoring it would give a
    row without its bytes, so the restore refuses and the install keeps what it has."""
    await open_base(install)
    try:
        kept = await file_register_bytes(b"kept", store="public", owner=Owner("task", "T1"))
        lost = await file_register_bytes(
            b"lost from the copy", store="private", owner=Owner("task", "T2")
        )
        copy = await asyncio.to_thread(back_up, install, tmp_path / "copy")
        lost_path = files.file_path(lost)
        await file_register_bytes(b"after the copy", store="public", owner=Owner("task", "T3"))
        live = {row.code for row in await rows()}
    finally:
        await close_database()
    relative = lost_path.relative_to(install.storage_root)
    (copy.target / STORAGE_DIR_NAME / relative).unlink()

    verified = await asyncio.to_thread(verify_copy, install, copy.target)
    with pytest.raises(RestoreRefused) as refusal:
        await asyncio.to_thread(restore, install, copy.target)

    assert not verified.whole
    assert relative.as_posix() in verified.describe()
    assert relative.as_posix() in str(refusal.value)
    assert lost_path.read_bytes() == b"lost from the copy"
    await open_base(install)
    try:
        assert {row.code for row in await rows()} == live
        assert bytes_of(next(row for row in await rows() if row.code == kept.code)) == b"kept"
    finally:
        await close_database()


async def test_the_copy_of_the_files_is_the_storage_tree_as_it_lies(install: Config, tmp_path: Path):
    await open_base(install)
    try:
        stored = await file_register_bytes(b"tree", store="private", owner=Owner("task", "T1"))
        copy = await asyncio.to_thread(back_up, install, tmp_path / "copy")
    finally:
        await close_database()

    relative = files.file_path(stored).relative_to(install.storage_root)
    assert (copy.target / STORAGE_DIR_NAME / relative).read_bytes() == b"tree"
    assert sorted(path.name for path in (copy.target / STORAGE_DIR_NAME).iterdir()) == sorted(STORES)
