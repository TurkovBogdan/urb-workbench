"""A codex note as an owner in ``core_storage`` — and releasing it once its files are let go.

A note holds its files as ``("CODEX", <note code>, "")``; one binding row in ``codex_file`` stands
for exactly one live owner row. The release runs after the transaction that removed the rows has
committed: the storage opens a write transaction of its own, and a nested writer on SQLite waits on
the lock until the timeout.

Imports nothing of this module but its constants, so the CRUD's hard deletions can call it.
"""

from __future__ import annotations

from collections.abc import Iterable
from contextlib import AbstractAsyncContextManager

from src.modules.codex.constants import CODEX_CODE_PREFIX
from src.modules.core_storage.dto import Owner
from src.modules.core_storage.errors import FileNotFound
from src.modules.core_storage.services.holder_lock import holder_lock
from src.modules.core_storage.services.ownership import file_release, owner_release_everywhere


def note_owner(note_code: str) -> Owner:
    return Owner(type=CODEX_CODE_PREFIX, id=note_code)


def note_files_lock(note_code: str) -> AbstractAsyncContextManager[None]:
    """One file operation of the note at a time — attach, detach, retitle
    (``core_storage.services.holder_lock``). Not reentrant: take it once, at the top."""
    return holder_lock(CODEX_CODE_PREFIX, note_code)


async def release_note_file(note_code: str, file_code: str) -> bool:
    """Release the note's hold on one file; ``False`` — it held none. A file already gone from the
    storage holds nobody, which is what releasing was for."""
    try:
        return await file_release(file_code, note_owner(note_code))
    except FileNotFound:
        return False


async def release_notes_everywhere(note_codes: Iterable[str]) -> None:
    """Release notes deleted for good from every file they held."""
    for note_code in note_codes:
        await owner_release_everywhere(CODEX_CODE_PREFIX, note_code)


__all__ = ["note_files_lock", "note_owner", "release_note_file", "release_notes_everywhere"]
