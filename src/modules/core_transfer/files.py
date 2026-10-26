"""Files of an archive: what becomes of each here, and taking them into the storage.

One content is one file per store, and its bytes never change — so a file is judged by the pair
«code + sha256»:

| here | outcome |
| --- | --- |
| neither the code nor the content | ``create`` — stored under the archive's code (``preferred_code``) |
| the same content under the same code | ``reuse`` — the bytes are skipped, the holder becomes an owner |
| the same content under another code | ``recode`` — the same, and the texts move to the code here |
| the code, holding other content | ``conflict`` — the archive's bytes can only come in as a new file |

The same sha256 is never a conflict (the person's rule, 2026-10-26): there is nothing to choose
between two copies of the same bytes.

Taking a file opens the storage's own write transaction, so it is never called from inside a
consumer's ``write_scope``: the consumer takes every file first, then writes its rows, and on a
failure there gives the owners back (``release_taken``).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from src.modules.core_storage.dto import Owner, StoredFile
from src.modules.core_storage.errors import FileNotFound
from src.modules.core_storage.services.files import file_find_content, file_get_many
from src.modules.core_storage.services.ownership import file_attach, file_release
from src.modules.core_storage.services.registration import file_register_spooled, file_spool
from src.modules.core_storage.settings import max_file_size
from src.modules.core_transfer.container import ArchiveReader
from src.modules.core_transfer.errors import FILE_TOO_LARGE, TransferError

FILE_CREATE = "create"
FILE_REUSE = "reuse"
FILE_RECODE = "recode"
FILE_CONFLICT = "conflict"


@dataclass(frozen=True)
class ArchivedFile:
    """A file as the archive holds it: its code there, its content, its entry, its name."""

    code: str
    sha256: str
    size: int
    entry: str
    filename: str


@dataclass(frozen=True)
class FileVerdict:
    """What becomes of an archived file here; ``local`` — the file here that decided it."""

    archived: ArchivedFile
    outcome: str
    local: StoredFile | None = None

    @property
    def code_here(self) -> str | None:
        """The code the file will have here; ``None`` — a new one, given when it is stored."""
        if self.outcome in (FILE_REUSE, FILE_RECODE) and self.local is not None:
            return self.local.code
        if self.outcome == FILE_CREATE:
            return self.archived.code
        return None


async def judge_files(files: Iterable[ArchivedFile], *, store: str) -> dict[str, FileVerdict]:
    """``archive code → verdict``; reads only."""
    listed = list(files)
    taken = await file_get_many([item.code for item in listed], include_deleted=True)
    verdicts: dict[str, FileVerdict] = {}
    for item in listed:
        same_content = await file_find_content(store, item.sha256)
        if same_content is not None:
            outcome = FILE_REUSE if same_content.code == item.code else FILE_RECODE
            verdicts[item.code] = FileVerdict(item, outcome, same_content)
        elif item.code in taken:
            verdicts[item.code] = FileVerdict(item, FILE_CONFLICT, taken[item.code])
        else:
            verdicts[item.code] = FileVerdict(item, FILE_CREATE)
    return verdicts


def refuse_over_ceiling(verdicts: Iterable[FileVerdict]) -> None:
    """A file to be stored here over this storage's ceiling refuses the import, by its name.

    Only the ones whose bytes will be stored: a file whose content is here already takes no space,
    and refusing it would refuse what the storage accepted before.
    """
    ceiling = max_file_size()
    for verdict in verdicts:
        if verdict.outcome in (FILE_REUSE, FILE_RECODE) or verdict.archived.size <= ceiling:
            continue
        name = verdict.archived.filename or verdict.archived.code
        raise TransferError(
            FILE_TOO_LARGE,
            f"The file {name} is over this installation's storage ceiling",
            params={"name": name, "limit_mb": ceiling // (1024 * 1024)},
        )


async def take_file(
    reader: ArchiveReader, verdict: FileVerdict, *, owner: Owner, store: str
) -> StoredFile:
    """Give the file to ``owner`` here; the answer's ``code`` is the one it has here.

    A file reused by content gets one more owner; its bytes are not read. Should it be gone since
    the plan (the cleanup removed it), the bytes come from the archive after all.
    """
    item = verdict.archived
    if verdict.outcome in (FILE_REUSE, FILE_RECODE) and verdict.local is not None:
        try:
            await file_attach(verdict.local.code, owner, filename=item.filename)
            return verdict.local
        except FileNotFound:
            pass
    preferred = item.code if verdict.outcome != FILE_CONFLICT else None
    async with file_spool(reader.file_chunks(item.entry)) as spooled:
        return await file_register_spooled(
            spooled, store=store, owner=owner, filename=item.filename, preferred_code=preferred
        )


async def release_taken(taken: Iterable[tuple[str, Owner]]) -> None:
    """Give back the owners an import took before its rows failed; a file left with none goes
    to the storage's cleanup by its term."""
    for code, owner in taken:
        try:
            await file_release(code, owner)
        except FileNotFound:
            continue


__all__ = [
    "ArchivedFile",
    "FILE_CONFLICT",
    "FILE_CREATE",
    "FILE_RECODE",
    "FILE_REUSE",
    "FileVerdict",
    "judge_files",
    "refuse_over_ceiling",
    "release_taken",
    "take_file",
]
