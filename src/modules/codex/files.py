"""Files of a codex note — the service the agent's tools and the uploads build on.

The bytes arrive through ``core_storage_upload``, already spooled (``codex_file_attach_spooled``,
called by the holder this module registers there — ``file_holders.py``); a file stored already is
bound by its code.

The same two steps as a task's files (``tasks/files.py``), in two transactions, the storage never
called from inside a ``write_scope`` of ours: every refusal known up front first — a codex code
instead of a note's, a note that is deleted or absent, a note of a deleted codex, an over-long
title, a file the note holds already, a file of another store — then the storage takes the file
for the note, then the binding row is written. A refusal at the row gives the owner back, unless
the note does hold the file.

Each operation runs under the note's lock (``file_owner.note_files_lock``), so nothing else of
the same note removes the row or releases the owner between the steps; the lock serialises
within the backend process — the one process there is. An upload's bytes arrive before the lock is
taken: the lock covers the storage and the row, never the network. The same bytes again behave as
in a task: a note holding the file refuses and nothing changes; a note whose binding stayed while
the file manager deleted the file gets it back, and the answer is the binding as it was.

Whether the agent may write in this codex at all is the mount's (``codex.rules.agent_may_write``)
and is asked by the agent surface before it calls here; the person's interface needs no mount.
Codes are bare on the way in and out.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.modules.codex.codes import tagged
from src.modules.codex.constants import FILE_CODE_PREFIX, FILE_STORE
from src.modules.codex.crud import file as file_crud
from src.modules.codex.errors import FILE_FOREIGN_STORE, FILE_NOT_STORED, CodexRuleError
from src.modules.codex.file_owner import note_files_lock, note_owner, release_note_file
from src.modules.codex.models import CodexFile
from src.modules.core_storage.dto import FileOwner, SpooledFile, StoredFile
from src.modules.core_storage.errors import FileNotFound
from src.modules.core_storage.services.files import file_get, file_get_many
from src.modules.core_storage.services.ownership import file_attach, file_owners_many
from src.modules.core_storage.services.registration import file_register_spooled


@dataclass(frozen=True)
class CodexFileView:
    """A file as the note shows it: the binding, the stored bytes, the name it came under here."""

    binding: CodexFile
    stored: StoredFile
    original_filename: str
    original_extension: str


async def codex_file_attach_spooled(
    note_code: str,
    spooled: SpooledFile,
    *,
    filename: str = "",
    title: str = "",
    description: str = "",
) -> CodexFile:
    """Store a file ``core_storage.file_spool`` wrote and bind it to the note, at the end of its
    files.

    The bytes were written before this call, OUTSIDE the note's lock, as a task's are
    (``tasks.files.task_file_attach_spooled``): the note's other file operations do not wait on a
    slow client. Under the lock the checks run, the file is registered by the counts the spool
    made, and bound.
    """
    async with note_files_lock(note_code):
        await file_crud.codex_file_check(note_code, title=title, description=description)
        hidden = await _hidden_files(note_code)
        stored = await file_register_spooled(
            spooled, store=FILE_STORE, owner=note_owner(note_code), filename=filename
        )
        return await _bind(note_code, stored.code, title, description, hidden=hidden)


async def codex_file_attach_existing(
    note_code: str,
    file_code: str,
    *,
    filename: str | None = None,
    title: str = "",
    description: str = "",
) -> CodexFile:
    """Bind a file the storage already holds; ``filename=None`` takes the name it came under
    elsewhere. A deleted file, like an absent one, is refused; so is a file of a store other
    than the codex's — it would be bound and never served."""
    try:
        stored = await file_get(file_code)
    except FileNotFound as error:
        raise CodexRuleError(
            FILE_NOT_STORED, f"No stored file {tagged(FILE_CODE_PREFIX, file_code)}."
        ) from error
    if stored.store != FILE_STORE:
        raise CodexRuleError(
            FILE_FOREIGN_STORE,
            f"{tagged(FILE_CODE_PREFIX, stored.code)} lies in the {stored.store!r} store — "
            f"a codex note holds files of {FILE_STORE!r} only.",
        )
    async with note_files_lock(note_code):
        await file_crud.codex_file_check(
            note_code, file_code=stored.code, title=title, description=description
        )
        await file_attach(stored.code, note_owner(note_code), filename=filename)
        return await _bind(note_code, stored.code, title, description)


async def codex_file_detach(note_code: str, file_code: str) -> bool:
    """Take the file out of the note; ``True`` — the note held it. The row goes first, then the
    note's storage owner. A deleted note, or a note of a deleted codex, is refused: a soft
    deletion keeps the files for the restore."""
    async with note_files_lock(note_code):
        await file_crud.codex_file_check(note_code)
        if not await file_crud.codex_file_delete(note_code, file_code):
            return False
        await release_note_file(note_code, file_code)
        return True


async def codex_file_retitle(
    note_code: str,
    file_code: str,
    *,
    title: str | None = None,
    description: str | None = None,
) -> CodexFileView | None:
    """Change the binding's title and description (``None`` = leave as is). ``None`` — the note
    does not show the file: no binding, or the file manager deleted the file; nothing is written.
    A deleted note, or a note of a deleted codex, is refused."""
    async with note_files_lock(note_code):
        await file_crud.codex_file_check(note_code, title=title, description=description)
        if await codex_file_view(note_code, file_code) is None:
            return None
        if await file_crud.codex_file_update(
            note_code, file_code, title=title, description=description
        ) is None:
            return None
        return await codex_file_view(note_code, file_code)


async def codex_file_views(note_code: str) -> list[CodexFileView]:
    """The note's files top to bottom, each with its stored data and the name it came under; a
    file the file manager deleted is left out. Three statements whatever the number of files: the
    rows, the stored files, their owners."""
    return await _views(await file_crud.codex_file_list(note_code))


async def codex_file_view(note_code: str, file_code: str) -> CodexFileView | None:
    row = await file_crud.codex_file_get(note_code, file_code)
    if row is None:
        return None
    views = await _views([row])
    return views[0] if views else None


async def _views(rows: list[CodexFile]) -> list[CodexFileView]:
    codes = [row.file_code for row in rows]
    stored = await file_get_many(codes)
    owners = await file_owners_many([code for code in codes if code in stored])
    return [
        _view(row, stored[row.file_code], owners.get(row.file_code, []))
        for row in rows
        if row.file_code in stored
    ]


def _view(row: CodexFile, stored: StoredFile, owners: list[FileOwner]) -> CodexFileView:
    owner = note_owner(row.note_code)
    place = next((p for p in owners if p.owner == owner), None)
    return CodexFileView(
        binding=row,
        stored=stored,
        original_filename=place.original_filename if place else "",
        original_extension=place.original_extension if place else "",
    )


async def _hidden_files(note_code: str) -> frozenset[str]:
    """The note's bound files the file manager deleted — taken before a registration, which may
    bring one of them back."""
    codes = [row.file_code for row in await file_crud.codex_file_list(note_code)]
    live = await file_get_many(codes)
    return frozenset(code for code in codes if code not in live)


async def _bind(
    note_code: str,
    file_code: str,
    title: str,
    description: str,
    *,
    hidden: frozenset[str] = frozenset(),
) -> CodexFile:
    if file_code in hidden:
        revived = await file_crud.codex_file_get(note_code, file_code)
        if revived is not None:
            return revived
    try:
        return await file_crud.codex_file_create(
            note_code=note_code, file_code=file_code, title=title, description=description
        )
    except Exception:
        if await file_crud.codex_file_get(note_code, file_code) is None:
            await release_note_file(note_code, file_code)
        raise


__all__ = [
    "CodexFileView",
    "codex_file_attach_existing",
    "codex_file_attach_spooled",
    "codex_file_detach",
    "codex_file_retitle",
    "codex_file_view",
    "codex_file_views",
]
