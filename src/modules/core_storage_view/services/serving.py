"""Which stored file goes out under a code, from where, and under which name.

Every miss — a store that is not served, a code nobody registered or a malformed one, a
soft-deleted file, a row whose bytes are gone — is the storage's ``FileNotFound``. The route turns
it into one answer, so the answer never tells which codes exist.

The name is the address's (``/download/<name>``): whoever hands the link out knows what the file is
called where it is shown, and the route reads no holder; a name without an extension takes the
file's. Without a name — or with one the storage could not keep as a name (a control character,
too long) — the neutral ``<CODE><extension>``.
The name only says what to save the bytes as: they and their type are the stored ones.
"""

from __future__ import annotations

import asyncio
import os
import stat

from src.core.loggers import get_logger
from src.modules.core_storage.dto import StoredFile
from src.modules.core_storage.errors import FileNotFound
from src.modules.core_storage.names import split_filename
from src.modules.core_storage.services.files import file_get, file_path
from src.modules.core_storage_view.constants import LOG_CHANNEL, SERVED_STORES
from src.modules.core_storage_view.dto import ServedFile

_LOG = get_logger(LOG_CHANNEL)


async def served_file(store: str, code: str, *, name: str | None = None) -> ServedFile:
    """``name`` — what the address asks to save the file as."""
    if store not in SERVED_STORES:
        raise FileNotFound(code)
    stored = await file_get(code)
    if stored.store != store:
        raise FileNotFound(stored.code)
    path = file_path(stored)
    try:
        found = await asyncio.to_thread(os.stat, path)
    except FileNotFoundError:
        found = None
    if found is None or not stat.S_ISREG(found.st_mode):
        _LOG.error("core_storage_view: row %s exists, its bytes at %s do not", stored.code, path)
        raise FileNotFound(stored.code)
    return ServedFile(
        code=stored.code,
        path=path,
        stat_result=found,
        mime=stored.mime,
        sha256=stored.sha256,
        extension=stored.extension,
        filename=download_name(stored, name),
    )


def download_name(stored: StoredFile, name: str | None = None) -> str:
    """``name`` as the address gives it, with the file's extension when it has none; else
    ``<CODE><extension>``.

    A name with no extension is usually the title a holder gave the file («Чек-лист проверки»): the
    address's sender knows the title, not the extension. Saved as it is, the file would open with
    nothing, so it takes the stored extension. A name with an extension of its own is kept as given.
    """
    neutral = f"{stored.code}{stored.extension}"
    if not name or not name.strip():
        return neutral
    try:
        split = split_filename(name)
    except ValueError:
        return neutral
    if not split.extension and stored.extension:
        return f"{name}{stored.extension}"
    return name


__all__ = ["download_name", "served_file"]
