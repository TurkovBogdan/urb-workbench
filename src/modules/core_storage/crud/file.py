"""CRUD of ``CoreStorageFile``.

Reads open a session of their own unless given one; writes take the caller's ``session`` — the
services put a file and its owner into one transaction. Reads hide soft-deleted rows unless
``include_deleted`` is passed: for the rest of the code a deleted file does not exist. The dedup
lookup is the exception — a soft-deleted file keeps its ``(store, sha256)`` key.

**The file's row is its writers' lock.** Whether a file is marked follows from whether a live owner
is left, and on PostgreSQL two transactions read the owners side by side: a release that sees none
marks the file while an attach it cannot see yet unmarks it — the file ends held but marked, or
nobody's and unmarked. So every transaction that changes the owners or the mark of a file takes
its row first (``file_lock``, ``file_find_by_sha256(lock=True)``: ``SELECT … FOR UPDATE``), and
the writers of one file queue there. SQLite renders no ``FOR UPDATE``: its writers are one at a
time already (``BEGIN IMMEDIATE``).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from datetime import datetime

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import session_scope
from src.modules.core_storage.models import CoreStorageFile

_CONTENT_KEY = ["store", "sha256"]


@asynccontextmanager
async def _reading(session: AsyncSession | None) -> AsyncIterator[AsyncSession]:
    """The caller's session when given, else a read scope of our own."""
    if session is not None:
        yield session
        return
    async with session_scope() as s:
        yield s


def _insert_for(session: AsyncSession):
    """The dialect's ``INSERT … ON CONFLICT``: one construct, a different module per dialect."""
    return sqlite_insert if session.bind.dialect.name == "sqlite" else pg_insert


async def file_get(
    code: str, *, include_deleted: bool = False, session: AsyncSession | None = None
) -> CoreStorageFile | None:
    query = select(CoreStorageFile).where(CoreStorageFile.code == code)
    if not include_deleted:
        query = query.where(CoreStorageFile.deleted_at.is_(None))
    async with _reading(session) as s:
        return (await s.execute(query)).scalar_one_or_none()


async def file_lock(code: str, *, session: AsyncSession) -> CoreStorageFile | None:
    """Take the file's row for this transaction — soft-deleted too; ``None`` — no such row.

    The first statement of every write to the file's owners or mark. A row removed by the
    transaction this one waited for is not found: its file is gone.
    """
    return await _locked(select(CoreStorageFile).where(CoreStorageFile.code == code), session)


async def files_lock(codes: Sequence[str], *, session: AsyncSession) -> list[CoreStorageFile]:
    """``file_lock`` of several files, in code order — two such writers cannot wait on each other."""
    if not codes:
        return []
    query = (
        select(CoreStorageFile)
        .where(CoreStorageFile.code.in_(sorted(set(codes))))
        .order_by(CoreStorageFile.code)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return list((await session.execute(query)).scalars())


async def _locked(query, session: AsyncSession) -> CoreStorageFile | None:
    # ``populate_existing``: a row this session read before the lock is read again under it.
    locked = query.with_for_update().execution_options(populate_existing=True)
    return (await session.execute(locked)).scalar_one_or_none()


async def file_get_many(
    codes: Sequence[str], *, include_deleted: bool = False
) -> list[CoreStorageFile]:
    if not codes:
        return []
    query = select(CoreStorageFile).where(CoreStorageFile.code.in_(list(codes)))
    if not include_deleted:
        query = query.where(CoreStorageFile.deleted_at.is_(None))
    async with session_scope() as s:
        return list((await s.execute(query)).scalars())


async def file_find_by_sha256(
    store: str, sha256: str, *, session: AsyncSession | None = None, lock: bool = False
) -> CoreStorageFile | None:
    """The file with these bytes in this store — soft-deleted too: it still holds the key.

    ``lock`` — take its row, as ``file_lock`` does, in the caller's ``session``.
    """
    query = select(CoreStorageFile).where(
        CoreStorageFile.store == store, CoreStorageFile.sha256 == sha256
    )
    if lock:
        if session is None:
            raise ValueError("A row is locked in the caller's transaction — pass its session")
        return await _locked(query, session)
    async with _reading(session) as s:
        return (await s.execute(query)).scalar_one_or_none()


async def file_insert(
    *,
    code: str,
    store: str,
    sha256: str,
    type: str,
    size: int,
    mime: str,
    extension: str,
    session: AsyncSession,
) -> CoreStorageFile | None:
    """Insert a file row; ``None`` — the same bytes in the same store got there first.

    The dedup lookup and this insert are not atomic, so two registrations of one content can
    both arrive here; the unique key lets one win, and the other gets ``None``. A taken
    ``code`` is a different event — a coincidence of random values — and comes out as the
    driver's ``IntegrityError`` for the caller to tell apart.
    """
    insert = _insert_for(session)
    statement = (
        insert(CoreStorageFile)
        .values(
            code=code,
            store=store,
            sha256=sha256,
            type=type,
            size=size,
            mime=mime,
            extension=extension,
        )
        .on_conflict_do_nothing(index_elements=_CONTENT_KEY)
        .returning(CoreStorageFile.code)
    )
    inserted = (await session.execute(statement)).scalar_one_or_none()
    if inserted is None:
        return None
    return await file_get(inserted, session=session)


async def file_mark_deleted(code: str, at: datetime, *, session: AsyncSession) -> None:
    """Soft-delete a live file; an already marked one keeps its first mark."""
    await session.execute(
        update(CoreStorageFile)
        .where(CoreStorageFile.code == code, CoreStorageFile.deleted_at.is_(None))
        .values(deleted_at=at)
    )


async def file_unmark(code: str, *, session: AsyncSession) -> None:
    await session.execute(
        update(CoreStorageFile).where(CoreStorageFile.code == code).values(deleted_at=None)
    )


async def file_delete_row(code: str, *, session: AsyncSession) -> None:
    await session.execute(delete(CoreStorageFile).where(CoreStorageFile.code == code))


async def file_expired(before: datetime, limit: int) -> list[CoreStorageFile]:
    """Files marked before ``before``, the oldest mark first; ``limit`` 0 — all of them."""
    query = (
        select(CoreStorageFile)
        .where(CoreStorageFile.deleted_at.is_not(None), CoreStorageFile.deleted_at <= before)
        .order_by(CoreStorageFile.deleted_at, CoreStorageFile.code)
    )
    if limit > 0:
        query = query.limit(limit)
    async with session_scope() as s:
        return list((await s.execute(query)).scalars())


async def file_page(after: str, limit: int) -> list[CoreStorageFile]:
    """Every file — soft-deleted too — with a code past ``after``, in code order, ``limit`` at most."""
    query = (
        select(CoreStorageFile)
        .where(CoreStorageFile.code > after)
        .order_by(CoreStorageFile.code)
        .limit(limit)
    )
    async with session_scope() as s:
        return list((await s.execute(query)).scalars())


async def file_stores_in_use() -> list[str]:
    async with session_scope() as s:
        result = await s.execute(select(CoreStorageFile.store).distinct())
        return sorted(result.scalars())


__all__ = [
    "file_delete_row",
    "file_expired",
    "file_find_by_sha256",
    "file_get",
    "file_get_many",
    "file_insert",
    "file_lock",
    "file_mark_deleted",
    "file_page",
    "files_lock",
    "file_stores_in_use",
    "file_unmark",
]
