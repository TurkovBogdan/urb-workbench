"""Owners and marks under concurrent writers, on PostgreSQL — where the writers really overlap.

SQLite takes one writer at a time (``BEGIN IMMEDIATE``), so nothing below can interleave there.
PostgreSQL runs the transactions side by side, and a file is consistent only while "some owner is
live" and "the file is not marked" stay one fact. Every transaction that changes the owners or the
mark of a file therefore takes the file's row first (``SELECT … FOR UPDATE``): the writers of one
file queue on it, and each one reads the owners the previous one committed.

Each scenario runs many rounds: one interleaving that loses the race is enough to fail.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest

from src.core.database import get_engine
from src.modules.core_storage.dto import Owner
from src.modules.core_storage.services.cleanup import purge_expired
from src.modules.core_storage.services.files import file_delete, file_get_many, file_path
from src.modules.core_storage.services.ownership import (
    file_attach,
    file_owners,
    file_release,
    owner_release_everywhere,
)
from src.modules.core_storage.services.registration import file_register_bytes

pytestmark = pytest.mark.heavy

ROUNDS = 30


async def _inconsistent(code: str) -> str | None:
    """What is wrong with the file, or ``None``: a live owner and a mark never go together, and
    neither do no live owner and no mark."""
    stored = (await file_get_many([code], include_deleted=True)).get(code)
    live = await file_owners(code)
    if stored is None:
        return "held, its row gone" if live else None
    if live and stored.deleted_at is not None:
        return "held but marked"
    if not live and stored.deleted_at is None:
        return "nobody holds it, no mark"
    return None


async def test_this_tier_really_runs_on_postgres(db):
    assert get_engine().dialect.name == "postgresql"


async def test_two_last_owners_leaving_at_once_mark_the_file(db):
    faults = []
    for n in range(ROUNDS):
        first, second = Owner("TASK", f"A{n}"), Owner("CODEX", f"B{n}")
        stored = await file_register_bytes(f"two-{n}".encode(), store="public", owner=first)
        await file_attach(stored.code, second, filename="")

        await asyncio.gather(file_release(stored.code, first), file_release(stored.code, second))

        faults.append(await _inconsistent(stored.code))
    assert [fault for fault in faults if fault] == []


async def test_a_release_racing_an_attach_never_hides_a_held_file(db):
    faults = []
    for n in range(ROUNDS):
        leaving, coming = Owner("TASK", f"A{n}"), Owner("CODEX", f"B{n}")
        stored = await file_register_bytes(f"attach-{n}".encode(), store="public", owner=leaving)

        await asyncio.gather(
            file_release(stored.code, leaving), file_attach(stored.code, coming, filename="")
        )

        faults.append(await _inconsistent(stored.code))
    assert [fault for fault in faults if fault] == []


async def test_a_release_racing_a_registration_of_the_same_bytes_never_hides_it(db):
    faults = []
    for n in range(ROUNDS):
        leaving, coming = Owner("TASK", f"A{n}"), Owner("TASK", f"B{n}")
        data = f"dedup-{n}".encode()
        stored = await file_register_bytes(data, store="public", owner=leaving)

        _, again = await asyncio.gather(
            file_release(stored.code, leaving),
            file_register_bytes(data, store="public", owner=coming),
        )

        assert again.code == stored.code
        faults.append(await _inconsistent(stored.code))
    assert [fault for fault in faults if fault] == []


async def test_an_entity_released_everywhere_racing_an_attach_never_hides_a_held_file(db):
    faults = []
    for n in range(ROUNDS):
        purged, coming = Owner("TASK", f"A{n}"), Owner("CODEX", f"B{n}")
        stored = await file_register_bytes(f"everywhere-{n}".encode(), store="public", owner=purged)

        await asyncio.gather(
            owner_release_everywhere(purged.type, purged.id),
            file_attach(stored.code, coming, filename=""),
        )

        faults.append(await _inconsistent(stored.code))
    assert [fault for fault in faults if fault] == []


async def test_the_managers_deletion_racing_an_attach_leaves_one_consistent_state(db):
    faults = []
    for n in range(ROUNDS):
        first, coming = Owner("TASK", f"A{n}"), Owner("CODEX", f"B{n}")
        stored = await file_register_bytes(f"delete-{n}".encode(), store="public", owner=first)

        await asyncio.gather(file_delete(stored.code), file_attach(stored.code, coming, filename=""))

        faults.append(await _inconsistent(stored.code))
    assert [fault for fault in faults if fault] == []


async def test_a_registration_racing_the_cleanup_of_the_same_bytes_is_stored(db):
    """The cleanup removing a file and a registration bringing its bytes back: the registration
    either revives the file before the cleanup reaches it, or stores the bytes anew after — never
    a refusal, never an owner on a removed row, never a row without its bytes."""
    for n in range(ROUNDS):
        first, coming = Owner("TASK", f"A{n}"), Owner("TASK", f"B{n}")
        data = f"cleanup-{n}".encode()
        stored = await file_register_bytes(data, store="public", owner=first)
        await file_release(stored.code, first)

        _, again = await asyncio.gather(
            purge_expired(timedelta(0), 0), file_register_bytes(data, store="public", owner=coming)
        )

        assert await _inconsistent(again.code) is None
        assert [place.owner for place in await file_owners(again.code)] == [coming]
        assert file_path(again).read_bytes() == data
