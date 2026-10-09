"""Distributed locks: the ``CoreLockRow`` ORM row, the CRUD operations, ``CoreLock``.

One file, because all three layers concern one entity and are used nowhere
separately except by each other.

Public:
- ``CoreLockRow`` — ORM model of the ``core_locks`` table (for selects in code).
- ``CoreLock`` — high-level wrapper: ``acquire`` / ``release`` / ``extend``.
- ``release_for_owners(owners)`` — bulk cleanup, used by the runner and the
  ticker to auto-release locks held by finished/zombie tasks.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import String, delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column
from ulid import ULID

from src.core.database import session_scope, write_scope
from src.core.database.runtime import Base
from src.core.database.types import timestamp
from src.core.utils.date import utc_now


# ── ORM ─────────────────────────────────────────────────────────────────────

class CoreLockRow(Base):
    """A ``core_locks`` row — one active lock per ``key``."""

    __tablename__ = "core_locks"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    owner: Mapped[str] = mapped_column(String(128), index=True)
    acquired_at: Mapped[datetime] = mapped_column(timestamp())
    expires_at: Mapped[datetime] = mapped_column(timestamp(), index=True)


# ── CRUD ────────────────────────────────────────────────────────────────────

def _insert_for(session: AsyncSession):
    dialect = session.bind.dialect.name if session.bind else "postgresql"
    return sqlite_insert if dialect == "sqlite" else pg_insert


async def _acquire(
    session: AsyncSession, *, key: str, owner: str, ttl_seconds: int
) -> bool:
    """INSERT, or take over an expired lock. True = the row is now ours."""
    insert = _insert_for(session)
    now = utc_now()
    expires = now + timedelta(seconds=ttl_seconds)
    stmt = insert(CoreLockRow).values(
        key=key, owner=owner, acquired_at=now, expires_at=expires
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["key"],
        set_={
            "owner": stmt.excluded.owner,
            "acquired_at": stmt.excluded.acquired_at,
            "expires_at": stmt.excluded.expires_at,
        },
        where=(CoreLockRow.expires_at < stmt.excluded.acquired_at),
    ).returning(CoreLockRow.owner)
    result = await session.execute(stmt)
    row = result.first()
    return row is not None and row[0] == owner


async def _release(
    session: AsyncSession, *, key: str, owner: str
) -> bool:
    """DELETE WHERE key=? AND owner=?. True = a row was actually deleted."""
    result = await session.execute(
        delete(CoreLockRow).where(
            CoreLockRow.key == key, CoreLockRow.owner == owner
        )
    )
    return result.rowcount > 0


async def _is_owner(
    session: AsyncSession, *, key: str, owner: str
) -> bool:
    """True if the lock exists AND belongs to ``owner``."""
    stmt = select(CoreLockRow.owner).where(CoreLockRow.key == key)
    current = (await session.execute(stmt)).scalar_one_or_none()
    return current == owner


async def _extend(
    session: AsyncSession, *, key: str, owner: str, ttl_seconds: int
) -> bool:
    """Extend the TTL if we are still the owner. False — the lock was lost."""
    expires = utc_now() + timedelta(seconds=ttl_seconds)
    stmt = (
        update(CoreLockRow)
        .where(CoreLockRow.key == key, CoreLockRow.owner == owner)
        .values(expires_at=expires)
    )
    result = await session.execute(stmt)
    return result.rowcount > 0


async def release_for_owners(owners: list[str]) -> None:
    """DELETE WHERE owner IN (...). Bulk cleanup for reaping zombie tasks."""
    if not owners:
        return
    async with write_scope() as s:
        await s.execute(
            delete(CoreLockRow).where(CoreLockRow.owner.in_(owners))
        )


# ── High-level ``CoreLock`` ─────────────────────────────────────────────────

class CoreLock:
    """A held distributed lock. Created through ``CoreLock.acquire``."""

    def __init__(self, key: str, owner: str) -> None:
        self.key = key
        self.owner = owner

    @classmethod
    async def acquire(
        cls, key: str, ttl: int, *, owner: str | None = None
    ) -> "CoreLock | None":
        """Take the lock. ``CoreLock`` if acquired, otherwise ``None``.

        ``ttl`` — TTL in seconds. ``owner`` is optional: when omitted, a ULID is
        generated (an anonymous single-use owner).
        """
        if owner is None:
            owner = str(ULID())
        async with write_scope() as s:
            ok = await _acquire(s, key=key, owner=owner, ttl_seconds=ttl)
        return cls(key, owner) if ok else None

    async def release(self) -> bool:
        """Release the lock. True = actually released (we were still the owner)."""
        async with write_scope() as s:
            return await _release(s, key=self.key, owner=self.owner)

    async def is_owner(self) -> bool:
        """Fencing check: is the lock still ours, or has someone taken it over?"""
        async with session_scope() as s:
            return await _is_owner(s, key=self.key, owner=self.owner)

    async def extend(self, ttl: int) -> bool:
        """Extend the TTL (seconds). Ownership is checked first, then UPDATE."""
        if not await self.is_owner():
            return False
        async with write_scope() as s:
            return await _extend(
                s, key=self.key, owner=self.owner, ttl_seconds=ttl
            )

    @classmethod
    async def force_release(cls, key: str) -> bool:
        """Release the lock by key without checking the owner. True = actually released."""
        async with write_scope() as s:
            result = await s.execute(
                delete(CoreLockRow).where(CoreLockRow.key == key)
            )
            return result.rowcount > 0


__all__ = ["CoreLock", "CoreLockRow", "release_for_owners"]
