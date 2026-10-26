"""Taking a file into storage: from bytes, from a stream, from a path — one order for all three.

Every entry first checks the store and the name, then turns its input into a ``SpooledFile`` —
a file on disk the module now owns, with its sha256, size and first bytes counted — and hands it
to ``_register``. The bytes are read once on the way: a stream spooled ahead
(``file_spool``) comes counted already and is taken by ``file_register_spooled`` as it is. A refusal before that point (unknown store, a name too long, over the
ceiling) leaves the caller's file where it was in every mode.

``filename`` does two jobs. It is the hint ``detect`` falls back on when the bytes carry no
signature, and it is the owner's original name, written to a new owner row and to a revived one
in every outcome — a new file, the same bytes already stored, a parallel registration that won
the content. A place that holds the file already keeps its name: its consumer refuses the second
registration, and the refusal must find the place unchanged. An empty ``filename`` brings no
name: a new row gets ``''``, an existing row keeps the one it has.

``_register`` puts the row in before the bytes. The code is random, and only the primary key
decides whether it is free: had the bytes been moved first, a taken code would be found out after
``replace`` had already overwritten someone else's file. The row first makes the place under the
code ours; a failed move takes the row back out.

The same content brought again heals a file whose bytes were lost: the dedup finds the row, and
when its bytes are missing or of another size, the ones brought now take their place.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
from collections.abc import AsyncIterable, AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import BinaryIO

from sqlalchemy.exc import IntegrityError

from src.core.database import write_scope
from src.core.loggers import get_logger
from src.modules.core_storage.codes import new_code
from src.modules.core_storage.constants import (
    CHUNK_SIZE,
    CODE_ATTEMPTS,
    FILE_MODE,
    HEAD_SIZE,
    LOG_CHANNEL,
)
from src.modules.core_storage.crud import file as file_crud
from src.modules.core_storage.crud import file_owner as owner_crud
from src.modules.core_storage.dto import Owner, SpooledFile, StoredFile, stored_file
from src.modules.core_storage.models import CoreStorageFile
from src.modules.core_storage.errors import (
    CodeCollision,
    FileTooLarge,
    SourceInsideStorage,
    SourceNotFound,
)
from src.modules.core_storage.layout import get_layout
from src.modules.core_storage.mime import detect
from src.modules.core_storage.names import OriginalName, split_filename
from src.modules.core_storage.settings import max_file_size

_LOG = get_logger(LOG_CHANNEL)


async def file_register_bytes(
    data: bytes, *, store: str, owner: Owner, filename: str = ""
) -> StoredFile:
    get_layout().require_store(store)
    name = _brought(filename)
    prepared = await _spool(_chunks_of(data))
    return await _register(prepared, store=store, owner=owner, filename=filename, name=name)


async def file_register_stream(
    chunks: AsyncIterable[bytes], *, store: str, owner: Owner, filename: str = ""
) -> StoredFile:
    get_layout().require_store(store)
    name = _brought(filename)
    prepared = await _spool(chunks)
    return await _register(prepared, store=store, owner=owner, filename=filename, name=name)


async def file_register_path(
    path: Path,
    *,
    store: str,
    owner: Owner,
    filename: str | None = None,
    move: bool = False,
) -> StoredFile:
    """Register the file at ``path``.

    ``move=False`` only reads the file. ``move=True`` hands it to the module: a new file is moved
    into place without a copy, and a file whose content is already stored is deleted. A download
    is registered this way — whoever fetched it put it into ``AppPath.tmp``.

    The owner's name of the file is the source's own name unless ``filename`` gives another —
    a download lands in ``tmp`` under a name of the fetcher's making.
    """
    layout = get_layout()
    layout.require_store(store)
    source = Path(path)
    if not source.is_file():
        raise SourceNotFound(source)
    # Handing over a file the storage already holds would end in deleting the stored bytes.
    if move and source.resolve().is_relative_to(layout.root.resolve()):
        raise SourceInsideStorage(source)
    given = source.name if filename is None else filename
    name = _brought(given)
    prepared = await _inspect(source) if move else await _spool(_chunks_of_file(source))
    return await _register(prepared, store=store, owner=owner, filename=given, name=name)


@asynccontextmanager
async def file_spool(chunks: AsyncIterable[bytes]) -> AsyncIterator[SpooledFile]:
    """Write a stream to a temporary file of the module, under the size ceiling, and yield it
    counted — its path, sha256, size and first bytes.

    For a consumer that must not hold anything while the bytes arrive — an upload over the network
    is as slow as the client — and registers afterwards with ``file_register_spooled``, which does
    not read the bytes again. Over the ceiling is ``FileTooLarge`` with nothing left behind; on
    leaving the block the file is removed whatever happened, unless a registration moved it away.
    """
    spooled = await _spool(chunks)
    try:
        yield spooled
    finally:
        spooled.path.unlink(missing_ok=True)


async def file_register_spooled(
    spooled: SpooledFile, *, store: str, owner: Owner, filename: str = ""
) -> StoredFile:
    """Register a file ``file_spool`` wrote, by the counts it made: the file is handed over — moved
    into place, or deleted when the content is already stored — and its bytes are not read again."""
    layout = get_layout()
    layout.require_store(store)
    # The counts are taken on trust, so only a file the module spooled itself is taken by them.
    if spooled.path.parent.resolve() != layout.tmp.resolve() or not spooled.path.is_file():
        raise SourceNotFound(spooled.path)
    name = _brought(filename)
    return await _register(spooled, store=store, owner=owner, filename=filename, name=name)


def _brought(filename: str) -> OriginalName | None:
    """The name the owner brings, checked before anything is written; ``None`` — it brings none.

    Every entry calls this ahead of the spool, so a refused name leaves the caller's file where
    it was in every mode, ``move`` included.
    """
    name = split_filename(filename)
    return name if name.filename or name.extension else None


async def _chunks_of(data: bytes) -> AsyncIterator[bytes]:
    for start in range(0, len(data), CHUNK_SIZE):
        yield data[start : start + CHUNK_SIZE]


async def _chunks_of_file(path: Path) -> AsyncIterator[bytes]:
    handle = await asyncio.to_thread(path.open, "rb")
    try:
        while chunk := await asyncio.to_thread(handle.read, CHUNK_SIZE):
            yield chunk
    finally:
        await asyncio.to_thread(handle.close)


async def _spool(chunks: AsyncIterable[bytes]) -> SpooledFile:
    """Write the stream to a temporary file, counting sha256, size and the first bytes."""
    temp = get_layout().temp_file()
    limit = max_file_size()
    digest = hashlib.sha256()
    head = bytearray()
    size = 0
    handle: BinaryIO = await asyncio.to_thread(temp.open, "wb")
    try:
        async for chunk in chunks:
            size += len(chunk)
            if size > limit:
                raise FileTooLarge(limit, size)
            digest.update(chunk)
            if len(head) < HEAD_SIZE:
                head.extend(chunk[: HEAD_SIZE - len(head)])
            await asyncio.to_thread(handle.write, chunk)
    except BaseException:
        # No await here: a cancelled upload cancels every await of its scope, and the file would
        # stay in ``tmp`` until the cleanup.
        handle.close()
        temp.unlink(missing_ok=True)
        raise
    await asyncio.to_thread(handle.close)
    return SpooledFile(path=temp, sha256=digest.hexdigest(), size=size, head=bytes(head))


async def _inspect(path: Path) -> SpooledFile:
    """Count sha256, size and the first bytes of a file in place, without a copy."""
    limit = max_file_size()
    size = path.stat().st_size
    if size > limit:
        raise FileTooLarge(limit, size)

    def measure() -> tuple[str, bytes]:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            head = handle.read(HEAD_SIZE)
            digest.update(head)
            while chunk := handle.read(CHUNK_SIZE):
                digest.update(chunk)
        return digest.hexdigest(), head

    sha256, head = await asyncio.to_thread(measure)
    return SpooledFile(path=path, sha256=sha256, size=size, head=head)


async def _register(
    prepared: SpooledFile, *, store: str, owner: Owner, filename: str, name: OriginalName | None
) -> StoredFile:
    """``filename`` is the type hint for ``detect``; ``name`` is what the owner's row keeps."""
    try:
        existing = await _take_existing(prepared, store, owner, name)
        if existing is not None:
            return existing
        return await _store_new(prepared, store=store, owner=owner, filename=filename, name=name)
    finally:
        # After a move the file is no longer at this path; in every other outcome it is a spare copy.
        prepared.path.unlink(missing_ok=True)


async def _take_existing(
    prepared: SpooledFile, store: str, owner: Owner, name: OriginalName | None
) -> StoredFile | None:
    """Dedup: the same bytes are already stored — add the owner under its own name (a live one
    keeps the name it has) and revive a marked file.

    The row is taken under its lock. A cleanup removing it meanwhile commits first, and the row is
    then not found: the bytes are registered as a new file, never as an owner of a removed row.
    A row whose bytes are gone gets the ones brought now (``_bring_back_bytes``).
    """
    async with write_scope() as s:
        existing = await file_crud.file_find_by_sha256(store, prepared.sha256, session=s, lock=True)
        if existing is None:
            return None
        await _bring_back_bytes(prepared, existing)
        await owner_crud.owner_take(existing.code, owner, name=name, session=s)
        await file_crud.file_unmark(existing.code, session=s)
        return stored_file(await file_crud.file_get(existing.code, session=s))


async def _bring_back_bytes(prepared: SpooledFile, row: CoreStorageFile) -> None:
    """The row is there and its bytes are not, or not whole — a crash, a base restored without
    its files. What is brought now has the row's sha256, so it is that content, and it goes where
    the row says. Under the row's lock: no cleanup removes the row meanwhile. A registration of the
    same content between its commit and its move puts the same bytes there too; either ``replace``
    leaves the same file."""
    layout = get_layout()
    target = layout.file_path(row.store, row.code, row.extension)
    try:
        if (await asyncio.to_thread(target.stat)).st_size == row.size:
            return
    except FileNotFoundError:
        pass
    await asyncio.to_thread(layout.place, prepared.path, target)
    await asyncio.to_thread(os.chmod, target, FILE_MODE)
    _LOG.warning("core_storage: the bytes of %s were gone and are back from a new upload", row.code)


async def _store_new(
    prepared: SpooledFile, *, store: str, owner: Owner, filename: str, name: OriginalName | None
) -> StoredFile:
    detected = detect(prepared.head, filename)
    layout = get_layout()
    for _ in range(CODE_ATTEMPTS):
        code = new_code()
        try:
            async with write_scope() as s:
                row = await file_crud.file_insert(
                    code=code,
                    store=store,
                    sha256=prepared.sha256,
                    type=detected.type,
                    size=prepared.size,
                    mime=detected.mime,
                    extension=detected.extension,
                    session=s,
                )
                if row is None:
                    # A parallel registration of the same content won the key: join it.
                    winner = await file_crud.file_find_by_sha256(
                        store, prepared.sha256, session=s, lock=True
                    )
                    if winner is None:
                        # The cleanup removed the winner in between: the key is free again.
                        continue
                    await owner_crud.owner_take(winner.code, owner, name=name, session=s)
                    await file_crud.file_unmark(winner.code, session=s)
                    return stored_file(await file_crud.file_get(winner.code, session=s))
                await owner_crud.owner_take(code, owner, name=name, session=s)
                result = stored_file(row)
        except IntegrityError:
            # Which key refused, the drivers tell only in text, and the text differs between
            # SQLite and PostgreSQL — so the code is asked about outside the rolled-back
            # transaction. A free code means the refusal was something else, and it goes out as is.
            if await file_crud.file_get(code, include_deleted=True) is None:
                raise
            continue

        target = layout.file_path(store, code, detected.extension)
        try:
            await asyncio.to_thread(layout.place, prepared.path, target)
            await asyncio.to_thread(os.chmod, target, FILE_MODE)
        except BaseException:
            _LOG.error("core_storage: bytes of %s did not reach %s — the row is taken back", code, target)
            async with write_scope() as s:
                await owner_crud.owner_delete_all(code, session=s)
                await file_crud.file_delete_row(code, session=s)
            raise
        return result

    raise CodeCollision(f"no free file code found in {CODE_ATTEMPTS} tries")


__all__ = [
    "file_register_bytes",
    "file_register_path",
    "file_register_spooled",
    "file_register_stream",
    "file_spool",
]
