"""CRUD of ``CoreStorageUploadRequest``: open, find, claim, give back, complete, and the cleanup.

**Claiming is one statement.** ``UPDATE … SET claimed_at = now WHERE token_hash = … AND
claimed_at IS NULL AND expires_at > now`` in a write transaction: on PostgreSQL the row's lock
queues two claims, and the second sees ``claimed_at`` set; on SQLite the writers are one at a
time (``BEGIN IMMEDIATE``). Of two PUTs on one token exactly one gets the request; the other finds
none — the same answer as a token never opened.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import delete, select, update

from src.core.database import session_scope, write_scope
from src.modules.core_storage_upload.models import CoreStorageUploadRequest


async def request_create(
    *,
    token_hash: str,
    holder: str,
    workspace_code: str,
    filename: str,
    payload: dict[str, Any],
    expires_at: datetime,
) -> CoreStorageUploadRequest:
    async with write_scope() as s:
        row = CoreStorageUploadRequest(
            token_hash=token_hash,
            holder=holder,
            workspace_code=workspace_code,
            filename=filename,
            payload=payload,
            expires_at=expires_at,
        )
        s.add(row)
        await s.flush()
        await s.refresh(row)
    return row


async def request_open(token_hash: str, now: datetime) -> CoreStorageUploadRequest | None:
    """The request under this hash, if it is open: not expired and no upload of it in flight."""
    stmt = select(CoreStorageUploadRequest).where(
        CoreStorageUploadRequest.token_hash == token_hash,
        CoreStorageUploadRequest.claimed_at.is_(None),
        CoreStorageUploadRequest.expires_at > now,
    )
    async with session_scope() as s:
        return (await s.execute(stmt)).scalar_one_or_none()


async def request_claim(token_hash: str, now: datetime) -> bool:
    """Take the request for one upload; ``False`` — it is not open any more."""
    stmt = (
        update(CoreStorageUploadRequest)
        .where(
            CoreStorageUploadRequest.token_hash == token_hash,
            CoreStorageUploadRequest.claimed_at.is_(None),
            CoreStorageUploadRequest.expires_at > now,
        )
        .values(claimed_at=now)
    )
    async with write_scope() as s:
        result = await s.execute(stmt)
    return (result.rowcount or 0) == 1


async def request_give_back(token_hash: str) -> None:
    """The upload failed before the binding: the request is open again until it expires."""
    stmt = (
        update(CoreStorageUploadRequest)
        .where(CoreStorageUploadRequest.token_hash == token_hash)
        .values(claimed_at=None)
    )
    async with write_scope() as s:
        await s.execute(stmt)


async def request_delete(token_hash: str) -> None:
    async with write_scope() as s:
        await s.execute(
            delete(CoreStorageUploadRequest).where(
                CoreStorageUploadRequest.token_hash == token_hash
            )
        )


async def request_purge_expired(now: datetime) -> int:
    """Delete the requests whose time is over; the number deleted."""
    async with write_scope() as s:
        result = await s.execute(
            delete(CoreStorageUploadRequest).where(CoreStorageUploadRequest.expires_at <= now)
        )
    return result.rowcount or 0


__all__ = [
    "request_claim",
    "request_create",
    "request_delete",
    "request_give_back",
    "request_open",
    "request_purge_expired",
]
