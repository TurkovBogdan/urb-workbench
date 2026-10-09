"""CRUD for :class:`CoreLockRow`."""

from __future__ import annotations

from sqlalchemy import select

from src.core.database import session_scope
from src.core.locks import CoreLockRow


async def get(key: str) -> CoreLockRow | None:
    """Read a lock row by key. ``None`` means the lock is free."""
    stmt = select(CoreLockRow).where(CoreLockRow.key == key)
    async with session_scope() as s:
        return (await s.execute(stmt)).scalar_one_or_none()


__all__ = ["get"]
