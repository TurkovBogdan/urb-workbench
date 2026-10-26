"""Getting a stored file — its data, its path, its bytes — and the file manager's deletion.

A soft-deleted file is absent by default; ``include_deleted=True`` reaches it until the cleanup
removes it, so a consumer can look into the bin before restoring.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from pathlib import Path
from typing import BinaryIO

from src.core.database import write_scope
from src.core.loggers import get_logger
from src.core.utils.date import utc_now
from src.modules.core_storage.codes import normalize_code, parse_code
from src.modules.core_storage.constants import LOG_CHANNEL
from src.modules.core_storage.crud import file as file_crud
from src.modules.core_storage.crud import file_owner as owner_crud
from src.modules.core_storage.dto import StoredFile, stored_file
from src.modules.core_storage.errors import FileNotFound
from src.modules.core_storage.layout import get_layout

_LOG = get_logger(LOG_CHANNEL)


async def file_get(code: str, *, include_deleted: bool = False) -> StoredFile:
    code = normalize_code(code)
    row = await file_crud.file_get(code, include_deleted=include_deleted)
    if row is None:
        raise FileNotFound(code)
    return stored_file(row)


async def file_get_many(
    codes: Sequence[str], *, include_deleted: bool = False
) -> dict[str, StoredFile]:
    """Files by code; a code with no file — or no well-formed code — is absent from the answer."""
    parsed = [code for code in map(parse_code, codes) if code is not None]
    rows = await file_crud.file_get_many(parsed, include_deleted=include_deleted)
    return {row.code: stored_file(row) for row in rows}


async def file_find_content(store: str, sha256: str) -> StoredFile | None:
    """The file holding these bytes in this store, a soft-deleted one too — it still holds the
    content's key, and registering the bytes would revive it. Read only: what a registration of
    the same content would answer with, asked before any write."""
    row = await file_crud.file_find_by_sha256(store, sha256.strip().lower())
    return stored_file(row) if row is not None else None


def file_path(file: StoredFile) -> Path:
    """The absolute path of the bytes. They are read-only: copy before changing."""
    return get_layout().file_path(file.store, file.code, file.extension)


async def file_open(code: str, *, include_deleted: bool = False) -> BinaryIO:
    """The file opened for reading; the caller closes it."""
    stored = await file_get(code, include_deleted=include_deleted)
    path = file_path(stored)
    try:
        return await asyncio.to_thread(path.open, "rb")
    except FileNotFoundError:
        _LOG.error("core_storage: row %s exists, its bytes at %s do not", stored.code, path)
        raise FileNotFound(stored.code) from None


async def file_delete(code: str) -> None:
    """The file manager's deletion: one mark for the file and every live owner of it.

    A deliberate act — the owners are not asked. The cleanup task removes the file after the term.
    """
    code = normalize_code(code)
    async with write_scope() as s:
        row = await file_crud.file_lock(code, session=s)
        if row is None or row.deleted_at is not None:
            raise FileNotFound(code)
        now = utc_now()
        await file_crud.file_mark_deleted(code, now, session=s)
        await owner_crud.owner_mark_all_of_file(code, now, session=s)


__all__ = [
    "file_delete",
    "file_find_content",
    "file_get",
    "file_get_many",
    "file_open",
    "file_path",
]
