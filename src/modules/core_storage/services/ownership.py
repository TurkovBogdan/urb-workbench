"""Ownership: take a file, release it, release an entity from everything it held.

Whether a file is still needed is the module's count, not the consumer's: the consumer releases
exactly the place it took the file out of, and when no live owner is left the file gets its
deletion mark in the same transaction. The cleanup task removes it after the configured term.

Each write takes the file's row first (``file_crud.file_lock``): the count of live owners and the
mark are one fact only while the writers of a file go one after another.
"""

from __future__ import annotations

from datetime import datetime

from src.core.database import write_scope
from src.core.utils.date import utc_now
from src.modules.core_storage.codes import normalize_code, parse_code
from src.modules.core_storage.crud import file as file_crud
from src.modules.core_storage.crud import file_owner as owner_crud
from src.modules.core_storage.dto import FileOwner, HeldFile, Owner, file_owner
from src.modules.core_storage.errors import FileNotFound
from src.modules.core_storage.names import split_filename


async def file_attach(code: str, owner: Owner, *, filename: str | None = None) -> None:
    """Take a stored file; a soft-deleted one can be taken back until the cleanup removes it.

    ``filename`` — the name the file takes in this place, written to the owner's row, a live one
    too: attaching by code under a name is a deliberate rename (``''`` clears it). ``None`` keeps the name of a row the owner already had; a new row takes the name
    of the earliest owner row of the file that has one, released rows too — a file attached
    from elsewhere keeps the name it came in under — else ``''``.

    That copy looks at every owner of the file: the module knows no boundary between them. A
    consumer that keeps its owners apart — one workspace must not see a name brought in another
    — passes ``filename`` itself.
    """
    code = normalize_code(code)
    name = None if filename is None else split_filename(filename)
    async with write_scope() as s:
        if await file_crud.file_lock(code, session=s) is None:
            raise FileNotFound(code)
        if name is None and await owner_crud.owner_get(code, owner, session=s) is None:
            name = await owner_crud.owner_earliest_name(code, session=s)
        await owner_crud.owner_take(
            code, owner, name=name, session=s, rename_live=filename is not None
        )
        await file_crud.file_unmark(code, session=s)


async def file_release(code: str, owner: Owner) -> bool:
    """Release one place of one owner; the last live owner leaving marks the file deleted.

    ``False`` — the owner held no live place under this key, and nothing changed. A consumer
    that got its key wrong learns it here instead of leaving the file held for good.
    """
    code = normalize_code(code)
    async with write_scope() as s:
        if await file_crud.file_lock(code, session=s) is None:
            raise FileNotFound(code)
        now = utc_now()
        if not await owner_crud.owner_release(code, owner, now, session=s):
            return False
        if not await owner_crud.owner_has_live(code, session=s):
            await file_crud.file_mark_deleted(code, now, session=s)
        return True


async def owner_release_everywhere(owner_type: str, owner_id: str) -> int:
    """Release an entity from every file and place it held — for a consumer deleting it.

    Returns the number of released owner rows.

    The files are locked before their owners change, all at once and in code order. A file the
    entity took after that read — by the consumer's own lock, never while it deletes the entity —
    is locked the moment it shows up, before its count is asked.
    """
    async with write_scope() as s:
        locked = {
            row.code
            for row in await file_crud.files_lock(
                await owner_crud.owner_live_files(owner_type, owner_id, session=s), session=s
            )
        }
        now = utc_now()
        released = await owner_crud.owner_release_all(owner_type, owner_id, now, session=s)
        await file_crud.files_lock(sorted(set(released) - locked), session=s)
        for code in sorted(set(released)):
            if not await owner_crud.owner_has_live(code, session=s):
                await file_crud.file_mark_deleted(code, now, session=s)
    return len(released)


async def file_owners(code: str, *, include_deleted: bool = False) -> list[FileOwner]:
    """Who holds the file, and under which name each place keeps it.

    No file under the code — or no well-formed code — holds nobody.
    """
    parsed = parse_code(code)
    if parsed is None:
        return []
    rows = await owner_crud.owner_list(parsed, include_deleted=include_deleted)
    return [file_owner(row) for row in rows]


async def file_owners_many(
    codes: list[str], *, include_deleted: bool = False
) -> dict[str, list[FileOwner]]:
    """``file_owners`` of several files in one query — for a consumer reading a batch.

    A code that no one holds, or that is not well-formed, is absent from the answer.
    """
    parsed = [code for code in map(parse_code, codes) if code is not None]
    owners: dict[str, list[FileOwner]] = {}
    for row in await owner_crud.owner_list_many(parsed, include_deleted=include_deleted):
        owners.setdefault(row.file_code, []).append(file_owner(row))
    return owners


async def held_by_type(
    owner_type: str, *, taken_before: datetime | None = None
) -> list[HeldFile]:
    """Every live place of one owner type — for a consumer reconciling its bindings with what the
    storage counts. Released places are not here: they hold nothing.

    ``taken_before`` — only the places that took their file before that moment (a revived place
    took it when it was revived). A consumer looking for leftovers to release passes its grace
    period here: an attach in flight in another process has taken its place and not yet written
    its binding, and only its age tells it from a leftover — its holder lock is this process's.
    """
    return [
        HeldFile(
            file_code=row.file_code,
            owner=Owner(type=row.owner_type, id=row.owner_id, key=row.owner_key),
        )
        for row in await owner_crud.owner_list_live_of_type(owner_type, taken_before=taken_before)
    ]


__all__ = [
    "file_attach",
    "file_owners",
    "file_owners_many",
    "file_release",
    "held_by_type",
    "owner_release_everywhere",
]
