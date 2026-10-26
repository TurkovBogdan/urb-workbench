"""Hourly reconciliation of the base with the disk (``services/reconcile.py``).

Hourly rather than daily: the backend runs only while it is in use, and a nightly run would not
happen on a machine that is off at night. Minute 20 keeps it apart from the cleanup at the top of
the hour and from the consumers' owner reconciliations at the half hour. No sha256 here — reading
every byte each hour is the cost of a hand run (`app.py storage check --sha`).
"""

from __future__ import annotations

from src.core.scheduler import CoreTaskBase, TaskContext
from src.modules.core_storage.constants import REPORT_NAMED
from src.modules.core_storage.services.reconcile import reconcile_storage


class ReconcileTask(CoreTaskBase):
    MODULE = "core_storage"
    CODE = "reconcile"
    NAME = "File reconciliation"
    # English fallback text: the UI shows the dictionary translation keyed by (MODULE, CODE).
    DESCRIPTION = (
        "Hourly: compares the stored files with the disk — reports files whose bytes are missing "
        "or of another size, and removes bytes no file points at once they are an hour old, "
        "unless there are too many of them to be a crash's leftovers."
    )
    SCHEDULE = "20 * * * *"
    TTL = 600

    @staticmethod
    async def handle(ctx: TaskContext) -> None:
        report = await reconcile_storage(fix=True, guarded=True)
        await ctx.info(
            "rows checked %d, live without bytes %d, marked without bytes %d, other size %d, "
            "bytes without a row %d (removed %d, younger than the term %d), unknown names %d",
            report.rows,
            len(report.missing),
            report.missing_marked,
            len(report.mismatched),
            len(report.orphans),
            report.removed,
            report.young,
            len(report.strangers),
        )
        for code in report.missing[:REPORT_NAMED]:
            await ctx.error("file %s is held and its bytes are gone", code)
        for code in report.mismatched[:REPORT_NAMED]:
            await ctx.error("file %s: the bytes on disk are of another size", code)
        for path in report.strangers[:REPORT_NAMED]:
            await ctx.warn("not a stored file's name, left alone: %s", path)
        if report.refused:
            await ctx.warn("%s", report.refused)


__all__ = ["ReconcileTask"]
