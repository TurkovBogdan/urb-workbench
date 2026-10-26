"""The physical removal of files marked deleted longer than the configured term.

Each file goes in a transaction of its own that takes the file's row first (``file_lock``), and
the owners are checked again inside it: a file that some owner took back while it waited keeps
living, and its mark is taken off. Every writer of owners takes the same row first, so no owner
arrives between the check and the deletion; a registration of the same bytes that waited for the
row finds it gone and stores them as a new file. The bytes are removed after the commit — the row
is gone by then, and nothing points at the file on disk — together with the code folders they
leave empty.

The same run removes temporary files a dead process left behind (``purge_temporaries``): the
module's own (``StorageLayout.stale_temporaries``) and those of a consumer that spools into a
folder of its own and named it here (``register_temporaries``) — the module cannot know them
otherwise, and a consumer with no scheduled task of its own would leave them forever.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from src.core.database import write_scope
from src.core.loggers import get_logger
from src.core.utils.date import utc_now
from src.modules.core_storage.constants import LOG_CHANNEL, TEMP_SUFFIX
from src.modules.core_storage.crud import file as file_crud
from src.modules.core_storage.crud import file_owner as owner_crud
from src.modules.core_storage.layout import get_layout, written_before

_LOG = get_logger(LOG_CHANNEL)

# ``(folder, prefix)`` of the consumers' temporary files: ``<folder>/<prefix>*.part``.
_temporaries: set[tuple[Path, str]] = set()


def register_temporaries(folder: Path, prefix: str) -> None:
    """Have the cleanup remove ``<folder>/<prefix>*.part`` once untouched for the stale term — for
    a consumer that spools into a temporary file of its own. A prefix names that consumer's
    files only: anything else in the folder is left alone."""
    if not prefix:
        raise ValueError("A temporary file prefix is needed — without one every .part file matches")
    _temporaries.add((Path(folder), prefix))


async def purge_temporaries(older_than: timedelta) -> int:
    """Remove the temporary files last written longer than ``older_than`` ago; how many went."""
    before = time.time() - older_than.total_seconds()

    def sweep() -> int:
        stale = get_layout().stale_temporaries(before)
        for folder, prefix in sorted(_temporaries):
            if folder.is_dir():
                stale.extend(
                    path
                    for path in folder.glob(f"{prefix}*{TEMP_SUFFIX}")
                    if written_before(path, before)
                )
        removed = 0
        for path in stale:
            try:
                path.unlink()
            except FileNotFoundError:
                continue
            except OSError:
                _LOG.exception("core_storage: temporary file %s stays", path)
                continue
            removed += 1
        return removed

    return await asyncio.to_thread(sweep)


@dataclass(frozen=True)
class PurgeReport:
    purged: int
    kept: int
    bytes_failed: int


async def purge_expired(older_than: timedelta, limit: int) -> PurgeReport:
    """Remove files marked longer than ``older_than`` ago; ``limit`` files at most, ``0`` — all."""
    layout = get_layout()
    purged = kept = bytes_failed = 0
    for candidate in await file_crud.file_expired(utc_now() - older_than, limit):
        async with write_scope() as s:
            row = await file_crud.file_lock(candidate.code, session=s)
            if row is None or row.deleted_at is None:
                kept += 1
                continue
            if await owner_crud.owner_has_live(row.code, session=s):
                await file_crud.file_unmark(row.code, session=s)
                kept += 1
                continue
            path = layout.file_path(row.store, row.code, row.extension)
            await owner_crud.owner_delete_released(row.code, session=s)
            await file_crud.file_delete_row(row.code, session=s)
        purged += 1
        try:
            await asyncio.to_thread(path.unlink, missing_ok=True)
        except OSError:
            _LOG.exception("core_storage: bytes of purged file %s stay at %s", candidate.code, path)
            bytes_failed += 1
            continue
        await asyncio.to_thread(layout.prune, path)
    return PurgeReport(purged=purged, kept=kept, bytes_failed=bytes_failed)


__all__ = ["PurgeReport", "purge_expired", "purge_temporaries", "register_temporaries"]
