"""Taking a file as it is: the name it came with, the ceiling, the holder that keeps it.

Every way a file arrives — the person's request body, the PUT of an upload request
(``requests.py``), a path on the server's disk (``server_path.py``) — goes the same road: the
refusals known before the bytes (the name, the holder, the declared size) come first and read
nothing; then the bytes are written to the storage's temporary file (``core_storage.file_spool``)
with no lock held, as slow as the client is; then the holder takes the spooled file under its own
lock, its checks repeated there. An upload never holds a holder's other file operations while its
bytes arrive.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterable, Mapping
from typing import Any

from src.core.utils.text import control_character
from src.modules.core_storage.errors import FileTooLarge
from src.modules.core_storage.names import split_filename
from src.modules.core_storage.services.registration import file_spool
from src.modules.core_storage.settings import max_file_size
from src.modules.core_storage_upload.dto import Payload
from src.modules.core_storage_upload.errors import (
    FILENAME_CONTROL_CHARACTER,
    FILENAME_TOO_LONG,
    FilenameRefused,
)
from src.modules.core_storage_upload.services.holders import upload_holder

_PATH_SEPARATORS = re.compile(r"[\\/]")


def kept_name(name: str) -> str:
    """``name`` as is, refused when the storage could not keep it as the file's original name:
    a control character in it, or more characters than its column takes."""
    control = control_character(name)
    try:
        split_filename(name)
    except ValueError as error:
        code = FILENAME_CONTROL_CHARACTER if control else FILENAME_TOO_LONG
        raise FilenameRefused(str(error), code=code) from error
    return name


def sent_name(name: str) -> str:
    """The name a client sent next to the bytes: its last path segment (``../dir\\отчёт.txt`` →
    ``отчёт.txt``), refused as ``kept_name`` refuses — a control character anywhere in what was
    sent included. A segment of dots only (``.``, ``..``) names nothing: in an address it would
    step out of the path instead of naming the file."""
    if control_character(name) is not None:
        kept_name(name)
    segment = _PATH_SEPARATORS.split(name)[-1].strip()
    return kept_name("" if not segment.strip(".") else segment)


def refuse_oversize(size: int | None) -> None:
    """A body whose size is known over the ceiling — announced, or a file's on disk — is refused
    before a byte of it is read."""
    limit = max_file_size()
    if size is not None and size > limit:
        raise FileTooLarge(limit, size)


async def upload_stream(
    holder_code: str,
    chunks: AsyncIterable[bytes],
    *,
    payload: Payload,
    filename: str = "",
    declared_size: int | None = None,
) -> Mapping[str, Any]:
    """The person's upload: the body into the holder, answered with the file as its list shows it.

    ``payload`` — what the page asks the holder for (a title, a description), handed over as is.
    ``declared_size`` — the request's ``Content-Length``. Refused before the body: the name, the
    holder and its checks, the declared size; while the body streams, a body running past the
    ceiling — ``FileTooLarge`` either way, and nothing is left behind. The same bytes the holder
    has already are ``AlreadyHeld``, with the file in ``params``.
    """
    name = sent_name(filename)
    holder, bare = upload_holder(holder_code)
    await holder.check(bare, payload)
    refuse_oversize(declared_size)
    async with file_spool(chunks) as spooled:
        attached = await holder.attach(bare, spooled, payload, filename=name)
    return await holder.answer(bare, attached)


__all__ = ["kept_name", "refuse_oversize", "sent_name", "upload_stream"]
