"""CRUD of ``CoreStorageFileOwner``: take, release, the names, and the questions the cleanup asks.

Writes run in the caller's ``session`` — taking a file is always part of a transaction that also
touches the file row. A released owner is a row with ``deleted_at``, not a removed row: the
cleanup task removes released owners together with the file they held.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import session_scope
from src.core.utils.date import utc_now
from src.modules.core_storage.dto import Owner
from src.modules.core_storage.models import CoreStorageFileOwner
from src.modules.core_storage.names import OriginalName


def _key(file_code: str, owner: Owner):
    return (
        CoreStorageFileOwner.file_code == file_code,
        CoreStorageFileOwner.owner_type == owner.type,
        CoreStorageFileOwner.owner_id == owner.id,
        CoreStorageFileOwner.owner_key == owner.key,
    )


async def owner_get(
    file_code: str, owner: Owner, *, session: AsyncSession
) -> CoreStorageFileOwner | None:
    """The owner's row for this file, released or live."""
    return (
        await session.execute(select(CoreStorageFileOwner).where(*_key(file_code, owner)))
    ).scalar_one_or_none()


async def owner_take(
    file_code: str,
    owner: Owner,
    *,
    name: OriginalName | None,
    session: AsyncSession,
    rename_live: bool = False,
) -> None:
    """Add the owner, or revive it if it was released.

    ``name`` — the name the owner brings the file under, written to a new row and to a revived
    one; ``None`` — it brings none: a new row gets ``''``, an existing one keeps the name it had.
    A live row keeps its name unless ``rename_live``: registering bytes a place already holds is
    an attempt its consumer refuses, and a refused attempt must leave the place as it found it.

    A revived row takes ``created_at`` anew: it is when the place took the file, and a
    reconciliation in another process tells an attach in flight from a leftover by that age.
    """
    row = await owner_get(file_code, owner, session=session)
    if row is None:
        kept = name or OriginalName(filename="", extension="")
        session.add(
            CoreStorageFileOwner(
                file_code=file_code,
                owner_type=owner.type,
                owner_id=owner.id,
                owner_key=owner.key,
                original_filename=kept.filename,
                original_extension=kept.extension,
            )
        )
        await session.flush()
        return
    if name is not None and (row.deleted_at is not None or rename_live):
        row.original_filename = name.filename
        row.original_extension = name.extension
    if row.deleted_at is not None:
        row.created_at = utc_now()
    row.deleted_at = None
    await session.flush()


async def owner_earliest_name(file_code: str, *, session: AsyncSession) -> OriginalName | None:
    """The name of the earliest owner row of the file that has one, released rows too.

    ``created_at`` keeps whole seconds, so rows taken in one second tie on it; the tie goes to the
    owner triple in plain order — ``owner_type``, ``owner_id``, ``owner_key`` — and never to the
    order the database happens to return.
    """
    row = (
        await session.execute(
            select(CoreStorageFileOwner)
            .where(
                CoreStorageFileOwner.file_code == file_code,
                or_(
                    CoreStorageFileOwner.original_filename != "",
                    CoreStorageFileOwner.original_extension != "",
                ),
            )
            .order_by(
                CoreStorageFileOwner.created_at,
                CoreStorageFileOwner.owner_type,
                CoreStorageFileOwner.owner_id,
                CoreStorageFileOwner.owner_key,
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    return OriginalName(filename=row.original_filename, extension=row.original_extension)


async def owner_release(
    file_code: str, owner: Owner, at: datetime, *, session: AsyncSession
) -> bool:
    """Mark a live owner released; ``False`` — no live owner with this key."""
    row = (
        await session.execute(
            select(CoreStorageFileOwner).where(
                *_key(file_code, owner), CoreStorageFileOwner.deleted_at.is_(None)
            )
        )
    ).scalar_one_or_none()
    if row is None:
        return False
    row.deleted_at = at
    await session.flush()
    return True


async def owner_release_all(
    owner_type: str, owner_id: str, at: datetime, *, session: AsyncSession
) -> list[str]:
    """Release the owner from every file and every place; the file code of each released row."""
    rows = (
        await session.execute(
            select(CoreStorageFileOwner).where(
                CoreStorageFileOwner.owner_type == owner_type,
                CoreStorageFileOwner.owner_id == owner_id,
                CoreStorageFileOwner.deleted_at.is_(None),
            )
        )
    ).scalars().all()
    for row in rows:
        row.deleted_at = at
    await session.flush()
    return [row.file_code for row in rows]


async def owner_live_files(owner_type: str, owner_id: str, *, session: AsyncSession) -> list[str]:
    """The files an entity holds a live place of — read before they are locked and released."""
    query = (
        select(CoreStorageFileOwner.file_code)
        .where(
            CoreStorageFileOwner.owner_type == owner_type,
            CoreStorageFileOwner.owner_id == owner_id,
            CoreStorageFileOwner.deleted_at.is_(None),
        )
        .distinct()
    )
    return list((await session.execute(query)).scalars())


async def owner_mark_all_of_file(file_code: str, at: datetime, *, session: AsyncSession) -> None:
    """One mark for every live owner of a file — the file manager's deletion."""
    rows = (
        await session.execute(
            select(CoreStorageFileOwner).where(
                CoreStorageFileOwner.file_code == file_code,
                CoreStorageFileOwner.deleted_at.is_(None),
            )
        )
    ).scalars().all()
    for row in rows:
        row.deleted_at = at
    await session.flush()


async def owner_has_live(file_code: str, *, session: AsyncSession) -> bool:
    query = select(
        exists().where(
            CoreStorageFileOwner.file_code == file_code,
            CoreStorageFileOwner.deleted_at.is_(None),
        )
    )
    return bool((await session.execute(query)).scalar())


async def owner_list(file_code: str, *, include_deleted: bool = False) -> list[CoreStorageFileOwner]:
    query = (
        select(CoreStorageFileOwner)
        .where(CoreStorageFileOwner.file_code == file_code)
        .order_by(
            CoreStorageFileOwner.owner_type,
            CoreStorageFileOwner.owner_id,
            CoreStorageFileOwner.owner_key,
        )
    )
    if not include_deleted:
        query = query.where(CoreStorageFileOwner.deleted_at.is_(None))
    async with session_scope() as s:
        return list((await s.execute(query)).scalars())


async def owner_list_many(
    file_codes: list[str], *, include_deleted: bool = False
) -> list[CoreStorageFileOwner]:
    """``owner_list`` of several files in one query, ordered by file, then as ``owner_list``."""
    if not file_codes:
        return []
    query = (
        select(CoreStorageFileOwner)
        .where(CoreStorageFileOwner.file_code.in_(file_codes))
        .order_by(
            CoreStorageFileOwner.file_code,
            CoreStorageFileOwner.owner_type,
            CoreStorageFileOwner.owner_id,
            CoreStorageFileOwner.owner_key,
        )
    )
    if not include_deleted:
        query = query.where(CoreStorageFileOwner.deleted_at.is_(None))
    async with session_scope() as s:
        return list((await s.execute(query)).scalars())


async def owner_list_live_of_type(
    owner_type: str, *, taken_before: datetime | None = None
) -> list[CoreStorageFileOwner]:
    """Every live owner row of one owner type, by file, then by owner; ``taken_before`` — only
    the rows that took their file before that moment."""
    query = (
        select(CoreStorageFileOwner)
        .where(
            CoreStorageFileOwner.owner_type == owner_type,
            CoreStorageFileOwner.deleted_at.is_(None),
        )
        .order_by(
            CoreStorageFileOwner.file_code,
            CoreStorageFileOwner.owner_id,
            CoreStorageFileOwner.owner_key,
        )
    )
    if taken_before is not None:
        query = query.where(CoreStorageFileOwner.created_at < taken_before)
    async with session_scope() as s:
        return list((await s.execute(query)).scalars())


async def owner_delete_released(file_code: str, *, session: AsyncSession) -> None:
    """Remove the released owners of a file — the cleanup's step before removing the file."""
    await session.execute(
        delete(CoreStorageFileOwner).where(
            CoreStorageFileOwner.file_code == file_code,
            CoreStorageFileOwner.deleted_at.is_not(None),
        )
    )


async def owner_delete_all(file_code: str, *, session: AsyncSession) -> None:
    """Remove every owner of a file — the rollback of a registration whose bytes did not land."""
    await session.execute(
        delete(CoreStorageFileOwner).where(CoreStorageFileOwner.file_code == file_code)
    )


__all__ = [
    "owner_delete_all",
    "owner_delete_released",
    "owner_earliest_name",
    "owner_get",
    "owner_has_live",
    "owner_list",
    "owner_list_live_of_type",
    "owner_list_many",
    "owner_live_files",
    "owner_mark_all_of_file",
    "owner_release",
    "owner_release_all",
    "owner_take",
]
