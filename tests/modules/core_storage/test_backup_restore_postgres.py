"""`app.py backup` and `app.py restore` on a real PostgreSQL: the dump, the empty schema it is
restored into, and the stored files beside it.

`heavy`: the base is the disposable database the root fixture makes from ``TEST_PG_DSN``. The
copy also needs `pg_dump` and `pg_restore` on ``PATH`` — the test skips without them rather than
pretending; a wrapper running them from the server's image does.
"""

from __future__ import annotations

import asyncio
import hashlib
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select, text

from src.core import maintenance
from src.core import restore as restore_module
from src.core.backup import back_up
from src.core.config import Config
from src.core.database import close_database, get_engine, init_database, session_scope
from src.core.restore import RestoreRefused, restore, verify_copy
from src.modules.core_storage import layout as layout_module
from src.modules.core_storage.dto import Owner
from src.modules.core_storage.layout import StorageLayout
from src.modules.core_storage.models import CoreStorageFile
from src.modules.core_storage.services import ownership
from src.modules.core_storage.services.registration import file_register_bytes

from .conftest import STORES

pytestmark = [
    pytest.mark.heavy,
    pytest.mark.skipif(
        shutil.which("pg_dump") is None or shutil.which("pg_restore") is None,
        reason="pg_dump and pg_restore are needed on PATH (postgresql-client)",
    ),
]


@pytest.fixture
def install(config: Config, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Config:
    assert config.db_provider == "postgres"
    installed = config.model_copy(update={"storage_path": str(tmp_path / "storage")})
    layout = StorageLayout(installed.storage_root, tmp_path / "tmp", STORES)
    layout.ensure_dirs()
    monkeypatch.setattr(layout_module, "_layout", layout)
    monkeypatch.setattr(maintenance, "project_root", lambda: tmp_path / "checkout")
    monkeypatch.setattr(restore_module, "resolve_runtime_root", lambda: tmp_path / "runtime")
    monkeypatch.setattr(
        restore_module,
        "plan_live_stop",
        lambda: SimpleNamespace(is_empty=True, foreign=(), strays=(), describe=lambda: ""),
    )
    return installed


async def open_base(config: Config) -> None:
    engine = await init_database(config)
    from src.core.database.runtime import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def rows() -> dict[str, CoreStorageFile]:
    async with session_scope() as s:
        return {row.code: row for row in (await s.execute(select(CoreStorageFile))).scalars()}


async def tables() -> set[str]:
    async with get_engine().connect() as conn:
        found = await conn.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        )
        return set(found.scalars())


async def test_a_wiped_base_and_storage_come_back_whole(install: Config, tmp_path: Path):
    await open_base(install)
    try:
        picture = b"\x89PNG\r\n\x1a\n" + b"x" * 999
        await file_register_bytes(picture, store="public", owner=Owner("task", "T1"))
        shared = await file_register_bytes(b"shared", store="private", owner=Owner("task", "T2"))
        await ownership.file_attach(shared.code, Owner("note", "N1"))
        expected = {code: (row.sha256, row.size) for code, row in (await rows()).items()}
        copy = await asyncio.to_thread(back_up, install, tmp_path / "copy")

        # What happens after the copy and must be gone after the restore: a table a migration made,
        # a file registered later, the stored files wiped.
        async with get_engine().begin() as conn:
            await conn.execute(text("CREATE TABLE made_after_the_copy (id integer)"))
        await file_register_bytes(b"later", store="public", owner=Owner("task", "T3"))
    finally:
        await close_database()
    shutil.rmtree(install.storage_root)

    report = await asyncio.to_thread(restore, install, copy.target)

    await open_base(install)
    try:
        restored = await rows()
        assert {code: (row.sha256, row.size) for code, row in restored.items()} == expected
        for row in restored.values():
            path = layout_module.get_layout().file_path(row.store, row.code, row.extension)
            assert hashlib.sha256(path.read_bytes()).hexdigest() == row.sha256
        assert "made_after_the_copy" not in await tables()
    finally:
        await close_database()
    aside = Path(next(line for line in report.aside if line.endswith(".dump")))
    assert aside.is_file() and aside.stat().st_size > 0


async def test_a_copy_that_lost_a_stored_file_leaves_the_base_untouched(
    install: Config, tmp_path: Path
):
    """The check runs before the schema is dropped and before the base is dumped aside: a refusal
    on PostgreSQL changes the base no more than on SQLite."""
    await open_base(install)
    try:
        lost = await file_register_bytes(b"lost", store="public", owner=Owner("task", "T1"))
        copy = await asyncio.to_thread(back_up, install, tmp_path / "copy")
        async with get_engine().begin() as conn:
            await conn.execute(text("CREATE TABLE made_after_the_copy (id integer)"))
        live = set(await rows())
    finally:
        await close_database()
    whole = await asyncio.to_thread(verify_copy, install, copy.target)
    live_path = layout_module.get_layout().file_path(lost.store, lost.code, lost.extension)
    (copy.target / "storage" / live_path.relative_to(install.storage_root)).unlink()
    files_before = sorted(str(path) for path in install.storage_root.rglob("*"))
    beside_before = sorted(install.storage_root.parent.glob("storage*"))

    broken = await asyncio.to_thread(verify_copy, install, copy.target)
    with pytest.raises(RestoreRefused) as refusal:
        await asyncio.to_thread(restore, install, copy.target)

    assert whole.whole and "pg_restore --list: ok" in whole.database
    assert not broken.whole
    assert lost.code in str(refusal.value)
    assert not (tmp_path / "runtime").exists()
    assert sorted(str(path) for path in install.storage_root.rglob("*")) == files_before
    assert sorted(install.storage_root.parent.glob("storage*")) == beside_before
    assert live_path.read_bytes() == b"lost"
    await open_base(install)
    try:
        assert "made_after_the_copy" in await tables()
        assert set(await rows()) == live
    finally:
        await close_database()


async def copy_then_write(install: Config, tmp_path: Path) -> tuple[Path, set[str]]:
    """A copy of a base with one stored file, then a table made after it; answers the copy and
    the base's tables as they stand — what a refusal must leave."""
    await open_base(install)
    try:
        await file_register_bytes(b"kept", store="public", owner=Owner("task", "T1"))
        copy = await asyncio.to_thread(back_up, install, tmp_path / "copy")
        async with get_engine().begin() as conn:
            await conn.execute(text("CREATE TABLE made_after_the_copy (id integer)"))
        return copy.target, await tables()
    finally:
        await close_database()


async def tables_now(install: Config) -> set[str]:
    await open_base(install)
    try:
        return await tables()
    finally:
        await close_database()


async def test_a_swap_undone_after_the_dump_aside_leaves_no_dump(
    install: Config, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """The base was dumped aside for real, and nothing reached it: the dump goes with the
    refusal, the folder made for it too."""
    copy, before = await copy_then_write(install, tmp_path)
    files_before = sorted(str(path) for path in install.storage_root.rglob("*"))
    real_rename = restore_module.os.rename

    def refuse_the_tree(source, target):
        if Path(source).name.startswith("storage.restoring."):
            raise PermissionError(13, "Permission denied", str(target))
        real_rename(source, target)

    monkeypatch.setattr(restore_module.os, "rename", refuse_the_tree)

    with pytest.raises(RestoreRefused, match="was undone"):
        await asyncio.to_thread(restore, install, copy)

    assert not (tmp_path / "runtime").exists()
    assert sorted(str(path) for path in install.storage_root.rglob("*")) == files_before
    assert sorted(path.name for path in install.storage_root.parent.glob("storage*")) == [
        "storage"
    ]
    assert await tables_now(install) == before


async def test_a_reset_the_server_answers_with_an_error_rolls_back_whole(
    install: Config, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """What the refusal rests on, on a real server: the drop and the failing statement after it
    run as one implicit transaction, so the base keeps every table and the dump is a duplicate."""
    copy, before = await copy_then_write(install, tmp_path)
    monkeypatch.setattr(
        restore_module,
        "_RESET_SCHEMA",
        "DROP SCHEMA public CASCADE; CREATE SCHEMA public; SELECT no_such_function()",
    )

    with pytest.raises(RestoreRefused, match="no_such_function"):
        await asyncio.to_thread(restore, install, copy)

    assert await tables_now(install) == before
    assert "made_after_the_copy" in before
    assert not (tmp_path / "runtime").exists()
    assert sorted(path.name for path in install.storage_root.parent.glob("storage*")) == [
        "storage"
    ]
