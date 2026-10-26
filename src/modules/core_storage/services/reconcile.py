"""The reconciliation of the base with the disk: rows without bytes, bytes without a row, bytes
that are not what the row says.

A crash leaves both kinds. The cleanup removes bytes after committing the row's deletion, so a
death between the two leaves bytes nobody counts; lost or damaged bytes leave a row whose file
cannot be opened. Two passes find them.

- **Rows → disk.** Every row older than the grace period is looked for on disk. A live row
  without bytes is reported and logged as an error, never removed: its owners hold it, they meet
  the loss as ``FileNotFound`` and 404 already, and the same content uploaded again brings the
  bytes back (``registration._take_existing``). A marked row without bytes is only counted — the
  cleanup removes it. Bytes of another size are reported; their sha256 is compared only when
  asked (``hash_bytes``), since that reads every byte.
- **Disk → rows.** What lies at the depth of stored bytes in every store is seen first and looked
  up second. A registration commits its row before it moves the bytes in, so bytes seen with no
  row are not a registration midway. Those older than the grace period are removed with ``fix``,
  each inside a write transaction that takes the row first (``file_lock``) and reads it again —
  the same queue every writer of a file stands in. Younger ones are left alone, and so is a name
  that is no file's bytes at all. Temporary ``.part`` files are not this pass's — the cleanup's
  ``purge_temporaries`` removes them.

``fix`` by itself does not mean the scheduled run deletes: a base on another base's root — a copy
left on the original's storage — sees every file the original registered since as bytes without
a row. So ``guarded`` refuses the removal when the layout says the root is likely shared, or when
the leftovers are too many to be a crash's (``ORPHAN_AUTO_LIMIT_*``); the report then says why.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

from src.core.database import write_scope
from src.core.loggers import get_logger
from src.core.utils.date import utc_now
from src.modules.core_storage.codes import parse_code
from src.modules.core_storage.constants import (
    CHUNK_SIZE,
    CODE_LEN,
    LOG_CHANNEL,
    ORPHAN_AUTO_LIMIT_FILES,
    ORPHAN_AUTO_LIMIT_SHARE,
    RECONCILE_GRACE_SECONDS,
    RECONCILE_PAGE,
)
from src.modules.core_storage.crud import file as file_crud
from src.modules.core_storage.layout import StorageLayout, get_layout, written_before
from src.modules.core_storage.models import CoreStorageFile

_LOG = get_logger(LOG_CHANNEL)

GRACE = timedelta(seconds=RECONCILE_GRACE_SECONDS)


@dataclass
class ReconcileReport:
    rows: int = 0
    """Rows looked for on disk — those past the grace period."""

    missing: list[str] = field(default_factory=list)
    """Codes of live rows whose bytes are not on disk."""

    missing_marked: int = 0
    """Marked rows without bytes — the cleanup takes them."""

    mismatched: list[str] = field(default_factory=list)
    """Codes of rows whose bytes are of another size, or another sha256 when it was compared."""

    orphans: list[Path] = field(default_factory=list)
    """Bytes without a row, past the grace period — removed when ``removed`` counts them."""

    removed: int = 0
    young: int = 0
    """Bytes without a row inside the grace period — left alone."""

    strangers: list[Path] = field(default_factory=list)
    """What lies where bytes lie but is named like no file — left alone."""

    refused: str = ""
    """Why the bytes without a row were not removed although asked to; ``''`` — they were, or
    removal was not asked for."""

    hashed: bool = False

    @property
    def clean(self) -> bool:
        """Nothing left to look at: every row has its bytes and every leftover is gone."""
        left = len(self.orphans) - self.removed
        return not (self.missing or self.mismatched or left or self.strangers)


async def reconcile_storage(
    *,
    fix: bool,
    hash_bytes: bool = False,
    guarded: bool = False,
    grace: timedelta = GRACE,
) -> ReconcileReport:
    """Compare the base with the disk; with ``fix`` remove the bytes without a row past ``grace``.

    ``guarded`` — the scheduled run's caution (module docstring); a person running the check by
    hand has looked at the root and decides themselves.
    """
    layout = get_layout()
    report = ReconcileReport(hashed=hash_bytes)
    settled = utc_now() - grace
    stores = await _stores_on_record(layout)
    total_rows = await _check_rows(layout, report, settled=settled, hash_bytes=hash_bytes)
    await _find_orphans(layout, stores, report, written_by=time.time() - grace.total_seconds())

    if fix and report.orphans:
        report.refused = _refusal(layout, report, total_rows) if guarded else ""
        if not report.refused:
            report.removed = await _remove_orphans(layout, report.orphans)
    _log(report)
    return report


async def _stores_on_record(layout: StorageLayout) -> list[str]:
    """The module's stores and those the base still has files in — a store taken off the list
    keeps its files readable, so its folder is checked too."""
    return sorted(set(layout.stores) | set(await file_crud.file_stores_in_use()))


async def _check_rows(
    layout: StorageLayout, report: ReconcileReport, *, settled, hash_bytes: bool
) -> int:
    """The rows → disk pass; answers how many rows the base holds in all."""
    after, total = "", 0
    while page := await file_crud.file_page(after, RECONCILE_PAGE):
        after = page[-1].code
        total += len(page)
        for row in page:
            if row.created_at > settled:
                continue
            report.rows += 1
            verdict = await asyncio.to_thread(_verdict, layout, row, hash_bytes)
            if verdict == _MISSING and row.deleted_at is None:
                report.missing.append(row.code)
            elif verdict == _MISSING:
                report.missing_marked += 1
            elif verdict == _MISMATCHED:
                report.mismatched.append(row.code)
    return total


_WHOLE, _MISSING, _MISMATCHED = "whole", "missing", "mismatched"


def _verdict(layout: StorageLayout, row: CoreStorageFile, hash_bytes: bool) -> str:
    path = layout.file_path(row.store, row.code, row.extension)
    try:
        size = path.stat().st_size
    except FileNotFoundError:
        return _MISSING
    if size != row.size:
        return _MISMATCHED
    if hash_bytes and _sha256_of(path) != row.sha256:
        return _MISMATCHED
    return _WHOLE


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def stored_name(path: Path) -> tuple[str, str] | None:
    """``(code, extension)`` when ``path`` is where the bytes of such a file would lie, else
    ``None``: the name starts with a code and its folders are the code's first four signs."""
    head = path.name[:CODE_LEN]
    if parse_code(head) != head:
        return None
    if path.parent.name != head[2:4] or path.parent.parent.name != head[0:2]:
        return None
    return head, path.name[CODE_LEN:]


async def _find_orphans(
    layout: StorageLayout, stores: list[str], report: ReconcileReport, *, written_by: float
) -> None:
    """The disk → rows pass: the bytes are seen first, their rows looked up after."""
    for store in stores:
        lying = await asyncio.to_thread(layout.lying_in, store)
        named: dict[str, list[tuple[Path, str]]] = {}
        for path in lying:
            parsed = stored_name(path)
            if parsed is None:
                report.strangers.append(path)
                continue
            code, extension = parsed
            named.setdefault(code, []).append((path, extension))
        for start in range(0, len(named), RECONCILE_PAGE):
            codes = list(named)[start : start + RECONCILE_PAGE]
            found = await file_crud.file_get_many(codes, include_deleted=True)
            rows = {row.code: row for row in found}
            for code in codes:
                row = rows.get(code)
                for path, extension in named[code]:
                    if row is not None and (row.store, row.extension) == (store, extension):
                        continue
                    if written_before(path, written_by):
                        report.orphans.append(path)
                    else:
                        report.young += 1


def _refusal(layout: StorageLayout, report: ReconcileReport, total_rows: int) -> str:
    if layout.root_shared:
        return (
            "the storage root is likely another database's too (a database file outside the "
            "profile's folder, STORAGE_PATH not set) — nothing removed"
        )
    limit = max(ORPHAN_AUTO_LIMIT_FILES, int(total_rows * ORPHAN_AUTO_LIMIT_SHARE))
    if len(report.orphans) > limit:
        return (
            f"{len(report.orphans)} files without a row is more than a crash leaves ({limit}) — "
            "this looks like the storage root of another database; nothing removed. Check "
            "STORAGE_PATH and DB_PATH, then remove them by hand: app.py storage check --fix"
        )
    return ""


async def _remove_orphans(layout: StorageLayout, orphans: list[Path]) -> int:
    removed = 0
    for path in orphans:
        parsed = stored_name(path)
        if parsed is None:  # pragma: no cover — listed by the same rule
            continue
        code, extension = parsed
        store = path.parent.parent.parent.name
        async with write_scope() as s:
            row = await file_crud.file_lock(code, session=s)
            if row is not None and (row.store, row.extension) == (store, extension):
                continue
            try:
                await asyncio.to_thread(path.unlink)
            except FileNotFoundError:
                continue
            except OSError:
                _LOG.exception("core_storage: bytes without a row stay at %s", path)
                continue
        removed += 1
        await asyncio.to_thread(layout.prune, path)
    return removed


def _log(report: ReconcileReport) -> None:
    for code in report.missing:
        _LOG.error("core_storage: live file %s has no bytes on disk", code)
    for code in report.mismatched:
        _LOG.error("core_storage: the bytes of %s are not what its row says", code)
    if report.refused:
        _LOG.warning("core_storage: reconciliation: %s", report.refused)


__all__ = ["GRACE", "ReconcileReport", "reconcile_storage", "stored_name"]
