"""Every write to a file's owners or mark takes the file's row first.

The concurrent proof is PostgreSQL's (``test_races_postgres.py``): SQLite runs one writer at a time
and cannot interleave them. Here — that the lock is the first thing each write does, before any
owner row is read or changed, and that it is ``FOR UPDATE`` where the dialect has one.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql, sqlite

from src.modules.core_storage.crud import file as file_crud
from src.modules.core_storage.crud import file_owner as owner_crud
from src.modules.core_storage.dto import Owner
from src.modules.core_storage.models import CoreStorageFile
from src.modules.core_storage.services.cleanup import purge_expired
from src.modules.core_storage.services.files import file_delete
from src.modules.core_storage.services.ownership import (
    file_attach,
    file_release,
    owner_release_everywhere,
)
from src.modules.core_storage.services.registration import file_register_bytes

TASK = Owner("TASK", "7DB4F6E0DE")
NOTE = Owner("CODEX", "BD98065ED2")

_LOCKS = ("file_lock", "files_lock", "file_find_by_sha256(lock)")


@pytest.mark.pure
def test_the_lock_is_for_update_on_postgres_and_plain_on_sqlite():
    query = (
        select(CoreStorageFile).where(CoreStorageFile.code == "AB12000001").with_for_update()
    )

    assert str(query.compile(dialect=postgresql.dialect())).endswith("FOR UPDATE")
    assert "FOR UPDATE" not in str(query.compile(dialect=sqlite.dialect()))


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """The storage's CRUD calls in order, the lock ones named apart."""
    seen: list[str] = []

    def spy(module, name):
        real = getattr(module, name)

        async def recorded(*args, **kwargs):
            seen.append(f"{name}(lock)" if kwargs.get("lock") else name)
            return await real(*args, **kwargs)

        monkeypatch.setattr(module, name, recorded)

    for name in (
        "file_lock",
        "files_lock",
        "file_find_by_sha256",
        "file_get",
        "file_unmark",
        "file_mark_deleted",
        "file_delete_row",
    ):
        spy(file_crud, name)
    for name in (
        "owner_get",
        "owner_take",
        "owner_release",
        "owner_release_all",
        "owner_live_files",
        "owner_has_live",
        "owner_mark_all_of_file",
        "owner_delete_released",
    ):
        spy(owner_crud, name)
    return seen


def _first_write_step_is_a_lock(seen: list[str]) -> bool:
    """Reading which files an entity holds may come before the lock; nothing else may."""
    steps = [step for step in seen if step != "owner_live_files"]
    return bool(steps) and steps[0] in _LOCKS


@pytest.mark.db
async def test_attach_takes_the_row_first(db, calls):
    stored = await file_register_bytes(b"a", store="public", owner=TASK)
    calls.clear()

    await file_attach(stored.code, NOTE)

    assert _first_write_step_is_a_lock(calls), calls


@pytest.mark.db
async def test_release_takes_the_row_first(db, calls):
    stored = await file_register_bytes(b"r", store="public", owner=TASK)
    calls.clear()

    await file_release(stored.code, TASK)

    assert _first_write_step_is_a_lock(calls), calls


@pytest.mark.db
async def test_release_everywhere_locks_every_file_before_its_owners_change(db, calls):
    for data in (b"e1", b"e2"):
        await file_register_bytes(data, store="public", owner=TASK)
    calls.clear()

    await owner_release_everywhere(TASK.type, TASK.id)

    assert calls.index("files_lock") < calls.index("owner_release_all"), calls
    assert _first_write_step_is_a_lock(calls), calls


@pytest.mark.db
async def test_the_managers_deletion_takes_the_row_first(db, calls):
    stored = await file_register_bytes(b"d", store="public", owner=TASK)
    calls.clear()

    await file_delete(stored.code)

    assert _first_write_step_is_a_lock(calls), calls


@pytest.mark.db
async def test_a_registration_of_stored_bytes_takes_the_row_first(db, calls):
    await file_register_bytes(b"same", store="public", owner=TASK)
    calls.clear()

    await file_register_bytes(b"same", store="public", owner=NOTE)

    assert _first_write_step_is_a_lock(calls), calls


@pytest.mark.db
async def test_the_cleanup_takes_each_row_first(db, calls):
    stored = await file_register_bytes(b"c", store="public", owner=TASK)
    await file_release(stored.code, TASK)
    calls.clear()

    report = await purge_expired(timedelta(0), 0)

    assert report.purged == 1
    assert _first_write_step_is_a_lock(calls), calls
