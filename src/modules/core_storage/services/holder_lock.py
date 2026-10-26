"""One holder's file operations, one at a time: a lock per owner entity, inside this process.

A consumer keeps a binding row next to every owner row of the storage, and writes the two in
separate transactions — the storage opens a write transaction of its own. Two operations of one
holder interleaved between those transactions break the pair: an attach checks "not bound",
a detach of the same file removes the row and releases the owner, the attach then writes its row
on a released owner. Holding ``holder_lock`` around each operation — check, storage, row; or
row, release — keeps the pair whole.

The lock lives in this process's memory. The backend is one process with the scheduler inside
it (``--backend --worker``), so every request and every scheduled task meets the same locks; a
second process writing the same database would not be serialised by them. ``src/app.py`` still
runs one — a separate ``--worker``, ``SERVER_PROCESSES > 1`` — and there the safety of the pair
rests elsewhere: a consumer's reconciliation releases only owners older than its grace period
(``held_by_type(…, taken_before=…)``), and an attach in flight in another process is never that
old. Two writes of one holder in two processes at the same moment are not covered.

A lock exists while someone holds or awaits it: the registry keeps weak references, and an idle
holder costs nothing.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterable
from contextlib import AsyncExitStack, asynccontextmanager
from weakref import WeakValueDictionary

_locks: WeakValueDictionary[tuple[str, str], asyncio.Lock] = WeakValueDictionary()


def _lock_of(owner_type: str, owner_id: str) -> asyncio.Lock:
    key = (owner_type, owner_id)
    lock = _locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _locks[key] = lock
    return lock


@asynccontextmanager
async def holder_lock(owner_type: str, owner_id: str) -> AsyncIterator[None]:
    """Hold the entity ``(owner_type, owner_id)`` for one file operation; not reentrant."""
    async with _lock_of(owner_type, owner_id):
        yield


@asynccontextmanager
async def holder_locks(owner_type: str, owner_ids: Iterable[str]) -> AsyncIterator[None]:
    """Hold several entities of one type — a deletion taking a branch at once. The order is
    sorted, so two such deletions over overlapping entities cannot wait on each other."""
    async with AsyncExitStack() as stack:
        for owner_id in sorted(set(owner_ids)):
            await stack.enter_async_context(holder_lock(owner_type, owner_id))
        yield


def held_locks() -> int:
    """How many locks exist now — for a test that the registry does not grow."""
    return len(_locks)


__all__ = ["held_locks", "holder_lock", "holder_locks"]
