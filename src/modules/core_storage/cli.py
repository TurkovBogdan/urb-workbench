"""`app.py storage check [--fix] [--sha]`: the reconciliation of the base with the disk, by hand.

The same service the hourly task runs (``services/reconcile.py``), with two differences that
make it the operator's tool: by default it only reports, and with ``--fix`` it removes the bytes
without a row whatever their number — the person has looked at the root, the scheduled run has
not. ``--sha`` reads every stored byte and compares its hash with the row's.

Safe beside a running install: every removal takes the file's row first, the queue every writer
of a file stands in, and nothing younger than the grace period is touched. Also the check of a
copy before trusting it — point ``DB_PATH`` and ``STORAGE_PATH`` at the copy, without ``--fix``.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

from src.core.config import Config
from src.core.database import close_database, init_database
from src.core.module import Module
from src.modules.core_storage.constants import REPORT_NAMED
from src.modules.core_storage.layout import set_layout
from src.modules.core_storage.module import CoreStorageModule, layout_of
from src.modules.core_storage.services.reconcile import ReconcileReport, reconcile_storage

EXIT_CLEAN = 0
EXIT_FOUND = 1
EXIT_UNAVAILABLE = 2


async def storage_check_command(
    modules: Sequence[Module], config: Config, *, fix: bool, hash_bytes: bool
) -> int:
    storage = next((module for module in modules if isinstance(module, CoreStorageModule)), None)
    if storage is None:
        print("error: core_storage is not one of this application's modules", file=sys.stderr)
        return EXIT_UNAVAILABLE
    set_layout(layout_of(config, storage.stores))
    try:
        await init_database(config)
        report = await reconcile_storage(fix=fix, hash_bytes=hash_bytes)
    except (SQLAlchemyError, OSError) as failure:
        print(f"error: the check could not run: {failure}", file=sys.stderr)
        return EXIT_UNAVAILABLE
    finally:
        await close_database()
    print(describe(report, root=config.storage_root, fix=fix))
    return EXIT_CLEAN if report.clean else EXIT_FOUND


def describe(report: ReconcileReport, *, root: Path, fix: bool) -> str:
    left = len(report.orphans) - report.removed
    if report.removed:
        orphans = f"{len(report.orphans)}, removed {report.removed}"
    elif report.orphans and not fix:
        orphans = f"{len(report.orphans)} — run with --fix to remove them"
    else:
        orphans = str(len(report.orphans))
    hashed = "yes" if report.hashed else "no — size only (--sha reads every byte)"
    lines = [
        f"storage root:            {root}",
        f"rows checked:            {report.rows} (younger than an hour are left for the next run)",
        f"sha256 compared:         {hashed}",
        f"held, bytes missing:     {len(report.missing)}",
        *_named(report.missing),
        f"marked, bytes missing:   {report.missing_marked} (the cleanup removes them)",
        f"bytes not as recorded:   {len(report.mismatched)}",
        *_named(report.mismatched),
        f"bytes without a row:     {orphans}",
        *_named([str(path) for path in report.orphans] if left else []),
        f"younger than an hour:    {report.young} (left alone)",
        f"unknown names:           {len(report.strangers)} (left alone)",
        *_named([str(path) for path in report.strangers]),
    ]
    if report.refused:
        lines.append(f"not removed: {report.refused}")
    lines.append("consistent" if report.clean else "discrepancies remain")
    return "\n".join(lines)


def _named(items: Sequence[str]) -> list[str]:
    shown = [f"  {item}" for item in items[:REPORT_NAMED]]
    hidden = len(items) - REPORT_NAMED
    return shown + ([f"  … and {hidden} more"] if hidden > 0 else [])


__all__ = ["EXIT_CLEAN", "EXIT_FOUND", "EXIT_UNAVAILABLE", "describe", "storage_check_command"]
