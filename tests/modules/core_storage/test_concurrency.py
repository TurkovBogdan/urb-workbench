"""Concurrent registrations and releases, on a file database.

In-memory SQLite shares one connection between every session, so it has one transaction state and
cannot show concurrency at all; a file in ``tmp_path`` gives every session its own connection and
the real ``BEGIN IMMEDIATE`` lock.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from src.core.config import Config
from src.core.database import close_database, init_database
from src.modules.core_storage.dto import Owner
from src.modules.core_storage.services import files, ownership
from src.modules.core_storage.services.registration import file_register_bytes

from .conftest import names_of, owners_of, temp_leftovers

pytestmark = pytest.mark.db


@pytest.fixture
async def file_db(tmp_path: Path, storage):
    config = Config(db_provider="sqlite", db_path=str(tmp_path / "storage.sqlite3"))
    engine = await init_database(config)
    from src.core.database.runtime import Base
    import src.modules.core_storage.models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield storage
    finally:
        await close_database()


async def test_parallel_registrations_of_one_content_make_one_file(file_db):
    owners = [Owner("task", f"T{index:09d}") for index in range(6)]

    stored = await asyncio.gather(
        *(
            file_register_bytes(b"same content", store="public", owner=owner, filename=f"{owner.id}.TXT")
            for owner in owners
        )
    )

    assert len({item.code for item in stored}) == 1
    assert sorted(await owners_of(stored[0].code), key=lambda o: o.id) == owners
    assert await names_of(stored[0].code) == {owner: (owner.id, ".TXT") for owner in owners}
    on_disk = sorted(p.name for p in file_db.store_dir("public").rglob("*") if p.is_file())
    assert on_disk == [files.file_path(stored[0]).name] == [f"{stored[0].code}.txt"]
    assert temp_leftovers(file_db) == []


async def test_parallel_registrations_of_different_contents_make_different_files(file_db):
    """Positive control for the test above: parallel registrations are not merged as such."""
    stored = await asyncio.gather(
        *(file_register_bytes(f"content {i}".encode(), store="public", owner=Owner("task", "T")) for i in range(6))
    )
    assert len({item.code for item in stored}) == 6


async def test_parallel_releases_of_the_last_owners_mark_the_file(file_db):
    """On SQLite the write lock serialises the releases, so the last one always sees no live
    owner. On PostgreSQL the same race is left to the cleanup task, which re-checks owners."""
    first, second = Owner("task", "A"), Owner("task", "B")
    stored = await file_register_bytes(b"shared", store="public", owner=first)
    await ownership.file_attach(stored.code, second)

    await asyncio.gather(
        ownership.file_release(stored.code, first), ownership.file_release(stored.code, second)
    )

    assert (await files.file_get(stored.code, include_deleted=True)).deleted_at is not None
